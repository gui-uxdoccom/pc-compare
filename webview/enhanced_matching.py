import re
from rapidfuzz import fuzz, process
import pandas as pd
from typing import Dict, List, Tuple, Optional

class EnhancedCompanyMatcher:
    def __init__(self, 
                 fuzzy_threshold: int = 90,  # Increased from 85 to be more strict
                 sector_threshold: int = 80,
                 exact_match_threshold: int = 95,
                 partial_match_threshold: int = 90):
        
        self.fuzzy_threshold = fuzzy_threshold
        self.sector_threshold = sector_threshold
        self.exact_match_threshold = exact_match_threshold
        self.partial_match_threshold = partial_match_threshold
        
        # Common business suffixes to normalize (order matters - most specific first)
        self.business_suffixes = [
            'holding company', 'holding co', 'holding corp', 'holding corporation',
            'investment company', 'investment co', 'trading company', 'trading co',
            'company limited', 'company ltd', 'co limited', 'co ltd',
            'corporation', 'corp', 'incorporated', 'inc', 
            'limited', 'ltd', 'limited liability company', 'llc',
            'holding', 'company', 'co', 'group', 'plc', 'sa', 'bsc', 'ksc'
        ]
        
        # Sector synonyms mapping
        self.sector_synonyms = {
            'technology': ['tech', 'it', 'information technology', 'software'],
            'healthcare': ['health', 'medical', 'pharma', 'pharmaceutical'],
            'financial services': ['finance', 'banking', 'bank', 'financial'],
            'real estate': ['property', 'realty', 'real estate development'],
            'energy': ['oil', 'gas', 'petroleum', 'renewable energy'],
            'telecommunications': ['telecom', 'communications', 'mobile'],
            'manufacturing': ['industrial', 'production', 'factory'],
            'retail': ['consumer', 'shopping', 'commerce'],
            'transportation': ['logistics', 'shipping', 'transport']
        }

    def normalize_company_name(self, name: str) -> str:
        """Normalize company name by removing common suffixes and cleaning"""
        if not name or pd.isna(name):
            return ""
        
        # Convert to lowercase and strip
        normalized = str(name).lower().strip()
        
        # Remove special characters except spaces and alphanumeric
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        
        # Remove common business suffixes (process multiple times to catch combinations)
        changed = True
        iterations = 0
        while changed and iterations < 3:  # Prevent infinite loops
            changed = False
            iterations += 1
            for suffix in sorted(self.business_suffixes, key=len, reverse=True):
                if normalized.endswith(f' {suffix}'):
                    new_normalized = normalized[:-len(f' {suffix}')].strip()
                    if new_normalized:  # Don't remove if it would make the name empty
                        normalized = new_normalized
                        changed = True
                        break
        
        return normalized

    def extract_core_name(self, name: str) -> str:
        """Extract the core business name (most important words)"""
        normalized = self.normalize_company_name(name)
        
        # Split into words
        words = normalized.split()
        
        # Remove common filler words
        filler_words = ['the', 'a', 'an', 'and', 'or', 'of', 'for', 'in', 'on', 'at']
        core_words = [word for word in words if word not in filler_words]
        
        return ' '.join(core_words)

    def calculate_match_score(self, baseline_name: str, website_name: str) -> Dict:
        """Calculate comprehensive match score using multiple strategies"""
        
        # Strategy 1: Exact match (after normalization)
        norm_baseline = self.normalize_company_name(baseline_name)
        norm_website = self.normalize_company_name(website_name)
        
        if norm_baseline == norm_website:
            return {
                'score': 100,
                'match_type': 'exact_normalized',
                'confidence': 'high'
            }
        
        # Strategy 2: Core name match
        core_baseline = self.extract_core_name(baseline_name)
        core_website = self.extract_core_name(website_name)
        
        if core_baseline == core_website and core_baseline:
            return {
                'score': 98,
                'match_type': 'core_exact',
                'confidence': 'high'
            }
        
        # Strategy 3: Substring containment (both directions) - with stricter validation
        if core_baseline and core_website:
            # Check if one name is an acronym/abbreviation of the other
            baseline_words = core_baseline.split()
            website_words = core_website.split()
            
            # Special case: if baseline is short (potential acronym) and website contains it AS A SEPARATE WORD
            if len(core_baseline) <= 10 and len(baseline_words) == 1:
                # Check if the short name appears as a complete word in the longer name
                if core_baseline in website_words or core_baseline.upper() in [w.upper() for w in website_words]:
                    return {
                        'score': 96,
                        'match_type': 'acronym_match',
                        'confidence': 'high'
                    }
            
            # Special case: if website is short (potential acronym) and baseline contains it AS A SEPARATE WORD
            if len(core_website) <= 10 and len(website_words) == 1:
                # Check if the short name appears as a complete word in the longer name  
                if core_website in baseline_words or core_website.upper() in [w.upper() for w in baseline_words]:
                    return {
                        'score': 96,
                        'match_type': 'acronym_match',
                        'confidence': 'high'
                    }
            
            # Regular substring matching with length validation
            # Only allow substring matching if both names are substantial (avoid matching on single words like "company")
            min_length_for_substring = 8  # Require at least 8 characters for core name
            if len(core_baseline) >= min_length_for_substring and len(core_website) >= min_length_for_substring:
                if core_baseline in core_website or core_website in core_baseline:
                    # Additional validation: ensure the shorter name is at least 60% of the longer name
                    shorter_len = min(len(core_baseline), len(core_website))
                    longer_len = max(len(core_baseline), len(core_website))
                    length_ratio = shorter_len / longer_len
                    
                    if length_ratio >= 0.6:  # At least 60% length similarity
                        containment_score = 95 if len(core_baseline) > 10 else 88
                        return {
                            'score': containment_score,
                            'match_type': 'substring',
                            'confidence': 'high' if containment_score >= 90 else 'medium'
                        }
        
        # Strategy 4: Token-based matching - with stricter requirements
        baseline_tokens = set(norm_baseline.split())
        website_tokens = set(norm_website.split())
        
        if baseline_tokens and website_tokens:
            common_tokens = baseline_tokens.intersection(website_tokens)
            total_tokens = baseline_tokens.union(website_tokens)
            
            # Remove generic business words that shouldn't count as meaningful matches
            generic_words = {'company', 'group', 'holding', 'corp', 'inc', 'ltd', 'limited', 'co', 'investment'}
            meaningful_common = common_tokens - generic_words
            meaningful_total = total_tokens - generic_words
            
            if meaningful_common and meaningful_total:
                token_ratio = len(meaningful_common) / len(meaningful_total)
                # Require higher threshold and meaningful word overlap
                if token_ratio >= 0.75 and len(meaningful_common) >= 2:  # 75% meaningful tokens + at least 2 meaningful words
                    return {
                        'score': int(token_ratio * 92),  # Reduced max score to 92
                        'match_type': 'token_based',
                        'confidence': 'high' if token_ratio >= 0.85 else 'medium'
                    }
        
        # Strategy 5: Fuzzy matching (fallback) - with minimum length validation
        # Avoid fuzzy matching very short names or names with very different lengths
        if len(norm_baseline) < 3 or len(norm_website) < 3:
            return {
                'score': 0,
                'match_type': 'too_short',
                'confidence': 'none'
            }
        
        # Avoid matching names with very different lengths (likely different companies)  
        # But allow reasonable length differences for business suffixes
        length_ratio = min(len(norm_baseline), len(norm_website)) / max(len(norm_baseline), len(norm_website))
        if length_ratio < 0.3:  # Reduced from 0.4 to allow "Dan Company" vs "Dan Company Ltd"
            return {
                'score': 0,
                'match_type': 'length_mismatch',
                'confidence': 'none'
            }
        
        fuzzy_score = fuzz.ratio(norm_baseline, norm_website)
        partial_score = fuzz.partial_ratio(norm_baseline, norm_website)
        token_sort_score = fuzz.token_sort_ratio(norm_baseline, norm_website)
        
        best_fuzzy = max(fuzzy_score, partial_score, token_sort_score)
        
        return {
            'score': best_fuzzy,
            'match_type': 'fuzzy',
            'confidence': 'high' if best_fuzzy >= 92 else 'medium' if best_fuzzy >= 85 else 'low'
        }

    def normalize_sector(self, sector: str) -> str:
        """Normalize sector name using synonyms"""
        if not sector or pd.isna(sector):
            return ""
        
        sector_lower = str(sector).lower().strip()
        
        # Check for exact matches in synonyms
        for main_sector, synonyms in self.sector_synonyms.items():
            if sector_lower == main_sector or sector_lower in synonyms:
                return main_sector
        
        return sector_lower

    def compare_sectors(self, baseline_sector: str, website_sector: str) -> Dict:
        """Compare sectors with normalization and synonyms"""
        norm_baseline = self.normalize_sector(baseline_sector)
        norm_website = self.normalize_sector(website_sector)
        
        if norm_baseline == norm_website:
            return {
                'match': True,
                'score': 100,
                'normalized_baseline': norm_baseline,
                'normalized_website': norm_website
            }
        
        # Fuzzy match for sectors
        if norm_baseline and norm_website:
            score = fuzz.ratio(norm_baseline, norm_website)
            return {
                'match': score >= self.sector_threshold,
                'score': score,
                'normalized_baseline': norm_baseline,
                'normalized_website': norm_website
            }
        
        return {
            'match': False,
            'score': 0,
            'normalized_baseline': norm_baseline,
            'normalized_website': norm_website
        }

    def debug_match(self, baseline_name: str, website_name: str) -> None:
        """Debug function to understand why two companies matched"""
        print(f"\n=== DEBUGGING MATCH ===")
        print(f"Baseline: '{baseline_name}'")
        print(f"Website: '{website_name}'")
        
        norm_baseline = self.normalize_company_name(baseline_name)
        norm_website = self.normalize_company_name(website_name)
        print(f"Normalized Baseline: '{norm_baseline}'")
        print(f"Normalized Website: '{norm_website}'")
        
        core_baseline = self.extract_core_name(baseline_name)
        core_website = self.extract_core_name(website_name)
        print(f"Core Baseline: '{core_baseline}'")
        print(f"Core Website: '{core_website}'")
        
        match_result = self.calculate_match_score(baseline_name, website_name)
        print(f"Match Result: {match_result}")
        print("=========================\n")

    def find_best_match(self, baseline_row: pd.Series, website_df: pd.DataFrame) -> Tuple[Optional[pd.Series], Dict]:
        """Find the best match for a baseline company in website data"""
        
        best_match = None
        best_score_info = {'score': 0, 'match_type': 'none', 'confidence': 'none'}
        
        baseline_cr = baseline_row.get('CR Name', '')
        baseline_brand = baseline_row.get('Brand Name', '')
        
        for _, website_row in website_df.iterrows():
            website_name = website_row.get('Company', '')
            
            # Try matching against both CR Name and Brand Name
            cr_match = self.calculate_match_score(baseline_cr, website_name)
            brand_match = self.calculate_match_score(baseline_brand, website_name)
            
            # Use the better match
            current_match = cr_match if cr_match['score'] >= brand_match['score'] else brand_match
            current_match['matched_field'] = 'CR Name' if cr_match['score'] >= brand_match['score'] else 'Brand Name'
            
            if current_match['score'] > best_score_info['score']:
                best_score_info = current_match
                best_match = website_row
        
        return best_match, best_score_info

