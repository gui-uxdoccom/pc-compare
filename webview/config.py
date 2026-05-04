# Configuration settings
WEBSITE_URL = "https://www.pif.gov.sa/en/our-investments/our-portfolio/"
FUZZY_MATCH_THRESHOLD = 85       # Minimum score for fuzzy matching
SECTOR_MATCH_THRESHOLD = 80      # Minimum score for categorical (portfolio/ecosystem) matching

# Selectors for web scraping
SELECTORS = {
    "cookie_accept": "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "pagination": "ul.page-selector-list li a.page-selector-item-link",
    "company_card": ".search-result-list li a",
    "company_name": "h4.investmentTitle.field-title",
    # Facet panels — exact container selectors get nailed down in Task 7 by
    # inspecting the live page; placeholder values shown here.
    "portfolio_facet_panel": "div.facet-search-filter[data-facet='portfolio']",
    "ecosystem_facet_panel": "div.facet-search-filter[data-facet='ecosystem']",
    "facet_item": "p.facet-value",
    "facet_value_attr": "data-facetvalue",
    "facet_checkbox": "input[type='checkbox']",
}