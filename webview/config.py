# Configuration settings
WEBSITE_URL = "https://www.pif.gov.sa/en/our-investments/our-portfolio/"
FUZZY_MATCH_THRESHOLD = 85  # Minimum score for fuzzy matching
SECTOR_MATCH_THRESHOLD = 80  # Minimum score for sector matching

# Selectors for web scraping
SELECTORS = {
    "cookie_accept": "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "pagination": "ul.page-selector-list li a.page-selector-item-link",
    "company_card": ".search-result-list li a",
    "company_name": "h4.investmentTitle.field-title",
    "company_sector": "div.field-phrase"
}