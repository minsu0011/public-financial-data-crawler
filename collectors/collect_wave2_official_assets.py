from __future__ import annotations
import argparse, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import pandas as pd
from bs4 import BeautifulSoup
from common_download import build_session, download_resumable, request_with_retry

EXTENSIONS = ('.zip','.csv','.json','.xml','.xlsx','.xls','.txt','.gz','.tar.gz','.dta')

def discover(session, source_id: str, landing: str, delay: float) -> list[dict]:
    if not landing:
        return []
    response = request_with_retry(session, landing, delay=delay)
    ctype = response.headers.get('content-type','').lower()
    if any(landing.lower().split('?')[0].endswith(x) for x in EXTENSIONS) or 'application/octet-stream' in ctype:
        return [{'sourceId':source_id,'landingPage':landing,'label':'direct','url':landing,'filename':Path(urlparse(landing).path).name or source_id}]
    soup=BeautifulSoup(response.text,'html.parser')
    out=[]
    for a in soup.find_all('a',href=True):
        url=urljoin(landing,a['href'])
        path=urlparse(url).path.lower()
        if not any(path.endswith(ext) or ext in path for ext in EXTENSIONS):
            continue
        out.append({'sourceId':source_id,'landingPage':landing,'label':' '.join(a.get_text(' ',strip=True).split()),'url':url,'filename':Path(urlparse(url).path).name})
    time.sleep(delay)
    return list({(r['sourceId'],r['url']):r for r in out}.values())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--user-agent',required=True,help='Example: PreEventResearch contact@example.com')
    ap.add_argument('--sources',nargs='*',default=[])
    ap.add_argument('--priority',nargs='*',default=[])
    ap.add_argument('--discover-only',action='store_true')
    ap.add_argument('--max-files',type=int,default=0)
    ap.add_argument('--delay',type=float,default=.35)
    args=ap.parse_args()
    cat=pd.read_csv(args.catalog,dtype=str).fillna('')
    if args.sources: cat=cat[cat.sourceId.isin(args.sources)]
    if args.priority: cat=cat[cat.priority.isin(args.priority)]
    cat=cat[~cat.packageStatus.str.startswith(('ACTUAL','EXCLUDED','MONITOR'))]
    session=build_session(args.user_agent)
    discovered=[]
    for row in cat.to_dict('records'):
        try:
            found=discover(session,row['sourceId'],row['landingPage'],args.delay)
            for x in found: x.update({'priority':row['priority'],'packageStatus':row['packageStatus'],'error':''})
            discovered.extend(found)
        except Exception as exc:
            discovered.append({'sourceId':row['sourceId'],'landingPage':row['landingPage'],'label':'','url':'','filename':'','priority':row['priority'],'packageStatus':row['packageStatus'],'error':repr(exc)})
    manifest=pd.DataFrame(discovered)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    manifest.to_csv(args.output_dir/'wave2_discovered_links.csv',index=False)
    if args.discover_only:
        print(json.dumps({'sources':len(cat),'links':int((manifest.url!='').sum()),'errors':int((manifest.error!='').sum())},indent=2)); return
    selected=manifest[(manifest.url!='') & (manifest.error=='')]
    if args.max_files>0: selected=selected.head(args.max_files)
    audit=[]
    for r in selected.to_dict('records'):
        target=args.output_dir/'raw'/r['sourceId']/r['filename']
        try:
            res=download_resumable(session,r['url'],target,delay=args.delay)
            audit.append({**r,**res,'error':''})
        except Exception as exc:
            audit.append({**r,'status':'FAILED','localFile':str(target),'bytes':'','sha256':'','error':repr(exc)})
    pd.DataFrame(audit).to_csv(args.output_dir/'wave2_download_audit.csv',index=False)
    failures=sum(x.get('status')=='FAILED' for x in audit)
    print(json.dumps({'sources':len(cat),'discovered':len(manifest),'attempted':len(audit),'failures':failures},indent=2))
    if failures: raise SystemExit(2)
if __name__=='__main__': main()
