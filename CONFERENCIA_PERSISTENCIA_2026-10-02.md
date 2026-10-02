# Conferência de persistência — 02/10/2026

Consulta do painel às 00:27 de Brasília. Serviço radar-norte-validado, commit observado 9616bf5288dcf86875b4a05a2f78ca76eb774f58.

## Resultado observado
- Plano pago 0.5c-512mb e disco de 10 GB em /var/data confirmados pela API Render.
- Reinício solicitado em 01/10 às 15:24:04 (dep-davaah7lot8c73cu39ug), concluído às 15:24:40. Houve outra publicação manual às 15:28:45, Live às 15:29:25 (dep-davacn8hfsis73c1cge0), mesmo commit.
- CSV obtido após os reinícios contém 3.800 registros, todos HTTP 200.
- Contém 50 registros de 50 municípios anteriores ao primeiro reinício, entre 15:18:16 e 15:20:30 de 01/10.
- Última coleta completa: 02/10 às 00:27:42, 50/50 respostas válidas, nenhum bloqueio, nenhum erro de worker.
- Candidato 70255 presente; apuração NAO_INICIADA, soma zero de preparação. Consultas novas não demonstram mudança nos resultados do TSE.

## Limites da conclusão
A retenção do histórico anterior ao reinício está demonstrada por seus registros e horários. A cópia temporária integral feita antes do reinício não estava mais disponível: não foi possível comparar cada byte contra aquela cópia. Não foi inspecionado todo o acervo de corpos brutos no disco remoto, nem testada restauração de backup. Isto não constitui liberação integral para a eleição; a regressão com três JSONs autênticos de 2022 continua pendente.

## Fontes e integridade
- https://radar-norte-validado.onrender.com/api/latest
- https://radar-norte-validado.onrender.com/historico.csv
- SHA256 da resposta API capturada: dc529fd0c692a2c75d0b7044b11b376cb1b1c6e3e312be04da815a61b49584d2
- SHA256 do CSV capturado: 6536673d34228e6bca36bf5506a2a3fc4ef80524eeb28f716e935b3592b90e0e

O texto fixo de hospedagem gratuita foi substituído por orientação para conferir os horários da consulta e da geração do TSE. Nenhuma regra de coleta ou cálculo foi modificada nesta atualização.
