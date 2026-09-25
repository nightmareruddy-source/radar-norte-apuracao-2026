# Pedido de auditoria independente

Audite este pacote como código-fonte de um sistema de apuração/monitoramento. Não presuma que MOCK comprova integração real.

Verifique especialmente:
- se MOCK e TSE real estão impossíveis de confundir nos dados, painel e evidências;
- se o intervalo efetivo entre requisições reais nunca fica abaixo de 2,5 s;
- comportamento em HTTP 403, 404, 429, timeout, JSON inválido e município/cargo divergente;
- se erro/ausência jamais vira 0 voto;
- se ciclo parcial pode destruir ou substituir o último snapshot completo;
- validação de `cdabr`, cargo 7 e caminho `carg -> agr -> par -> cand`;
- se o parser pode associar candidato/partido incorretamente;
- se `vap` e `pvap` são usados sem inferir denominadores não comprovados;
- riscos de concorrência, corrupção de CSV/SQLite, duplicação no histórico e atualização do painel;
- segurança e robustez do servidor web;
- se os 50 municípios/códigos e URLs devem ser revalidados contra a fonte oficial antes de produção;
- quaisquer alegações de FINAL/PARCIAL: não aceitar sem semântica oficial comprovada.

Entregue achados por severidade, com arquivo/trecho afetado e correção recomendada. Não altere os arquivos nesta primeira auditoria.
