import re
from rapidfuzz import fuzz
import pandas as pd
from typing import Dict, Tuple, Optional
from config import FUZZY_MATCH_THRESHOLD, SECTOR_MATCH_THRESHOLD

class EnhancedCompanyMatcher:
    def __init__(self,
                 fuzzy_threshold: int = FUZZY_MATCH_THRESHOLD,
                 sector_threshold: int = SECTOR_MATCH_THRESHOLD,
                 exact_match_threshold: int = 95):

        self.fuzzy_threshold = fuzzy_threshold
        self.sector_threshold = sector_threshold
        self.exact_match_threshold = exact_match_threshold
        
        # Common business suffixes to normalize (order matters - most specific first)
        self.business_suffixes = [
            'holding company', 'holding co', 'holding corp', 'holding corporation',
            'investment company', 'investment co', 'trading company', 'trading co',
            'company limited', 'company ltd', 'co limited', 'co ltd',
            'corporation', 'corp', 'incorporated', 'inc',
            'limited', 'ltd', 'limited liability company', 'llc',
            'holding', 'company', 'co', 'group', 'plc', 'sa', 'bsc', 'ksc'
        ]

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

    def normalize_categorical(self, value: str) -> str:
        """Lowercase + strip; return '' for null/empty inputs."""
        if pd.isna(value) or not value:
            return ""
        return str(value).lower().strip()

    def compare_categorical(self, baseline_value: str, website_value: str) -> dict:
        """Compare categorical values with normalization and fuzzy matching."""
        norm_baseline = self.normalize_categorical(baseline_value)
        norm_website = self.normalize_categorical(website_value)

        if not norm_baseline or not norm_website:
            return {"match": False, "score": 0,
                    "normalized_baseline": norm_baseline,
                    "normalized_website": norm_website}

        if norm_baseline == norm_website:
            return {"match": True, "score": 100,
                    "normalized_baseline": norm_baseline,
                    "normalized_website": norm_website}

        score = fuzz.ratio(norm_baseline, norm_website)
        return {"match": score >= self.sector_threshold, "score": score,
                "normalized_baseline": norm_baseline,
                "normalized_website": norm_website}

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

def _compare_field(matcher, baseline_value, website_value, exists: bool) -> tuple:
    """Compare one categorical field. Returns (match_label, mismatch_flag).

    match_label is one of "Yes" / "No" / "N/A". mismatch_flag is True only
    when the field has both sides present and they don't match.
    """
    if not baseline_value or pd.isna(baseline_value):
        return "N/A", False
    if not exists:
        return "N/A", False
    cmp = matcher.compare_categorical(baseline_value, website_value)
    return ("Yes" if cmp['match'] else "No"), not cmp['match']


def _build_result_row(
    matcher: 'EnhancedCompanyMatcher',
    baseline_row: pd.Series,
    best_match,
    match_info: dict,
    spec: 'TemplateSpec',
) -> dict:
    """Build a single result row, including spec-conditional columns."""
    exists = match_info['score'] >= matcher.fuzzy_threshold and best_match is not None
    website_name = best_match['Company'] if exists else ""

    row = {
        "CR Name": baseline_row.get(spec.name_field, ''),
        "Brand Name": baseline_row.get(spec.brand_field, ''),
        "Website Name": website_name,
    }

    name_matches = exists and match_info['score'] >= matcher.exact_match_threshold
    field_mismatch = False

    if spec.portfolio_field is not None:
        baseline_portfolio = baseline_row.get(spec.portfolio_field, '')
        website_portfolio = best_match['Portfolio'] if exists else ''
        portfolio_match, mismatch = _compare_field(matcher, baseline_portfolio, website_portfolio, exists)
        if mismatch:
            field_mismatch = True
        row["Portfolio"] = baseline_portfolio
        row["Website Portfolio"] = website_portfolio
        row["Portfolio Match"] = portfolio_match

    if spec.ecosystem_field is not None:
        baseline_ecosystem = baseline_row.get(spec.ecosystem_field, '')
        website_ecosystem = (best_match['Ecosystem'] if exists else '') or ''
        ecosystem_match, mismatch = _compare_field(matcher, baseline_ecosystem, website_ecosystem, exists)
        if mismatch:
            field_mismatch = True
        row["Ecosystem"] = baseline_ecosystem
        row["Website Ecosystem"] = website_ecosystem
        row["Ecosystem Match"] = ecosystem_match

    row.update({
        "Match Score": round(match_info['score'], 1),
        "Match Type": match_info.get('match_type', 'none'),
        "Match Confidence": match_info.get('confidence', 'none'),
        "Matched Field": match_info.get('matched_field', 'N/A'),
        "PC exist in website": "Yes" if exists else "No",
    })

    if not exists:
        row["Status"] = "Add"
    elif not name_matches or field_mismatch:
        row["Status"] = "Requires update"
    else:
        row["Status"] = "OK"

    return row


def _build_remove_row(website_row: pd.Series, spec: 'TemplateSpec') -> dict:
    """Build a result row for an unmatched website company."""
    row = {
        "CR Name": "",
        "Brand Name": "",
        "Website Name": website_row['Company'],
    }
    if spec.portfolio_field is not None:
        row["Portfolio"] = ""
        row["Website Portfolio"] = website_row.get('Portfolio', '') or ''
        row["Portfolio Match"] = "N/A"
    if spec.ecosystem_field is not None:
        row["Ecosystem"] = ""
        row["Website Ecosystem"] = website_row.get('Ecosystem', '') or ''
        row["Ecosystem Match"] = "N/A"
    row.update({
        "Match Score": 0,
        "Match Type": "unmatched",
        "Match Confidence": "none",
        "Matched Field": "N/A",
        "PC exist in website": "Yes",
        "Status": "Remove",
    })
    return row


def enhanced_compare_companies(
    baseline_df: pd.DataFrame,
    website_df: pd.DataFrame,
    template_spec,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compare baseline against website using the supplied TemplateSpec."""
    matcher = EnhancedCompanyMatcher()
    if template_spec.portfolio_field is not None:
        assert 'Portfolio' in website_df.columns, (
            "TemplateSpec declares portfolio_field but website_df is missing 'Portfolio' column"
        )
    if template_spec.ecosystem_field is not None:
        assert 'Ecosystem' in website_df.columns, (
            "TemplateSpec declares ecosystem_field but website_df is missing 'Ecosystem' column"
        )
    results = []
    matched_website_companies = set()

    print(f"Comparing {len(baseline_df)} baseline companies against "
          f"{len(website_df)} website companies (template={template_spec.kind})...")

    for idx, baseline_row in baseline_df.iterrows():
        best_match, match_info = matcher.find_best_match(baseline_row, website_df)
        if best_match is not None and match_info['score'] >= matcher.fuzzy_threshold:
            matched_website_companies.add(best_match['Company'])
        results.append(_build_result_row(matcher, baseline_row, best_match, match_info, template_spec))

    for _, website_row in website_df.iterrows():
        if website_row['Company'] not in matched_website_companies:
            results.append(_build_remove_row(website_row, template_spec))

    results_df = pd.DataFrame(results)

    unmatched_rows = []
    for _, website_row in website_df.iterrows():
        if website_row['Company'] not in matched_website_companies:
            entry = {"Company": website_row['Company']}
            if 'Portfolio' in website_df.columns:
                entry["Portfolio"] = website_row.get('Portfolio', '')
            if 'Ecosystem' in website_df.columns:
                entry["Ecosystem"] = website_row.get('Ecosystem', '')
            unmatched_rows.append(entry)
    unmatched_df = pd.DataFrame(unmatched_rows)

    return results_df, unmatched_df
