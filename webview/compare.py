import os
import pandas as pd
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from datetime import datetime
from config import *


async def _open_portfolio_page(playwright, headless, browser_type, timeout):
    """Launch the browser, apply stealth, navigate, dismiss cookies, and wait for the company list.

    Returns (browser, context, page) so the caller can drive interactions and tear down.
    """
    if browser_type == 'firefox':
        browser = await playwright.firefox.launch(headless=headless)
    elif browser_type == 'webkit':
        browser = await playwright.webkit.launch(headless=headless)
    else:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ],
        )

    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='America/New_York',
        color_scheme='light',
        permissions=['geolocation'],
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        },
    )

    page = await context.new_page()
    await Stealth().apply_stealth_async(page)

    await page.mouse.move(100, 100)
    await page.wait_for_timeout(500)

    try:
        await page.goto(WEBSITE_URL, wait_until='domcontentloaded', timeout=timeout)
        await page.wait_for_timeout(5000)
    except Exception:
        await page.goto(WEBSITE_URL, wait_until='load', timeout=timeout)
        await page.wait_for_timeout(5000)

    content = await page.content()
    if 'cloudflare' in content.lower() and ('challenge' in content.lower() or 'checking' in content.lower()):
        print("⚠ CLOUDFLARE CHALLENGE DETECTED — waiting 30s...")
        await page.wait_for_timeout(30000)
        if not headless:
            content = await page.content()
            if 'cloudflare' in content.lower() and 'challenge' in content.lower():
                print("   Solve manually in browser; waiting 120s...")
                await page.wait_for_timeout(120000)

    try:
        await page.wait_for_selector(SELECTORS["cookie_accept"], timeout=5000)
        await page.click(SELECTORS["cookie_accept"])
        await page.wait_for_timeout(3000)
    except Exception:
        pass

    await page.wait_for_selector('div.search-results', state='visible', timeout=30000)
    await page.wait_for_selector('ul.search-result-list', state='visible', timeout=30000)
    await page.wait_for_timeout(3000)

    return browser, context, page


async def _discover_facets(page) -> dict:
    """Read facet values from the Portfolio and Ecosystem panels.

    Returns {"portfolio": [...values...], "ecosystem": [...values...]}.
    Values come from the `data-facetvalue` attribute and are URL-encoded —
    the caller decodes them before display.
    """
    from urllib.parse import unquote

    async def _read(panel_selector: str) -> list[str]:
        items = await page.query_selector_all(
            f'{panel_selector} {SELECTORS["facet_item"]}'
        )
        values = []
        for item in items:
            raw = await item.get_attribute(SELECTORS["facet_value_attr"])
            if raw:
                values.append(unquote(raw))
        return values

    portfolio = await _read(SELECTORS["portfolio_facet_panel"])
    ecosystem = await _read(SELECTORS["ecosystem_facet_panel"])

    print(f"Discovered facets: portfolio={portfolio}, ecosystem={ecosystem}")
    return {"portfolio": portfolio, "ecosystem": ecosystem}


