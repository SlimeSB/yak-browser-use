"""Quick integration test: load local HTML, run a11y snapshot via CDP, print results.

Usage:
    python tests/run_a11y_on_html.py tests/fixtures/淘宝.html
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def main(html_path: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        if html_path.startswith("http"):
            await page.goto(html_path, wait_until="domcontentloaded")
        else:
            try:
                await page.goto(
                    f"file:///{Path(html_path).resolve().as_posix()}",
                    wait_until="domcontentloaded",
                    timeout=10000,
                )
            except Exception:
                pass  # large HTML with external resources may not fully load
        await asyncio.sleep(2)  # let a11y tree settle

        # Get a11y tree via CDP
        cdp = await page.context.new_cdp_session(page)
        try:
            result = await cdp.send("Accessibility.getFullAXTree", {"max_depth": -1})
        finally:
            await cdp.detach()

        nodes = result.get("nodes", [])
        print(f"Page: {page.url}")
        print(f"Title: {await page.title()}")
        print(f"AXTree nodes: {len(nodes)}")
        print()

        # Show interactive nodes (count first, then print top N)
        interactive_roles = {
            "button", "link", "checkbox", "radio", "switch", "tab",
            "menuitem", "combobox", "listbox", "textbox", "searchbox",
            "slider", "spinbutton", "treeitem",
        }
        interactive = []
        for node in nodes:
            role = (node.get("role", {}).get("value", "") or "").lower()
            if role in interactive_roles:
                name = (node.get("name", {}).get("value", "") or "")
                value = (node.get("value", {}).get("value", "") or "")
                props = node.get("properties", [])
                disabled = any(
                    p.get("name") == "disabled" and p.get("value", {}).get("value") is True
                    for p in props
                )
                interactive.append((role, name, value, disabled))

        print(f"Interactive elements: {len(interactive)}")
        print()

        for role, name, value, disabled in interactive[:50]:
            # safe print for Windows GBK terminal
            try:
                print(f"  {role:12s} | name={name[:50]:50s} | value={value[:20]} | disabled={disabled}")
            except UnicodeEncodeError:
                print(f"  {role:12s} | name=<unicode> | value={value[:20]} | disabled={disabled}")

        if len(interactive) > 50:
            print(f"  ... and {len(interactive) - 50} more")

        await browser.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/a11y_test.html"
    asyncio.run(main(target))
