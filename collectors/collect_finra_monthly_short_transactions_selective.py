from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

from common_download import build_session, download_resumable, request_with_retry

LANDING="https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/monthly-short-sale-volume-files"


def main() -> None:
    ap=argparse.ArgumentParser(description="Discover/download only selected FINRA monthly transaction archives; files can exceed 1 GB each.")
    ap.add_argument("--symbols",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--user-agent",required=True)
    ap.add_argument("--label-regex",default="",help="Required for download, e.g. 'June 2026.*Chicago'")
    ap.add_argument("--discover-only",action="store_true")
    ap.add_argument("--max-files",type=int,default=0)
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    symbols={x.strip().upper() for x in args.symbols.read_text(encoding="utf-8").splitlines() if x.strip()}
    session=build_session(args.user_agent)
    soup=BeautifulSoup(request_with_retry(session,LANDING).text,"html.parser")
    rows=[]
    for a in soup.find_all("a",href=True):
        href=urljoin(LANDING,a["href"]); label=" ".join(a.get_text(" ",strip=True).split())
        if ".zip" in href.lower(): rows.append({"label":label,"url":href,"filename":Path(urlparse(href).path).name})
    manifest=pd.DataFrame(rows).drop_duplicates("url")
    manifest.to_csv(args.output_dir/"finra_monthly_discovered_links.csv",index=False)
    if args.discover_only:
        print(json.dumps({"links":len(manifest)},indent=2)); return
    if not args.label_regex:
        raise SystemExit("Refusing multi-GB bulk download without --label-regex")
    selected=manifest[manifest['label'].str.contains(args.label_regex,case=False,regex=True,na=False)]
    if args.max_files>0: selected=selected.head(args.max_files)
    audit=[]
    for row in selected.to_dict('records'):
        target=args.output_dir/'raw'/row['filename']
        try:
            result=download_resumable(session,row['url'],target,expected_min_bytes=100)
            audit.append({**row,**result,'error':''})
            # Keep raw ZIP. Format varies; a separate parser should inspect headers before symbol filtering.
        except Exception as exc:
            audit.append({**row,'status':'FAILED','error':repr(exc)})
    pd.DataFrame(audit).to_csv(args.output_dir/'finra_monthly_download_audit.csv',index=False)
    print(json.dumps({'discovered':len(manifest),'selected':len(selected),'attempted':len(audit)},indent=2))

if __name__=='__main__': main()
