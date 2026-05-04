import os
import pandas as pd
import json
from datetime import datetime
from typing import Dict, List, Optional
import sqlite3

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "comparison_history.db"
)


class HistoricalTracker:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Create tables if they don't exist (with current schema)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comparison_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                baseline_file TEXT NOT NULL,
                total_baseline_companies INTEGER,
                total_website_companies INTEGER,
                summary_stats TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS company_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                cr_name TEXT,
                brand_name TEXT,
                website_name TEXT,
                portfolio TEXT,
                website_portfolio TEXT,
                ecosystem TEXT,
                website_ecosystem TEXT,
                match_score REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES comparison_runs (id)
            )
        ''')

        conn.commit()
        conn.close()
    
    def save_comparison_run(self, results_df: pd.DataFrame, baseline_file: str,
                           website_count: int, summary: Dict) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO comparison_runs
            (run_date, baseline_file, total_baseline_companies, total_website_companies, summary_stats)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            baseline_file,
            len(results_df[results_df['CR Name'] != '']),
            website_count,
            json.dumps(summary),
        ))

        run_id = cursor.lastrowid

        for _, row in results_df.iterrows():
            cursor.execute('''
                INSERT INTO company_history
                (run_id, cr_name, brand_name, website_name,
                 portfolio, website_portfolio, ecosystem, website_ecosystem,
                 match_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                row.get('CR Name', ''),
                row.get('Brand Name', ''),
                row.get('Website Name', ''),
                row.get('Portfolio', None),
                row.get('Website Portfolio', None),
                row.get('Ecosystem', None),
                row.get('Website Ecosystem', None),
                row.get('Match Score', 0),
                row.get('Status', ''),
            ))

        conn.commit()
        conn.close()
        return run_id
    
    def get_historical_comparison(self, quarters_back: int = 1) -> Optional[pd.DataFrame]:
        """Get comparison data from previous quarters"""
        conn = sqlite3.connect(self.db_path)
        
        # Get the most recent run that's not the current one
        query = '''
            SELECT * FROM comparison_runs 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET 1
        '''
        
        runs = pd.read_sql_query(query, conn, params=(quarters_back,))
        
        if runs.empty:
            conn.close()
            return None
        
        # Get company data for the selected run
        run_id = runs.iloc[0]['id']
        company_query = '''
            SELECT * FROM company_history 
            WHERE run_id = ?
        '''
        
        historical_data = pd.read_sql_query(company_query, conn, params=(run_id,))
        conn.close()
        
        return historical_data

