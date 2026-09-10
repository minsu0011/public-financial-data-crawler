from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def get(session: requests.Session, url: str, delay: float) -> requests.Response:
    last = None
    for attempt in range(5):
        try:
            response = session.get(url, timeout=120)
            if response.status_code == 429:
                time.sleep(delay * (2 ** attempt))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt < 4:
                time.sleep(delay * (2 ** attempt))
    raise RuntimeError(f"request failed: {url}: {last}")

def normalize_cik(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return text.lstrip("0")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--max-files", type=int, default=0)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": f"PreEventSusceptibilityResearch/22 {args.email}"})

    manifest = pd.read_csv(args.manifest, dtype=str).fillna("")
    targets = pd.read_csv(args.targets, dtype=str).fillna("")
    targets["mappedCikNorm"] = targets["mappedCik"].map(normalize_cik)
    target_ciks = set(targets["mappedCikNorm"]) - {""}
    selected = manifest.head(args.max_files) if args.max_files > 0 else manifest

    attention_parts = []
    download_rows = []
    for _, row in selected.iterrows():
        date = row["date"]
        target = raw_dir / f"log{date.replace('-', '')}.zip"
        if not target.exists():
            try:
                response = get(session, row["url"], args.delay)
                target.write_bytes(response.content)
                status = "DOWNLOADED"
            except Exception as exc:
                download_rows.append({**row.to_dict(), "status": f"ERROR:{exc}"})
                continue
            time.sleep(args.delay)
        else:
            status = "CACHED"

        try:
            with zipfile.ZipFile(target) as archive:
                csv_name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
                frame = pd.read_csv(archive.open(csv_name), low_memory=False)
            cik_column = next((c for c in frame.columns if c.lower() == "cik"), None)
            if cik_column is None:
                raise ValueError("CIK column not found")
            frame["cikNorm"] = frame[cik_column].map(normalize_cik)
            matched = frame[frame["cikNorm"].isin(target_ciks)].copy()
            if len(matched):
                matched["logDate"] = date
                attention_parts.append(matched)
            download_rows.append({
                **row.to_dict(), "status": status, "localFile": str(target.relative_to(args.output_dir)),
                "bytes": target.stat().st_size, "sha256": sha256_file(target), "matchedRows": len(matched),
            })
        except Exception as exc:
            download_rows.append({**row.to_dict(), "status": f"PARSE_ERROR:{exc}"})

    attention = pd.concat(attention_parts, ignore_index=True) if attention_parts else pd.DataFrame()
    attention.to_csv(args.output_dir / "selected_edgar_attention_rows.csv.gz", index=False, compression="gzip")
    pd.DataFrame(download_rows).to_csv(args.output_dir / "download_manifest.csv", index=False)

    if len(attention):
        counts = attention.groupby(["cikNorm", "logDate"], as_index=False).size().rename(columns={"size": "requestCount"})
        counts.to_csv(args.output_dir / "cik_daily_attention.csv.gz", index=False, compression="gzip")
    print(json.dumps({"filesProcessed": len(download_rows), "selectedRows": len(attention)}, indent=2))

if __name__ == "__main__":
    main()
