"""Explicit release check; missing real fixtures is a failure, never a pass.

Manifest must contain three preserved TSE bodies and independently checked
expected candidate votes, section counts and percentages with source attribution.
No converter or synthetic fixture is accepted as the original response.
"""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from coletor_actions import parse_result
from radar_norte import indicators

root=Path(__file__).parent/'fixtures/2022'
manifest=root/'esperados.json'
if not manifest.exists():
    sys.exit('PENDENTE: faltam três JSONs reais de 2022 e esperados.json com totais oficiais conferidos. Nenhuma aprovação de 2022.')
records=json.loads(manifest.read_text())
if len(records)!=3:sys.exit('PENDENTE: exigidos exatamente três arquivos reais.')
for item in records:
    body=(root/item['arquivo']).read_bytes()
    assert hashlib.sha256(body).hexdigest()==item['sha256']
    assert item['fonte_total_oficial'].startswith('https://')
    try:
        status,votes,name,party=parse_result(body,str(item['codigo_tse']),str(item['numero']),str(item['eleicao']))
    except ValueError as exc:
        sys.exit(f"INCOMPATÍVEL: {item['arquivo']} → {exc}. Documentar o layout; não converter silenciosamente.")
    assert status=='DADO_VALIDO' and votes==item['votos'] and votes>0
    metrics=indicators(json.loads(body))
    assert metrics['secoes_totalizadas']==item['secoes_totalizadas']
    assert metrics['percentual_secoes']==item['percentual_secoes']
    assert metrics['apuracao']!='NAO_INICIADA'
print('Parser: três arquivos reais passaram. Ainda executar DOM com estes estados, não com mock.')
