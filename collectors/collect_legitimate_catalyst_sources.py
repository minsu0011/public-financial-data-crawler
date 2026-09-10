from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from common_download import build_session, request_with_retry, write_json


def clean_terms(values: pd.Series) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values.dropna().astype(str):
        value = " ".join(value.strip().split())
        if len(value) < 3 or value.lower() in {"nan", "none"}:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            terms.append(value)
    return terms


def fetch_json(session, url: str, *, method: str = "GET", payload: dict | None = None, delay: float = 0.15) -> dict:
    if method == "POST":
        response = session.post(url, json=payload, timeout=180)
        response.raise_for_status()
    else:
        response = request_with_retry(session, url, delay=delay)
    time.sleep(delay)
    return response.json()


def collect_clinical_trials(session, terms: list[str], output: Path, delay: float, max_terms: int) -> list[dict]:
    audit: list[dict] = []
    rows: list[dict] = []
    for term in terms[:max_terms or None]:
        url = "https://clinicaltrials.gov/api/v2/studies?format=json&pageSize=100&query.term=" + quote(f'"{term}"')
        try:
            payload = fetch_json(session, url, delay=delay)
            for study in payload.get("studies", []):
                protocol = study.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                status = protocol.get("statusModule", {})
                sponsor = protocol.get("sponsorCollaboratorsModule", {})
                rows.append({
                    "queryTerm": term,
                    "nctId": ident.get("nctId", ""),
                    "organizationFullName": (ident.get("organization") or {}).get("fullName", ""),
                    "briefTitle": ident.get("briefTitle", ""),
                    "overallStatus": status.get("overallStatus", ""),
                    "studyFirstPostDate": (status.get("studyFirstPostDateStruct") or {}).get("date", ""),
                    "lastUpdatePostDate": (status.get("lastUpdatePostDateStruct") or {}).get("date", ""),
                    "leadSponsorName": (sponsor.get("leadSponsor") or {}).get("name", ""),
                })
            audit.append({"sourceId": "CLINICALTRIALS_GOV_API", "term": term, "url": url, "status": "PASS", "records": len(payload.get("studies", [])), "error": ""})
        except Exception as exc:
            audit.append({"sourceId": "CLINICALTRIALS_GOV_API", "term": term, "url": url, "status": "FAILED", "records": 0, "error": repr(exc)})
    pd.DataFrame(rows).drop_duplicates(["queryTerm", "nctId"]).to_csv(output / "clinical_trials_company_matches.csv.gz", index=False, compression="gzip")
    return audit


def collect_openfda(session, terms: list[str], output: Path, delay: float, max_terms: int) -> list[dict]:
    audit: list[dict] = []
    endpoints = {
        "OPENFDA_DRUGSFDA": ("https://api.fda.gov/drug/drugsfda.json", "sponsor_name"),
        "OPENFDA_DRUG_ENFORCEMENT": ("https://api.fda.gov/drug/enforcement.json", "recalling_firm"),
        "OPENFDA_DEVICE_510K": ("https://api.fda.gov/device/510k.json", "applicant"),
        "OPENFDA_DEVICE_PMA": ("https://api.fda.gov/device/pma.json", "applicant"),
    }
    for source_id, (endpoint, field) in endpoints.items():
        rows: list[dict] = []
        for term in terms[:max_terms or None]:
            url = f"{endpoint}?search={field}:\"{quote(term)}\"&limit=100"
            try:
                payload = fetch_json(session, url, delay=delay)
                for record in payload.get("results", []):
                    rows.append({"sourceId": source_id, "queryTerm": term, "recordJson": json.dumps(record, ensure_ascii=False, sort_keys=True)})
                audit.append({"sourceId": source_id, "term": term, "url": url, "status": "PASS", "records": len(payload.get("results", [])), "error": ""})
            except Exception as exc:
                # 404 means no match in openFDA; retain it as audited zero rather than a fatal error.
                status = "NO_MATCH_OR_FAILED"
                audit.append({"sourceId": source_id, "term": term, "url": url, "status": status, "records": 0, "error": repr(exc)})
        pd.DataFrame(rows).drop_duplicates(["sourceId", "queryTerm", "recordJson"]).to_csv(output / f"{source_id.lower()}_company_matches.csv.gz", index=False, compression="gzip")
    return audit


