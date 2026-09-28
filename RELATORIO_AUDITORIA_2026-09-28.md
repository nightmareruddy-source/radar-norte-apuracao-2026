# Auditoria da simulação TSE — 28/09/2026

Ambiente: SIMULADO_TSE_2026 (dados de teste).
EA12: 50/50 nomes e códigos confirmados, SHA-256 616bb78c722c1b0507322225ec8e77f1180039dc9034ab1b8d73fa90672e3ffa.
Resultados: 50/50 endpoints HTTP 200, 50/50 JSONs válidos para município e cargo 0007, 50/50 `CANDIDATO_AUSENTE` para número 70255. Não há votos do Rafael nesta simulação; ausência não representa zero.
Os 50 hashes do CSV foram recalculados contra os arquivos brutos e conferem.
Testes locais: `python -m unittest -v test_coletor_actions` (2 testes, incluindo zero verdadeiro, ausência, HTTP 503, JSON quebrado e preservação do último dado válido).

A coleta não escreve em Raw_Atual.csv, Historico_Apuracao.csv ou na Central. O módulo novo não foi integrado ao painel existente. O comportamento da eleição real não está validado por esta simulação.

Arquivos: `coletor_actions.py`, `test_coletor_actions.py`, `config.json`, `README.md` e `evidencias/` com relatório, CSV e 51 JSONs brutos (EA12 + 50 municípios).
Execução: `python coletor_actions.py --limit 2` e, depois, `python coletor_actions.py`.

## Localização das evidências

Neste repositório, o CSV com os 50 resultados e hashes e o resumo estão em `simulacao/auditoria/20260928T185150_915313Z/`. Os 51 JSONs brutos completos estão no pacote `Radar_Norte_Auditoria_TSE_2026-09-28.zip`, entregue na conversa. A lista de arquivos acima descreve esse pacote.
