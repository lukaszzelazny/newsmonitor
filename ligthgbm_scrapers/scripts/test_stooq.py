import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        print("Navigating to Stooq...")
        await page.goto("https://stooq.pl/q/p/?s=bdx", wait_until="domcontentloaded")
        
        # Check for consent frame or button
        try:
            btn = page.locator("button:has-text('Zgadzam się')")
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass
            
        text = await page.content()
        with open("/tmp/stooq_bdx.html", "w", encoding="utf-8") as f:
            f.write(text)
        print("Content length:", len(text))
        print("Sektor in text:", "Sektor" in text)
        print("EKD in text:", "EKD" in text)
        
        # Look for EKD text specifically
        if "EKD" in text:
            import bs4
            soup = bs4.BeautifulSoup(text, "html.parser")
            elements = soup.find_all(string=lambda x: x and "EKD" in x)
            for el in elements:
                tr = el.find_parent("tr")
                if tr:
                    print("Found TR:")
                    print("  ", tr.text.strip().replace('\n', ' '))
                
                # Check siblings
                td = el.find_parent("td")
                if td:
                    print("Found TD parent:", td.text.strip())
                    sib = td.find_next_sibling("td")
                    if sib:
                        print("  Value:", sib.text.strip())
                        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
