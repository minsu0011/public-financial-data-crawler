from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

from common_download import build_session, download_resumable, request_with_retry

DEFAULT_FORMS = [
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
    "S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
    "EFFECT", "POS AM", "RW", "AW",
    "8-K", "8-K/A", "6-K", "6-K/A",
    "3", "3/A", "4", "4/A", "5", "5/A", "144", "144/A",
    "DEF 14A", "DEFA14A", "PRE 14A", "SC TO-T", "SC TO-I", "SC 14D9",
]


def normalize_cik(value: object) -> str:
    text = str(value).strip().replace(".0", "")
    if not text or text.lower() == "nan":
        return ""
    return text.zfill(10)


def flatten_recent(payload: dict, cik: str) -> pd.DataFrame:
    recent = payload.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict) or not recent:
        return pd.DataFrame()
    lengths = [len(value) for value in recent.values() if isinstance(value, list)]
    if not lengths:
        return pd.DataFrame()
    n = min(lengths)
    frame = pd.DataFrame({key: value[:n] for key, value in recent.items() if isinstance(value, list)})
    frame["cik10"] = cik
    frame["companyNameFromSubmissions"] = payload.get("name", "")
    return frame


def load_historical_files(session, payload: dict, cik: str, delay: float) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for row in payload.get("filings", {}).get("files", []) or []:
        name = row.get("name")
        if not name:
            continue
        url = f"https://data.sec.gov/submissions/{name}"
        response = request_with_retry(session, url, delay=delay)
        history = response.json()
        frame = pd.DataFrame(history)
        if not frame.empty:
            frame["cik10"] = cik
            frame["companyNameFromSubmissions"] = payload.get("name", "")
            frames.append(frame)
        time.sleep(delay)
    return frames


