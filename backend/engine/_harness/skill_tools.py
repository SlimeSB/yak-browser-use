"""Thin wrapper layer — calls skill_loader and converts exceptions to
``{"ok": false, "error": "..."}`` format.
"""

from __future__ import annotations

import json

from utils import skill_loader
from utils.logging import get_logger

logger = get_logger(__name__)


def _require(params: dict, *keys: str) -> str | None:
    for k in keys:
        if k not in params or params[k] is None:
            return f"'{k}' is required"
    return None


def skill_list(**kwargs: object) -> dict:
    try:
        result = skill_loader.skill_list()
        return {"ok": True, "result": json.dumps(result, ensure_ascii=False)}
    except Exception as e:
        logger.exception("skill_list failed")
        return {"ok": False, "error": str(e)}


def skill_view(**kwargs: object) -> dict:
    try:
        name = kwargs.get("name")
        loaded = skill_loader.skill_view(str(name) if name else "")
        if "error" in loaded:
            return {"ok": False, "error": loaded["error"]}
        source = loaded.get("source")
        if source:
            from pathlib import Path
            raw = Path(source).read_text(encoding="utf-8")
            return {"ok": True, "result": raw}
        return {"ok": False, "error": f"Skill '{name}' source not found"}
    except Exception as e:
        logger.exception("skill_view failed")
        return {"ok": False, "error": str(e)}


def skill_create(**kwargs: object) -> dict:
    try:
        params = {k: v for k, v in kwargs.items() if v is not None}
        missing = _require(params, "name", "description", "content")
        if missing:
            return {"ok": False, "error": missing}
        return skill_loader.skill_create(
            str(params["name"]),
            str(params["description"]),
            str(params["content"]),
            params.get("tags"),
        )
    except Exception as e:
        logger.exception("skill_create failed")
        return {"ok": False, "error": str(e)}


def skill_edit(**kwargs: object) -> dict:
    try:
        params = {k: v for k, v in kwargs.items() if v is not None}
        missing = _require(params, "name", "content")
        if missing:
            return {"ok": False, "error": missing}
        raw = bool(params.get("raw", False))
        return skill_loader.skill_edit(
            str(params["name"]),
            str(params["content"]),
            raw,
        )
    except Exception as e:
        logger.exception("skill_edit failed")
        return {"ok": False, "error": str(e)}


def skill_delete(**kwargs: object) -> dict:
    try:
        params = {k: v for k, v in kwargs.items() if v is not None}
        missing = _require(params, "name")
        if missing:
            return {"ok": False, "error": missing}
        absorbed_into = params.get("absorbed_into")
        return skill_loader.skill_delete(
            str(params["name"]),
            str(absorbed_into) if absorbed_into else None,
        )
    except Exception as e:
        logger.exception("skill_delete failed")
        return {"ok": False, "error": str(e)}
