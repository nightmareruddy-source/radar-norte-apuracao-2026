#!/usr/bin/env python3
import argparse, csv, json, os, sqlite3, tempfile, threading, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).resolve().parent
CFG=json.loads((BASE/'config.json').read_text(encoding='utf-8'))
REAL_DATA=BASE/'data'; MOCK_DATA=BASE/'data_mock'
DATA=REAL_DATA; DB=None; LATEST=None; HIST=None
URL=CFG['endpoint_template']

def select_data_dir(mock=False):
    global DATA,DB,LATEST,HIST
    DATA=MOCK_DATA if mock else REAL_DATA
    DATA.mkdir(exist_ok=True)
    DB=DATA/'radar.sqlite3'; LATEST=DATA/'raw_atual.csv'; HIST=DATA/'historico_apuracao.csv'
FIELDS=['timestamp','municipio','codigo_municipio','http','json_valido','municipio_confere','cargo7_confere','schema_confere','candidato_presente','candidato','numero','partido','votos','pct_candidato','dg','hg','tf','estado','source_url','erro']

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD',str(s or '')) if unicodedata.category(c)!='Mn').upper().strip()

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

def init_db():
    if DB is None: select_data_dir(False)
    with sqlite3.connect(DB) as c:
        c.execute('''create table if not exists snapshots(id integer primary key, timestamp text, municipio text, codigo text, estado text, votos integer, payload text)''')
        c.execute('create index if not exists ix_snap_mun on snapshots(municipio,timestamp)')

