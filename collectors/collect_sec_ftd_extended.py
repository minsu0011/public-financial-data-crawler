from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

from common_download import build_session, download_resumable, request_with_retry

LANDING = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--user-agent", required=True)
    ap.add_argument("--start", default="2004-02-01")
    ap.add_argument("--end", default=pd.Timestamp.today().date().isoformat())
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()
    symbols = {x.strip().upper() for x in args.symbols.read_text(encoding="utf-8").splitlines() if x.strip()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.user_agent)
    html = request_with_retry(session, LANDING, delay=args.delay).text
    soup = BeautifulSoup(html, "html.parser")
    links=[]
    for a in soup.find_all("a", href=True):
        href=urljoin(LANDING,a["href"])
        if ".zip" not in href.lower(): continue
        label=" ".join(a.get_text(" ",strip=True).split())
        links.append({"label":label,"url":href,"filename":Path(urlparse(href).path).name})
    manifest=pd.DataFrame(links).drop_duplicates("url")
    manifest.to_csv(args.output_dir/"ftd_discovered_links.csv",index=False)
    if args.discover_only:
        print(json.dumps({"links":len(manifest)},indent=2)); return
    selected=[]; audits=[]
    start=pd.Timestamp(args.start); end=pd.Timestamp(args.end)
    for row in manifest.to_dict("records"):
        # Download all discovered archives and date-filter rows after parsing. The landing-page list is authoritative.
        target=args.output_dir/"raw"/row["filename"]
        try:
            result=download_resumable(session,row["url"],target,delay=args.delay)
            audits.append({**row,**result,"error":""})
            with zipfile.ZipFile(target) as z:
                for member in z.namelist():
                    if member.endswith("/"): continue
                    raw=z.read(member)
                    text=raw.decode("latin-1",errors="replace")
                    try:
                        frame=pd.read_csv(io.StringIO(text),sep="|",dtype=str)
                    except Exception:
                        continue
                    frame.columns=[c.strip().upper() for c in frame.columns]
                    sym=next((c for c in frame.columns if c in {"SYMBOL","TICKER SYMBOL"}),None)
                    dat=next((c for c in frame.columns if "SETTLEMENT" in c and "DATE" in c),None)
                    if not sym or not dat: continue
                    frame[sym]=frame[sym].astype(str).str.upper().str.strip()
                    frame[dat]=pd.to_datetime(frame[dat],format="%Y%m%d",errors="coerce")
                    part=frame[frame[sym].isin(symbols)&frame[dat].between(start,end)].copy()
                    if len(part):
                        part["sourceArchive"]=row["filename"]; part["sourceUrl"]=row["url"]
                        selected.append(part)
        except Exception as exc:
            audits.append({**row,"status":"FAILED","error":repr(exc)})
    out=pd.concat(selected,ignore_index=True) if selected else pd.DataFrame()
    out.to_csv(args.output_dir/"sec_ftd_selected.csv.gz",index=False,compression="gzip")
    pd.DataFrame(audits).to_csv(args.output_dir/"sec_ftd_download_audit.csv",index=False)
    failures=sum(a.get("status")=="FAILED" for a in audits)
    print(json.dumps({"selectedRows":len(out),"archives":len(audits),"failures":failures},indent=2))
    if failures: raise SystemExit(2)

if __name__ == "__main__": main()
