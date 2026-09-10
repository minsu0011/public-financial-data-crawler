from __future__ import annotations

import argparse
import csv
import hashlib
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

BASE = "https://cdn.finra.org/equity/regsho/daily"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def families_for_date(ts: pd.Timestamp, facility_breakdown: bool) -> list[str]:
    if ts >= pd.Timestamp("2018-08-01"):
        return ["CNMS", "FORF"] if not facility_breakdown else ["CNMS", "FNQC", "FNSQ", "FNYX", "FNRA", "FORF"]
    return ["FNSQ", "FNYX", "FNRA", "FORF"]


def download(session: requests.Session, url: str, target: Path, attempts: int = 6) -> tuple[str, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return "CACHED", sha256_file(target)
    part = target.with_suffix(target.suffix + ".part")
    for attempt in range(attempts):
        try:
            start = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={start}-"} if start else {}
            r = session.get(url, timeout=90, stream=True, headers=headers)
            if r.status_code == 404:
                return "404", ""
            if r.status_code in {403, 429, 500, 502, 503, 504}:
                time.sleep(min(30, 0.5 * (2 ** attempt)))
                continue
            r.raise_for_status()
            append = start > 0 and r.status_code == 206
            mode = "ab" if append else "wb"
            if not append and part.exists():
                part.unlink()
            with part.open(mode) as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
            part.replace(target)
            return "DOWNLOADED", sha256_file(target)
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise
            time.sleep(min(30, 0.5 * (2 ** attempt)))
    raise RuntimeError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser(description="Download raw FINRA Reg SHO daily short-sale-volume text files.")
    ap.add_argument("--start", default="2009-08-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--facility-breakdown", action="store_true")
    ap.add_argument("--delay", type=float, default=0.12)
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "finra_raw_download_audit.csv"
    session = requests.Session()
    session.headers.update({"User-Agent": "PreEventPublicDataCollector/1.0"})
    write_header = not audit_path.exists()
    with audit_path.open("a", newline="", encoding="utf-8-sig") as af:
        writer = csv.DictWriter(af, fieldnames=["date", "family", "url", "status", "bytes", "sha256", "error"])
        if write_header:
            writer.writeheader()
        for ts in pd.bdate_range(args.start, args.end):
            ymd = ts.strftime("%Y%m%d")
            for family in families_for_date(ts, args.facility_breakdown):
                url = f"{BASE}/{family}shvol{ymd}.txt"
                target = args.output_dir / "raw" / ts.strftime("%Y") / f"{family}shvol{ymd}.txt"
                try:
                    status, digest = download(session, url, target)
                    writer.writerow({"date": ts.date(), "family": family, "url": url, "status": status,
                                     "bytes": target.stat().st_size if target.exists() else 0, "sha256": digest, "error": ""})
                except Exception as exc:
                    writer.writerow({"date": ts.date(), "family": family, "url": url, "status": "FAILED",
                                     "bytes": 0, "sha256": "", "error": repr(exc)})
                af.flush()
                time.sleep(args.delay)


if __name__ == "__main__":
    main()
