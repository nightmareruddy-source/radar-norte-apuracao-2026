#!/usr/bin/env python3
import argparse, csv, html as html_escape, json, os, sqlite3, tempfile, threading, time, unicodedata, urllib.request, urllib.error
from coletor_actions import parse_result, atomic_json
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).resolve().parent
CFG=json.loads((BASE/'config.json').read_text(encoding='utf-8'))
REAL_DATA=BASE/'data'; MOCK_DATA=BASE/'data_mock'
DATA=REAL_DATA; DB=None; LATEST=None; HIST=None
ATTEMPTS=None; VALID=None; STATUS=None
STATE_LOCK=threading.RLock()
URL=CFG['endpoint_template']

def select_data_dir(mock=False):
    global DATA,DB,LATEST,HIST,ATTEMPTS,VALID,STATUS
    DATA=MOCK_DATA if mock else REAL_DATA
    DATA.mkdir(exist_ok=True)
    DB=DATA/'radar.sqlite3'; LATEST=DATA/'raw_atual.csv'; HIST=DATA/'historico_apuracao.csv'
    ATTEMPTS=DATA/'ultima_tentativa.csv'; VALID=DATA/'ultimo_dado_valido.csv'; STATUS=DATA/'estado_coleta.json'
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
            raw=r.read()
            try: return r.status,json.loads(raw.decode('utf-8-sig')),''
            except (ValueError,UnicodeError): return r.status,None,'JSON_INVALIDO'
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
    if http != 200:
        row['estado']=f'HTTP_{http}' if http else 'ERRO_COLETA'; return row
    if err or not isinstance(payload,dict):
        row['estado']='JSON_INVALIDO' if err == 'JSON_INVALIDO' or not err else 'ERRO_COLETA'; return row
    row['json_valido']='SIM'
    row['municipio_confere']='SIM' if str(payload.get('cdabr',''))==str(code) else 'NÃO'
    row['dg']=payload.get('dg',''); row['hg']=payload.get('hg',''); row['tf']=payload.get('tf','')
    target=str(CFG.get('candidate_number','70255'))
    try:
        state,votes,name,party=parse_result(json.dumps(payload).encode(),str(code),target,CFG['election_code'])
    except ValueError as exc:
        row.update(estado=str(exc),erro=str(exc)); return row
    row.update(cargo7_confere='SIM',schema_confere='SIM',numero=target)
    if state=='DADO_VALIDO':
        hit=next(c for c,p in extract_candidates(find_cargo7(payload)) if str(c.get('n','')).strip()==target)
        row.update(candidato_presente='SIM',candidato=name,partido=party,votos=votes,
                   pct_candidato=hit.get('pvap',''),estado=state)
    else: row.update(candidato_presente='NÃO',estado='CANDIDATO_AUSENTE_NO_SIMULADO')
    return row

def indicators(payload):
    """Optional section counts; invalid or missing values remain unknown."""
    def integer(x):
        text=str(x)
        return int(text) if text.isascii() and text.isdigit() else None
    sec=payload.get('s',{}) if isinstance(payload,dict) else {}
    votes=payload.get('v',{}) if isinstance(payload,dict) else {}
    sec=sec if isinstance(sec,dict) else {}
    votes=votes if isinstance(votes,dict) else {}
    total,done=integer(sec.get('ts')),integer(sec.get('st'))
    if total is None or done is None or total<=0 or done>total:
        total=done=None
    return {'secoes_total':total,'secoes_totalizadas':done,
            'percentual_secoes':round(100*done/total,2) if total else None,
            'votos_validos':integer(votes.get('vv')),
            'apuracao':'SECOES_TOTALIZADAS' if total and done==total else 'PARCIAL' if total else 'INDEFINIDO'}

def mock_payload(mun,code):
    return {'ele':CFG['election_code'],'cdabr':str(code),'dg':'22/09/2026','hg':'15:00:00','tf':'n','carg':[{'cd':'7','agr':[{'par':[{'sg':'FICT','cand':[{'n':'99999','nm':'CANDIDATO FICTÍCIO','vap':'123','pvap':'1,23'}]}]}]}]}

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
    with STATE_LOCK:
        return _save(rows)

def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig') as stream: return list(csv.DictReader(stream))

def municipalities():
    return [(x[0],str(x[1])) if isinstance(x,(list,tuple)) else (x['name'],str(x['code'])) for x in CFG['municipalities']]

def ensure_context():
    context={key:CFG.get(key) for key in ('environment','election_code','cargo_code','candidate_number','endpoint_template')}
    context['municipalities']=[list(x) for x in municipalities()]
    path=DATA/'contexto_validacao.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=context:
            raise ValueError('Configuração mudou: use uma pasta de dados separada para este contexto')
    elif VALID.exists():
        raise ValueError('Dados validados sem identificação do contexto; mantenha-os isolados')
    else: atomic_json(path,context)

