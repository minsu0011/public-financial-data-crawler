from pathlib import Path
import argparse, subprocess, sys
GROUP=['OPENFDA_FAERS','OPENFDA_MAUDE','OPENFDA_COMPLETE_RESPONSE_LETTERS','OPENFDA_DRUG_LABEL','OPENFDA_DRUG_SHORTAGES','FDA_WARNING_LETTERS','FDA_IMPORT_ALERTS','OPENFDA_FOOD_ENFORCEMENT','OPENFDA_DEVICE_ENFORCEMENT','FDA_DRUG_SAFETY_COMMUNICATIONS','FDA_MEDWATCH_ALERTS','NHTSA_RECALLS','NHTSA_MANUFACTURER_COMMUNICATIONS','NHTSA_INVESTIGATIONS','NHTSA_COMPLAINTS','CPSC_RECALLS','GRANTS_GOV_DAILY_XML','SBIR_AWARDS_BULK','NIH_EXPORTER_PATENTS','NIH_EXPORTER_CLINICAL_STUDIES','USPTO_PATENT_ASSIGNMENTS','PATENTSVIEW_ASSIGNEE','PATENTSVIEW_PATENT_DATA']
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--catalog',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); ap.add_argument('--user-agent',required=True); ap.add_argument('--download',action='store_true'); ap.add_argument('--max-files',type=int,default=0); args=ap.parse_args()
    cmd=[sys.executable,str(Path(__file__).with_name('collect_wave2_official_assets.py')),'--catalog',str(args.catalog),'--output-dir',str(args.output_dir),'--user-agent',args.user_agent,'--sources',*GROUP]
    if not args.download: cmd.append('--discover-only')
    if args.max_files: cmd += ['--max-files',str(args.max_files)]
    raise SystemExit(subprocess.call(cmd))
if __name__=='__main__': main()
