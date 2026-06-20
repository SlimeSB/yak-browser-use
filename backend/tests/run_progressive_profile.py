"""
Profile progressive mode on real e-commerce HTML.
Steps:
  1. Launch headless Chromium, load the fixture HTML
  2. CDP DOM.getDocument({depth:-1, pierce:true})
  3. CollectState.walk() → collect all interactive elements
  4. build_llm_view() → density detection → folded + view
  5. Print stats: containers, dense vs non-dense, folded summaries, final view size
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Import progressive mode code
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cdp.playwright_bridge import (
    CollectState,
    build_llm_view,
    DENSITY_THRESHOLD,
    SHALLOW_QUOTA,
    BODY_QUOTA,
    PAGE_LEVEL_DEPTH,
    MAX_LLM_ELEMENTS,
    CONTAINER_DEPTH_RANGE,
)


async def profile(html_path: str) -> None:
    name = Path(html_path).stem
    print(f"\n{'='*70}")
    print(f"  Progressive Profile: {name}")
    print(f"{'='*70}")
    print(f"  DENSITY_THRESHOLD={DENSITY_THRESHOLD}, SHALLOW_QUOTA={SHALLOW_QUOTA}, BODY_QUOTA={BODY_QUOTA}, MAX_LLM_ELEMENTS={MAX_LLM_ELEMENTS}")
    print(f"  CONTAINER_DEPTH_RANGE={CONTAINER_DEPTH_RANGE} (semantic heuristics)")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        abs_path = str(Path(html_path).resolve())
        await page.goto(f"file:///{abs_path}", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        cdp = await ctx.new_cdp_session(page)
        try:
            doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        finally:
            await cdp.detach()

        await browser.close()

    # ── Phase 1: Collect ──
    ref_map: dict = {}
    state = CollectState(ref_map)
    state.walk(doc.get("root", {}))

    all_count = len(state.elements_all)
    container_count = len(state.stats_map)
    whitelist_count = sum(1 for el in state.elements_all if el["_whitelist"])

    print(f"\n  Phase 1 — Collect:")
    print(f"    Interactive elements found: {all_count}")
    print(f"    Whitelist (button/input/a/select/textarea): {whitelist_count}")
    print(f"    Non-whitelist (onclick/role/tabindex): {all_count - whitelist_count}")
    print(f"    Containers created (depth {CONTAINER_DEPTH_RANGE[0]}-{CONTAINER_DEPTH_RANGE[1]}, semantic heuristic): {container_count}")

    # Container stats sorted by total_descendants
    containers_by_size = sorted(
        state.stats_map.items(),
        key=lambda kv: kv[1]["total_descendants"],
        reverse=True,
    )

    print(f"\n  Top 20 containers by descendant count:")
    for ckey, stats in containers_by_size[:20]:
        print(f"    {ckey:6s}  depth={stats['depth']}  tag={stats['tag']:<10s}  "
              f"total={stats['total_descendants']:>4d}  whitelist={stats['whitelist_count']:>4d}  "
              f"selector={stats['selector'][:50]}")

    # ── Phase 2: Project ──
    view, folded, branch_index = build_llm_view(state)

    print(f"\n  Phase 2 — Project:")
    print(f"    View elements (→ LLM): {len(view)}")
    print(f"    Folded containers: {len(folded)}")
    print(f"    Branch index entries: {len(branch_index)}")

    # Debug: which containers have elements in the final view?
    view_per_c = {}
    for ckey in state.stats_map:
        cnt = sum(1 for e in view if ckey in e.get("_containers", []))
        if cnt > 0:
            view_per_c[ckey] = cnt
    print(f"\n  View contributors (containers with >0 elements in final view):")
    for ckey, cnt in sorted(view_per_c.items(), key=lambda x: -x[1])[:15]:
        c = state.stats_map[ckey]
        print(f"    {ckey:6s}  depth={c['depth']}  tag={c['tag']:<10s}  in_view={cnt:>3d}  sel={c['selector'][:45]}")

    # Dense vs non-dense breakdown
    dense_keys = {f["key"] for f in folded}
    dense_containers = {k: v for k, v in state.stats_map.items() if k in dense_keys}
    non_dense = {k: v for k, v in state.stats_map.items() if k not in dense_keys}

    total_in_dense = sum(s["total_descendants"] for s in dense_containers.values())
    total_in_non_dense = sum(s["total_descendants"] for s in non_dense.values())

    print(f"\n  Density breakdown:")
    print(f"    Dense containers:  {len(dense_containers)} ({total_in_dense} elements)")
    print(f"    Non-dense containers: {len(non_dense)} ({total_in_non_dense} elements)")

    print(f"\n  Folded containers (dense -> sampled):")
    for f in sorted(folded, key=lambda x: x["total"], reverse=True):
        safe_summary = f["summary"].encode("ascii", errors="replace").decode("ascii")
        print(f"    {f['key']:6s}  type={f['type']:<10s}  total={f['total']:>4d}  "
              f"sampled={f['sampled']:>3d}  sel={f['selector'][:40]}  |  {safe_summary}")

    unsampled_in_dense = total_in_dense - sum(f["total"] for f in folded)
    if unsampled_in_dense > 0:
        print(f"\n  ⚠  {unsampled_in_dense} elements in dense containers NOT in folded list (self-count noise)")

    print(f"\n  Branch index sizes (top 20):")
    for ckey, refs in sorted(branch_index.items(), key=lambda kv: len(kv[1]), reverse=True)[:20]:
        print(f"    {ckey:6s}  {len(refs):>4d} refs")

    # Highlight the savings
    if all_count > 0:
        reduction = (1 - len(view) / all_count) * 100
        print(f"\n  {'='*50}")
        print(f"  TOTAL: {all_count} interactive → {len(view)} in LLM view ({reduction:.0f}% reduction)")
        print(f"  Folded: {len(folded)} containers, {sum(f['total'] for f in folded)} elements hidden")
        print(f"  {'='*50}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_progressive_profile.py <path/to/page.html>")
        sys.exit(1)

    asyncio.run(profile(sys.argv[1]))
