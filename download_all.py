from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
C = ROOT / "collectors"
M = ROOT / "metadata"

# Sources with dedicated collectors. Generic collection is used only for the remainder.
DEDICATED = {
    "SEC_FORM_345_ACTUAL", "SEC_MIDAS_SECURITY", "SEC_MIDAS_SECURITY_EXCHANGE",
    "SEC_FINANCIAL_STATEMENTS", "SEC_FINANCIAL_NOTES", "SEC_FORM_13F", "SEC_FORM_D",
    "SEC_NPORT", "SEC_REG_A", "SEC_CROWDFUNDING", "SEC_QUOTE_HAZARDS", "SEC_CANCEL_TRADE",
    "SEC_TRANSFER_AGENT", "SEC_FORM_ADV", "SEC_BDC_DATA", "SEC_BDC_REPORT", "SEC_NCEN", "SEC_NMFP",
    "SEC_FUND_SERIES_CLASS", "SEC_CLOSED_END_FUND", "SEC_MMF_INFO", "SEC_MIDAS_SUMMARY_EXCHANGE",
    "SEC_MIDAS_DECILE_QUARTILE", "SEC_MIDAS_SPREAD_DEPTH_2013", "FDA_PURPLE_BOOK",
    "PCAOB_FORM_AP_AUDITORSEARCH", "FINRA_DAILY_SHORT", "SEC_FTD", "SEC_SUBMISSIONS_BULK",
}


