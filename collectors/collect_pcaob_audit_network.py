from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from common_download import build_session, download_resumable

FORM_AP_URL='https://assets.pcaobus.org/firm-filings/FirmFilings.zip'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',type=Path,required=True); ap.add_argument('--user-agent',required=True); ap.add_argument('--overwrite',action='store_true'); args=ap.parse_args()
    session=build_session(args.user_agent); args.output_dir.mkdir(parents=True,exist_ok=True)
    audit=[]
    try:
        result=download_resumable(session,FORM_AP_URL,args.output_dir/'raw'/'PCAOB_FORM_AP_AUDITORSEARCH'/'FirmFilings.zip',delay=.5,overwrite=args.overwrite)
        audit.append({'sourceId':'PCAOB_FORM_AP_AUDITORSEARCH',**result,'error':''})
    except Exception as exc:
        audit.append({'sourceId':'PCAOB_FORM_AP_AUDITORSEARCH','url':FORM_AP_URL,'status':'FAILED','error':repr(exc)})
    pd.DataFrame(audit).to_csv(args.output_dir/'pcaob_download_audit.csv',index=False)
    print(json.dumps(audit,indent=2));
    if any(x['status']=='FAILED' for x in audit): raise SystemExit(2)
if __name__=='__main__': main()
