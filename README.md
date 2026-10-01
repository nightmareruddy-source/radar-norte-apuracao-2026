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

## Painel com preservação dos dados

`python radar_norte.py --mock` abre o painel local com dados sintéticos; `python radar_norte.py`
consulta a simulação TSE configurada. O servidor abre enquanto a primeira coleta roda em segundo plano.
O Dockerfile existente usa `COPY . /app` e inclui também `painel.html` e `coletor_actions.py`.

Cada coleta registra `ultima_tentativa.csv`. Os votos confirmados ficam em
`ultimo_dado_valido.csv`; uma ausência mantém o valor anterior do município.
O painel mostra os 50 municípios, a situação da tentativa, votos confirmados,
indicação de valor preservado e datas da coleta e do TSE. Zero é exibido como `0`;
sem dado confirmado aparece `—`. Erros de conexão com o painel geram aviso visível.

O disjuntor exige, por padrão, 50 respostas válidas (incluindo ausência do candidato).
Ciclo incompleto, HTTP 403/429 ou formato/conteúdo divergente impedem a atualização
do conjunto de votos válidos. `raw_atual.csv` só é escrito quando existem dados
confirmados para os 50 municípios e a coleta passou no disjuntor.
Histórico CSV e SQLite registram as tentativas, inclusive erros com voto vazio/NULL.

Arquivos antigos são mantidos no disco. O painel usa o novo arquivo de dados validados;
não importa automaticamente valores antigos que o parser anterior possa ter aceitado
sem validar município, eleição ou votos. A primeira coleta válida estabelece a nova base.
`contexto_validacao.json` impede misturar candidatos, eleições e configurações diferentes
na mesma pasta. `data_mock/` permanece isolado de `data/`.

Verificação completa: `python -m unittest -v test_coletor_actions test_painel`.
Evidências da integração: `INTEGRACAO_PAINEL_2026-09-28.md`,
`RESULTADO_REPLAY_PAINEL.json` e `RESULTADO_INTERFACE.json`.


## Atualização de 01/10/2026

Consulte [CORRECOES_2026-10-01.md](CORRECOES_2026-10-01.md) para comportamento atual, configuração oficial, testes e limitações de hospedagem. O histórico acima documenta versões anteriores; não é declaração de prontidão eleitoral.
