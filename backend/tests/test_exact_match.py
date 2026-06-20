"""Test Playwright get_by_role(name, exact=True) matching against CDP AXTree.

Tests 10 elements to verify the approach works.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


INTERACTIVE_ROLES = {
    "button", "link", "checkbox", "radio", "switch", "tab",
    "menuitem", "combobox", "listbox", "textbox", "searchbox",
    "slider", "spinbutton", "treeitem",
}


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
                pass
        await asyncio.sleep(2)

        cdp = await page.context.new_cdp_session(page)
        try:
            result = await cdp.send("Accessibility.getFullAXTree", {"max_depth": -1})
        finally:
            await cdp.detach()

        nodes = result.get("nodes", [])
        elements = []
        for node in nodes:
            role = (node.get("role", {}).get("value", "") or "").lower()
            if role in INTERACTIVE_ROLES:
                name = (node.get("name", {}).get("value", "") or "").strip()
                elements.append((role, name))

        print(f"Page: {Path(html_path).name}")
        print(f"Interactive elements: {len(elements)}")
        print()

        # Test first 10 with Playwright's actual get_by_role
        sample = elements[:50]
        matched = 0
        failed = 0

        for role, name in sample:
            try:
                locator = page.get_by_role(role, name=name, exact=True)
                count = await locator.count()
                if count > 0:
                    matched += 1
                    status = "OK"
                else:
                    failed += 1
                    status = "MISS"
            except Exception:
                failed += 1
                status = "ERR"
            # safe print
            try:
                print(f"  {status:4s} {role}: {name[:50]}")
            except UnicodeEncodeError:
                print(f"  {status:4s} {role}: <unicode>")

        total = matched + failed
        rate = matched / total * 100 if total > 0 else 0
        print()
        print(f"exact=True match rate: {matched}/{total} = {rate:.1f}%")

        await browser.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/淘宝.html"
    asyncio.run(main(target))
