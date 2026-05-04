"""End-to-end smoke test against a running Flask instance.

Uploads a baseline Excel, polls /status until complete, downloads the result,
and prints a schema/counts summary. Useful after refactors to confirm the full
pipeline (template detection → facet scrape → match → output) still works
against the live PIF site.

Usage:
    python3 webview/app.py &              # in one terminal
    python3 webview/smoke_test.py         # in another
    python3 webview/smoke_test.py --baseline path/to/other.xlsx
    python3 webview/smoke_test.py --base-url http://localhost:5001

Exits 0 on success, 1 on any failure.
"""

import argparse
import os
import sys
import time

import pandas as pd
import requests


DEFAULT_BASELINE = os.path.join(os.path.dirname(__file__), "uploads", "new-template.xlsx")
DEFAULT_BASE = "http://127.0.0.1:5000"
POLL_INTERVAL = 5
POLL_DEADLINE = 600  # 10 minutes


def upload(base: str, path: str) -> str:
    print(f"uploading {path}")
    with open(path, "rb") as fh:
        files = {"file": (os.path.basename(path), fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"browser_type": "firefox", "headless": "true", "debug": "true", "timeout": "120000"}
        r = requests.post(f"{base}/upload", files=files, data=data, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"upload failed: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["result_id"]


def wait_for_complete(base: str, result_id: str) -> None:
    deadline = time.time() + POLL_DEADLINE
    last_status = None
    while time.time() < deadline:
        r = requests.get(f"{base}/status/{result_id}", timeout=10)
        body = r.json()
        status = body.get("status")
        if status != last_status:
            msg = body.get("message", "")
            print(f"  status: {status}{(' — ' + msg) if msg else ''}")
            last_status = status
        if status == "complete":
            return
        if status == "error":
            raise SystemExit(f"server reported error: {body.get('message')}")
        time.sleep(POLL_INTERVAL)
    raise SystemExit(f"timed out after {POLL_DEADLINE}s waiting for {result_id}")


def download_and_inspect(base: str, result_id: str, expect_template: str) -> None:
    out = f"/tmp/smoke_{result_id}.xlsx"
    r = requests.get(f"{base}/download/{result_id}", timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"download failed: HTTP {r.status_code}")
    with open(out, "wb") as fh:
        fh.write(r.content)
    print(f"\ndownloaded -> {out}")

    sheets = pd.ExcelFile(out).sheet_names
    print(f"sheets: {sheets}")
    expected_sheets = {"Comparison Results", "Unmatched Website Companies", "Summary"}
    missing = expected_sheets - set(sheets)
    if missing:
        raise SystemExit(f"missing sheets: {missing}")

    results = pd.read_excel(out, sheet_name="Comparison Results")
    print(f"\ncomparison rows: {len(results)}")
    print(f"comparison columns: {list(results.columns)}")
    print(f"status counts: {results['Status'].value_counts().to_dict()}")

    if expect_template == "new":
        new_cols = {"Portfolio", "Website Portfolio", "Portfolio Match",
                    "Ecosystem", "Website Ecosystem", "Ecosystem Match"}
        missing_cols = new_cols - set(results.columns)
        if missing_cols:
            raise SystemExit(f"new-template result missing columns: {missing_cols}")
        for col in ("Portfolio Match", "Ecosystem Match"):
            counts = results[col].value_counts(dropna=False).to_dict()
            print(f"{col}: {counts}")
    elif expect_template == "legacy":
        forbidden = {"Portfolio Match", "Ecosystem Match"}
        present = forbidden & set(results.columns)
        if present:
            raise SystemExit(f"legacy result unexpectedly contains columns: {present}")

    statuses = set(results["Status"].dropna().unique())
    expected_statuses = {"OK", "Add", "Remove", "Requires update"}
    extra = statuses - expected_statuses
    if extra:
        raise SystemExit(f"unexpected status values: {extra}")

    unmatched = pd.read_excel(out, sheet_name="Unmatched Website Companies")
    for col in ("Company", "Portfolio", "Ecosystem"):
        if col not in unmatched.columns:
            raise SystemExit(f"unmatched sheet missing column: {col}")
    print(f"unmatched website rows: {len(unmatched)}")


def detect_expected_template(path: str) -> str:
    df = pd.read_excel(path, nrows=0)
    cols = set(c.strip() for c in df.columns)
    if {"Portfolio", "Ecosystem"}.issubset(cols):
        return "new"
    if "VRP Sector" in cols and "Portfolio" not in cols:
        return "legacy"
    raise SystemExit(f"baseline at {path} matches neither template (cols: {sorted(cols)})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--baseline", default=DEFAULT_BASELINE,
                    help=f"baseline xlsx path (default: {DEFAULT_BASELINE})")
    ap.add_argument("--base-url", default=DEFAULT_BASE,
                    help=f"Flask base URL (default: {DEFAULT_BASE})")
    args = ap.parse_args()

    if not os.path.exists(args.baseline):
        print(f"baseline not found: {args.baseline}", file=sys.stderr)
        return 1

    try:
        requests.get(f"{args.base_url}/", timeout=5)
    except requests.RequestException as e:
        print(f"Flask not reachable at {args.base_url}: {e}", file=sys.stderr)
        print("Start it with:  python3 webview/app.py", file=sys.stderr)
        return 1

    expect = detect_expected_template(args.baseline)
    print(f"expected template: {expect}\n")

    result_id = upload(args.base_url, args.baseline)
    print(f"result_id: {result_id}")
    wait_for_complete(args.base_url, result_id)
    download_and_inspect(args.base_url, result_id, expect)

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
