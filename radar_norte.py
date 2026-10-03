#!/usr/bin/env python3
import hashlib, argparse, csv, html as html_escape, json, os, sqlite3, tempfile, threading, time, unicodedata, urllib.request, urllib.error
from coletor_actions import parse_result, atomic_json
from datetime import datetime, timezone
from contextlib import closing
from evidencias import salvar_se_mudou
from transporte_tse import request_bytes
from urllib.parse import urlsplit
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).resolve().parent
CFG=json.loads((BASE/os.environ.get('RADAR_CONFIG','config.json')).read_text(encoding='utf-8'))
REAL_DATA=Path(os.environ.get('RADAR_DATA_DIR',str(BASE/'data'))); MOCK_DATA=BASE/'data_mock'
MOCK_MODE=False
REFRESH=300
STARTED=time.time()
DATA=REAL_DATA; DB=None; LATEST=None; HIST=None
ATTEMPTS=None; VALID=None; STATUS=None
STATE_LOCK=threading.RLock()
URL=CFG['endpoint_template']

def select_data_dir(mock=False):
    global DATA,DB,LATEST,HIST,ATTEMPTS,VALID,STATUS,MOCK_MODE
    MOCK_MODE=mock
    context={k:CFG.get(k) for k in ('environment','election_code','cargo_code','candidate_number','endpoint_template','municipalities')}
    digest=hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest()[:16]
    DATA=(MOCK_DATA if mock else REAL_DATA)/digest
    DATA.mkdir(parents=True,exist_ok=True)
    DB=DATA/'radar.sqlite3'; LATEST=DATA/'raw_atual.csv'; HIST=DATA/'historico_apuracao.csv'
    ATTEMPTS=DATA/'ultima_tentativa.csv'; VALID=DATA/'ultimo_dado_valido.csv'; STATUS=DATA/'estado_coleta.json'
FIELDS=['timestamp','municipio','codigo_municipio','http','json_valido','municipio_confere','cargo7_confere','schema_confere','candidato_presente','candidato','numero','partido','votos','pct_candidato','dg','hg','tf','estado','source_url','erro']

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD',str(s or '')) if unicodedata.category(c)!='Mn').upper().strip()

def now(): return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')

def init_db():
    if DB is None: select_data_dir(False)
    with closing(sqlite3.connect(DB)) as c, c:
        c.execute('''create table if not exists snapshots(id integer primary key, timestamp text, municipio text, codigo text, estado text, votos integer, payload text)''')
        c.execute('create index if not exists ix_snap_mun on snapshots(municipio,timestamp)')

def record_response(url,status,raw,headers,started,error=''):
    # Use TSE municipality code (not IBGE) plus URL identity. A different
    # endpoint must not share a municipality observation stream by accident.
    match=re.search(r'/pr([0-9]{5})-c0007-',urlsplit(url).path)
    code=match.group(1) if match else 'outro'
    key=code+'-'+hashlib.sha256(url.encode()).hexdigest()[:16]
    return salvar_se_mudou(DATA/'evidencias',key,raw,meta={
        'url':url,'codigo_tse':code,'http':status,'inicio':started,'fim':now(),
        'headers':dict(headers),'erro':error})

def fetch(url,timeout=10):
    started=now()
    try:
        status,raw,headers=request_bytes(url,timeout)
        record_response(url,status,raw,headers,started)
        if status!=200: return status,None,f'HTTP {status}'
        try: return status,json.loads(raw.decode('utf-8-sig')),''
        except (ValueError,UnicodeError): return status,None,'JSON_INVALIDO'
    except urllib.error.HTTPError as e:
        record_response(url,e.code,b'',e.headers,started,str(e))
        return e.code,None,str(e)
    except Exception as e:
        error=f'{type(e).__name__}: {e}'
        record_response(url,0,b'',{},started,error)
        return 0,None,error

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
    if CFG['environment']=='OFICIAL_TSE_2026' and not MOCK_MODE and payload.get('f')!='o':
        row.update(estado='FASE_DIVERGENTE',erro='Esperado arquivo de fase oficial (f=o)');return row
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
    else: row.update(candidato_presente='NÃO',estado='CANDIDATO_AUSENTE_OFICIAL' if CFG['environment']=='OFICIAL_TSE_2026' else 'CANDIDATO_AUSENTE_NO_SIMULADO')
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
    counted=integer(sec.get('sa'))
    if total is None or counted is None or counted>total: counted=None
    return {'secoes_total':total,'secoes_totalizadas':done,
            'percentual_secoes':round(100*done/total,2) if total else None,
            'votos_validos':integer(votes.get('vv')),
            'secoes_apuradas':counted,
            'tf':payload.get('tf'),'andamento':payload.get('and'),
            'apuracao':'NAO_INICIADA' if payload.get('and')=='n' else 'FINAL' if payload.get('tf')=='s' and total and done==total else 'PARCIAL' if total else 'INDEFINIDO'}

