import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

import coletor_actions as c


def result(code, candidates):
    return json.dumps({'cdabr': code, 'carg': [
        {'cd': '7', 'agr': [{'par': [{'sg': 'AVANTE', 'cand': candidates}]}]}]}
    ).encode()


class AuditoriaTests(unittest.TestCase):
    def test_parser_distinguishes_zero_absence_and_corruption(self):
        code = '75914'
        present = [{'n': '70255', 'nmu': 'RAFAEL', 'vap': '0'}]
        self.assertEqual(c.parse_result(result(code, present), code, '70255')[:2],
                         ('DADO_VALIDO', 0))
        self.assertEqual(c.parse_result(result(code, []), code, '70255')[:2],
                         ('CANDIDATO_AUSENTE', None))
        for body in (b'{', b'{}', result('76678', present),
                     result(code, [{'n': '70255'}])):
            with self.assertRaises(ValueError):
                c.parse_result(body, code, '70255')

    def test_last_valid_survives_absence_http_and_broken_json(self):
        municipalities = c.CFG['municipalities']
        ea12 = json.dumps({'abr': [{'cd': 'pr', 'mu': [
            {'nm': name, 'cd': code} for name, code in municipalities]}]}).encode()
        codes = [str(x[1]) for x in municipalities[:2]]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def transport_first(url):
                if url == c.CFG['municipality_config_url']:
                    return 200, ea12
                return 200, result(codes[0], [{'n': '70255', 'vap': '9'}])

            first, summary = c.audit(2, transport_first, out=output)
            self.assertEqual(summary['estados']['DADO_VALIDO'], 1)
            self.assertEqual(summary['estados']['MUNICIPIO_DIVERGENTE'], 1)
            saved = json.loads((output / 'ultimo_dado_valido.json').read_text())
            self.assertEqual(saved[codes[0]]['votos'], 9)
            self.assertEqual(len(list((first / 'raw').glob('*.json'))), 3)

            scenarios = [result(codes[0], []), b'{', urllib.error.HTTPError(
                'test', 503, 'Unavailable', {}, None)]
            for scenario, expected in zip(scenarios,
                                          ('CANDIDATO_AUSENTE', 'JSON_INVALIDO', 'HTTP_503')):
                def transport(url):
                    if url == c.CFG['municipality_config_url']:
                        return 200, ea12
                    if url.endswith(f'pr{codes[0]}-c0007-e021272-u.json'):
                        if isinstance(scenario, Exception):
                            raise scenario
                        return 200, scenario
                    return 200, result(codes[1], [])

                _, report = c.audit(2, transport, out=output)
                self.assertEqual(report['estados'][expected],
                                 2 if expected == 'CANDIDATO_AUSENTE' else 1)
                saved = json.loads((output / 'ultimo_dado_valido.json').read_text())
                self.assertEqual(saved[codes[0]]['votos'], 9)
                attempt = json.loads((output / 'ultima_tentativa.json').read_text())
                self.assertEqual(attempt['municipios'][0]['votos'], '')


if __name__ == '__main__':
    unittest.main()
