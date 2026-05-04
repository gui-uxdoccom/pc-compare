import os
import sys
import asyncio
import threading
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from datetime import datetime

# Ensure webview/ directory is on path so imports work regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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

    # Get scraping options from request
    browser_type = request.form.get('browser_type', 'firefox')  # Firefox has better Cloudflare bypass
    headless_mode = request.form.get('headless', 'true').lower() == 'true'
    debug_mode = request.form.get('debug', 'true').lower() == 'true'
    timeout = int(request.form.get('timeout', '90000'))  # 90 seconds default

    result_id = datetime.now().strftime("%Y%m%d%H%M%S")
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'results_{result_id}.xlsx')

    # Mark as processing immediately so /status/<result_id> responds correctly
    processing_results[result_id] = {'status': 'processing'}

    # Run scraping in a background thread so this endpoint returns immediately
    # Clients should poll /status/<result_id> to check progress
    def run_in_thread():
        asyncio.run(process_file(filepath, output_path, result_id, browser_type, headless_mode, debug_mode, timeout))

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    return jsonify({
        'message': 'Upload successful, processing started',
        'result_id': result_id
    })


async def process_file(filepath, output_path, result_id, browser_type='firefox', headless=True, debug=True, timeout=90000):
    try:
        print(f"Starting processing for result_id: {result_id}")
        print(f"Scraping options: browser={browser_type}, headless={headless}, debug={debug}, timeout={timeout}ms")

        baseline_df = pd.read_excel(filepath)
        print(f"Loaded {len(baseline_df)} companies from baseline file")

        print("Starting website scraping...")
        try:
            website_df = await scrape_website(
                headless=headless,
                browser_type=browser_type,
                debug_mode=debug,
                timeout=timeout
            )
            if website_df is None:
                processing_results[result_id] = {
                    'status': 'error',
                    'message': 'Failed to scrape website. Check server logs. Try Firefox browser or visible mode.'
                }
                print("ERROR: Website scraping returned None")
                return
        except Exception as e:
            error_msg = f'Failed to scrape website: {str(e)}'
            if 'ERR_NAME_NOT_RESOLVED' in str(e) or 'Cloudflare' in str(e) or '403' in str(e):
                error_msg += '\n\nSuggestions:\n- Try Firefox browser (better Cloudflare bypass)\n- Enable visible mode to solve CAPTCHA manually\n- Check your internet connection'
            processing_results[result_id] = {'status': 'error', 'message': error_msg}
            print(f"ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return

        print(f"Scraped {len(website_df)} companies from website")

        print("Starting enhanced comparison...")
        results_df, unmatched_df = enhanced_compare_companies(baseline_df, website_df)

        print("Generating summary and historical analysis...")
        summary = summarizer.save_and_summarize(
            results_df,
            os.path.basename(filepath),
            len(website_df)
        )

        print("Saving results to Excel...")
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            results_df.to_excel(writer, sheet_name='Comparison Results', index=False)
            unmatched_df.to_excel(writer, sheet_name='Unmatched Website Companies', index=False)

            summary_df = pd.DataFrame([{
                'Metric': k.replace('_', ' ').title(),
                'Value': v
            } for k, v in summary['current_analysis']['totals'].items()])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

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
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug)