def mock_payload(mun,code):
    return {'ele':CFG['election_code'],'cdabr':str(code),'dg':'22/09/2026','hg':'15:00:00','tf':'n','and':'p','s':{'ts':'100','st':'25','sa':'25'},'v':{'vv':'1000'},'carg':[{'cd':'7','agr':[{'par':[{'sg':'FICT','cand':[{'n':str(CFG['candidate_number']),'nm':'DEMONSTRAÇÃO — VOTOS FICTÍCIOS','vap':'123','pvap':'1,23'}]}]}]}]}

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

def save(rows,metrics=None):
    with STATE_LOCK:
        return _save(rows,metrics)

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

def _save(rows,metrics=None):
    ensure_context()
    expected={code for name,code in municipalities()}
    if len(expected)!=len(CFG['municipalities']): raise ValueError('Códigos municipais duplicados na configuração')
    codes=[str(r['codigo_municipio']) for r in rows]
    if len(set(codes))!=len(codes) or not set(codes)<=expected:
        raise ValueError('Municípios duplicados ou não configurados no ciclo')
    acceptable={'DADO_VALIDO','CANDIDATO_AUSENTE_NO_SIMULADO','CANDIDATO_AUSENTE_OFICIAL'}
    schema_errors={'FASE_DIVERGENTE','JSON_INVALIDO','SCHEMA_DIVERGENTE','CARGO_DIVERGENTE','MUNICIPIO_DIVERGENTE','ELEICAO_DIVERGENTE','CANDIDATO_DUPLICADO','VOTOS_INVALIDOS'}
    good=sum(r['estado'] in acceptable for r in rows)
    threshold=max(2,int(CFG.get('schema_error_limit',3)))
    reasons=[]
    if not good: reasons.append('SEM_RESPOSTA_VALIDA')
    if sum(r['estado'] in schema_errors for r in rows)>=threshold: reasons.append('FORMATO_OU_CONTEUDO_DIVERGENTE')
    if any(r['estado'] in ('HTTP_403','HTTP_429') for r in rows): reasons.append('ACESSO_BLOQUEADO')
    allowed=not reasons
    bundle_path=DATA/'snapshot.json'
    old=json.loads(bundle_path.read_text()) if bundle_path.exists() else {}
    previous={r['codigo_municipio']:r for r in old.get('rows',[])}
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
    with closing(sqlite3.connect(DB)) as c, c:
        for r in rows:
            v=None
            try: v=int(r['votos']) if str(r['votos']).strip() else None
            except: pass
            c.execute('insert into snapshots(timestamp,municipio,codigo,estado,votos,payload) values(?,?,?,?,?,?)',(r['timestamp'],r['municipio'],r['codigo_municipio'],r['estado'],v,json.dumps(r,ensure_ascii=False)))
    atomic_write_csv(ATTEMPTS,rows)
    if allowed and updated: atomic_write_csv(VALID,valid_rows)
    if publish_latest: atomic_write_csv(LATEST,valid_rows)
    status={'timestamp':now(),'esperados':len(expected),'consultados':len(rows),
            'respostas_validas':good,'limite_erros_formato':threshold,'bloqueada':not allowed,
            'motivos':reasons,'municipios_atualizados':updated,
            'dados_validos_guardados':len(valid_rows),'snapshot_publicado':publish_latest}
    atomic_json(STATUS,status)
    # One atomic file is the source of truth for API votes, status and indicators.
    # CSVs remain compatible exports; an interrupted export never mixes API generations.
    atomic_json(bundle_path,{'rows':valid_rows,'tentativas':rows,'coleta':status,'metrics':metrics or {}})
    return publish_latest

