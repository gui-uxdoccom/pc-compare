# 🧮 PC Compare Tool

## 📝 Overview

**PC Compare** is a powerful data comparison tool that matches company records from an Excel baseline file against a web-based directory. It uses web scraping and fuzzy matching algorithms to identify matches, discrepancies, and suggest corrective actions.

---

## 🚀 Key Features

- **🔎 Web Scraping**  
  Automatically extracts company names and sectors from a target website.

- **🤖 Intelligent Matching**  
  Uses fuzzy logic to match similar company names, including acronyms and partial matches.

- **⚙️ Action-Oriented Results**  
  Categorizes companies into:
  - `OK`
  - `Add`
  - `Remove`
  - `Requires name update`
  - `Requires sector update`

- **🌐 Web Interface**  
  Browser-based UI for uploading Excel files and downloading results.

- **💻 Command Line Interface**  
  Enables batch processing and automation.

---

## 🧑‍💻 Installation

### 📦 Prerequisites

- Python 3.8 or higher  
- pip (Python package installer)

### 🔧 Setup Steps

1a. **Clone the repository  // Later implementation** 
   ```bash
   git clone https://github.com/yourusername/pc-compare.git
   cd pc-compare
   ```

1. **Unzip File**
   ```bash
   Unzip the webview file. Open the terminal under the file name
   Example: $/your-folder/webview
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
4. **Install Playwright browsers (in case of issues)**
   ```bash
   playwright install
   ```

---

## ⚙️ Configuration

All you need is under `config.py` file in the root directory.
Add and adjust the following content as needed:

```python
# Example config.py
WEBSITE_URL = "https://www.pif.gov.sa/en/our-investments/our-portfolio/"
FUZZY_MATCH_THRESHOLD = 85  # Minimum score for fuzzy matching
SECTOR_MATCH_THRESHOLD = 80  # Minimum score for sector matching

```

---

## 🧪 Usage

### Web Interface

1. Start the Flask server:
   ```bash
   python app.py
   ```
2. Open your browser and go to: `http://127.0.0.1:5000`  
3. Upload your Excel file  
4. Wait for processing  
5. Download the result file

---

## 📊 Understanding the Results

The output Excel file contains two sheets:

1. **Comparison Results**
   - `OK`: Company exists in both with good match
   - `Requires name update`: Names differ significantly
   - `Requires sector update`: Sector mismatch
   - `Add`: Exists in baseline but not on website
   - `Remove`: Exists on website but not in baseline

2. **Unmatched Website Companies**
   - Companies found online but not matched to any baseline record

3. You will find the output Excel under the folder /uploads
---

## 🛠️ Troubleshooting

- **Web scraping issues**  
  Run browser visibly for debugging:
  ```bash
  playwright codegen https://example.com
  ```

- **Import Errors**  
  Make sure your current directory and file paths are correct

- **Excel Format**  
  Required columns:
  - `CR Name`
  - `Brand Name`
  - `VRP Sector`

---

## 📄 License

This project is licensed under the MIT License.  
See the [LICENSE](LICENSE) file for more details.