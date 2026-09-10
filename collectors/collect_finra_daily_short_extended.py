from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://cdn.finra.org/equity/regsho/daily"


def families_for_date(date: pd.Timestamp, include_facility_breakdown: bool) -> list[str]:
    if date >= pd.Timestamp("2018-08-01"):
        # CNMS already combines TRFs and ADF for NMS. Pair only with ORF by default to avoid double-counting.
        return ["CNMS", "FORF"] if not include_facility_breakdown else ["CNMS", "FNQC", "FNSQ", "FNYX", "FNRA", "FORF"]
    # Before consolidated NMS, request facility files separately. Missing files are audited, not fabricated.
    return ["FNSQ", "FNYX", "FNRA", "FORF"]


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols",type=Path,required=True)
    ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--include-facility-breakdown",action="store_true")
    ap.add_argument("--delay",type=float,default=0.2)
    args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    symbols={x.strip().upper() for x in args.symbols.read_text(encoding="utf-8").splitlines() if x.strip()}
    session=requests.Session(); session.headers.update({"User-Agent":"PreEventSusceptibilityResearch/EXT20260820 contact-required"})
    selected=[]; audit=[]
    for date in pd.bdate_range(args.start,args.end):
        ymd=date.strftime("%Y%m%d")
        for family in families_for_date(date,args.include_facility_breakdown):
            url=f"{BASE}/{family}shvol{ymd}.txt"
            try:
                r=session.get(url,timeout=60)
                if r.status_code==404:
                    audit.append({"date":date.date(),"family":family,"url":url,"status":"404","rows":""}); continue
                r.raise_for_status()
                frame=pd.read_csv(io.StringIO(r.text),sep="|")
                if "Symbol" not in frame.columns:
                    raise RuntimeError(f"missing Symbol column: {list(frame.columns)}")
                part=frame[frame["Symbol"].astype(str).str.upper().isin(symbols)].copy()
                part["sourceFamily"]=family; part["sourceDate"]=date.date().isoformat(); part["sourceUrl"]=url
                selected.append(part)
                audit.append({"date":date.date(),"family":family,"url":url,"status":"PASS","rows":len(frame),"selectedRows":len(part)})
            except Exception as exc:
                audit.append({"date":date.date(),"family":family,"url":url,"status":"FAILED","error":repr(exc)})
            time.sleep(args.delay)
    out=pd.concat(selected,ignore_index=True) if selected else pd.DataFrame()
    out.to_csv(args.output_dir/"finra_daily_short_selected.csv.gz",index=False,compression="gzip")
    pd.DataFrame(audit).to_csv(args.output_dir/"finra_daily_short_audit.csv",index=False)
    failures=sum(a.get("status")=="FAILED" for a in audit)
    print(json.dumps({"rows":len(out),"requests":len(audit),"failures":failures},indent=2))
    if failures: raise SystemExit(2)

if __name__ == "__main__": main()
