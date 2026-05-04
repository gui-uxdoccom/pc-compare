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


async def _scrape_with_facet(page, panel_selector: str, facet_value: str) -> list[str]:
    """Click one facet checkbox, paginate the filtered list, return company names, then uncheck.

    Asserts that the result list visibly changed after the click — if it didn't,
    we abort this facet and return an empty list rather than scrape the
    unfiltered list silently.
    """
    from urllib.parse import quote

    encoded = quote(facet_value)
    item_selector = (
        f'{panel_selector} {SELECTORS["facet_item"]}'
        f'[{SELECTORS["facet_value_attr"]}="{encoded}"]'
    )

    # Capture the first card's name so we can detect a change
    before_card = await page.query_selector('ul.search-result-list li a h4')
    before_name = await before_card.inner_text() if before_card else ""
    before_count_elems = await page.query_selector_all('ul.search-result-list li')
    before_count = len(before_count_elems)

    # Click the facet's checkbox
    try:
        item = await page.wait_for_selector(item_selector, timeout=10000)
        checkbox = await item.query_selector(SELECTORS["facet_checkbox"])
        target = checkbox or item
        await target.click()
    except Exception as e:
        print(f"  ⚠ could not click facet '{facet_value}': {e}")
        return []

    # Wait for the list to actually change
    changed = False
    for _ in range(20):
        await page.wait_for_timeout(500)
        after_card = await page.query_selector('ul.search-result-list li a h4')
        after_name = await after_card.inner_text() if after_card else ""
        after_count = len(await page.query_selector_all('ul.search-result-list li'))
        if after_name != before_name or after_count != before_count:
            changed = True
            break

    if not changed:
        print(f"  ⚠ facet '{facet_value}' click had no visible effect; skipping")
        # Try to uncheck anyway to restore state
        try:
            await target.click()
            await page.wait_for_timeout(1000)
        except Exception:
            pass
        return []

    # Determine total pages for the filtered list
    page_links = await page.query_selector_all('ul.page-selector-list li a')
    page_numbers = []
    for link in page_links:
        text = await link.inner_text()
        if text.isdigit():
            page_numbers.append(int(text))
    total_pages = max(page_numbers) if page_numbers else 1

    names: list[str] = []
    for page_num in range(1, total_pages + 1):
        cards = await page.query_selector_all('ul.search-result-list li a')
        for card in cards:
            name_elem = await card.query_selector('h4')
            if name_elem:
                name = (await name_elem.inner_text()).strip()
                if name:
                    names.append(name)

        if page_num < total_pages:
            first_before = await page.query_selector('ul.search-result-list li a h4')
            first_before_name = await first_before.inner_text() if first_before else ""
            next_link = await page.query_selector(
                f'ul.page-selector-list li a[data-itemnumber="{page_num + 1}"]'
            )
            if next_link:
                await next_link.click()
                for _ in range(10):
                    await page.wait_for_timeout(500)
                    first_after = await page.query_selector('ul.search-result-list li a h4')
                    first_after_name = await first_after.inner_text() if first_after else ""
                    if first_after_name != first_before_name:
                        break

    # Uncheck the facet to restore the unfiltered state for the next pass
    try:
        item = await page.query_selector(item_selector)
        checkbox = await item.query_selector(SELECTORS["facet_checkbox"]) if item else None
        target = checkbox or item
        if target:
            await target.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    print(f"  ✓ facet '{facet_value}': {len(names)} companies")
    return names


async def scrape_website(headless=True, browser_type='firefox', debug_mode=False, timeout=60000):
    """Scrape company data from PIF portfolio site, traversing facets to extract
    Portfolio and Ecosystem per company.

    Returns a DataFrame with columns: Company, Portfolio, Ecosystem.
    """
    print("=" * 80)
    print("STARTING WEBSITE SCRAPING (facet traversal)")
    print(f"Browser: {browser_type} | Headless: {headless} | Timeout: {timeout}ms")
    print("=" * 80)

    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

    try:
        async with async_playwright() as p:
            browser = context = page = None
            try:
                browser, context, page = await _open_portfolio_page(
                    p, headless, browser_type, timeout,
                )
            except Exception as e:
                if debug_mode and page is not None:
                    os.makedirs(debug_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    await page.screenshot(path=os.path.join(debug_dir, f'error_screenshot_{ts}.png'))
                    with open(os.path.join(debug_dir, f'error_page_{ts}.html'), 'w', encoding='utf-8') as f:
                        f.write(await page.content())
                raise

            try:
                facets = await _discover_facets(page)

                # Pass 1: Portfolio facets — defines the company universe
                portfolio_map: dict[str, str] = {}
                for value in facets["portfolio"]:
                    print(f"Scraping portfolio facet: {value}")
                    names = await _scrape_with_facet(
                        page, SELECTORS["portfolio_facet_panel"], value,
                    )
                    for name in names:
                        portfolio_map[name] = value

                # Pass 2: Ecosystem facets — enriches the universe
                ecosystem_map: dict[str, str] = {}
                for value in facets["ecosystem"]:
                    print(f"Scraping ecosystem facet: {value}")
                    names = await _scrape_with_facet(
                        page, SELECTORS["ecosystem_facet_panel"], value,
                    )
                    for name in names:
                        ecosystem_map[name] = value

                # Merge into a single record per company
                all_names = set(portfolio_map.keys()) | set(ecosystem_map.keys())
                companies = []
                for name in sorted(all_names):
                    portfolio = portfolio_map.get(name)
                    ecosystem = ecosystem_map.get(name)
                    if portfolio is None:
                        print(f"  ⚠ data inconsistency: '{name}' tagged with ecosystem but no portfolio")
                    companies.append({
                        "Company": name,
                        "Portfolio": portfolio,
                        "Ecosystem": ecosystem,
                    })

                print(f"Scraped {len(companies)} companies "
                      f"({sum(1 for c in companies if c['Ecosystem'])} with ecosystem)")
                return pd.DataFrame(companies)

            finally:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()

    except Exception as e:
        print(f"Failed to scrape website: {e}")
        import traceback
        traceback.print_exc()
        return None
