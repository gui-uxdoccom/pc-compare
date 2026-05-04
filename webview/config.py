# Configuration settings
WEBSITE_URL = "https://www.pif.gov.sa/en/our-investments/our-portfolio/"
FUZZY_MATCH_THRESHOLD = 90       # Minimum score for fuzzy matching (raised from 85 to reduce false positives)
SECTOR_MATCH_THRESHOLD = 80      # Minimum score for categorical (portfolio/ecosystem) matching

# Selectors for web scraping
SELECTORS = {
    "cookie_accept": "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "pagination": "ul.page-selector-list li a.page-selector-item-link",
    "company_card": ".search-result-list li a",
    "company_name": "h4.investmentTitle.field-title",
    # Both panels carry class "facet-search-filter" with no discriminating
    # attribute. We tell them apart by the contents of their facet items:
    # portfolio data-facetvalues all contain "Portfolio" (e.g. "Vision Portfolio");
    # ecosystem values never do.
    "portfolio_facet_panel": "div.facet-search-filter:has(p[data-facetvalue*='Portfolio'])",
    "ecosystem_facet_panel": "div.facet-search-filter:not(:has(p[data-facetvalue*='Portfolio']))",
    "facet_item": "p.facet-value",
    "facet_value_attr": "data-facetvalue",
    "facet_checkbox": "input[type='checkbox']",
}