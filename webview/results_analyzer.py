import pandas as pd
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import sqlite3

class HistoricalTracker:
    def __init__(self, db_path: str = "comparison_history.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for historical tracking"""
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
                vrp_sector TEXT,
                website_sector TEXT,
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
        """Save a comparison run to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert comparison run
        cursor.execute('''
            INSERT INTO comparison_runs 
            (run_date, baseline_file, total_baseline_companies, total_website_companies, summary_stats)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            baseline_file,
            len(results_df[results_df['CR Name'] != '']),  # Count baseline companies
            website_count,
            json.dumps(summary)
        ))
        
        run_id = cursor.lastrowid
        
        # Insert individual company results
        for _, row in results_df.iterrows():
            cursor.execute('''
                INSERT INTO company_history 
                (run_id, cr_name, brand_name, website_name, vrp_sector, website_sector, match_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id,
                row.get('CR Name', ''),
                row.get('Brand Name', ''),
                row.get('Website Name', ''),
                row.get('VRP Sector', ''),
                row.get('Website Sector', ''),
                row.get('Match Score', 0),
                row.get('Status', '')
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
    def __init__(self):
        self.tracker = HistoricalTracker()
    
    def generate_summary(self, results_df: pd.DataFrame, baseline_file: str, 
                        website_count: int) -> Dict:
        """Generate comprehensive summary of comparison results"""
        
        # Basic counts
        total_baseline = len(results_df[results_df['CR Name'] != ''])
        
        status_counts = results_df['Status'].value_counts().to_dict()
        
        # Detailed analysis
        missing_companies = results_df[results_df['Status'] == 'Add']
        extra_companies = results_df[results_df['Status'] == 'Remove']
        name_updates_needed = results_df[results_df['Status'] == 'Requires name update']
        sector_updates_needed = results_df[results_df['Status'] == 'Requires sector update']
        perfect_matches = results_df[results_df['Status'] == 'OK']
        
        # Calculate accuracy metrics
        total_matches = len(results_df[results_df['PC exist in website'] == 'Yes'])
        accuracy_rate = (total_matches / total_baseline * 100) if total_baseline > 0 else 0
        
        # Match confidence analysis
        confidence_breakdown = results_df['Match Confidence'].value_counts().to_dict()
        
        summary = {
            'run_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'baseline_file': baseline_file,
            'totals': {
                'baseline_companies': total_baseline,
                'website_companies': website_count,
                'matched_companies': total_matches,
                'accuracy_rate': round(accuracy_rate, 1)
            },
            'status_breakdown': {
                'ok': status_counts.get('OK', 0),
                'missing_from_website': status_counts.get('Add', 0),
                'extra_on_website': status_counts.get('Remove', 0),
                'name_updates_needed': status_counts.get('Requires name update', 0),
                'sector_updates_needed': status_counts.get('Requires sector update', 0)
            },
            'confidence_breakdown': confidence_breakdown,
            'detailed_analysis': {
                'perfect_matches': {
                    'count': len(perfect_matches),
                    'percentage': round(len(perfect_matches) / total_baseline * 100, 1) if total_baseline > 0 else 0
                },
                'missing_companies': {
                    'count': len(missing_companies),
                    'companies': missing_companies[['CR Name', 'Brand Name', 'VRP Sector']].to_dict('records')[:10]  # Top 10
                },
                'extra_companies': {
                    'count': len(extra_companies),
                    'companies': extra_companies[['Website Name', 'Website Sector']].to_dict('records')[:10]  # Top 10
                },
                'name_updates_needed': {
                    'count': len(name_updates_needed),
                    'companies': name_updates_needed[['CR Name', 'Website Name', 'Match Score']].to_dict('records')[:10]
                },
                'sector_updates_needed': {
                    'count': len(sector_updates_needed),
                    'companies': sector_updates_needed[['CR Name', 'VRP Sector', 'Website Sector']].to_dict('records')[:10]
                }
            }
        }
        
        return summary
    
    def generate_historical_comparison(self, current_summary: Dict) -> Dict:
        """Compare current results with historical data"""
        
        historical_data = self.tracker.get_historical_comparison()
        
        if historical_data is None:
            return {
                'has_historical_data': False,
                'message': 'No historical data available for comparison'
            }
        
        # Analyze changes
        historical_status_counts = historical_data['status'].value_counts().to_dict()
        current_status_counts = current_summary['status_breakdown']
        
        changes = {}
        for status in ['ok', 'missing_from_website', 'extra_on_website', 'name_updates_needed', 'sector_updates_needed']:
            current_count = current_status_counts.get(status, 0)
            historical_count = historical_status_counts.get(status.replace('_', ' ').title(), 0)
            change = current_count - historical_count
            
            changes[status] = {
                'current': current_count,
                'previous': historical_count,
                'change': change,
                'trend': 'improved' if change < 0 and status != 'ok' else 'worsened' if change > 0 and status != 'ok' else 'same'
            }
        
        return {
            'has_historical_data': True,
            'changes': changes,
            'overall_trend': self._calculate_overall_trend(changes)
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
                          website_count: int) -> Dict:
        """Generate summary and save to historical tracking"""
        
        summary = self.generate_summary(results_df, baseline_file, website_count)
        historical_comparison = self.generate_historical_comparison(summary)
        
        # Save to database
        run_id = self.tracker.save_comparison_run(results_df, baseline_file, website_count, summary)
        
        # Combine summaries
        complete_summary = {
            'run_id': run_id,
            'current_analysis': summary,
            'historical_comparison': historical_comparison,
            'recommendations': self._generate_recommendations(summary, historical_comparison)
        }
        
        return complete_summary
    
    def _generate_recommendations(self, summary: Dict, historical: Dict) -> List[str]:
        """Generate actionable recommendations based on results"""
        recommendations = []
        
        status_breakdown = summary['status_breakdown']
        
        # High priority recommendations
        if status_breakdown['missing_from_website'] > 10:
            recommendations.append(f"HIGH PRIORITY: {status_breakdown['missing_from_website']} companies are missing from the website and need to be added.")
        
        if status_breakdown['extra_on_website'] > 5:
            recommendations.append(f"REVIEW NEEDED: {status_breakdown['extra_on_website']} companies appear on the website but not in your baseline. Verify if they should be removed or added to baseline.")
        
        # Medium priority recommendations
        if status_breakdown['name_updates_needed'] > 0:
            recommendations.append(f"Name standardization needed for {status_breakdown['name_updates_needed']} companies to improve matching accuracy.")
        
        if status_breakdown['sector_updates_needed'] > 0:
            recommendations.append(f"Sector alignment needed for {status_breakdown['sector_updates_needed']} companies.")
        
        # Accuracy-based recommendations
        accuracy = summary['totals']['accuracy_rate']
        if accuracy < 95:
            recommendations.append(f"Current accuracy is {accuracy}%. Review companies with low match scores to improve data quality.")
        
        # Historical trend recommendations
        if historical['has_historical_data']:
            overall_trend = historical['overall_trend']
            if overall_trend == 'declining':
                recommendations.append("Data quality appears to be declining compared to previous quarter. Consider implementing stricter data validation processes.")
            elif overall_trend == 'improving':
                recommendations.append("Good progress! Data quality is improving compared to previous quarter.")
        
        return recommendations
