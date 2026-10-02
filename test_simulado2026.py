"""Regression from original TSE simulation responses, never production votes."""
import gzip,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import radar_norte as r

FIX=Path(__file__).parent/'test/fixtures/simulado2026'
EXPECTED=[('Ibiporã','75914',44,119,32744),('Londrina','76678',330,1181,322014),('Cambé','74713',57,221,61685)]

def fixture_state():
    config=json.loads((r.BASE/'config.json').read_text())
    config.update(candidate_number='68028',municipalities=[[name,code] for name,code,*_ in EXPECTED])
    with tempfile.TemporaryDirectory() as tmp,patch.object(r,'CFG',config),patch.object(r,'REAL_DATA',Path(tmp)),patch.object(r,'URL',config['endpoint_template']):
        r.select_data_dir(False);r.init_db();rows=[];metrics={}
        for name,code,*_ in EXPECTED:
            payload=json.loads(gzip.decompress((FIX/f'pr{code}.json.gz').read_bytes()))
            row=r.parse_one(name,code,payload);rows.append(row)
            metrics[code]={'tentativa_em':row['timestamp'],**r.indicators(payload)}
        r.save(rows,metrics)
        return r.api_state()

class Simulado2026Tests(unittest.TestCase):
    def test_original_responses_same_parser_and_sections(self):
        s=fixture_state()
        self.assertEqual(s['resumo']['soma_ultimos_dados'],431)
        self.assertEqual(s['resumo']['apuracao'],'FINAL')
        for row,(name,code,votes,sections,vv) in zip(s['municipios'],EXPECTED):
            meta=json.loads((FIX/f'pr{code}.meta.json').read_text())
            raw=gzip.decompress((FIX/f'pr{code}.json.gz').read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['sha256'])
            self.assertEqual(meta['http'],200)
            self.assertEqual(row['votos'],votes)
            self.assertEqual((row['secoes_totalizadas'],row['secoes_total']),(sections,sections))
            self.assertEqual(row['percentual_secoes'],100)
            self.assertEqual(row['votos_validos'],vv)

    def test_monitored_candidate_absence_is_not_zero(self):
        from coletor_actions import parse_result
        for _,code,*_ in EXPECTED:
            result=parse_result(gzip.decompress((FIX/f'pr{code}.json.gz').read_bytes()),code,'70255','21272')
            self.assertNotEqual(result[0],'DADO_VALIDO')
            self.assertNotEqual(result[1],0)
