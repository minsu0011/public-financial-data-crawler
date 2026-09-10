from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common_download import build_session, download_resumable

STATIC = {
    "NASDAQ_LISTED_CURRENT": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "NASDAQ_OTHER_LISTED_CURRENT": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--user-agent",required=True)
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    session=build_session(args.user_agent); rows=[]
    for sid,url in STATIC.items():
        target=args.output_dir/f"{sid.lower()}.txt"
        try: rows.append({"sourceId":sid,"snapshotDate":pd.Timestamp.today().date().isoformat(),**download_resumable(session,url,target)})
        except Exception as exc: rows.append({"sourceId":sid,"url":url,"status":"FAILED","error":repr(exc)})
    pd.DataFrame(rows).to_csv(args.output_dir/'current_reference_download_audit.csv',index=False)
    print(json.dumps({'requests':len(rows),'failures':sum(r.get('status')=='FAILED' for r in rows)},indent=2))

if __name__=='__main__': main()
