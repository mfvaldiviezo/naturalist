#!/usr/bin/env python3
"""Read-only scan: identify actual H10 runner files and TraCI hook locations."""
import argparse
import hashlib
import json
import re
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('.'))
    args=p.parse_args()
    root=args.root.resolve()
    source=root/'H10_Vine_H09_Imprudencia_v112'
    if not source.is_dir(): raise FileNotFoundError(f'Falta ejecutor H10: {source}')
    results=[]
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.py','.ps1'): continue
        code=path.read_text(encoding='utf-8-sig',errors='replace')
        m=[]
        for ix,line in enumerate(code.splitlines(),1):
            if re.search(r'\bsimulationStep\s*\(|\btraci\.start\s*\(|\b\.on_step\s*\(|\bpython\b',line,re.I):
                m.append({'line':ix,'text':line.strip()[:200]})
        if m:
            results.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'hooks':m})
    print('H11.2 PREFLIGHT H10 v112: SOLO LECTURA')
    for r in results:
        print('\nARCHIVO',r['path'],'SHA',r['sha256'])
        for m in r['hooks'][:18]: print(f"  L{m['line']:4d} {m['text']}")
    print('\nSe detectaron',len(results),'archivos con llamadas relevantes.')
    print('No se ha cambiado ningún archivo. Las líneas exactas de integración se determinan con este resultado.')
    return results

if __name__=='__main__':main()
