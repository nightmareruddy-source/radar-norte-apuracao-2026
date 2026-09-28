#!/usr/bin/env python3
"""Auditoria isolada da simulação TSE. Nunca abre os arquivos da Central."""
import argparse
import csv
import hashlib
import json
import os
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))
OUT = BASE / 'simulacao' / 'auditoria'
FIELDS = ['municipio', 'codigo_tse', 'url', 'http', 'estado', 'votos',
          'candidato', 'partido', 'sha256', 'arquivo_bruto', 'erro']


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value))
                   if unicodedata.category(c) != 'Mn').upper().strip()


def request(url, timeout=25):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'RadarNorte-Auditoria/2.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read()


def parse_result(body, code, number):
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('JSON_INVALIDO') from exc
    if not isinstance(data, dict) or str(data.get('cdabr', '')) != str(code):
        raise ValueError('MUNICIPIO_DIVERGENTE')
    cargos = data.get('carg')
    if not isinstance(cargos, list):
        raise ValueError('SCHEMA_DIVERGENTE')
    matches = [x for x in cargos if isinstance(x, dict) and
               str(x.get('cd', '')).zfill(4) == '0007']
    if len(matches) != 1:
        raise ValueError('CARGO_DIVERGENTE')
    agrs = matches[0].get('agr')
    if not isinstance(agrs, list) or not agrs:
        raise ValueError('SCHEMA_DIVERGENTE')
    candidates = []
    party_count = 0
    for agr in agrs:
        if not isinstance(agr, dict) or not isinstance(agr.get('par'), list):
            raise ValueError('SCHEMA_DIVERGENTE')
        for par in agr['par']:
            if not isinstance(par, dict) or not isinstance(par.get('cand'), list):
                raise ValueError('SCHEMA_DIVERGENTE')
            party_count += 1
            for cand in par['cand']:
                if not isinstance(cand, dict):
                    raise ValueError('SCHEMA_DIVERGENTE')
                if str(cand.get('n', '')).strip() == number:
                    candidates.append((cand, par.get('sg', '')))
    if not party_count:
        raise ValueError('SCHEMA_DIVERGENTE')
    if not candidates:
        return 'CANDIDATO_AUSENTE', None, '', ''
    if len(candidates) != 1:
        raise ValueError('CANDIDATO_DUPLICADO')
    cand, party = candidates[0]
    votes = cand.get('vap')
    if isinstance(votes, bool) or not str(votes).isdigit():
        raise ValueError('VOTOS_INVALIDOS')
    return 'DADO_VALIDO', int(votes), cand.get('nmu') or cand.get('nm') or '', party


def codes_from_ea12(body):
    doc = json.loads(body)
    prs = [x for x in doc['abr'] if x.get('cd') == 'pr']
    if len(prs) != 1 or not isinstance(prs[0].get('mu'), list):
        raise ValueError('EA12_SEM_PARANA')
    records = prs[0]['mu']
    by_name = {normalize(x['nm']): str(x['cd']) for x in records}
    if len(by_name) != len(records):
        raise ValueError('EA12_NOMES_DUPLICADOS')
    return by_name


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_config():
    municipalities = CFG['municipalities']
    if (len(municipalities) != 50 or
        len({x[0] for x in municipalities}) != 50 or
        len({str(x[1]) for x in municipalities}) != 50):
        raise ValueError('CONFIG_50_INVALIDA')
    if (CFG.get('environment') != 'SIMULADO_TSE_2026' or
        not CFG['endpoint_template'].startswith(
            'https://resultados-sim.tse.jus.br/simulado/simulado2026/')):
        raise ValueError('AMBIENTE_NAO_SIMULADO')


def audit(limit=50, transport=request, interval=None, out=OUT):
    validate_config()
    limit = min(limit, 50)
    if limit < 1:
        raise ValueError('LIMITE_INVALIDO')
    interval = max(2.5, float(CFG.get('request_interval_seconds', 2.5))
                   if interval is None else float(interval))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run = out / stamp
    raw = run / 'raw'
    raw.mkdir(parents=True)
    rows = []
    ea12 = {'estado': 'ERRO_COLETA', 'erro': ''}
    try:
        status, body = transport(CFG['municipality_config_url'])
        (raw / 'ea12.json').write_bytes(body)
        ea12['sha256'] = hashlib.sha256(body).hexdigest()
        if status != 200:
            raise ValueError(f'HTTP_{status}')
        codes = codes_from_ea12(body)
        mismatches = [{'municipio': name, 'config': str(code), 'ea12': codes.get(normalize(name))}
                      for name, code in CFG['municipalities']
                      if codes.get(normalize(name)) != str(code)]
        ea12.update(estado='VALIDO' if not mismatches else 'CODIGOS_DIVERGENTES',
                    confirmados=50 - len(mismatches), divergencias=mismatches)
    except Exception as exc:
        ea12['erro'] = f'{type(exc).__name__}: {exc}'

    # Rejeita os endpoints se a configuração de códigos não for comprovada.
    if ea12['estado'] == 'VALIDO':
        for index, (name, code) in enumerate(CFG['municipalities'][:limit], 1):
            url = CFG['endpoint_template'].format(code=code)
            row = {field: '' for field in FIELDS}
            row.update(municipio=name, codigo_tse=str(code), url=url,
                       estado='ERRO_COLETA')
            try:
                status, body = transport(url)
                row['http'] = status
                filename = f'{index:02d}_{code}.json'
                (raw / filename).write_bytes(body)
                row['arquivo_bruto'] = f'raw/{filename}'
                row['sha256'] = hashlib.sha256(body).hexdigest()
                if status != 200:
                    row['estado'] = f'HTTP_{status}'
                else:
                    state, votes, candidate, party = parse_result(
                        body, code, str(CFG['candidate_number']))
                    row.update(estado=state, votos=votes if votes is not None else '',
                               candidato=candidate, partido=party)
            except urllib.error.HTTPError as exc:
                row.update(http=exc.code, estado=f'HTTP_{exc.code}', erro=str(exc)[:250])
            except ValueError as exc:
                row.update(estado=str(exc), erro=str(exc))
            except Exception as exc:
                row.update(estado='ERRO_COLETA', erro=f'{type(exc).__name__}: {exc}'[:250])
            rows.append(row)
            if row['estado'] in ('HTTP_403', 'HTTP_429'):
                break
            if index < limit and transport is request:
                time.sleep(interval)

    with (run / 'tentativas.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {'ambiente': CFG['environment'], 'esperados': 50,
               'consultados': len(rows), 'ea12': ea12,
               'estados': dict(Counter(x['estado'] for x in rows)),
               'completo': limit == 50 and len(rows) == 50 and
                           all(x['estado'] in ('DADO_VALIDO', 'CANDIDATO_AUSENTE') for x in rows)}
    atomic_json(run / 'resumo.json', summary)
    # Última tentativa é um arquivo separado do último dado validado.
    atomic_json(out / 'ultima_tentativa.json', {'execucao': stamp, 'resumo': summary,
                                                'municipios': rows})
    valid_path = out / 'ultimo_dado_valido.json'
    previous = json.loads(valid_path.read_text(encoding='utf-8')) if valid_path.exists() else {}
    for row in rows:
        if row['estado'] == 'DADO_VALIDO':
            previous[str(row['codigo_tse'])] = {'execucao': stamp, **row}
    if previous:
        atomic_json(valid_path, previous)
    return run, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, choices=(2, 50), default=50)
    args = parser.parse_args()
    directory, result = audit(args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(directory)
    raise SystemExit(0 if result['completo'] else 2)
