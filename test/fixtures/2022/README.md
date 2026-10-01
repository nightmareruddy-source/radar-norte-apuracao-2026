# Regressão histórica — PENDENTE

Não há JSON de resultado real nesta pasta. Os endereços de divulgação de 2022 consultados retornaram HTTP 404 em 01/10/2026. `fontes.json` registra as novas tentativas pelos três municípios. Não foram colocados mocks no lugar dos arquivos reais.

A página oficial de interessados de 2022 descreve arquivos separados de dados fixos (EA01), variáveis (EA02) e consolidados (EA04):
https://www.tse.jus.br/eleicoes/eleicoes-2022/arquivos/interessados

O parser atual requer `cdabr`, `ele` e `carg[].agr[].par[].cand[]`, com `vap`; o painel lê `s.st`, `s.ts`, `s.sa`, `v.vv`, `and`, `tf`. Sem os corpos históricos não foi possível comprovar compatibilidade nem fazer comparação campo a campo. Não alterar o parser para aceitar silenciosamente outro layout.

O portal de resultados históricos encaminha 2022 para Estatísticas e Dados Abertos:
https://www.tse.jus.br/eleicoes/resultados-eleicoes
CSV histórico pode servir para conferir totais, mas não substitui um JSON original no teste do parser.

Comando de validação preparado: `python test/validar_2022.py`. Ele termina com erro enquanto faltarem três arquivos originais e `esperados.json`; não conta como teste aprovado. Os registros esperados devem informar arquivo, SHA256, codigo_tse, numero, eleicao, votos, secoes_totalizadas, percentual_secoes e fonte_total_oficial. Os valores devem ser conferidos em outra publicação oficial, não copiados do próprio parser.

A integração DOM `test/painel_nonzero.cjs` usa dados fictícios de 2026, explicitamente marcados. Não é a regressão histórica solicitada. A etapa DOM com dados reais de 2022 também permanece pendente.
