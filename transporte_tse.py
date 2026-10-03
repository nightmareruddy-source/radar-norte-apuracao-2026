"""HTTP em processo isolado: prazo total inclui DNS, conexão e corpo."""
import base64
import json
import io
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error

MAX_BODY=8*1024*1024

def request_bytes(url, timeout=10):
    try:
        proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),url,str(timeout)],
                            capture_output=True,timeout=timeout,check=True)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and waits for the child; no abandoned request.
        try: observed=json.loads(exc.stderr or b'{}')
        except (ValueError,TypeError): observed={}
        if observed.get('status') in (403,429):
            raise urllib.error.HTTPError(url,observed['status'],'TEMPO_LIMITE_CORPO',observed['headers'],io.BytesIO(b'')) from exc
        raise TimeoutError(f'TEMPO_LIMITE_TOTAL_{timeout}s') from exc
    result=json.loads(proc.stdout)
    if result.get('error'):
        if result.get('status') in (403,429):
            raise urllib.error.HTTPError(url,result['status'],result['error'],result.get('headers',{}),io.BytesIO(b''))
        raise OSError(result['error'])
    return result['status'],base64.b64decode(result['body']),result['headers']

def _main():
    response=None
    try:
        req=urllib.request.Request(sys.argv[1],headers={'User-Agent':'RadarNorte2026/1.0','Accept':'application/json'})
        try: response=urllib.request.urlopen(req,timeout=float(sys.argv[2]))
        except urllib.error.HTTPError as exc: response=exc
        print(json.dumps({'status':response.code,'headers':dict(response.headers)}),file=sys.stderr,flush=True)
        with response:
            raw=response.read(MAX_BODY+1)
            if len(raw)>MAX_BODY: raise ValueError('RESPOSTA_EXCEDE_8_MIB')
            result={'status':response.code,'headers':dict(response.headers),'body':base64.b64encode(raw).decode()}
    except Exception as exc:
        result={'error':f'{type(exc).__name__}: {exc}'}
        if response is not None:
            result.update(status=response.code,headers=dict(response.headers))
    print(json.dumps(result))

if __name__=='__main__': _main()
