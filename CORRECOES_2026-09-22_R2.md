# Revisão R2 — 22/09/2026

Correções aplicadas após auditoria independente:

- `raw_atual.csv` agora é escrito em arquivo temporário, `fsync` e `os.replace()`. O painel não consegue mais ler um snapshot parcialmente escrito.
- Dashboard não usa mais `innerHTML` com valores do TSE. As células são criadas via DOM e preenchidas com `textContent`.
- Respostas HTTP do painel usam `Cache-Control: no-store` e `X-Content-Type-Options: nosniff`.
- `auditar_tse.py` aplica piso duro de 2,5 s mesmo que `--interval` receba valor menor.
- Servidor local agora escuta em `127.0.0.1` por padrão. Exposição externa exige `--host 0.0.0.0`.
- Docker usa `0.0.0.0` explicitamente e contém aviso de que autenticação/reverse proxy é obrigatória antes de publicação na Internet.
- Histórico continua registrando cada ciclo intencionalmente. Não foi aplicada deduplicação porque o requisito de auditoria é preservar snapshots observados; otimização/compactação pode ser feita separadamente.

Limite atual: não há evidência de uma bateria real 50/50 do TSE dentro deste pacote. As evidências mock permanecem identificadas como mock.
