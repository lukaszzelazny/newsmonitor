import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def handle_response(response):
            # Print URLs of AJAX requests returning JSON
            if "/ajaxindex.php" in response.url or "/backend" in response.url or response.request.resource_type in ["xhr", "fetch"]:
                try:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type or "xml" in content_type or "html" in content_type:
                        print(f"XHR/Fetch: {response.url} - Status: {response.status}")
                        if "GPWSpolki" in response.url:
                            text = await response.text()
                            print(f"Snippet of GPWSpolki: {text[:200]}")
                except Exception as e:
                    pass
        
        page.on("response", handle_response)
        
        print("Navigating to https://www.gpw.pl/spolki")
        await page.goto("https://www.gpw.pl/spolki", wait_until="networkidle")
        
        # also click on standard tab just in case
        await asyncio.sleep(2)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
