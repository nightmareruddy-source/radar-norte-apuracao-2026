# Auditoria TSE 2026 — Radar Norte

Pacote isolado. Não escreve na Central, no Radar v8 nem em qualquer planilha de produção.

- `config.json`: 50 municípios e códigos TSE.
- `auditar_tse.py`: consulta sequencial, intervalo padrão 2,5 s; para em 403/429; preserva JSON bruto e SHA-256; exige município, cargo 7 e caminho `carg→agr→par→cand`.
- `--mock`: testa somente a infraestrutura local com 50 respostas sintéticas.

Execução real: `python auditar_tse.py`
Teste local: `python auditar_tse.py --mock`