def cycle(mock=False):
    select_data_dir(mock)
    init_db()
    rows=[]; metrics={}; started=time.monotonic()
    for index,item in enumerate(CFG['municipalities']):
        if not mock and time.monotonic()-started>float(CFG.get('cycle_budget_seconds',600)): break
        if isinstance(item, (list, tuple)):
            mun, code = item[0], str(item[1])
        else:
            mun, code = item['name'], str(item['code'])
        if mock: status,payload,err=200,mock_payload(mun,code),''
        else: status,payload,err=fetch(URL.format(code=code))
        row=parse_one(mun,code,payload,status,err); rows.append(row)
        if row['estado'] in ('DADO_VALIDO','CANDIDATO_AUSENTE_NO_SIMULADO','CANDIDATO_AUSENTE_OFICIAL'):
            metrics[code]={'tentativa_em':row['timestamp'],**indicators(payload)}
        if not mock and status in (403,429):
            # Stop safely; never fill remaining municipalities with zero.
            break
        if not mock and index<len(CFG['municipalities'])-1: time.sleep(max(2.5,float(CFG.get('request_interval_seconds',2.5))))
    with STATE_LOCK:
        save(rows,metrics)
    return rows

def latest_rows():
    return read_csv(LATEST)

def api_state():
    with STATE_LOCK:
        ensure_context()
        bundle_path=DATA/'snapshot.json'
        bundle=json.loads(bundle_path.read_text()) if bundle_path.exists() else {}
        attempts={r['codigo_municipio']:r for r in bundle.get('tentativas',[])}
        valid=bundle.get('rows',[])
        saved={r['codigo_municipio']:r for r in valid}
        status=bundle.get('coleta',{})
        metrics=bundle.get('metrics',{})
        worker_path=DATA/'worker.json'
        worker=json.loads(worker_path.read_text()) if worker_path.exists() else {}
        stale_limit=900
        checked_at=time.time()
        def age(stamp):
            try:return max(0,checked_at-datetime.fromisoformat(stamp).timestamp())
            except (ValueError,TypeError):return None
        cycle_age=age(worker.get('inicio')) if worker.get('em_coleta') else None
        worker_stalled=cycle_age is not None and cycle_age>stale_limit
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
                            'desatualizado':bool(last) and (age(last.get('timestamp')) is None or age(last.get('timestamp'))>stale_limit),
                            'atualizacao_tse':(' '.join([last.get('dg',''),last.get('hg','')])).strip()})
        allfresh=len(valid)==len(display) and all(not r['preservado'] and not r['desatualizado'] for r in display)
        states=[r.get('apuracao','INDEFINIDO') for r in display]
        aggregate='NAO_INICIADA' if all(x=='NAO_INICIADA' for x in states) else 'FINAL' if allfresh and all(x=='FINAL' for x in states) else 'PARCIAL'
        if not valid: aggregate='SEM_DADOS'
        sections=[r for r in display if r.get('secoes_total') is not None and r.get('secoes_totalizadas') is not None]
        sections_complete=len(sections)==len(display)
        # Failed attempts must never reset the age of validated votes.
        stale=age(status.get('timestamp'))
        stale_alarm=worker_stalled or (not valid and time.time()-STARTED>stale_limit) or any(r['desatualizado'] for r in display) or (stale>stale_limit if stale is not None else time.time()-STARTED>stale_limit)
        return {'timestamp':status.get('timestamp'),'rows':valid,'tentativas':list(attempts.values()),
                'coleta':status,'municipios':display,'worker':worker,
                'ambiente':'DEMONSTRACAO' if MOCK_MODE else CFG['environment'],
                'eleicao':CFG['election_code'],'numero':CFG['candidate_number'],
                'alarme_desatualizacao':stale_alarm,
                'limite_atraso_segundos':stale_limit,
                'verificado_em':datetime.fromtimestamp(checked_at,timezone.utc).isoformat(),
                'coleta_prolongada':worker_stalled,'duracao_coleta_segundos':cycle_age,
                'timeout_requisicao_segundos':10,'limite_espera_bloqueio_segundos':1200,
                'resumo':{'soma_ultimos_dados':sum(int(r['votos']) for r in valid) if valid else None,
                          'secoes_total':sum(r['secoes_total'] for r in sections) if sections_complete else None,
                          'secoes_totalizadas':sum(r['secoes_totalizadas'] for r in sections) if sections_complete else None,
                          'municipios_com_secoes':len(sections),'secoes_cobertura_completa':sections_complete,
                          'municipios_com_votos':len(valid),'municipios_atuais':sum(r['votos'] is not None and not r['preservado'] and not r['desatualizado'] for r in display),
                          'total_atual_completo':allfresh,'apuracao':aggregate}}


