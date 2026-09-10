from pathlib import Path
import argparse, subprocess, sys
GROUP=['FINRA_MARGIN_STATISTICS','FINRA_TRACE_MONTHLY_VOLUME','FINRA_TREASURY_DAILY_AGG','FINRA_TREASURY_MONTHLY_AGG','CFTC_COT_LEGACY','CFTC_COT_TFF','CFTC_COT_DISAGG','FDIC_BANKFIND_INSTITUTIONS','FDIC_BANKFIND_FINANCIALS','FDIC_BANKFIND_HISTORY_EVENTS','FDIC_BANK_FAILURES','FFIEC_NIC_STRUCTURE','FFIEC_Y9C_FINANCIALS','FFIEC_Y15_SYSTEMIC_RISK','OFAC_SDN_CURRENT','OFAC_NONSDN_CURRENT','OFAC_DELTA_ARCHIVE']
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--catalog',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); ap.add_argument('--user-agent',required=True); ap.add_argument('--download',action='store_true'); ap.add_argument('--max-files',type=int,default=0); args=ap.parse_args()
    cmd=[sys.executable,str(Path(__file__).with_name('collect_wave2_official_assets.py')),'--catalog',str(args.catalog),'--output-dir',str(args.output_dir),'--user-agent',args.user_agent,'--sources',*GROUP]
    if not args.download: cmd.append('--discover-only')
    if args.max_files: cmd += ['--max-files',str(args.max_files)]
    raise SystemExit(subprocess.call(cmd))
if __name__=='__main__': main()
