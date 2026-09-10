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

# Official landing pages whose linked ZIP/CSV/XML/XLSX/JSON assets can be
# discovered without hard-coding versioned filenames.
SOURCES: dict[str, dict[str, object]] = {
    "SEC_TRANSFER_AGENT": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/transfer-agent-data-sets",
        "extensions": {".zip"},
    },
    "SEC_FORM_ADV": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers",
        "extensions": {".zip", ".xlsx", ".csv"},
    },
    "SEC_BDC_DATA": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/bdc-data-sets",
        "extensions": {".zip"},
    },
    "SEC_BDC_REPORT": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/opendatasetsshtmlbdc",
        "extensions": {".csv", ".xml"},
    },
    "SEC_NCEN": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/form-n-cen-data-sets",
        "extensions": {".zip"},
    },
    "SEC_NMFP": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/dera-form-n-mfp-data-sets",
        "extensions": {".zip"},
    },
    "SEC_FUND_SERIES_CLASS": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/investment-company-series-class-information",
        "extensions": {".csv", ".xml"},
    },
    "SEC_CLOSED_END_FUND": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/closed-end-fund-information",
        "extensions": {".csv", ".xml"},
    },
    "SEC_MMF_INFO": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/money-market-fund-information",
        "extensions": {".csv", ".xml"},
    },
    "SEC_MIDAS_SUMMARY_EXCHANGE": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-exchange",
        "extensions": {".zip"},
    },
    "SEC_MIDAS_DECILE_QUARTILE": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-decile-quartile",
        "extensions": {".zip"},
    },
    "SEC_MIDAS_SPREAD_DEPTH_2013": {
        "url": "https://www.sec.gov/data-research/sec-markets-data/marketstructuredata-spreads-depth",
        "extensions": {".zip"},
    },
    "FDA_PURPLE_BOOK": {
        "url": "https://purplebooksearch.fda.gov/downloads",
        "extensions": {".csv", ".xlsx"},
    },
}

PERIOD_PATTERNS = [
    re.compile(r"(?P<year>20\d{2})\s*[-_ ]?[qQ](?P<quarter>[1-4])"),
    re.compile(r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<year>20\d{2})", re.I),
    re.compile(r"(?P<year>20\d{2})"),
]
MONTHS = {name.lower(): i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1
)}


def infer_period(text: str) -> tuple[object, object, object]:
    for pattern in PERIOD_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        gd = match.groupdict()
        year = int(gd["year"]) if gd.get("year") else ""
        quarter = int(gd["quarter"]) if gd.get("quarter") else ""
        month = MONTHS.get(gd.get("month", "").lower(), "") if gd.get("month") else ""
        return year, quarter, month
    return "", "", ""


def discover(session, source_id: str, config: dict[str, object], delay: float) -> list[dict]:
    landing = str(config["url"])
    allowed = set(config["extensions"])
    response = request_with_retry(session, landing, delay=delay)
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(landing, anchor["href"])
        suffix = Path(urlparse(href).path).suffix.lower()
        if suffix not in allowed:
            continue
        label = " ".join(anchor.get_text(" ", strip=True).split())
        filename = Path(urlparse(href).path).name or f"{source_id}_{len(rows):05d}{suffix}"
        year, quarter, month = infer_period(f"{label} {filename}")
        rows.append({
            "sourceId": source_id,
            "landingPage": landing,
            "label": label,
            "url": href,
            "filename": filename,
            "extension": suffix,
            "year": year,
            "quarter": quarter,
            "month": month,
        })
    unique = {(row["sourceId"], row["url"]): row for row in rows}
    time.sleep(delay)
    return list(unique.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and optionally download official linked data assets.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--user-agent", required=True, help='SEC-compliant value such as "Project contact@example.com"')
    parser.add_argument("--sources", nargs="+", default=list(SOURCES))
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--min-year", type=int, default=0)
    parser.add_argument("--max-year", type=int, default=9999)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()

    unknown = set(args.sources) - set(SOURCES)
    if unknown:
        raise SystemExit(f"unknown sources: {sorted(unknown)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.user_agent)
    rows: list[dict] = []
    for source_id in args.sources:
        rows.extend(discover(session, source_id, SOURCES[source_id], args.delay))

    columns = ["sourceId", "landingPage", "label", "url", "filename", "extension", "year", "quarter", "month"]
    manifest = pd.DataFrame(rows, columns=columns)
    if not manifest.empty:
        manifest = manifest.drop_duplicates(["sourceId", "url"])
        numeric_year = pd.to_numeric(manifest["year"], errors="coerce")
        manifest = manifest[numeric_year.isna() | numeric_year.between(args.min_year, args.max_year)].copy()
        manifest = manifest.sort_values(["sourceId", "year", "quarter", "month", "filename"], na_position="last")
    manifest["status"] = "DISCOVERED"
    manifest.to_csv(args.output_dir / "official_linked_asset_manifest.csv", index=False)

    if args.discover_only:
        print(json.dumps({"discovered": len(manifest), "downloaded": 0}, indent=2))
        return

    selected = manifest.head(args.max_files) if args.max_files > 0 else manifest
    audit: list[dict] = []
    for row in selected.to_dict("records"):
        target = args.output_dir / "raw" / row["sourceId"] / row["filename"]
        try:
            result = download_resumable(session, row["url"], target, delay=args.delay)
            audit.append({**row, **result, "error": ""})
        except Exception as exc:  # retain a complete audit rather than silently skipping
            audit.append({**row, "status": "FAILED", "localFile": str(target), "bytes": "", "sha256": "", "error": repr(exc)})
    pd.DataFrame(audit).to_csv(args.output_dir / "official_linked_asset_download_audit.csv", index=False)
    failures = sum(row.get("status") == "FAILED" for row in audit)
    print(json.dumps({"discovered": len(manifest), "attempted": len(audit), "failures": failures}, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
