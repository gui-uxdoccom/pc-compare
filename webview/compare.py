import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from rapidfuzz import fuzz
import argparse
import sys
from datetime import datetime
from config import *
from tqdm import tqdm
import re

async def scrape_website():
    """Scrape company data from website"""
    companies = []
    print("Starting website scraping...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        try:
            await page.goto(WEBSITE_URL)
            
            # Handle cookie consent
            try:
                await page.wait_for_selector(SELECTORS["cookie_accept"], timeout=5000)
                await page.click(SELECTORS["cookie_accept"])
                print("Accepted cookies.")
                await page.wait_for_timeout(2000)  # Wait for cookie banner to disappear
            except:
                print("No cookie consent needed or already accepted.")
            
            # Wait for company list to load
            await page.wait_for_selector('ul.search-result-list')
            
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
                
                # Get companies from current page
                company_cards = await page.query_selector_all('ul.search-result-list li a')
                
                for card in company_cards:
                    sector_elem = await card.query_selector('h5')
                    name_elem = await card.query_selector('h4')

                    name = await name_elem.inner_text() if name_elem else ""
                    sector = await sector_elem.inner_text() if sector_elem else ""
                    
                    if name:  # Only add if we found a name
                        companies.append({
                            "Company": name.strip(),
                            "Sector": sector.strip()
                        })
                
                # Click next page if not on last page
                if page_num < total_pages:
                    next_page = await page.query_selector(f'ul.page-selector-list li a[data-itemnumber="{page_num + 1}"]')
                    if next_page:
                        await next_page.click()
                        await page.wait_for_timeout(1500)  # Wait for page content to load
                        await page.wait_for_selector('ul.search-result-list')  # Wait for company list
            
            print(f"Successfully scraped {len(companies)} companies.")
        
        except Exception as e:
            print(f"Error during scraping: {e}")
            return None
        
        finally:
            await browser.close()
    
    return pd.DataFrame(companies)

def compare_companies(baseline_df, website_df):
    """Compare baseline with website data"""
    results = []
    matched_website_companies = set()  # Track matched companies

    for _, row in tqdm(baseline_df.iterrows(), total=len(baseline_df)):
        best_match = None
        best_score = 0

        cr_name = str(row['CR Name']).lower().strip()
        brand_name = str(row['Brand Name']).lower().strip()

        for _, web_row in website_df.iterrows():
            web_name = str(web_row['Company']).lower().strip()
            
            # Standard fuzzy match
            score_cr = fuzz.ratio(cr_name, web_name)
            score_brand = fuzz.ratio(brand_name, web_name)
            score = max(score_cr, score_brand)
            
            # Check for acronyms in parentheses - SIMPLE APPROACH
            # Example: "The Helicopter Company (THC)" should match with "THC"
            acronym_match = re.search(r'\(([A-Za-z]+)\)', web_row['Company'])
            if acronym_match:
                acronym = acronym_match.group(1).lower()
                # Check if CR name or brand name matches this acronym
                if acronym.lower() == cr_name.lower() or acronym.lower() == brand_name.lower():
                    score = max(score, 90)  # Strong match for exact acronym
            
            # Check if baseline name is contained in website name
            if len(cr_name) > 2 and cr_name in web_name:
                score = max(score, 85)
            
            if len(brand_name) > 2 and brand_name in web_name:
                score = max(score, 85)

            if score > best_score:
                best_score = score
                best_match = web_row

        website_name = None
        website_sector = None
        exists_in_website = "No"
        sectors_matching = "N/A"
        status = "Add"  # Default: company needs to be ADDED to website

        if best_score >= FUZZY_MATCH_THRESHOLD and best_match is not None:
            website_name = best_match['Company']
            website_sector = best_match['Sector']
            exists_in_website = "Yes"
            matched_website_companies.add(website_name)
            
            # Set status based on match score
            if best_score >= 90:
                # Check sector match
                sector_score = fuzz.ratio(str(row['VRP Sector']).lower(), str(website_sector).lower())
                if sector_score >= SECTOR_MATCH_THRESHOLD:
                    status = "OK"  # Both name and sector match well
                    sectors_matching = "Yes"
                else:
                    status = "Requires sector update"
                    sectors_matching = "No"
            else:
                status = "Requires name update"
                
                # Also check sector
                sector_score = fuzz.ratio(str(row['VRP Sector']).lower(), str(website_sector).lower())
                sectors_matching = "Yes" if sector_score >= SECTOR_MATCH_THRESHOLD else "No"

        # Always append the baseline company
        results.append({
            "CR Name": row['CR Name'],
            "Brand Name": row['Brand Name'],
            "Website Name": website_name if website_name else "",
            "VRP Sector": row['VRP Sector'],
            "Website Sector": website_sector if website_sector else "",
            "Match Score": best_score,
            "PC exist in website": exists_in_website,
            "Sectors matching": sectors_matching,
            "Status": status
        })

    # Process website companies that don't match any baseline company
    for _, web_row in website_df.iterrows():
        if web_row['Company'] not in matched_website_companies:
            # This website company should be REMOVED (exists on website but not in baseline)
            results.append({
                "CR Name": "",
                "Brand Name": "",
                "Website Name": web_row['Company'],
                "VRP Sector": "",
                "Website Sector": web_row['Sector'],
                "Match Score": 0,
                "PC exist in website": "Yes",
                "Sectors matching": "N/A",
                "Status": "Remove"
            })

    return pd.DataFrame(results), pd.DataFrame([
        {"Company": r["Website Name"], "Sector": r["Website Sector"]} 
        for _, r in pd.DataFrame(results).iterrows() 
        if r["Status"] == "Remove"
    ])

async def main():
    parser = argparse.ArgumentParser(description='Compare portfolio companies')
    parser.add_argument('baseline', help='Baseline Excel file')
    parser.add_argument('output', help='Output Excel file')
    
    args = parser.parse_args()
    
    try:
        print("Reading baseline data...")
        baseline_df = pd.read_excel(args.baseline)
        
        print("Scraping website data...")
        website_df = await scrape_website()
        if website_df is None:
            sys.exit(1)
        
        print("Comparing data...")
        results_df, unmatched_df = compare_companies(baseline_df, website_df)
        
        print("Saving results...")
        with pd.ExcelWriter(args.output, engine='openpyxl') as writer:
            results_df.to_excel(writer, sheet_name='Comparison Results', index=False)
            unmatched_df.to_excel(writer, sheet_name='Unmatched Website Companies', index=False)
        print(f"Results saved to {args.output}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())

