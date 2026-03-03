# Cloudflare Bypass Guide

## Current Solution: `playwright-stealth`

`playwright-stealth` is now integrated directly into `compare.py`. It patches the Playwright browser context to remove over 20 automation fingerprints that Cloudflare detects, including:
- `navigator.webdriver` property
- Chrome automation flags
- Plugin and language mocking
- TLS/header inconsistencies

No extra configuration needed — it applies automatically on every scrape using the v2 API:
```python
from playwright_stealth import Stealth
await Stealth().apply_stealth_async(page)
```

---

## What Cloudflare Is Detecting

1. **Request arrives** at Cloudflare's edge servers
2. **Cloudflare analyzes** TLS fingerprint, HTTP headers, JavaScript execution environment
3. **Detection vectors**: `navigator.webdriver`, missing `window.chrome`, uniform plugin lists, automation-specific headers
4. **Block happens** — returns 403 or drops connection
5. **Browser reports** misleading `ERR_NAME_NOT_RESOLVED`

---

## Debugging a Failed Scrape

### 1. Run the debug selector script (visible browser)
```bash
cd webview
python debug_selectors.py
```
This opens a real browser window. Watch for:
- Cloudflare challenge pages (verify stealth is working)
- Page structure changes (CSS selectors may have changed)

### 2. Check network connectivity
```bash
nslookup www.pif.gov.sa
curl -I https://www.pif.gov.sa/en/our-investments/our-portfolio/
```

### 3. Enable debug mode in the web UI
The "Debug" option saves screenshots and the raw HTML to `webview/uploads/` on failure, making it easy to see what Cloudflare is showing.

---

## Escalation Path (if playwright-stealth is blocked)

### Option A: Switch to visible mode
Disable headless in the web UI to let a real browser window handle any CAPTCHA manually.

### Option B: Use `camoufox` (stronger bypass)
`camoufox` patches Firefox at binary level — much harder for Cloudflare to detect than JS-level patches.

```bash
pip install camoufox[geoip]
python -m camoufox fetch   # downloads patched Firefox binary
```

Then in `compare.py`, swap the browser launch for:
```python
from camoufox.async_api import AsyncCamoufox

async with AsyncCamoufox(headless=True, geoip=True) as browser:
    page = await browser.new_page()
    await page.goto(WEBSITE_URL, ...)
```

### Option C: ScraperAPI (managed Cloudflare bypass)
Services like ScraperAPI handle Cloudflare at the proxy level.
- Add proxy to the Playwright context instead of changing the browser
- Requires a paid account

---

## Selector Verification

If the scraper loads the page but finds 0 companies, the CSS selectors may have changed. Run `debug_selectors.py` and compare current page HTML against `config.py`:

| What | Selector in `config.py` |
|------|------------------------|
| Cookie accept button | `button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll` |
| Company list | `ul.search-result-list` |
| Pagination | `ul.page-selector-list li a` |
| Company name | `h4` (inside list item `a`) |
| Company sector | `h5` (inside list item `a`) |

Update `webview/config.py` if any selectors have changed.