def _save(rows):
    ensure_context()
    expected={code for name,code in municipalities()}
    if len(expected)!=len(CFG['municipalities']): raise ValueError('Códigos municipais duplicados na configuração')
    codes=[str(r['codigo_municipio']) for r in rows]
    if len(set(codes))!=len(codes) or not set(codes)<=expected:
        raise ValueError('Municípios duplicados ou não configurados no ciclo')
    acceptable={'DADO_VALIDO','CANDIDATO_AUSENTE_NO_SIMULADO'}
    schema_errors={'JSON_INVALIDO','SCHEMA_DIVERGENTE','CARGO_DIVERGENTE','MUNICIPIO_DIVERGENTE','ELEICAO_DIVERGENTE','CANDIDATO_DUPLICADO','VOTOS_INVALIDOS'}
    good=sum(r['estado'] in acceptable for r in rows)
    threshold=int(CFG.get('min_municipios_ok_to_overwrite',len(expected)))
    if not 1<=threshold<=len(expected): raise ValueError('Limite de municípios válidos inválido')
    reasons=[]
    if set(codes)!=expected: reasons.append('CICLO_INCOMPLETO')
    if good<threshold: reasons.append('MUNICIPIOS_VALIDOS_INSUFICIENTES')
    if any(r['estado'] in schema_errors for r in rows): reasons.append('FORMATO_OU_CONTEUDO_DIVERGENTE')
    if any(r['estado'] in ('HTTP_403','HTTP_429') for r in rows): reasons.append('ACESSO_BLOQUEADO')
    allowed=not reasons
    # The old snapshot remains on disk. Only this version's validated store feeds the panel.
    previous={r['codigo_municipio']:r for r in read_csv(VALID)}
    updated=[]
    if allowed:
        for r in rows:
            if r['estado']=='DADO_VALIDO':
                previous[str(r['codigo_municipio'])]=r; updated.append(str(r['codigo_municipio']))
    valid_rows=[previous[code] for name,code in municipalities() if code in previous]
    publish_latest=allowed and len(valid_rows)==len(expected) and bool(updated)
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
    atomic_write_csv(ATTEMPTS,rows)
    if allowed and updated: atomic_write_csv(VALID,valid_rows)
    if publish_latest: atomic_write_csv(LATEST,valid_rows)
    atomic_json(STATUS,{'timestamp':now(),'esperados':len(expected),'consultados':len(rows),
                       'respostas_validas':good,'limite_minimo':threshold,'bloqueada':not allowed,
                       'motivos':reasons,'municipios_atualizados':updated,
                       'dados_validos_guardados':len(valid_rows),'snapshot_publicado':publish_latest})
    return publish_latest

def cycle(mock=False):
    select_data_dir(mock)
    init_db()
    rows=[]; metrics={}
    for index,item in enumerate(CFG['municipalities']):
        if isinstance(item, (list, tuple)):
            mun, code = item[0], str(item[1])
        else:
            mun, code = item['name'], str(item['code'])
        if mock: status,payload,err=200,mock_payload(mun,code),''
        else: status,payload,err=fetch(URL.format(code=code))
        row=parse_one(mun,code,payload,status,err); rows.append(row)
        if row['estado'] in ('DADO_VALIDO','CANDIDATO_AUSENTE_NO_SIMULADO'):
            metrics[code]={'tentativa_em':row['timestamp'],**indicators(payload)}
        if not mock and status in (403,429):
            # Stop safely; never fill remaining municipalities with zero.
            break
        if not mock and index<len(CFG['municipalities'])-1: time.sleep(max(2.5,float(CFG.get('request_interval_seconds',2.5))))
    with STATE_LOCK:
        save(rows)
        atomic_json(DATA/'indicadores_municipais.json',metrics)
    return rows

def latest_rows():
    return read_csv(LATEST)

def api_state():
    with STATE_LOCK:
        ensure_context()
        attempts={r['codigo_municipio']:r for r in read_csv(ATTEMPTS)}
        valid=read_csv(VALID)
        saved={r['codigo_municipio']:r for r in valid}
        status=json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
        metric_path=DATA/'indicadores_municipais.json'
        metrics=json.loads(metric_path.read_text()) if metric_path.exists() else {}
        display=[]
        for name,code in municipalities():
            attempt=attempts.get(code,{})
            last=saved.get(code,{})
            fresh=code in status.get('municipios_atualizados',[]) and not status.get('bloqueada',False)
            metric=metrics.get(code,{})
            if metric.get('tentativa_em')!=attempt.get('timestamp'): metric={}
            display.append({**metric,'geracao_tentativa_tse':(' '.join([attempt.get('dg',''),attempt.get('hg','')])).strip(),'municipio':name,'codigo_municipio':code,
                            'estado_tentativa':attempt.get('estado','NAO_CONSULTADO'),
                            'http':attempt.get('http',''),'tentativa_em':attempt.get('timestamp'),
                            'votos':int(last['votos']) if last else None,
                            'dado_valido_em':last.get('timestamp'),
                            'candidato':last.get('candidato',''),
                            'preservado':bool(last) and not fresh,
                            'atualizacao_tse':(' '.join([last.get('dg',''),last.get('hg','')])).strip()})
        return {'timestamp':status.get('timestamp'),'rows':valid,'tentativas':list(attempts.values()),
                'coleta':status,'municipios':display}

def html():
    page=(BASE/'painel.html').read_text(encoding='utf-8')
    return page.replace('__ENV__',html_escape.escape(CFG.get('environment','SIMULADO_TSE_2026'))).replace('__NUMERO__',html_escape.escape(str(CFG['candidate_number'])))

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/' or self.path.startswith('/index'):
            b=html().encode(); typ='text/html; charset=utf-8'
        elif self.path.startswith('/api/latest'):
            b=json.dumps(api_state(),ensure_ascii=False).encode(); typ='application/json; charset=utf-8'
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass

def serve(host,port,mock,refresh):
    select_data_dir(mock); init_db()
    def worker():
        while True:
            try: cycle(mock)
            except Exception as e: print('coleta:',e,flush=True)
            time.sleep(refresh)
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
