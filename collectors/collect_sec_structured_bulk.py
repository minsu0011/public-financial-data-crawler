from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

from common_download import build_session, download_resumable, request_with_retry

SOURCES = {
    "SEC_FORM_345_ACTUAL": "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
    "SEC_MIDAS_SECURITY": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-security",
    "SEC_MIDAS_SECURITY_EXCHANGE": "https://www.sec.gov/data-research/sec-markets-data/market-structure-data-security-exchange",
    "SEC_FINANCIAL_STATEMENTS": "https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets",
    "SEC_FINANCIAL_NOTES": "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets",
    "SEC_FORM_13F": "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
    "SEC_FORM_D": "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets",
    "SEC_NPORT": "https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets",
    "SEC_REG_A": "https://www.sec.gov/data-research/sec-markets-data/regulation-data-sets",
    "SEC_CROWDFUNDING": "https://www.sec.gov/data-research/sec-markets-data/crowdfunding-offerings-data-sets",
    "SEC_QUOTE_HAZARDS": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-hazards-survivors",
    "SEC_CANCEL_TRADE": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-conditional-cancel",
}


def discover(session, source_id: str, url: str, delay: float) -> list[dict]:
    response = request_with_retry(session, url, delay=delay)
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if ".zip" not in href.lower():
            continue
        label = " ".join(a.get_text(" ", strip=True).split())
        filename = Path(urlparse(href).path).name
        period_match = re.search(r"(20\d{2})[\-_ ]?[qQ]([1-4])", label + " " + filename)
        rows.append({
            "sourceId": source_id,
            "landingPage": url,
            "label": label,
            "url": href,
            "filename": filename,
            "year": int(period_match.group(1)) if period_match else "",
            "quarter": int(period_match.group(2)) if period_match else "",
        })
    unique = {(r["sourceId"], r["url"]): r for r in rows}
    time.sleep(delay)
    return list(unique.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--user-agent", required=True, help='Example: "ProjectName contact@example.com"')
    ap.add_argument("--sources", nargs="+", default=list(SOURCES))
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--min-year", type=int, default=0)
    ap.add_argument("--max-year", type=int, default=9999)
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()
    unknown = set(args.sources) - set(SOURCES)
    if unknown:
        raise SystemExit(f"unknown sources: {sorted(unknown)}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.user_agent)
    rows = []
    for sid in args.sources:
        rows.extend(discover(session, sid, SOURCES[sid], args.delay))
    manifest = pd.DataFrame(rows).drop_duplicates(["sourceId", "url"]).sort_values(["sourceId", "year", "quarter", "filename"])
    if "year" in manifest:
        numeric = pd.to_numeric(manifest["year"], errors="coerce")
        keep = numeric.isna() | numeric.between(args.min_year, args.max_year)
        manifest = manifest[keep].copy()
    manifest["status"] = "DISCOVERED"
    manifest.to_csv(args.output_dir / "discovered_sec_bulk_links.csv", index=False)
    if args.discover_only:
        print(json.dumps({"discovered": len(manifest), "downloaded": 0}, indent=2))
        return
    selected = manifest.head(args.max_files) if args.max_files > 0 else manifest
    audit = []
    for row in selected.to_dict("records"):
        target = args.output_dir / "raw" / row["sourceId"] / row["filename"]
        try:
            result = download_resumable(session, row["url"], target, delay=args.delay)
            audit.append({**row, **result, "error": ""})
        except Exception as exc:
            audit.append({**row, "status": "FAILED", "localFile": str(target), "bytes": "", "sha256": "", "error": repr(exc)})
    pd.DataFrame(audit).to_csv(args.output_dir / "sec_bulk_download_audit.csv", index=False)
    failures = sum(r["status"] == "FAILED" for r in audit)
    print(json.dumps({"discovered": len(manifest), "attempted": len(audit), "failures": failures}, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
