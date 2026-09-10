from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common_download import build_session, download_resumable


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--ciks",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--user-agent",required=True)
    ap.add_argument("--bulk",action="store_true",help="Also download nightly submissions.zip and companyfacts.zip")
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    session=build_session(args.user_agent); rows=[]
    for raw in args.ciks.read_text(encoding='utf-8').splitlines():
        raw=raw.strip()
        if not raw: continue
        cik=str(int(raw)).zfill(10)
        url=f"https://data.sec.gov/submissions/CIK{cik}.json"
        target=args.output_dir/'submissions_by_cik'/f'CIK{cik}.json'
        try: rows.append({"sourceId":"SEC_SUBMISSIONS_CIK","cik":cik,**download_resumable(session,url,target)})
        except Exception as exc: rows.append({"sourceId":"SEC_SUBMISSIONS_CIK","cik":cik,"url":url,"status":"FAILED","error":repr(exc)})
    if args.bulk:
        for sid,url,name in [
            ('SEC_SUBMISSIONS_BULK','https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip','submissions.zip'),
            ('SEC_COMPANYFACTS_BULK','https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip','companyfacts.zip')]:
            try: rows.append({"sourceId":sid,"cik":"",**download_resumable(session,url,args.output_dir/'bulk'/name)})
            except Exception as exc: rows.append({"sourceId":sid,"cik":"","url":url,"status":"FAILED","error":repr(exc)})
    pd.DataFrame(rows).to_csv(args.output_dir/'sec_submissions_download_audit.csv',index=False)
    failures=sum(r.get('status')=='FAILED' for r in rows)
    print(json.dumps({'requests':len(rows),'failures':failures},indent=2))
    if failures: raise SystemExit(2)

if __name__=='__main__': main()
