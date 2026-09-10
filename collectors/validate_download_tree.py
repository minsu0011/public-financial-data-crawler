from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); args=ap.parse_args()
    rows=[]; failures=[]
    for p in sorted(args.root.rglob('*')):
        if not p.is_file(): continue
        status='PASS'; detail=''
        try:
            if p.suffix.lower()=='.zip':
                with zipfile.ZipFile(p) as z:
                    bad=z.testzip()
                    if bad: raise RuntimeError(f'bad member {bad}')
            if p.name.endswith('.csv') or p.name.endswith('.csv.gz'):
                pd.read_csv(p,nrows=20)
        except Exception as exc:
            status='FAIL'; detail=repr(exc); failures.append(str(p))
        rows.append({'relativePath':str(p.relative_to(args.root)),'bytes':p.stat().st_size,'sha256':sha(p),'status':status,'detail':detail})
    pd.DataFrame(rows).to_csv(args.root/'download_tree_validation.csv',index=False)
    payload={'checkedAtUtc':pd.Timestamp.utcnow().isoformat(),'files':len(rows),'failures':failures,'allPass':not failures}
    (args.root/'download_tree_validation.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps(payload,indent=2))
    if failures: raise SystemExit(2)

if __name__=='__main__': main()