def build_document_url(cik10: str, accession: str, primary_document: str) -> str:
    cik_int = str(int(cik10))
    accession_compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_compact}/{primary_document}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect event-CIK SEC filing metadata and selected primary documents with strict PIT filtering.")
    parser.add_argument("--events", type=Path, required=True, help="Development-only event/CIK registry.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--forms", nargs="+", default=DEFAULT_FORMS)
    parser.add_argument("--lookback-days", type=int, default=756)
    parser.add_argument("--include-history", action="store_true")
    parser.add_argument("--download-documents", action="store_true")
    parser.add_argument("--max-ciks", type=int, default=0)
    parser.add_argument("--max-documents", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.12)
    args = parser.parse_args()

    events = pd.read_csv(args.events, low_memory=False)
    required = {"eventId", "eventDate"}
    if not required.issubset(events.columns):
        raise ValueError(f"events must contain {sorted(required)}")
    cik_column = "cik10" if "cik10" in events.columns else "mappedCikText"
    if cik_column not in events.columns:
        raise ValueError("events must contain cik10 or mappedCikText")

    events = events.copy()
    events["eventDate"] = pd.to_datetime(events["eventDate"], errors="coerce")
    events["cik10"] = events[cik_column].map(normalize_cik)
    events = events[events["eventDate"].notna() & events["cik10"].ne("")].copy()
    ciks = sorted(events["cik10"].unique())
    if args.max_ciks > 0:
        ciks = ciks[: args.max_ciks]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.user_agent)
    filing_frames: list[pd.DataFrame] = []
    submission_audit: list[dict] = []

    for cik in ciks:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            response = request_with_retry(session, url, delay=args.delay)
            payload = response.json()
            frames = [flatten_recent(payload, cik)]
            if args.include_history:
                frames.extend(load_historical_files(session, payload, cik, args.delay))
            frames = [frame for frame in frames if not frame.empty]
            if frames:
                filing_frames.append(pd.concat(frames, ignore_index=True, sort=False))
            submission_audit.append({"cik10": cik, "url": url, "status": "PASS", "error": ""})
        except Exception as exc:
            submission_audit.append({"cik10": cik, "url": url, "status": "FAILED", "error": repr(exc)})
        time.sleep(args.delay)

    pd.DataFrame(submission_audit).to_csv(args.output_dir / "sec_submission_fetch_audit.csv", index=False)
    if not filing_frames:
        raise RuntimeError("No SEC submission data were retrieved; inspect sec_submission_fetch_audit.csv")

    filings = pd.concat(filing_frames, ignore_index=True, sort=False)
    filings["filingDate"] = pd.to_datetime(filings.get("filingDate"), errors="coerce")
    filings["acceptanceDateTime"] = pd.to_datetime(filings.get("acceptanceDateTime"), errors="coerce", utc=True)
    filings["form"] = filings.get("form", "").astype(str)
    filings = filings[filings["form"].isin(set(args.forms))].copy()
    filings = filings.drop_duplicates([column for column in ["cik10", "accessionNumber", "form", "filingDate"] if column in filings.columns])

    joined = events.merge(filings, on="cik10", how="inner", suffixes=("", "_filing"))
    joined["lookbackStart"] = joined["eventDate"] - pd.to_timedelta(args.lookback_days, unit="D")
    # Strict pre-event rule. Filing date is used because all rows must be public before eventDate;
    # acceptance timestamps are retained for finer session policy downstream.
    joined = joined[(joined["filingDate"] < joined["eventDate"]) & (joined["filingDate"] >= joined["lookbackStart"])].copy()
    joined["daysBeforeEvent"] = (joined["eventDate"] - joined["filingDate"]).dt.days
    joined["pitEligiblePreEvent"] = 1
    if {"accessionNumber", "primaryDocument"}.issubset(joined.columns):
        joined["primaryDocumentUrl"] = joined.apply(
            lambda row: build_document_url(row["cik10"], str(row["accessionNumber"]), str(row["primaryDocument"]))
            if pd.notna(row["primaryDocument"]) and str(row["primaryDocument"]).strip() else "",
            axis=1,
        )
    else:
        joined["primaryDocumentUrl"] = ""

    joined = joined.sort_values(["eventDate", "eventId", "filingDate", "form"])
    joined.to_csv(args.output_dir / "event_sec_filing_manifest_pre_event.csv.gz", index=False, compression="gzip")

    form_counts = joined.groupby(["eventId", "form"], as_index=False).size().rename(columns={"size": "filingCount"})
    form_counts.to_csv(args.output_dir / "event_sec_form_counts_pre_event.csv.gz", index=False, compression="gzip")

    document_audit: list[dict] = []
    if args.download_documents:
        documents = joined[joined["primaryDocumentUrl"].ne("")].drop_duplicates("primaryDocumentUrl")
        if args.max_documents > 0:
            documents = documents.head(args.max_documents)
        for row in documents.to_dict("records"):
            accession = str(row.get("accessionNumber", "unknown"))
            filename = Path(str(row.get("primaryDocument", "document.html"))).name
            target = args.output_dir / "raw_documents" / row["cik10"] / accession / filename
            try:
                result = download_resumable(session, row["primaryDocumentUrl"], target, delay=args.delay)
                document_audit.append({"cik10": row["cik10"], "accessionNumber": accession, "form": row.get("form", ""), **result, "error": ""})
            except Exception as exc:
                document_audit.append({"cik10": row["cik10"], "accessionNumber": accession, "form": row.get("form", ""), "url": row["primaryDocumentUrl"], "localFile": str(target), "status": "FAILED", "bytes": "", "sha256": "", "error": repr(exc)})
        pd.DataFrame(document_audit).to_csv(args.output_dir / "sec_primary_document_download_audit.csv", index=False)

    result = {
        "eventsWithCik": int(events["eventId"].nunique()),
        "ciksAttempted": len(ciks),
        "filingRowsPreEvent": len(joined),
        "eventsWithSelectedFilings": int(joined["eventId"].nunique()),
        "documentsAttempted": len(document_audit),
        "submissionFailures": sum(row["status"] == "FAILED" for row in submission_audit),
    }
    (args.output_dir / "collection_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
