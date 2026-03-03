import asyncio
from playwright.async_api import async_playwright
from config import WEBSITE_URL

async def debug_page():
    """Debug script to inspect page structure and find correct selectors"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Visible browser
        page = await browser.new_page()

        try:
            print(f"Navigating to {WEBSITE_URL}")
            await page.goto(WEBSITE_URL, timeout=30000)

            # Handle cookie consent
            try:
                await page.wait_for_selector("button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll", timeout=5000)
                await page.click("button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll")
                print("Accepted cookies.")
                await page.wait_for_timeout(2000)
            except:
                print("No cookie consent needed or already accepted.")

            # Wait a bit for dynamic content to load
            await page.wait_for_timeout(3000)

            # Try different selectors
            print("\n=== Testing Selectors ===")

            selectors_to_test = [
                'ul.search-result-list',
                '.search-result-list',
                'ul[class*="search-result"]',
                '[class*="search-result-list"]',
                '.search-result-list li',
                'div.search-results',
                '[class*="portfolio"]',
                '[class*="investment"]',
                'ul.list',
                '.result-list',
            ]

            for selector in selectors_to_test:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        html = await element.inner_html()
                        print(f"✓ FOUND: {selector}")
                        print(f"  HTML preview (first 200 chars): {html[:200]}")
                    else:
                        print(f"✗ NOT FOUND: {selector}")
                except Exception as e:
                    print(f"✗ ERROR with {selector}: {e}")

            # Get page content to analyze
            print("\n=== Page Body Preview ===")
            content = await page.content()

            # Look for list-related classes
            print("\n=== Searching for list/result related classes ===")
            import re
            classes = re.findall(r'class="([^"]*(?:list|result|portfolio|investment)[^"]*)"', content)
            unique_classes = set(classes)
            for cls in sorted(unique_classes):
                print(f"  - {cls}")

            # Take a screenshot for manual inspection
            await page.screenshot(path='/Users/grodrigues/Documents/Sandbox/Automation/pc-compare/webview/debug_screenshot.png', full_page=True)
            print("\n✓ Screenshot saved to debug_screenshot.png")

            print("\n=== Press Enter to close browser ===")
            input()

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(debug_page())
