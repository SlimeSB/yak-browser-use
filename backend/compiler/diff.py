"""
diff.py — Step diff engine for comparing and merging browser operations.

Compares agent-executed operations against original browser_ops,
manages a rejected-ops blacklist, generates suggestions for new ops,
and provides merge logic for incorporating extra operations.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

LEARN_DIR = Path("logs") / "learn"


# ── Selector matching ──


def _extract_identifier(op: dict) -> str:
    """Extract the best identifier from an op regardless of field name.

    Prefers ``selector`` over ``value``; both fields represent the same
    semantic concept (a CSS selector, URL, label text, etc.) and may be
    used interchangeably between agent and original ops.
    """
    return op.get("selector") or op.get("value") or ""


def _selector_matches(agent_sel: str, orig_sel: str) -> bool:
    """Check if agent_sel contains or equals orig_sel (substring match)."""
    if not orig_sel:
        return False
    return orig_sel in agent_sel or agent_sel == orig_sel


def _selector_lists_match(agent_selectors: list[str], orig_selectors: list[str]) -> bool:
    """Check if any agent selector matches any original selector."""
    if not orig_selectors or not agent_selectors:
        return False
    for orig in orig_selectors:
        for agent in agent_selectors:
            if _selector_matches(agent, orig):
                return True
    return False


# ── Core diff logic ──


def diff_ops(agent_ops: list[dict], original_ops: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compare agent-executed ops against the original browser_ops.

    Matching rule: same type AND selector containment (agent's selector
    is a substring of — or equal to — the original selector).
    Everything in agent_ops that doesn't match goes into extra_ops.

    Args:
        agent_ops: Ops actually executed by the agent (from execution trace).
        original_ops: Ops from the original pipeline.yaml step definition.

    Returns:
        (matched_ops, extra_ops). Each op includes an '_index' field
        tracking its position in the agent execution sequence.
    """
    matched_ops: list[dict] = []
    extra_ops: list[dict] = []
    used = [False] * len(original_ops)

    for idx, agent_op in enumerate(agent_ops):
        agent_op["_index"] = idx
        agent_type = agent_op.get("type", "")
        agent_id = _extract_identifier(agent_op)
        agent_selectors = agent_op.get("selectors", [])
        if not agent_selectors and agent_id:
            agent_selectors = [agent_id]

        matched = False
        for j, orig_op in enumerate(original_ops):
            if used[j]:
                continue
            if orig_op.get("type", "") != agent_type:
                continue

            orig_id = _extract_identifier(orig_op)

            if agent_id and orig_id:
                if _selector_matches(agent_id, orig_id):
                    matched = True
            elif agent_selectors and orig_id:
                if _selector_lists_match(agent_selectors, [orig_id]):
                    matched = True
            elif agent_id and not orig_id and agent_id == str(orig_op.get("value", "")):
                matched = True
            elif not orig_id and not agent_id and agent_type == orig_op.get("type"):
                matched = True

            if matched:
                used[j] = True
                matched_ops.append(agent_op)
                break

        if not matched:
            extra_ops.append(agent_op)

    return matched_ops, extra_ops


# ── Rejected ops management ──


def filter_rejected(pipeline_name: str, ops: list[dict]) -> list[dict]:
    """Remove ops that appear in the rejected.json blacklist.

    Matching is by (selector, type) pair.

    Args:
        pipeline_name: Pipeline name for locating the rejected.json.
        ops: List of ops to filter.

    Returns:
        Filtered list of ops.
    """
    rejected_path = LEARN_DIR / pipeline_name / "rejected.json"
    if not rejected_path.exists():
        return ops

    try:
        data = json.loads(rejected_path.read_text(encoding="utf-8"))
        blocked = data.get("blocked", [])
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read rejected.json for '%s'", pipeline_name)
        return ops

    blocked_keys: set[tuple[str, str, str]] = set()
    for item in blocked:
        selector = item.get("selector", "")
        op_type = item.get("type", "")
        if selector:
            blocked_keys.add((selector, op_type, ""))
        else:
            op_hash = item.get("op_hash", "")
            blocked_keys.add((op_type, "", op_hash))

    filtered: list[dict] = []
    for op in ops:
        sel = op.get("value") or op.get("selector") or ""
        op_type = op.get("type", "")
        if sel:
            op_key = (sel, op_type, "")
        else:
            op_hash = hashlib.md5(
                json.dumps(op, sort_keys=True).encode()
            ).hexdigest()[:12]
            op_key = (op_type, "", op_hash)
        if op_key not in blocked_keys:
            filtered.append(op)
        else:
            logger.debug("Filtered rejected op: type=%s selector=%s", op_type, sel)

    return filtered


