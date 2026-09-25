#!/usr/bin/env python3
import argparse, csv, hashlib, json, time, urllib.request, urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CFG=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
OUT=ROOT/'auditoria'
OUT.mkdir(exist_ok=True)

def get(url, timeout=25):
    req=urllib.request.Request(url, headers={'User-Agent':'RadarNorte-Auditoria/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def has_cargo7(obj):
    for c in obj.get('carg',[]) if isinstance(obj,dict) else []:
        try:
            if str(int(str(c.get('cd'))))=='7': return True
        except: pass
    return False

def has_schema(obj):
    if not isinstance(obj,dict): return False
    for c in obj.get('carg',[]):
        try: ok=str(int(str(c.get('cd'))))=='7'
        except: ok=False
        if not ok: continue
        for agr in c.get('agr',[]) or []:
            for par in agr.get('par',[]) or []:
                if isinstance(par.get('cand'),list): return True
    return False

def audit(interval=2.5, mock=False):
    interval=max(2.5,float(interval))
    stamp=time.strftime('%Y%m%d_%H%M%S')
    run=OUT/stamp; raw=run/'raw'; raw.mkdir(parents=True)
    rows=[]
    for i,(name,code) in enumerate(CFG['municipalities'],1):
        url=CFG['endpoint_template'].format(code=code)
        row={'ordem':i,'municipio':name,'codigo_tse':code,'url':url,'http':'','json_valido':'NAO','municipio_confere':'NAO','cargo7':'NAO','schema_agr_par_cand':'NAO','estado':'ERRO_COLETA','dg':'','hg':'','tf':'','sha256':''}
        try:
            if mock:
                payload={'cdabr':code,'dg':'MOCK','hg':'MOCK','tf':'n','carg':[{'cd':'7','agr':[{'par':[{'cand':[]}]}]}]}; body=json.dumps(payload).encode(); status=200
            else: status,body=get(url)
            row['http']=status
            p=raw/f'{i:02d}_{code}.json'; p.write_bytes(body); row['sha256']=hashlib.sha256(body).hexdigest()
            obj=json.loads(body); row['json_valido']='SIM'
            row['municipio_confere']='SIM' if str(obj.get('cdabr',''))==code else 'NAO'
            row['cargo7']='SIM' if has_cargo7(obj) else 'NAO'; row['schema_agr_par_cand']='SIM' if has_schema(obj) else 'NAO'
            row['dg']=obj.get('dg',''); row['hg']=obj.get('hg',''); row['tf']=obj.get('tf','')
            row['estado']='DADO_VALIDO' if status==200 and row['municipio_confere']=='SIM' and row['cargo7']=='SIM' and row['schema_agr_par_cand']=='SIM' else 'DADO_INVALIDO'
        except urllib.error.HTTPError as e:
            row['http']=e.code; row['estado']=f'HTTP_{e.code}'
            rows.append(row)
            if e.code in (403,429): break
            if not mock: time.sleep(interval)
            continue
        except Exception as e:
            row['estado']='ERRO_COLETA'; row['erro']=str(e)[:300]
        rows.append(row)
        if not mock and i<len(CFG['municipalities']): time.sleep(interval)
    fields=['ordem','municipio','codigo_tse','url','http','json_valido','municipio_confere','cargo7','schema_agr_par_cand','estado','dg','hg','tf','sha256','erro']
    with (run/'auditoria.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    ok=sum(r['estado']=='DADO_VALIDO' for r in rows)
    summary={'esperados':50,'consultados':len(rows),'validos':ok,'completo':len(rows)==50 and ok==50,'modo':'mock' if mock else 'tse'}
    (run/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    print(run)
    return 0 if summary['completo'] else 2

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--mock',action='store_true'); ap.add_argument('--interval',type=float,default=2.5); a=ap.parse_args(); raise SystemExit(audit(a.interval,a.mock))
