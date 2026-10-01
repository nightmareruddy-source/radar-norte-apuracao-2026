"""Raw-byte deduplication. One writer process per data directory.

Every successful call appends an observation. Bodies are content-addressed per
source and compressed losslessly; timestamps and HTTP metadata are never ignored.
"""
import gzip
import hashlib
import json
import os
import re
import tempfile
import threading
import zlib
from pathlib import Path

_LOCK = threading.RLock()


def _atomic_bytes(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name+'.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def salvar_se_mudou(dir, chave, corpo, *, meta=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', chave):
        raise ValueError('Chave de evidência inválida')
    if not isinstance(corpo, bytes):
        raise TypeError('O corpo deve conter os bytes originais, sem recodificação')
    folder = Path(dir) / chave
    digest = hashlib.sha256(corpo).hexdigest()
    target = folder / (digest+'.body.gz')
    with _LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        # Disk is the authority: handles restart, directory isolation, deletion
        # and corrupt gzip. No process-global hash cache can hide a missing body.
        try:
            present = hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == digest
        except (OSError, EOFError, ValueError, zlib.error):
            present = False
        if not present:
            _atomic_bytes(target, gzip.compress(corpo, mtime=0))
        entry = {'sha256_bruto':digest, 'bytes':len(corpo), 'arquivo':target.name,
                 'corpo_gravado':not present, 'meta':meta or {}}
        # Body first, observation second: never log a successful observation
        # referring to a body which has not yet been stored.
        with (folder/'consultas.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
            stream.flush(); os.fsync(stream.fileno())
    return {'salvou':not present,'hash':digest,'arquivo':str(target)}
