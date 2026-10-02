from contextlib import closing
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
        self.patches=[patch.object(radar,'CFG',json.loads((radar.BASE/'config.json').read_text())),patch.object(radar,'REAL_DATA',self.root/'data'),
                      patch.object(radar,'MOCK_DATA',self.root/'mock')]
        for p in self.patches: p.start()
        radar.select_data_dir(False); radar.init_db()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def payload(self,code,votes=9):
        return {'f':'o','ele':radar.CFG['election_code'],'cdabr':code,'dg':'28/09/2026','hg':'16:00:00','tf':'n',
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
        with closing(sqlite3.connect(radar.DB)) as db, db:
            self.assertEqual(db.execute('select count(*) from snapshots where estado="HTTP_503" and votos is null').fetchone()[0],50)

    def test_schema_change_blocks_entire_cycle(self):
        snapshot,valid=self.baseline()
        rows=self.rows(99)
        for i,(name,code) in enumerate(radar.municipalities()[:3]):
            broken=self.payload(code);del broken['carg'][0]['agr'][0]['par'][0]['cand']
            rows[i]=radar.parse_one(name,code,broken)
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
        latest_path,valid_path=radar.LATEST,radar.VALID
        radar.cycle(True)
        self.assertEqual(latest_path.read_bytes(),snapshot)
        self.assertEqual(valid_path.read_bytes(),valid)
        self.assertEqual(len(radar.api_state()['tentativas']),50)
        self.assertTrue(all(x['votos']==123 for x in radar.api_state()['municipios']))

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

    def test_one_failure_updates_other_49(self):
        for failure in (503,200):
            with self.subTest(failure=failure):
                self.baseline()
                rows=self.rows(500)
                rows[0]=radar.parse_one(*radar.municipalities()[0],None,failure,'JSON_INVALIDO' if failure==200 else 'HTTP 503')
                radar.save(rows)
                state=radar.api_state()
                self.assertFalse(state['coleta']['bloqueada'])
                self.assertEqual(state['municipios'][0]['votos'],9)
                self.assertTrue(state['municipios'][0]['preservado'])
                self.assertTrue(all(r['votos']==500 for r in state['municipios'][1:]))
                self.assertEqual(state['resumo']['municipios_atuais'],49)
                self.assertFalse(state['resumo']['total_atual_completo'])

    def test_environment_switch_and_return(self):
        self.baseline();original=radar.DATA
        with patch.dict(radar.CFG,{'environment':'OFICIAL_TSE_2026','election_code':'6259','endpoint_template':'https://example.invalid/{code}'}):
            radar.select_data_dir();radar.init_db()
            self.assertNotEqual(original,radar.DATA)
            self.assertEqual(radar.api_state()['resumo']['municipios_com_votos'],0)
            radar.save(self.rows(700))
            self.assertEqual(radar.api_state()['municipios'][0]['votos'],700)
        radar.select_data_dir();radar.init_db()
        self.assertEqual(radar.api_state()['municipios'][0]['votos'],9)

    def test_failed_cycles_do_not_clear_stale_alarm(self):
        rows=self.rows()
        for row in rows: row['timestamp']='2020-01-01T00:00:00+00:00'
        radar.save(rows)
        radar.save([radar.parse_one(n,c,None,503,'HTTP 503') for n,c in radar.municipalities()])
        self.assertTrue(radar.api_state()['alarme_desatualizacao'])

    def test_snapshot_is_authority_after_interrupted_export(self):
        self.baseline()
        original=radar.atomic_json
        def interrupted(path,value):
            if path.name=='snapshot.json': raise OSError('interrupted')
            return original(path,value)
        with patch.object(radar,'atomic_json',side_effect=interrupted):
            with self.assertRaises(OSError):radar.save(self.rows(500))
        self.assertTrue(all(r['votos']==9 for r in radar.api_state()['municipios']))

    def test_initial_failures_raise_alarm(self):
        radar.save([radar.parse_one(n,c,None,503,'HTTP 503') for n,c in radar.municipalities()])
        with patch.object(radar,'STARTED',0):
            self.assertTrue(radar.api_state()['alarme_desatualizacao'])

    def test_official_rejects_nonofficial_phase(self):
        with patch.dict(radar.CFG,{'environment':'OFICIAL_TSE_2026'}):
            name,code=radar.municipalities()[0]
            p=self.payload(code);p['f']='s'
            self.assertEqual(radar.parse_one(name,code,p)['estado'],'FASE_DIVERGENTE')

    def test_backoff(self):
        streak=0
        for expected in (600,1200,2400,3600,3600):
            delay,streak=radar.next_delay([{'estado':'HTTP_429'}],streak,300)
            self.assertEqual(delay,expected)
        self.assertEqual(radar.next_delay([{'estado':'DADO_VALIDO'}],streak,300),(300,0))

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
        self.assertEqual(r.indicators({'s':{'ts':'10','st':'10'}})['apuracao'],'PARCIAL')
        for sec in ({},{'ts':'0','st':'0'},{'ts':'10','st':'11'},{'ts':True,'st':'0'}):
            self.assertIsNone(r.indicators({'s':sec})['percentual_secoes'])
        self.assertIsNone(r.indicators({'v':{'vv':True}})['votos_validos'])

    def test_final_requires_tf_and_sections(self):
        self.assertEqual(radar.indicators({'s':{'ts':'10','st':'10','sa':'9'},'tf':'s'})['apuracao'],'FINAL')
        self.assertEqual(radar.indicators({'s':{'ts':'10','st':'10'},'tf':'n'})['apuracao'],'PARCIAL')
        self.assertEqual(radar.indicators({'s':{'ts':'10','st':'0'},'and':'n'})['apuracao'],'NAO_INICIADA')
        self.assertIsNone(radar.indicators({'s':{'ts':'10','st':'10','sa':'11'}})['secoes_apuradas'])

# Include storage regressions in the existing Render build gate.
from test_evidencias import EvidenciasTests


class WorkerScheduleTests(unittest.TestCase):
    setUp=PainelTests.setUp
    tearDown=PainelTests.tearDown
    rows=PainelTests.rows
    payload=PainelTests.payload
    baseline=PainelTests.baseline

    def run_worker(self, outcomes, persisted=None, duration=135):
        clock=[1000.0];starts=[];states=[]
        class Finished(BaseException): pass
        if persisted: radar.atomic_json(radar.DATA/'worker.json',persisted)
        original=radar.atomic_json
        def collect(mock):
            if len(starts)==len(outcomes): raise Finished()
            starts.append(clock[0]);clock[0]+=duration
            return [{'estado':outcomes[len(starts)-1]}]
        def write(path,state):
            if not state['em_coleta']: states.append(dict(state))
            original(path,state)
        with patch.object(radar.time,'time',side_effect=lambda:clock[0]),patch.object(radar.time,'sleep',side_effect=lambda t:clock.__setitem__(0,clock[0]+t)),patch.object(radar,'cycle',side_effect=collect),patch.object(radar,'atomic_json',side_effect=write):
            with self.assertRaises(Finished):radar.worker_loop(False,300)
        return starts,states

    def test_interval_from_start_and_immediate_startup(self):
        starts,states=self.run_worker(['DADO_VALIDO']*3,{'proxima_tentativa_epoch':1500,'bloqueios_consecutivos':0})
        self.assertEqual(starts,[1000,1300,1600])
        self.assertEqual(states[0]['proxima_tentativa_epoch'],1300)

    def test_403_and_429_recover_automatically(self):
        for status in ('HTTP_403','HTTP_429'):
            with self.subTest(status=status):
                starts,states=self.run_worker([status,status,'DADO_VALIDO','DADO_VALIDO'],{'bloqueios_consecutivos':0})
                self.assertEqual(starts,[1000,1735,3070,3370])
                self.assertEqual([s['bloqueios_consecutivos'] for s in states],[1,2,0,0])

    def test_restart_preserves_block_cooldown(self):
        starts,_=self.run_worker(['DADO_VALIDO'],{'bloqueios_consecutivos':1,'proxima_tentativa_epoch':1600})
        self.assertEqual(starts,[1600])

    def test_slow_cycle_does_not_overlap_or_catch_up(self):
        starts,_=self.run_worker(['DADO_VALIDO']*2,duration=400)
        self.assertEqual(starts,[1000,1410])

    def test_alarm_boundary_900_seconds(self):
        self.baseline();state=radar.api_state()
        from datetime import datetime
        stamp=min(datetime.fromisoformat(x['dado_valido_em']).timestamp() for x in state['municipios'])
        with patch.object(radar.time,'time',return_value=stamp+899):
            self.assertFalse(radar.api_state()['alarme_desatualizacao'])
        with patch.object(radar.time,'time',return_value=stamp+901):
            self.assertTrue(radar.api_state()['alarme_desatualizacao'])
        self.assertEqual(radar.api_state()['limite_atraso_segundos'],900)

    def test_section_summary_complete_and_missing(self):
        rows=self.rows();metrics={r['codigo_municipio']:{'tentativa_em':r['timestamp'],'secoes_total':100,'secoes_totalizadas':25} for r in rows}
        radar.save(rows,metrics);s=radar.api_state()['resumo']
        self.assertEqual((s['secoes_totalizadas'],s['secoes_total']),(1250,5000))
        metrics.pop(rows[0]['codigo_municipio']);radar.save(rows,metrics)
        s=radar.api_state()['resumo'];self.assertIsNone(s['secoes_total']);self.assertFalse(s['secoes_cobertura_completa'])

# Include authentic simulation regression in Render's existing build test gate.
from test_simulado2026 import Simulado2026Tests
