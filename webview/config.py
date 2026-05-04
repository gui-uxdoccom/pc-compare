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
    # Facet panels are identified via Playwright's :has-text() pseudo applied
    # to the surrounding component-content block (panels themselves don't carry
    # a discriminating attribute — both have class "facet-search-filter").
    "portfolio_facet_panel": "div.component-content:has-text('Investment Portfolios') div.facet-search-filter",
    "ecosystem_facet_panel": "div.component-content:has-text('Ecosystems') div.facet-search-filter",
    "facet_item": "p.facet-value",
    "facet_value_attr": "data-facetvalue",
    "facet_checkbox": "input[type='checkbox']",
}