class ResultsSummarizer:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.tracker = HistoricalTracker(db_path=db_path)
    
    def generate_summary(self, results_df: pd.DataFrame, baseline_file: str,
                        website_count: int, template_spec) -> Dict:
        """Generate comprehensive summary of comparison results"""
        total_baseline = len(results_df[results_df['CR Name'] != ''])

        exists = results_df['PC exist in website'] == 'Yes'
        is_baseline = results_df['CR Name'] != ''

        breakdown = {
            "ok": int((results_df['Status'] == 'OK').sum()),
            "missing_from_website": int((results_df['Status'] == 'Add').sum()),
            "extra_on_website": int((results_df['Status'] == 'Remove').sum()),
            "name_mismatches": int((exists & is_baseline & (results_df['Match Score'] < 95)).sum()),
        }

        if template_spec.portfolio_field is not None and 'Portfolio Match' in results_df.columns:
            breakdown["portfolio_mismatches"] = int((results_df['Portfolio Match'] == 'No').sum())

        if template_spec.ecosystem_field is not None and 'Ecosystem Match' in results_df.columns:
            breakdown["ecosystem_mismatches"] = int((results_df['Ecosystem Match'] == 'No').sum())

        matched = int(exists.sum())
        accuracy_rate = round(matched / total_baseline * 100, 1) if total_baseline else 0.0

        return {
            'run_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'baseline_file': baseline_file,
            'template_kind': template_spec.kind,
            'totals': {
                'baseline_companies': total_baseline,
                'website_companies': website_count,
                'matched_companies': matched,
                'accuracy_rate': accuracy_rate,
            },
            'status_breakdown': breakdown,
        }
    
    def generate_historical_comparison(self, current_summary: Dict) -> Dict:
        """Compare current results with historical data"""
        historical_data = self.tracker.get_historical_comparison()

        if historical_data is None:
            return {'has_historical_data': False, 'message': 'No historical data available'}

        historical_status_counts = historical_data['status'].value_counts().to_dict()
        current_breakdown = current_summary['status_breakdown']

        # Map status_breakdown keys back to Status string values for historical comparison
        status_label_map = {
            'ok': 'OK', 'missing_from_website': 'Add', 'extra_on_website': 'Remove',
        }

        changes = {}
        for key, current_count in current_breakdown.items():
            historical_count = historical_status_counts.get(status_label_map.get(key, ''), 0)
            change = current_count - historical_count
            changes[key] = {
                'current': current_count,
                'previous': historical_count,
                'change': change,
                'trend': 'improved' if change < 0 and key != 'ok' else 'worsened' if change > 0 and key != 'ok' else 'same',
            }

        return {
            'has_historical_data': True,
            'changes': changes,
            'overall_trend': self._calculate_overall_trend(changes),
        }
    
    def _calculate_overall_trend(self, changes: Dict) -> str:
        """Calculate overall trend from changes"""
        issues_reduced = 0
        issues_increased = 0
        
        for status, change_data in changes.items():
            if status != 'ok':  # Don't count OK status as issues
                if change_data['change'] < 0:
                    issues_reduced += 1
                elif change_data['change'] > 0:
                    issues_increased += 1
        
        if issues_reduced > issues_increased:
            return 'improving'
        elif issues_increased > issues_reduced:
            return 'declining'
        else:
            return 'stable'
    
    def save_and_summarize(self, results_df: pd.DataFrame, baseline_file: str,
                          website_count: int, template_spec) -> Dict:
        """Generate summary and save to historical tracking"""
        summary = self.generate_summary(results_df, baseline_file, website_count, template_spec)
        historical_comparison = self.generate_historical_comparison(summary)
        run_id = self.tracker.save_comparison_run(results_df, baseline_file, website_count, summary)

        return {
            'run_id': run_id,
            'current_analysis': summary,
            'historical_comparison': historical_comparison,
            'recommendations': self._generate_recommendations(summary, historical_comparison, template_spec),
        }
    
    def _generate_recommendations(self, summary: Dict, historical: Dict, template_spec) -> List[str]:
        """Generate actionable recommendations based on results"""
        recommendations = []
        breakdown = summary['status_breakdown']

        if breakdown.get('missing_from_website', 0) > 10:
            recommendations.append(
                f"HIGH PRIORITY: {breakdown['missing_from_website']} companies are missing from the website."
            )

        if breakdown.get('extra_on_website', 0) > 5:
            recommendations.append(
                f"REVIEW NEEDED: {breakdown['extra_on_website']} companies appear on the website but not in your baseline."
            )

        if breakdown.get('name_mismatches', 0) > 0:
            recommendations.append(
                f"Name standardization needed for {breakdown['name_mismatches']} companies."
            )

        if template_spec.portfolio_field and breakdown.get('portfolio_mismatches', 0) > 0:
            recommendations.append(
                f"Portfolio assignment differs for {breakdown['portfolio_mismatches']} companies."
            )

        if template_spec.ecosystem_field and breakdown.get('ecosystem_mismatches', 0) > 0:
            recommendations.append(
                f"Ecosystem assignment differs for {breakdown['ecosystem_mismatches']} companies."
            )

        accuracy = summary['totals']['accuracy_rate']
        if accuracy < 95:
            recommendations.append(
                f"Current accuracy is {accuracy}%. Review companies with low match scores."
            )

        if historical.get('has_historical_data'):
            if historical.get('overall_trend') == 'declining':
                recommendations.append("Data quality is declining vs. previous run.")
            elif historical.get('overall_trend') == 'improving':
                recommendations.append("Data quality is improving vs. previous run.")

        return recommendations