def html():
    page=(BASE/'painel.html').read_text(encoding='utf-8')
    return page.replace('__ENV__',html_escape.escape('DEMONSTRAÇÃO — VOTOS FICTÍCIOS' if MOCK_MODE else CFG.get('environment','SIMULADO_TSE_2026'))).replace('__NUMERO__',html_escape.escape(str(CFG['candidate_number'])))

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/' or self.path.startswith('/index'):
            b=html().encode(); typ='text/html; charset=utf-8'
        elif self.path=='/api/latest':
            try: state=api_state()
            except Exception as exc:
                self.send_response(503); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps({'erro':'CONFIGURACAO_OU_DADOS','mensagem':str(exc)}).encode()); return
            b=json.dumps(state,ensure_ascii=False).encode(); typ='application/json; charset=utf-8'
        elif self.path=='/api/history':
            with closing(sqlite3.connect(DB)) as db, db:
                records=db.execute('select payload from snapshots order by id desc limit 200').fetchall()
            b=json.dumps([json.loads(r[0]) for r in records],ensure_ascii=False).encode(); typ='application/json; charset=utf-8'
        elif self.path=='/historico.csv':
            with STATE_LOCK: b=HIST.read_bytes() if HIST.exists() else b''
            typ='text/csv; charset=utf-8'
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass

def next_delay(rows,streak,refresh):
    blocked=any(r['estado'] in ('HTTP_403','HTTP_429') for r in rows)
    streak=streak+1 if blocked else 0
    return (min(1200,600*2**min(streak-1,1)) if blocked else max(10,refresh)),streak

def worker_loop(mock,refresh):
    path=DATA/'worker.json'
    state=json.loads(path.read_text()) if path.exists() else {}
    streak=int(state.get('bloqueios_consecutivos',0))
    # Start immediately unless a persisted access-block cooldown is still active.
    # Restarting must never bypass a 403/429 backoff.
    if not streak: state['proxima_tentativa_epoch']=0
    elif state.get('fim'):
        finished=datetime.fromisoformat(state['fim']).timestamp()
        state['proxima_tentativa_epoch']=min(float(state.get('proxima_tentativa_epoch',0)),finished+1200)
    while True:
        remaining=max(0,float(state.get('proxima_tentativa_epoch',0))-time.time())
        if remaining>0:
            time.sleep(min(60,remaining)); continue
        started_epoch=time.time()
        state={'em_coleta':True,'inicio':now(),'inicio_epoch':started_epoch,
               'intervalo_segundos':max(10,refresh),'bloqueios_consecutivos':streak}
        atomic_json(path,state)
        try:
            rows=cycle(mock)
            delay,streak=next_delay(rows,streak,refresh)
            # No overlap or catch-up burst: long cycles wait at least 10 seconds.
            deadline=time.time()+delay if streak else max(started_epoch+delay,time.time()+10)
            state.update(erro=None)
        except Exception as exc:
            delay=max(60,refresh);deadline=time.time()+delay;state.update(erro=type(exc).__name__+': '+str(exc))
            print('coleta:',exc,flush=True)
        state.update(em_coleta=False,fim=now(),proxima_tentativa_epoch=deadline,bloqueios_consecutivos=streak)
        atomic_json(path,state)
        print('ciclo_concluido',json.dumps(state,ensure_ascii=False),flush=True)

def serve(host,port,mock,refresh):
    global REFRESH
    REFRESH=refresh
    select_data_dir(mock); init_db()
    threading.Thread(target=worker_loop,args=(mock,refresh),daemon=True).start()
    print(f'Radar Norte ativo | mock={mock} | refresh={refresh}s',flush=True)
    ThreadingHTTPServer((host,port),H).serve_forever()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--mock',action='store_true'); p.add_argument('--once',action='store_true'); p.add_argument('--host',default='127.0.0.1',help='Interface do painel; use 0.0.0.0 somente atrás de proteção/rede controlada'); p.add_argument('--port',type=int,default=8080); p.add_argument('--refresh',type=int,default=int(CFG.get('refresh_seconds',60))); a=p.parse_args(); select_data_dir(a.mock); init_db()
    if a.once:
        rows=cycle(a.mock); print(json.dumps({'coletados':len(rows),'estados':{s:sum(1 for r in rows if r['estado']==s) for s in sorted(set(r['estado'] for r in rows))}},ensure_ascii=False,indent=2)); return
    serve(a.host,a.port,a.mock,a.refresh)
if __name__=='__main__': main()