def fetch(url,timeout=20):
    req=urllib.request.Request(url,headers={'User-Agent':'RadarNorte2026/1.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read(); return r.status,json.loads(raw.decode('utf-8-sig')),''
    except urllib.error.HTTPError as e: return e.code,None,f'HTTP {e.code}'
    except Exception as e: return 0,None,f'{type(e).__name__}: {e}'

def find_cargo7(payload):
    for x in payload.get('carg',[]) if isinstance(payload,dict) else []:
        try: cd=str(int(str(x.get('cd','0'))))
        except: cd=str(x.get('cd',''))
        if cd=='7': return x
    return None

def extract_candidates(cargo):
    out=[]
    if not isinstance(cargo,dict): return out
    for agr in cargo.get('agr',[]) or []:
        for par in agr.get('par',[]) or []:
            partido=par.get('sg') or par.get('nm') or ''
            for cand in par.get('cand',[]) or []:
                if isinstance(cand,dict): out.append((cand,partido))
    return out

def parse_one(mun,code,payload,http=200,err=''):
    row={k:'' for k in FIELDS}; row.update(timestamp=now(),municipio=mun,codigo_municipio=code,http=http,source_url=URL.format(code=code),erro=err)
    if not isinstance(payload,dict): row['estado']='ERRO_COLETA' if err else 'JSON_INVALIDO'; return row
    row['json_valido']='SIM'
    cdabr=str(payload.get('cdabr') or payload.get('cd') or '')
    row['municipio_confere']='SIM' if (not cdabr or cdabr==str(code)) else 'NÃO'
    cargo=find_cargo7(payload); row['cargo7_confere']='SIM' if cargo else 'NÃO'
    if not cargo: row['estado']='CARGO_DIVERGENTE'; return row
    cands=extract_candidates(cargo); row['schema_confere']='SIM' if cands else 'NÃO'
    row['dg']=payload.get('dg',''); row['hg']=payload.get('hg',''); row['tf']=payload.get('tf','')
    if not cands: row['estado']='SCHEMA_DIVERGENTE'; return row
    target=str(CFG.get('candidate_number','70255'))
    hit=None; party=''
    for c,p in cands:
        if str(c.get('n','')).strip()==target: hit=c; party=p; break
    if hit:
        row.update(candidato_presente='SIM',candidato=hit.get('nm') or hit.get('nmu') or '',numero=target,partido=party,votos=hit.get('vap',''),pct_candidato=hit.get('pvap',''),estado='DADO_VALIDO')
    else:
        # Important: absence in synthetic simulation is not converted to zero votes.
        row.update(candidato_presente='NÃO',numero=target,estado='CANDIDATO_AUSENTE_NO_SIMULADO')
    return row

def mock_payload(mun,code):
    return {'cdabr':str(code),'dg':'22/09/2026','hg':'15:00:00','tf':'n','carg':[{'cd':'7','agr':[{'par':[{'sg':'FICT','cand':[{'n':'99999','nm':'CANDIDATO FICTÍCIO','vap':'123','pvap':'1,23'}]}]}]}]}

def atomic_write_csv(path, rows):
    """Write a complete CSV and atomically replace the previous snapshot.

    The web server may read raw_atual.csv while collection is running. Writing to
    a temporary file first prevents readers from observing a half-written CSV.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader(); w.writerows(rows)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try: os.unlink(tmp_name)
        except FileNotFoundError: pass
        raise

def save(rows):
    # History always records what was observed. Latest is only replaced by a complete 50-row cycle,
    # preventing a blocked/partial request from destroying the last complete snapshot.
    publish_latest = len(rows) == len(CFG['municipalities'])
    if publish_latest:
        atomic_write_csv(LATEST, rows)
    new=not HIST.exists()
    with HIST.open('a',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if new: w.writeheader()
        w.writerows(rows)
    with sqlite3.connect(DB) as c:
        for r in rows:
            v=None
            try: v=int(r['votos']) if str(r['votos']).strip() else None
            except: pass
            c.execute('insert into snapshots(timestamp,municipio,codigo,estado,votos,payload) values(?,?,?,?,?,?)',(r['timestamp'],r['municipio'],r['codigo_municipio'],r['estado'],v,json.dumps(r,ensure_ascii=False)))
    return publish_latest

def cycle(mock=False):
    select_data_dir(mock)
    init_db()
    rows=[]
    for item in CFG['municipalities']:
        if isinstance(item, (list, tuple)):
            mun, code = item[0], str(item[1])
        else:
            mun, code = item['name'], str(item['code'])
        if mock: status,payload,err=200,mock_payload(mun,code),''
        else: status,payload,err=fetch(URL.format(code=code))
        row=parse_one(mun,code,payload,status,err); rows.append(row)
        if not mock and status in (403,429):
            # Stop safely; never fill remaining municipalities with zero.
            break
        if not mock: time.sleep(max(2.5,float(CFG.get('request_interval_seconds',2.5))))
    save(rows); return rows

def latest_rows():
    if not LATEST.exists(): return []
    with LATEST.open(encoding='utf-8-sig') as f: return list(csv.DictReader(f))

def html():
    env=CFG.get('environment','SIMULADO_TSE_2026')
    page='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Radar Norte 2026</title><style>body{font-family:system-ui;margin:20px;background:#f5f5f5}h1{margin-bottom:4px}.card{background:white;padding:16px;border-radius:12px;margin:12px 0;box-shadow:0 1px 5px #ccc}.ok{font-weight:700}table{width:100%;border-collapse:collapse;background:white}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left;font-size:13px}th{position:sticky;top:0;background:#eee}.wrap{overflow:auto;max-height:70vh}button{padding:10px 14px}</style></head><body><h1>Radar Norte — Apuração 2026</h1><div class="card"><b>Ambiente:</b> __ENV__ — DADOS DE TESTE, NÃO É PRODUÇÃO<br><b>Cargo:</b> Deputado Estadual (7)<br><b>Municípios:</b> 50<br><span id="status">Carregando…</span></div><div class="wrap"><table><thead><tr><th>Município</th><th>Estado</th><th>HTTP</th><th>Candidato</th><th>Votos</th><th>Atualização</th></tr></thead><tbody id="tb"></tbody></table></div><script>function td(v){const e=document.createElement('td');e.textContent=v==null?'':String(v);return e}async function go(){let r=await fetch('/api/latest',{cache:'no-store'});let d=await r.json();document.querySelector('#status').textContent='Última leitura: '+(d.timestamp||'sem coleta')+' | '+d.rows.length+'/50 registros';const tb=document.querySelector('#tb');tb.replaceChildren();for(const x of d.rows){const tr=document.createElement('tr');tr.append(td(x.municipio),td(x.estado),td(x.http),td(x.candidato_presente||''),td(x.votos||'—'),td((x.dg||'')+' '+(x.hg||'')));tb.appendChild(tr)}}go();setInterval(go,10000)</script></body></html>'''
    return page.replace('__ENV__', env)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/' or self.path.startswith('/index'):
            b=html().encode(); typ='text/html; charset=utf-8'
        elif self.path.startswith('/api/latest'):
            rows=latest_rows(); b=json.dumps({'timestamp':rows[0]['timestamp'] if rows else None,'rows':rows},ensure_ascii=False).encode(); typ='application/json; charset=utf-8'
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass

def serve(host,port,mock,refresh):
    select_data_dir(mock); init_db(); cycle(mock)
    def worker():
        while True:
            time.sleep(refresh)
            try: cycle(mock)
            except Exception as e: print('coleta:',e,flush=True)
    threading.Thread(target=worker,daemon=True).start()
    shown_host='127.0.0.1' if host in ('127.0.0.1','localhost') else host
    print(f'Radar Norte ativo em http://{shown_host}:{port} | mock={mock} | refresh={refresh}s',flush=True)
    ThreadingHTTPServer((host,port),H).serve_forever()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--mock',action='store_true'); p.add_argument('--once',action='store_true'); p.add_argument('--host',default='127.0.0.1',help='Interface do painel; use 0.0.0.0 somente atrás de proteção/rede controlada'); p.add_argument('--port',type=int,default=8080); p.add_argument('--refresh',type=int,default=int(CFG.get('refresh_seconds',60))); a=p.parse_args(); select_data_dir(a.mock); init_db()
    if a.once:
        rows=cycle(a.mock); print(json.dumps({'coletados':len(rows),'estados':{s:sum(1 for r in rows if r['estado']==s) for s in sorted(set(r['estado'] for r in rows))}},ensure_ascii=False,indent=2)); return
    serve(a.host,a.port,a.mock,a.refresh)
if __name__=='__main__': main()