def load_catalog() -> list[dict[str, str]]:
    with (M / "source_catalog_175.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def remaining_source_ids(mode: str) -> list[str]:
    rows = load_catalog()
    ids: list[str] = []
    for r in rows:
        sid = r.get("sourceId", "")
        priority = r.get("priority", "")
        status = r.get("packageStatus", "")
        access = r.get("accessMode", "")
        if not sid or sid in DEDICATED:
            continue
        if priority.startswith("EXCLUDED") or status.startswith(("ACTUAL", "EXCLUDED", "MONITOR")):
            continue
        if access.upper() in {"PAID", "TERMS_RESTRICTED"}:
            continue
        if mode == "recommended" and not (priority.startswith("P1") or priority in {"P2", "P2_SECTOR"}):
            continue
        ids.append(sid)
    return sorted(set(ids))


def run_step(name: str, cmd: list[str], log_dir: Path, continue_on_error: bool = True) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    out_path = log_dir / f"{name}.stdout.log"
    err_path = log_dir / f"{name}.stderr.log"
    print(f"\n=== {name} ===")
    print(" ".join(cmd))
    with out_path.open("a", encoding="utf-8") as out, err_path.open("a", encoding="utf-8") as err:
        proc = subprocess.run(cmd, stdout=out, stderr=err, text=True)
    row = {
        "step": name,
        "returncode": proc.returncode,
        "elapsedSeconds": round(time.time() - started, 2),
        "stdout": str(out_path),
        "stderr": str(err_path),
    }
    print(json.dumps(row, ensure_ascii=False))
    if proc.returncode != 0 and not continue_on_error:
        raise SystemExit(proc.returncode)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="One-command downloader for public data used by the Pre-Event project.")
    ap.add_argument("--email", required=True, help="Contact email used in the SEC User-Agent.")
    ap.add_argument("--mode", choices=["discover", "recommended", "maximum"], default="recommended")
    ap.add_argument("--output", type=Path, default=ROOT / "DOWNLOADED_DATA")
    ap.add_argument("--stop-on-error", action="store_true")
    ap.add_argument("--start-finra", default="2009-08-01")
    ap.add_argument("--end", default=date.today().isoformat())
    args = ap.parse_args()

    if "@" not in args.email:
        raise SystemExit("SEC 요청용 연락 이메일을 --email에 넣어야 합니다.")

    out = args.output.resolve()
    logs = out / "_RUN_LOGS"
    out.mkdir(parents=True, exist_ok=True)
    ua = f"PreEventPublicDataCollector/20260821 {args.email}"
    py = sys.executable
    cont = not args.stop_on_error
    rows: list[dict] = []

    def step(name: str, script: str, *argv: str) -> None:
        rows.append(run_step(name, [py, str(C / script), *map(str, argv)], logs, cont))
        (logs / "run_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    discover_only = args.mode == "discover"

    # 1) Highest-value SEC structured bulk: MIDAS, actual Form 3/4/5, financials, Form D/13F, etc.
    cmd = ["--output-dir", out / "01_SEC_STRUCTURED_BULK", "--user-agent", ua]
    if discover_only:
        cmd.append("--discover-only")
    step("01_sec_structured_bulk", "collect_sec_structured_bulk.py", *cmd)

    # 2) Transfer agents / ADV / BDC / fund identities / MIDAS peer summaries / Purple Book.
    cmd = ["--output-dir", out / "02_OFFICIAL_LINKED_ASSETS", "--user-agent", ua]
    if discover_only:
        cmd.append("--discover-only")
    step("02_official_linked_assets", "collect_official_linked_assets.py", *cmd)

    # 3) Event CIK identity and SEC bulk snapshots. Small relative to the large quarterly sets.
    if not discover_only:
        step("03_sec_submissions_identity", "collect_sec_submissions_and_identity.py",
             "--ciks", M / "development_ciks_10digit.txt", "--output-dir", out / "03_SEC_SUBMISSIONS_IDENTITY",
             "--user-agent", ua, "--bulk")

    # 4) PCAOB auditor network.
    if not discover_only:
        step("04_pcaob_form_ap", "collect_pcaob_audit_network.py",
             "--output-dir", out / "04_PCAOB_FORM_AP", "--user-agent", ua)

    # 5) Current symbol reference snapshots.
    if not discover_only:
        step("05_current_symbol_refs", "collect_current_symbol_references.py",
             "--output-dir", out / "05_CURRENT_SYMBOL_REFERENCES", "--user-agent", ua)

    # 6) SEC FTD archives. Raw ZIPs are preserved; selected event symbols are also extracted.
    cmd = ["--symbols", M / "development_symbols.txt", "--output-dir", out / "06_SEC_FTD",
           "--user-agent", ua, "--start", "2004-02-01", "--end", args.end]
    if discover_only:
        cmd.append("--discover-only")
    step("06_sec_ftd", "collect_sec_ftd_extended.py", *cmd)

    # 7) Exact EDGAR attention windows used by project events.
    if not discover_only:
        step("07_edgar_attention", "collect_sec_edgar_attention_v22.py",
             "--manifest", M / "sec_edgar_log_exact_manifest_v22.csv",
             "--targets", M / "event_external_bulk_targets_v22.csv",
             "--output-dir", out / "07_EDGAR_ATTENTION", "--email", args.email)

    # 8) Filing chronology. Maximum mode additionally downloads primary filing documents.
    if not discover_only:
        filing_args = ["--events", M / "development_issuer_identity.csv", "--output-dir", out / "08_EVENT_SEC_FILINGS",
                       "--user-agent", ua, "--lookback-days", "1095", "--include-history"]
        if args.mode == "maximum":
            filing_args += ["--download-documents"]
        step("08_event_sec_filings", "collect_sec_event_filing_documents.py", *filing_args)

    # 9) FINRA daily short-sale volume. Recommended extracts target symbols; maximum also retains every raw text file.
    if not discover_only:
        step("09_finra_short_selected", "collect_finra_daily_short_extended.py",
             "--symbols", M / "development_symbols.txt", "--start", args.start_finra, "--end", args.end,
             "--output-dir", out / "09_FINRA_SHORT_SELECTED")
        if args.mode == "maximum":
            step("09b_finra_short_raw", "collect_finra_daily_short_raw.py",
                 "--start", args.start_finra, "--end", args.end, "--output-dir", out / "09B_FINRA_SHORT_RAW",
                 "--facility-breakdown")

    # 10) Legitimate-catalyst APIs by issuer. This is request-heavy, but resumable by rerunning the package.
    if not discover_only:
        step("10_legitimate_catalyst_apis", "collect_legitimate_catalyst_sources.py",
             "--issuers", M / "development_issuer_identity.csv", "--output-dir", out / "10_LEGITIMATE_CATALYST_APIS",
             "--user-agent", ua, "--max-terms", "0")

    # 11) Everything else in the 175-source catalog that is public and not already covered above.
    remaining = remaining_source_ids("recommended" if args.mode == "recommended" else "maximum")
    if remaining:
        generic = ["--catalog", M / "source_catalog_175.csv", "--output-dir", out / "11_GENERIC_OFFICIAL_SOURCES",
                   "--user-agent", ua, "--sources", *remaining]
        if discover_only:
            generic.append("--discover-only")
        step("11_generic_official_sources", "collect_wave2_official_assets.py", *generic)

    # 12) Discover FINRA monthly transaction archives. These can exceed 1 GB each, so do not blindly pull all venues/months.
    # The discovery manifest is retained so the user can choose exact archives later.
    step("12_finra_monthly_transaction_discovery", "collect_finra_monthly_short_transactions_selective.py",
         "--symbols", M / "development_symbols.txt", "--output-dir", out / "12_FINRA_MONTHLY_DISCOVERY",
         "--user-agent", ua, "--discover-only")

    # Final validation of whatever was actually downloaded.
    if not discover_only:
        step("99_validate_download_tree", "validate_download_tree.py",
             "--root", out, "--output", out / "download_tree_validation.csv")

    summary = {
        "mode": args.mode,
        "output": str(out),
        "steps": len(rows),
        "failedSteps": [r["step"] for r in rows if r["returncode"] != 0],
        "note": "A failed source does not delete successful downloads. Rerun the same BAT to resume/cached-skip.",
    }
    (out / "RUN_FINISHED.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
