import os
import sys
import asyncio
import pandas as pd
import json
from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
import tempfile

# Add the parent directory to the path so we can import compare.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from compare import scrape_website
from enhanced_matching import enhanced_compare_companies
from results_analyzer import ResultsSummarizer

# Create Flask app with custom template folder
app = Flask(__name__, 
            template_folder=os.path.dirname(os.path.abspath(__file__)))

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global storage for processing results and summaries
processing_results = {}
summarizer = ResultsSummarizer()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'error': 'File must be an Excel (.xlsx) file'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Start the processing task
    result_id = datetime.now().strftime("%Y%m%d%H%M%S")
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'results_{result_id}.xlsx')
    
    # In a production app, this would be better handled with a task queue
    asyncio.run(process_file(filepath, output_path, result_id))
    
    return jsonify({
        'message': 'Upload successful',
        'result_id': result_id
    })

async def process_file(filepath, output_path, result_id):
    try:
        print(f"Starting processing for result_id: {result_id}")
        
        # Read the baseline data
        baseline_df = pd.read_excel(filepath)
        print(f"Loaded {len(baseline_df)} companies from baseline file")
        
        # Scrape website data
        print("Starting website scraping...")
        website_df = await scrape_website()
        if website_df is None:
            processing_results[result_id] = {'status': 'error', 'message': 'Failed to scrape website'}
            return
        
        print(f"Scraped {len(website_df)} companies from website")
        
        # Compare data using enhanced matching
        print("Starting enhanced comparison...")
        results_df, unmatched_df = enhanced_compare_companies(baseline_df, website_df)
        
        # Generate comprehensive summary
        print("Generating summary and historical analysis...")
        summary = summarizer.save_and_summarize(
            results_df, 
            os.path.basename(filepath), 
            len(website_df)
        )
        
        # Save results to Excel
        print("Saving results to Excel...")
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            results_df.to_excel(writer, sheet_name='Comparison Results', index=False)
            unmatched_df.to_excel(writer, sheet_name='Unmatched Website Companies', index=False)
            
            # Add summary sheet
            summary_df = pd.DataFrame([{
                'Metric': k.replace('_', ' ').title(),
                'Value': v
            } for k, v in summary['current_analysis']['totals'].items()])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Store results
        processing_results[result_id] = {
            'status': 'complete', 
            'output_path': output_path,
            'summary': summary
        }
        
        print(f"Processing completed successfully for result_id: {result_id}")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        processing_results[result_id] = {'status': 'error', 'message': str(e)}

@app.route('/status/<result_id>')
def get_status(result_id):
    if result_id in processing_results:
        result = processing_results[result_id]
        return jsonify({
            'status': result['status'],
            'result_id': result_id,
            'message': result.get('message', '')
        })
    else:
        # Still processing
        return jsonify({'status': 'processing'})

@app.route('/summary/<result_id>')
def get_summary(result_id):
    if result_id in processing_results and processing_results[result_id]['status'] == 'complete':
        summary = processing_results[result_id].get('summary', {})
        return jsonify({'summary': summary})
    else:
        return jsonify({'error': 'Summary not available'}), 404

@app.route('/download/<result_id>')
def download_file(result_id):
    if result_id in processing_results and processing_results[result_id]['status'] == 'complete':
        output_path = processing_results[result_id]['output_path']
        if os.path.exists(output_path):
            return send_file(output_path, as_attachment=True)
    
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)