def enhanced_compare_companies(baseline_df: pd.DataFrame, website_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Enhanced company comparison with improved matching"""
    
    matcher = EnhancedCompanyMatcher()
    results = []
    matched_website_companies = set()
    
    print(f"Starting enhanced comparison of {len(baseline_df)} baseline companies against {len(website_df)} website companies...")
    
    for idx, baseline_row in baseline_df.iterrows():
        print(f"Processing company {idx + 1}/{len(baseline_df)}: {baseline_row.get('CR Name', 'N/A')}")
        
        best_match, match_info = matcher.find_best_match(baseline_row, website_df)
        
        # Determine status based on match quality
        status = "Add"  # Default: needs to be added to website
        website_name = ""
        website_sector = ""
        sectors_match = "N/A"
        exists_in_website = "No"
        
        if match_info['score'] >= matcher.fuzzy_threshold and best_match is not None:
            website_name = best_match['Company']
            website_sector = best_match['Sector']
            exists_in_website = "Yes"
            matched_website_companies.add(website_name)
            
            # Check sector match
            sector_comparison = matcher.compare_sectors(
                baseline_row.get('VRP Sector', ''), 
                website_sector
            )
            
            sectors_match = "Yes" if sector_comparison['match'] else "No"
            
            # Determine final status
            if match_info['score'] >= matcher.exact_match_threshold:
                if sector_comparison['match']:
                    status = "OK"
                else:
                    status = "Requires sector update"
            else:
                status = "Requires name update"
        
        # Store detailed result
        result = {
            "CR Name": baseline_row.get('CR Name', ''),
            "Brand Name": baseline_row.get('Brand Name', ''),
            "Website Name": website_name,
            "VRP Sector": baseline_row.get('VRP Sector', ''),
            "Website Sector": website_sector,
            "Match Score": round(match_info['score'], 1),
            "Match Type": match_info.get('match_type', 'none'),
            "Match Confidence": match_info.get('confidence', 'none'),
            "Matched Field": match_info.get('matched_field', 'N/A'),
            "PC exist in website": exists_in_website,
            "Sectors matching": sectors_match,
            "Status": status
        }
        
        results.append(result)
    
    # Handle unmatched website companies (should be removed)
    for _, website_row in website_df.iterrows():
        if website_row['Company'] not in matched_website_companies:
            results.append({
                "CR Name": "",
                "Brand Name": "",
                "Website Name": website_row['Company'],
                "VRP Sector": "",
                "Website Sector": website_row['Sector'],
                "Match Score": 0,
                "Match Type": "unmatched",
                "Match Confidence": "none",
                "Matched Field": "N/A",
                "PC exist in website": "Yes",
                "Sectors matching": "N/A",
                "Status": "Remove"
            })
    
    results_df = pd.DataFrame(results)
    
    # Create unmatched website companies dataframe
    unmatched_df = pd.DataFrame([
        {"Company": r["Website Name"], "Sector": r["Website Sector"]} 
        for r in results 
        if r["Status"] == "Remove"
    ])
    
    return results_df, unmatched_df
