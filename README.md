# Auditoria TSE 2026 — Radar Norte

Pacote isolado. Não escreve na Central, no Radar v8 nem em qualquer planilha de produção.

- `config.json`: 50 municípios e códigos TSE.
- `auditar_tse.py`: consulta sequencial, intervalo padrão 2,5 s; para em 403/429; preserva JSON bruto e SHA-256; exige município, cargo 7 e caminho `carg→agr→par→cand`.
- `--mock`: testa somente a infraestrutura local com 50 respostas sintéticas.

Execução real: `python auditar_tse.py`
Teste local: `python auditar_tse.py --mock`

## Auditoria resiliente e isolada

`python coletor_actions.py --limit 2` consulta Ibiporã e Londrina; `python coletor_actions.py`
consulta os 50 municípios. O programa valida primeiro todos os 50 códigos contra o EA12
oficial. Cada execução cria `simulacao/auditoria/<data>/resumo.json`, `tentativas.csv`
e a pasta `raw/` com os JSONs brutos e os hashes SHA-256 registrados no CSV.
`ultima_tentativa.json` registra a coleta recente; `ultimo_dado_valido.json` preserva
por município o último resultado com o candidato presente e `vap` inteiro válido.

Estados distintos: `DADO_VALIDO` (inclusive `vap=0`), `CANDIDATO_AUSENTE`,
`JSON_INVALIDO`, `SCHEMA_DIVERGENTE`, `HTTP_<código>` e `ERRO_COLETA`.
Uma ausência ou falha nunca vira zero e não substitui o último dado válido.
O programa só aceita a URL da simulação configurada e não escreve na Central,
em `data/`, `Raw_Atual.csv` ou `Historico_Apuracao.csv`.

Teste de falhas locais, sem rede: `python -m unittest -v test_coletor_actions`.
Uma auditoria de 50 endpoints exige ao menos 2,5 segundos entre requisições;
interrompe ao receber HTTP 403 ou 429. A simulação valida a integração,
mas não representa votos reais nem garante disponibilidade no dia da eleição.