def collect_usaspending(session, terms: list[str], output: Path, delay: float, max_terms: int) -> list[dict]:
    audit: list[dict] = []
    rows: list[dict] = []
    endpoint = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    for term in terms[:max_terms or None]:
        payload = {
            "filters": {
                "time_period": [{"start_date": "2007-10-01", "end_date": "2026-09-30"}],
                "recipient_search_text": [term],
                "award_type_codes": ["A", "B", "C", "D", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"],
            },
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency", "Description"],
            "page": 1,
            "limit": 100,
            "subawards": False,
        }
        try:
            data = fetch_json(session, endpoint, method="POST", payload=payload, delay=delay)
            for record in data.get("results", []):
                rows.append({"queryTerm": term, "recordJson": json.dumps(record, ensure_ascii=False, sort_keys=True)})
            audit.append({"sourceId": "USASPENDING_AWARDS", "term": term, "url": endpoint, "status": "PASS", "records": len(data.get("results", [])), "error": ""})
        except Exception as exc:
            audit.append({"sourceId": "USASPENDING_AWARDS", "term": term, "url": endpoint, "status": "FAILED", "records": 0, "error": repr(exc)})
    pd.DataFrame(rows).drop_duplicates(["queryTerm", "recordJson"]).to_csv(output / "usaspending_company_matches.csv.gz", index=False, compression="gzip")
    return audit


def collect_federal_register(session, terms: list[str], output: Path, delay: float, max_terms: int) -> list[dict]:
    audit: list[dict] = []
    rows: list[dict] = []
    for term in terms[:max_terms or None]:
        url = "https://www.federalregister.gov/api/v1/documents.json?per_page=100&conditions%5Bterm%5D=" + quote(term)
        try:
            payload = fetch_json(session, url, delay=delay)
            for record in payload.get("results", []):
                rows.append({"queryTerm": term, "documentNumber": record.get("document_number", ""), "publicationDate": record.get("publication_date", ""), "title": record.get("title", ""), "type": record.get("type", ""), "htmlUrl": record.get("html_url", ""), "rawJson": json.dumps(record, ensure_ascii=False, sort_keys=True)})
            audit.append({"sourceId": "FEDERAL_REGISTER_API", "term": term, "url": url, "status": "PASS", "records": len(payload.get("results", [])), "error": ""})
        except Exception as exc:
            audit.append({"sourceId": "FEDERAL_REGISTER_API", "term": term, "url": url, "status": "FAILED", "records": 0, "error": repr(exc)})
    pd.DataFrame(rows).drop_duplicates(["queryTerm", "documentNumber"]).to_csv(output / "federal_register_company_matches.csv.gz", index=False, compression="gzip")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public legitimate-catalyst controls by issuer/company name.")
    parser.add_argument("--issuers", type=Path, required=True, help="Development-only issuer identity table.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--sources", nargs="+", choices=["clinicaltrials", "openfda", "usaspending", "federalregister"], default=["clinicaltrials", "openfda", "usaspending", "federalregister"])
    parser.add_argument("--max-terms", type=int, default=0, help="0 means all unique company names.")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()

    issuers = pd.read_csv(args.issuers, low_memory=False)
    name_columns = [column for column in ["mappedCompanyName", "companyName", "historicalCompanyName"] if column in issuers.columns]
    if not name_columns:
        raise ValueError("issuer table must include a company-name column")
    terms = clean_terms(pd.concat([issuers[column] for column in name_columns], ignore_index=True))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.user_agent)

    audit: list[dict] = []
    if "clinicaltrials" in args.sources:
        audit.extend(collect_clinical_trials(session, terms, args.output_dir, args.delay, args.max_terms))
    if "openfda" in args.sources:
        audit.extend(collect_openfda(session, terms, args.output_dir, args.delay, args.max_terms))
    if "usaspending" in args.sources:
        audit.extend(collect_usaspending(session, terms, args.output_dir, args.delay, args.max_terms))
    if "federalregister" in args.sources:
        audit.extend(collect_federal_register(session, terms, args.output_dir, args.delay, args.max_terms))

    audit_df = pd.DataFrame(audit)
    audit_df.to_csv(args.output_dir / "legitimate_catalyst_collection_audit.csv", index=False)
    summary = {
        "issuerSearchTerms": len(terms),
        "requests": len(audit_df),
        "pass": int((audit_df.get("status", pd.Series(dtype=str)) == "PASS").sum()),
        "failedOrNoMatch": int((audit_df.get("status", pd.Series(dtype=str)) != "PASS").sum()),
        "pointInTimePolicy": "Use only records whose first public/release/posting date is strictly before eventDate for pre-event features.",
    }
    write_json(args.output_dir / "collection_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
