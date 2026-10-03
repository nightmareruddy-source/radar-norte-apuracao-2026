# Timeout, alerta e bloqueio — 03/10/2026

## Implementação
- Todas as consultas do painel passam por processo HTTP isolado, com prazo total de 10 segundos para DNS, conexão, cabeçalhos e corpo. Em expiração, o processo filho é encerrado e aguardado; não ficam consultas abandonadas. Corpo limitado a 8 MiB. O coletor de auditoria também usa esse transporte com seu prazo de 25 segundos.
- Erro/timeout não sobrescreve votos validados. Se um 403/429 já foi recebido e o corpo trava, preserva o código para acionar a pausa.
- A API calcula o atraso no instante de cada GET, mesmo se worker.json permanecer em coleta. Campos novos: verificado_em, coleta_prolongada, duracao_coleta_segundos, timeout_requisicao_segundos=10, limite_espera_bloqueio_segundos=1200. Alerta de atraso continua em 900 segundos.
- Pausa após bloqueio: 600, 1200, 1200… segundos. Reinício respeita a pausa; pausas antigas de 40/60 minutos são limitadas a 20 minutos a partir do fim da coleta bloqueada.
- Cada ciclo concluído registra seus horários no log do Render, permitindo diagnóstico futuro.

## Testes
50 testes locais aprovados, incluindo servidor HTTP que envia corpo lentamente, encerramento por prazo total, preservação de votos após timeout, 403 com corpo travado e worker parado enquanto a API responde. O teste do worker consulta a API antes e depois de avançar o relógio 901 segundos e confirma que o alerta muda sem nenhum novo ciclo concluído.

## Diagnóstico anterior
A observação isolada “em coleta desde 00:32” não permite distinguir cache de falha transitória. Havia ciclos completos posteriores no histórico desta conversa. Em consulta direta de 03/10, o painel registrava coleta concluída às 08:37:15 e ciclo iniciado às 08:39:59 (Brasília). Não se afirma que foi apenas cache.

## Limites
O prazo HTTP não resolve eventual travamento do sistema de arquivos ou indisponibilidade de todo o servidor. Se o processo inteiro estiver indisponível, o navegador mostra falha ao atualizar; a API não consegue gerar um alerta novo enquanto estiver fora do ar. Este teste não provoca bloqueio no TSE e não afirma recuperação de um bloqueio real.
