import copy
import csv
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import radar_norte as radar


class PainelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patches=[patch.object(radar,'REAL_DATA',self.root/'data'),
                      patch.object(radar,'MOCK_DATA',self.root/'mock')]
        for p in self.patches: p.start()
        radar.select_data_dir(False); radar.init_db()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def payload(self,code,votes=9):
        return {'ele':radar.CFG['election_code'],'cdabr':code,'dg':'28/09/2026','hg':'16:00:00','tf':'n',
                'carg':[{'cd':'7','agr':[{'par':[{'sg':'TESTE','cand':[
                    {'n':'70255','nmu':'CANDIDATO DE TESTE','vap':str(votes)}]}]}]}]}

    def rows(self,votes=9):
        return [radar.parse_one(name,code,self.payload(code,votes)) for name,code in radar.municipalities()]

    def baseline(self):
        radar.save(self.rows())
        return radar.LATEST.read_bytes(),radar.VALID.read_bytes()

    def test_full_cycle_zero_absence_and_new_votes(self):
        rows=self.rows();rows[0]=radar.parse_one(*radar.municipalities()[0],self.payload('75914',0))
        self.assertTrue(radar.save(rows))
        self.assertEqual(radar.api_state()['municipios'][0]['votos'],0)
        rows=self.rows(22)
        absent=self.payload('75914');absent['carg'][0]['agr'][0]['par'][0]['cand']=[]
        rows[0]=radar.parse_one('Ibiporã','75914',absent)
        self.assertTrue(radar.save(rows))
        state=radar.api_state();first=state['municipios'][0]
        self.assertEqual(first['votos'],0)
        self.assertTrue(first['preservado'])
        self.assertEqual(first['estado_tentativa'],'CANDIDATO_AUSENTE_NO_SIMULADO')
        self.assertEqual(state['municipios'][1]['votos'],22)
        self.assertFalse(state['municipios'][1]['preservado'])
        self.assertEqual(len(radar.latest_rows()),50)

    def test_all_failures_preserve_snapshot_byte_for_byte(self):
        snapshot,valid=self.baseline()
        rows=[radar.parse_one(name,code,None,503,'HTTP 503') for name,code in radar.municipalities()]
        self.assertFalse(radar.save(rows))
        self.assertEqual(snapshot,radar.LATEST.read_bytes())
        self.assertEqual(valid,radar.VALID.read_bytes())
        state=radar.api_state()
        self.assertTrue(state['coleta']['bloqueada'])
        self.assertTrue(all(r['votos']=='' for r in state['tentativas']))
        self.assertTrue(all(r['preservado'] for r in state['municipios']))
        with sqlite3.connect(radar.DB) as db:
            self.assertEqual(db.execute('select count(*) from snapshots where estado="HTTP_503" and votos is null').fetchone()[0],50)

    def test_schema_change_blocks_entire_cycle(self):
        snapshot,valid=self.baseline()
        rows=self.rows(99)
        broken=self.payload('75914');del broken['carg'][0]['agr'][0]['par'][0]['cand']
        rows[0]=radar.parse_one('Ibiporã','75914',broken)
        with patch.dict(radar.CFG,{'min_municipios_ok_to_overwrite':1}):
            self.assertFalse(radar.save(rows))
        self.assertEqual(snapshot,radar.LATEST.read_bytes())
        self.assertEqual(valid,radar.VALID.read_bytes())
        self.assertIn('FORMATO_OU_CONTEUDO_DIVERGENTE',radar.api_state()['coleta']['motivos'])

    def test_http403_stops_collection_and_marks_unconsulted(self):
        snapshot,valid=self.baseline()
        with patch.object(radar,'fetch',return_value=(403,None,'HTTP 403')) as fetch:
            radar.cycle(False)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(snapshot,radar.LATEST.read_bytes())
        self.assertEqual(valid,radar.VALID.read_bytes())
        state=radar.api_state()
        self.assertEqual(state['municipios'][0]['estado_tentativa'],'HTTP_403')
        self.assertEqual(state['municipios'][1]['estado_tentativa'],'NAO_CONSULTADO')

    def test_strict_municipality_election_votes_and_http(self):
        name,code=radar.municipalities()[0]
        cases=[]
        p=self.payload(code);del p['cdabr'];cases.append((p,'MUNICIPIO_DIVERGENTE'))
        p=self.payload('76678');cases.append((p,'MUNICIPIO_DIVERGENTE'))
        p=self.payload(code);p['ele']='00000';cases.append((p,'ELEICAO_DIVERGENTE'))
        for value in (None,True,-1,1.5,'', '1.000'):
            p=self.payload(code);p['carg'][0]['agr'][0]['par'][0]['cand'][0]['vap']=value
            cases.append((p,'VOTOS_INVALIDOS'))
        p=self.payload(code);p['carg'][0]['agr'][0]['par'][0]['cand']=[{}];cases.append((p,'SCHEMA_DIVERGENTE'))
        for payload,expected in cases:
            with self.subTest(expected=expected,payload=payload):
                row=radar.parse_one(name,code,payload)
                self.assertEqual(row['estado'],expected)
                self.assertEqual(row['votos'],'')
        self.assertEqual(radar.parse_one(name,code,self.payload(code),503)['estado'],'HTTP_503')

    def test_mock_isolation(self):
        snapshot,valid=self.baseline()
        radar.cycle(True)
        self.assertEqual((self.root/'data/raw_atual.csv').read_bytes(),snapshot)
        self.assertEqual((self.root/'data/ultimo_dado_valido.csv').read_bytes(),valid)
        self.assertEqual(len(radar.api_state()['tentativas']),50)
        self.assertTrue(all(x['votos'] is None for x in radar.api_state()['municipios']))

    def test_context_change_cannot_mix_candidates(self):
        snapshot,valid=self.baseline()
        with patch.dict(radar.CFG,{'candidate_number':'99999'}):
            with self.assertRaises(ValueError): radar.api_state()
            with self.assertRaises(ValueError): radar.save(self.rows())
        self.assertEqual(snapshot,radar.LATEST.read_bytes())
        self.assertEqual(valid,radar.VALID.read_bytes())

    def test_old_file_preserved_until_new_valid_baseline(self):
        radar.LATEST.write_text('arquivo anterior preservado',encoding='utf-8')
        radar.save([radar.parse_one(name,code,None,503,'HTTP 503') for name,code in radar.municipalities()])
        self.assertEqual(radar.LATEST.read_text(),'arquivo anterior preservado')
        self.assertEqual(radar.api_state()['rows'],[])

    def test_http_api_and_invalid_json(self):
        self.baseline()
        server=ThreadingHTTPServer(('127.0.0.1',0),radar.H)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base+'/api/latest') as response:
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                data=json.load(response)
                self.assertEqual(len(data['municipios']),50)
                self.assertEqual(data['municipios'][0]['votos'],9)
            with urllib.request.urlopen(base+'/') as response:
                self.assertIn('Votos confirmados',response.read().decode())
            http,payload,error=radar.fetch(base+'/')
            self.assertEqual((http,payload,error),(200,None,'JSON_INVALIDO'))
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()

class IndicadoresTests(unittest.TestCase):
    def test_sections_and_unknown_are_distinct(self):
        import radar_norte as r
        self.assertEqual(r.indicators({'s':{'ts':'10','st':'0'},'v':{'vv':'0'}})['percentual_secoes'],0)
        self.assertEqual(r.indicators({'s':{'ts':'10','st':'10'}})['apuracao'],'SECOES_TOTALIZADAS')
        for sec in ({},{'ts':'0','st':'0'},{'ts':'10','st':'11'},{'ts':True,'st':'0'}):
            self.assertIsNone(r.indicators({'s':sec})['percentual_secoes'])
        self.assertIsNone(r.indicators({'v':{'vv':True}})['votos_validos'])
