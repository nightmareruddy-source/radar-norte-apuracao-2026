import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import evidencias

class EvidenciasTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def save(self,body=b'{"vap":"10"}',key='75914',root=None,**kw):
        return evidencias.salvar_se_mudou(root or self.root,key,body,**kw)
    def logs(self):
        return [json.loads(x) for x in (self.root/'75914/consultas.jsonl').read_text().splitlines()]
    def test_repeat_is_one_body_and_three_observations(self):
        self.assertTrue(self.save()['salvou'])
        self.assertFalse(self.save()['salvou']);self.assertFalse(self.save()['salvou'])
        self.assertEqual(len(list(self.root.rglob('*.gz'))),1);self.assertEqual(len(self.logs()),3)
    def test_changes_and_return_to_old_body(self):
        self.save();self.assertTrue(self.save(b'{"vap":"152"}')['salvou'])
        self.assertFalse(self.save()['salvou']);self.assertEqual(len(list(self.root.rglob('*.gz'))),2)
    def test_generation_time_is_preserved_exactly(self):
        for b in (b'{"hg":"08:00:00","vap":"0"}',b'{"hg":"08:01:00","vap":"0"}'):
            r=self.save(b);self.assertTrue(r['salvou']);self.assertEqual(gzip.decompress(Path(r['arquivo']).read_bytes()),b)
    def test_restart_and_directory_isolation(self):
        self.save()
        import importlib;importlib.reload(evidencias)
        self.assertFalse(self.save()['salvou'])
        self.assertTrue(self.save(root=self.root/'other')['salvou'])
        self.assertTrue(self.save(key='76678')['salvou'])
    def test_missing_and_corrupt_body_recovered(self):
        r=self.save();p=Path(r['arquivo']);p.unlink();self.assertTrue(self.save()['salvou'])
        p.write_bytes(b'broken');self.assertTrue(self.save()['salvou'])
    def test_failed_body_write_does_not_log_success(self):
        with patch.object(evidencias,'_atomic_bytes',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.save()
        self.assertFalse((self.root/'75914/consultas.jsonl').exists())
    def test_metadata_cannot_override_hash_and_invalid_json_is_preserved(self):
        b=b'\xffbad json';r=self.save(b,meta={'sha256_bruto':'forged','http':503})
        self.assertEqual(self.logs()[0]['sha256_bruto'],hashlib.sha256(b).hexdigest())
        self.assertEqual(gzip.decompress(Path(r['arquivo']).read_bytes()),b)
    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):self.save(key='../escape')

    def test_real_2026_body_roundtrip_and_collection_log(self):
        import radar_norte as radar
        body=gzip.decompress((Path(__file__).parent/'test/fixtures/comparacao2026/ibipora.json.gz').read_bytes())
        url='https://resultados.tse.jus.br/oficial/ele2026/6259/dados/pr/pr75914-c0007-e006259-u.json'
        with patch.object(radar,'DATA',self.root):
            first=radar.record_response(url,200,body,{},'2026-10-01T11:52:23Z')
            second=radar.record_response(url,200,body,{},'2026-10-01T11:52:33Z')
        self.assertTrue(first['salvou']);self.assertFalse(second['salvou'])
        self.assertEqual(gzip.decompress(Path(first['arquivo']).read_bytes()),body)
        logs=list(self.root.rglob('consultas.jsonl'))
        self.assertEqual(len(logs[0].read_text().splitlines()),2)