def add_to_rejected(pipeline_name: str, ops: list[dict], rejected_by: str) -> None:
    """Add rejected ops to the per-pipeline rejected.json blacklist.

    Each op must have a 'type' and a selector-like identifier.
    Entries include a 'reason' field for auditability.

    Args:
        pipeline_name: Pipeline name for the blacklist file.
        ops: List of op dicts to blacklist.
        rejected_by: Identifier of who/what rejected these ops.
    """
    rdir = LEARN_DIR / pipeline_name
    rdir.mkdir(parents=True, exist_ok=True)
    rejected_path = rdir / "rejected.json"

    existing: dict = {"pipeline": pipeline_name, "blocked": []}
    if rejected_path.exists():
        try:
            existing = json.loads(rejected_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    existing.setdefault("pipeline", pipeline_name)

    now = datetime.now(timezone.utc).isoformat()
    for op in ops:
        selector = op.get("value", op.get("selector", ""))
        op_type = op.get("type", "")
        reason = op.get("reason", "rejected")
        if not reason or not isinstance(reason, str) or not reason.strip():
            reason = "rejected"

        entry: dict = {
            "selector": selector,
            "type": op_type,
            "rejected_by": rejected_by,
            "reason": reason,
            "rejected_at": now,
        }
        if not selector:
            entry["op_hash"] = hashlib.md5(
                json.dumps(op, sort_keys=True).encode()
            ).hexdigest()[:12]
        existing["blocked"].append(entry)

    rejected_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Added %d ops to rejected.json for '%s'", len(ops), pipeline_name)


# ── Suggestions ──


def save_suggestions(
    ops: list[dict],
    pipeline_name: str,
    status: str,
    reason: str,
    interrupt_reason: str | None = None,
) -> str:
    """Save ops to suggestions.json with the given status.

    Args:
        ops: List of extra ops found during execution.
        pipeline_name: Pipeline name for the suggestions file.
        status: Status label (e.g. 'pending', 'accepted', 'rejected').
        reason: Human-readable explanation.
        interrupt_reason: Optional reason if execution was interrupted.

    Returns:
        The suggestion id (hex string).
    """
    rdir = LEARN_DIR / pipeline_name
    rdir.mkdir(parents=True, exist_ok=True)
    sug_path = rdir / "suggestions.json"

    existing: list[dict] = []
    if sug_path.exists():
        try:
            existing = json.loads(sug_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    now = datetime.now(timezone.utc).isoformat()
    sid = uuid.uuid4().hex[:8]

    entry: dict = {
        "id": sid,
        "pipeline": pipeline_name,
        "status": status,
        "reason": reason,
        "extra_ops": ops,
        "created_at": now,
    }
    if interrupt_reason:
        entry["interrupt_reason"] = interrupt_reason

    # Dedup: skip if identical entry already exists
    for existing_entry in existing:
        if (existing_entry.get("status") == status
                and existing_entry.get("extra_ops") == ops
                and existing_entry.get("reason") == reason):
            logger.debug("Skipping duplicate suggestion for '%s'", pipeline_name)
            return existing_entry["id"]

    existing.append(entry)
    sug_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Saved suggestion %s (status=%s) for '%s'", sid, status, pipeline_name)
    return sid


# ── Merge logic ──


def merge_extra_ops(matched: list[dict], extra: list[dict]) -> list[dict]:
    """Insert extra_ops into matched_ops preserving the agent execution order.

    Uses the '_index' field (added by diff_ops) to interleave extras at the
    correct positions relative to matched ops.

    Args:
        matched: Ops that matched the original definition.
        extra: New ops discovered during execution.

    Returns:
        Combined list of ops sorted by execution order.
    """
    all_ops = matched + extra
    all_ops.sort(key=lambda op: op.get("_index", 0))
    return all_ops


def extract_summary(ops: list[dict]) -> str:
    """Generate a human-readable summary string from a list of ops.

    Args:
        ops: List of op dicts.

    Returns:
        Short string like "goto(url1), click(button), fill(input)".
    """
    if not ops:
        return "(empty)"

    parts: list[str] = []
    for op in ops:
        op_type = op.get("type", "?")
        value = op.get("value", op.get("selector", ""))
        if value:
            parts.append(f"{op_type}({value[:40]})")
        else:
            parts.append(op_type)
    return ", ".join(parts)
