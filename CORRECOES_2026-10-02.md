# Correções operacionais — 02/10/2026

## Alterações
1. Intervalo de 300 segundos contado do início da coleta. Uma coleta de 135 segundos deixa 165 segundos até a próxima. Ciclos longos não se sobrepõem nem geram rajada para recuperar horários: pausa mínima de 10 segundos após término.
2. Primeiro ciclo imediato após iniciar serviço. Exceção obrigatória: respeita espera persistida após 403/429.
3. Retomada automática testada com relógio controlado: 403 e 429 param o ciclo; espera de 600/1200/2400/3600 segundos; sucesso zera contador e volta à cadência normal. Não foi provocado bloqueio real no TSE.
4. Alerta de dado válido atrasado reduzido para 900 segundos. Resposta recente com erro não renova o horário do voto preservado. Isso mede saúde da coleta, não exige que o TSE publique conteúdo novo a cada consulta.
5. Python fixado em `.python-version`: 3.14.3, mesma versão observada nos logs do Render antes desta alteração. Testes locais em Python 3.12.14; build Render executa sua própria suíte.
6. API e topo do painel exibem soma de seções totalizadas e total de seções. Denominador calculado dos arquivos, não fixado em 3.782. Cobertura incompleta exibe aviso, nunca apresenta subtotal como total. Na apuração parcial/final, municípios ordenados por votos decrescentes; valores desconhecidos no fim.
7. Três respostas autênticas do simulado TSE 2026 congeladas em `test/fixtures/simulado2026`, sem modificar bytes originais (gzip). Metadados contêm fonte, HTTP 200, horário e SHA256 do corpo original; cabeçalhos disponíveis para Londrina e Cambé.

## Regressão de simulado (não votos eleitorais)
Eleição 21272, candidato do teste 68028. O 70255 está ausente nessas três respostas; sua ausência foi testada e não é convertida em zero. Configuração oficial do painel continua 6259 / 70255, inalterada.

| Município | Votos do 68028 | Seções totalizadas/total | Votos válidos |
|---|---:|---:|---:|
| Ibiporã | 44 | 119/119 | 32744 |
| Londrina | 330 | 1181/1181 | 322014 |
| Cambé | 57 | 221/221 | 61685 |

Valores esperados transcritos dos corpos originais, hash verificado antes do teste. Não são uma comparação com uma segunda fonte independente. Esses arquivos simulados marcam FINAL; os números de seções podem diferir da eleição oficial. A coleta dos três arquivos ocorreu em 02/10/2026, fora da janela do exercício; comprova leitura de respostas disponibilizadas, não acompanhamento ao vivo de votos mudando.

## Validação executada
- `python -m unittest -q test_coletor_actions test_painel test_evidencias`: 46 testes aprovados.
- `test/painel_nonzero.cjs` com jsdom: parser/API/tela sintéticos; ordenação por votos; seções no topo; três arquivos reais do simulado pelo mesmo parser/API/DOM, soma 431, FINAL, sem rótulo de preparação, ambiente SIMULADO.
- A regressão autêntica está incluída em test_painel, portanto no comando de build atual do Render.

## Limites
O teste de 2022 deixa de ser a prioridade desta rodada; não foi concluído nem declarado aprovado. Permanecem não demonstrados o fluxo real de votos em evolução da eleição oficial e a recuperação integral de backup do disco. Nenhum teste offline ou simulado garante disponibilidade do TSE no dia da eleição.
