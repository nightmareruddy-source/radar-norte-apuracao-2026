# Radar Norte — correções de 01/10/2026

## Comportamento implementado

- Falha pontual preserva apenas os votos daquela cidade; as demais atualizam. Três ou mais divergências de formato/conteúdo bloqueiam a publicação do ciclo. 403/429 interrompem as consultas e bloqueiam o ciclo.
- Pastas automáticas por contexto de configuração, com hash de ambiente, eleição, cargo, candidato, endpoint e municípios. Trocar configuração inicia outro conjunto; voltar recupera o anterior, desde que o armazenamento exista.
- API lê um snapshot JSON atômico para votos, tentativas, status e métricas. CSV/SQLite são históricos/exportações secundários e podem avançar antes do snapshot em uma interrupção.
- Soma regional explicita cobertura; votos preservados podem ter horários diferentes. Apuração não iniciada é diferente de parcial/final. FINAL exige tf=s e st=ts em todos os municípios atualizados.
- Seções totalizadas (st) e apuradas (sa) separadas, votos válidos (vv), percentual st/ts. Indicadores correspondem à última tentativa válida da passagem; votos podem ser preservados de passagem anterior.
- Alarme por idade dos votos validados, mesmo com tentativas recentes falhando. Limite: duas vezes (intervalo de descanso + orçamento de coleta), atualmente 30 minutos no servidor com refresh=300 e orçamento=600.
- Espera após bloqueio: 10, 20, 40 e até 60 minutos; estado salvo para reinício. Arquivos efêmeros não sobrevivem a reinício do Render grátis.
- Consultas sequenciais com pelo menos 2,5 segundos de intervalo. Timeout de socket de 10 segundos; orçamento de 600 segundos impede novas consultas após o limite, mas não constitui prazo absoluto de interrupção de uma requisição em andamento.
- Respostas HTTP brutas em evidencias/*.body, com URL, horários, status, cabeçalhos e SHA256 em *.json. Arquivos não são servidos publicamente. Sem descarte automático; monitorar espaço do disco.
- Mock possui votos fictícios do candidato configurado, armazenados separadamente e identificados como demonstração.
- Histórico recente no painel e download CSV. Erros de configuração retornam HTTP503 com mensagem específica. Atualização da tela tem timeout.

## Configurações

- `config.json`: simulado, mantido para auditoria isolada.
- `config.oficial.json`: eleição estadual 6259, cargo 7, candidato 70255, 50 municípios do PR. Ativar com `RADAR_CONFIG=config.oficial.json`.
- `RADAR_DATA_DIR`: raiz dos dados, por exemplo `/var/data/radar`. Só persiste se estiver dentro de um disco efetivamente anexado. Definir variável sem anexar disco NÃO resolve persistência.
- Oficial exige fase f=o além das validações de município, eleição, cargo e votos.

## Evidência de testes

20 testes unitários/integração passam: parser, 49 atualizações com 1 HTTP503 ou JSON inválido, bloqueio por múltiplas divergências, zero distinto de ausência, troca/retorno de contexto, interrupção antes de gravar snapshot, alerta diante de falhas, isolamento do mock, backoff e HTTP/API.
DOM com jsdom: zero visível, rótulo pré-eleição, 11 colunas, filtro, proteção contra HTML de dados e alerta. Isso não é validação visual em iPhone.
Replay local dos 50 arquivos oficiais coletados em 30/09: candidato presente, votos zero, apuração não iniciada, 3782 seções totais. Replay NÃO é nova coleta ao vivo nem prova de apuração iniciada.

## Pendências para uso eleitoral

- Render ainda no plano grátis; sono e perda do disco continuam. Pagar compute sem anexar disco também não basta.
- Validar coleta diretamente no serviço após deploy e ambiente selecionado.
- Validar abertura no celular do usuário e após inatividade com infraestrutura definitiva.
- Sem implementação de ETag/304. Não foi executado teste de carga ou de apuração em andamento.
- Comparação EA16/EA20 de seções foi feita em 30/09; mudanças futuras na configuração oficial exigem nova conferência.
