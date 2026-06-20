import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await b.new_page()
        await pg.goto("about:blank")
        print("Page type:", type(pg))
        print("Has accessibility:", hasattr(pg, "accessibility"))
        if hasattr(pg, "accessibility"):
            print("Accessibility type:", type(pg.accessibility))
            print("Accessibility dir:", [x for x in dir(pg.accessibility) if not x.startswith("_")])
        await b.close()

asyncio.run(main())