async def scrape_website(headless=True, browser_type='firefox', debug_mode=False, timeout=60000):
    """Scrape company data from website with Cloudflare bypass via playwright-stealth.

    Args:
        headless: If False, runs browser in visible mode (useful for debugging/CAPTCHA)
        browser_type: Browser to use ('chromium', 'firefox', 'webkit')
        debug_mode: If True, saves screenshots and HTML on errors
        timeout: Timeout in milliseconds for page load (default 60000ms = 60s)
    """
    companies = []
    print("=" * 80)
    print("STARTING WEBSITE SCRAPING")
    print("=" * 80)
    print(f"Browser: {browser_type}")
    print(f"Headless mode: {headless}")
    print(f"Debug mode: {debug_mode}")
    print(f"Timeout: {timeout}ms")
    print(f"Target: {WEBSITE_URL}")
    print("=" * 80)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

    try:
        async with async_playwright() as p:
            # Select browser based on type
            if browser_type == 'firefox':
                print("Launching Firefox with playwright-stealth...")
                browser = await p.firefox.launch(headless=headless)
            elif browser_type == 'webkit':
                print("Launching WebKit with playwright-stealth...")
                browser = await p.webkit.launch(headless=headless)
            else:  # chromium (default)
                print("Launching Chromium with playwright-stealth...")
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process'
                    ]
                )

            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                color_scheme='light',
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"'
                }
            )
            page = await context.new_page()

            # Apply playwright-stealth to remove all automation fingerprints
            print("Applying playwright-stealth patches...")
            await Stealth().apply_stealth_async(page)

            try:
                print(f"Navigating to {WEBSITE_URL}")

                # Add random mouse movement to appear more human
                await page.mouse.move(100, 100)
                await page.wait_for_timeout(500)

                # Try with domcontentloaded first (faster and more reliable)
                try:
                    await page.goto(WEBSITE_URL, wait_until='domcontentloaded', timeout=timeout)
                    print("✓ Page loaded (domcontentloaded)")
                    # Give it extra time for JS/Cloudflare challenge to resolve
                    await page.wait_for_timeout(5000)
                except Exception as e:
                    print(f"⚠ First attempt failed, retrying with load event...")
                    print(f"   Error: {str(e)[:100]}")
                    await page.goto(WEBSITE_URL, wait_until='load', timeout=timeout)
                    await page.wait_for_timeout(5000)
                    print("✓ Page loaded (load)")

                # Check for Cloudflare challenge
                content = await page.content()

                if 'cloudflare' in content.lower() and ('challenge' in content.lower() or 'checking' in content.lower()):
                    print("⚠ CLOUDFLARE CHALLENGE DETECTED!")
                    print("   Waiting 30 seconds for automatic resolution...")
                    await page.wait_for_timeout(30000)

                    content = await page.content()
                    if 'cloudflare' in content.lower() and 'challenge' in content.lower():
                        if not headless:
                            print("   ⚠ Challenge still present - please solve manually in browser window")
                            print("   Waiting 120 seconds for manual intervention...")
                            await page.wait_for_timeout(120000)
                        else:
                            print("   ⚠ WARNING: Cloudflare challenge persists in headless mode")
                            print("   Attempting to continue anyway...")
                            await page.wait_for_timeout(20000)

                # Handle cookie consent
                try:
                    await page.wait_for_selector(SELECTORS["cookie_accept"], timeout=5000)
                    await page.click(SELECTORS["cookie_accept"])
                    print("Accepted cookies.")
                    await page.wait_for_timeout(3000)
                except Exception:
                    print("No cookie consent needed or already accepted.")

                # Wait for company list to load
                print("Waiting for company list to load...")
                try:
                    await page.wait_for_selector('div.search-results', state='visible', timeout=30000)
                    print("Search results container found.")

                    await page.wait_for_selector('ul.search-result-list', state='visible', timeout=30000)
                    print("Company list found.")

                    await page.wait_for_timeout(3000)

                    list_items = await page.query_selector_all('ul.search-result-list li')
                    print(f"Found {len(list_items)} list items initially")

                    if len(list_items) == 0:
                        print("Warning: List found but no items yet, waiting longer...")
                        await page.wait_for_timeout(5000)
                        list_items = await page.query_selector_all('ul.search-result-list li')
                        print(f"After waiting: {len(list_items)} list items")

                except Exception as e:
                    error_msg = f"Failed to find company list: {e}"
                    print(f"❌ {error_msg}")

                    if debug_mode:
                        print("💾 Saving debug information...")
                        os.makedirs(debug_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                        screenshot_path = os.path.join(debug_dir, f'error_screenshot_{timestamp}.png')
                        html_path = os.path.join(debug_dir, f'error_page_{timestamp}.html')

                        await page.screenshot(path=screenshot_path)
                        print(f"   ✓ Screenshot: {screenshot_path}")

                        html = await page.content()
                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        print(f"   ✓ HTML: {html_path}")
                        print(f"   ✓ Current URL: {page.url}")

                    raise Exception(error_msg)

                # Get total pages
                page_numbers = []
                page_links = await page.query_selector_all('ul.page-selector-list li a')
                for link in page_links:
                    text = await link.inner_text()
                    if text.isdigit():
                        page_numbers.append(int(text))

                total_pages = max(page_numbers) if page_numbers else 1
                print(f"Found {total_pages} pages to scrape.")

                # Scrape each page
                for page_num in range(1, total_pages + 1):
                    print(f"Scraping page {page_num}/{total_pages}")

                    company_cards = await page.query_selector_all('ul.search-result-list li a')

                    for card in company_cards:
                        sector_elem = await card.query_selector('h5')
                        name_elem = await card.query_selector('h4')

                        name = await name_elem.inner_text() if name_elem else ""
                        sector = await sector_elem.inner_text() if sector_elem else ""

                        if name:
                            companies.append({
                                "Company": name.strip(),
                                "Sector": sector.strip()
                            })

                    # Click next page if not on last page
                    if page_num < total_pages:
                        first_card_before = await page.query_selector('ul.search-result-list li a h4')
                        first_name_before = await first_card_before.inner_text() if first_card_before else ""

                        next_page = await page.query_selector(f'ul.page-selector-list li a[data-itemnumber="{page_num + 1}"]')
                        if next_page:
                            await next_page.click()
                            await page.wait_for_timeout(2000)

                            for _ in range(10):
                                await page.wait_for_timeout(500)
                                first_card_after = await page.query_selector('ul.search-result-list li a h4')
                                first_name_after = await first_card_after.inner_text() if first_card_after else ""
                                if first_name_after != first_name_before:
                                    print(f"  Page content changed: '{first_name_before}' -> '{first_name_after}'")
                                    break

                            await page.wait_for_selector('ul.search-result-list')

                print(f"Successfully scraped {len(companies)} companies.")

            except Exception as e:
                print(f"Error during scraping: {e}")
                import traceback
                traceback.print_exc()
                return None

            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        print(f"Failed to launch browser: {e}")
        import traceback
        traceback.print_exc()
        return None

    return pd.DataFrame(companies)
