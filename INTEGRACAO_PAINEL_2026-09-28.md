# Integração do painel — 28/09/2026

## Resultado

Implementação preparada somente na ramificação `auditoria-isolada-tse-2026-09-28`.
Não houve PR, merge, atualização do Render nem execução do coletor sobre dados de produção.

O painel utiliza o mesmo validador da auditoria e separa a última tentativa do último
dado válido. Exige HTTP 200, município correto, eleição configurada, cargo 0007,
estrutura de candidatos e votos inteiros não negativos. Candidato ausente não vira zero.
Cada município preservado é identificado na tela com a data do dado anterior.

Um ciclo de 50 erros não substitui o snapshot. Ciclos incompletos, bloqueio HTTP
403/429 e mudança de formato bloqueiam a atualização. A configuração padrão exige
50 respostas válidas. Mudança do candidato ou da eleição não pode misturar os dados guardados.

## Evidências executadas

- 11 testes Python aprovados: zero verdadeiro, candidato ausente, novos votos,
  falha dos 50 municípios, preservação byte a byte dos arquivos, mudança de formato,
  HTTP 403 com interrupção, município divergente/ausente, eleição divergente,
  votos inválidos, isolamento mock, troca de candidato, preservação de arquivo antigo,
  API HTTP local e detecção de JSON inválido.
- Reprodução dos 50 JSONs oficiais coletados anteriormente nesta sessão:
  50 chamadas, 50 municípios exibidos, 50 candidatos ausentes, 50 votos nulos,
  nenhum snapshot de votos criado. Os hashes dos arquivos foram conferidos antes da leitura.
  Isso é reprodução de evidência real salva, não uma segunda rodada ao vivo no TSE.
- Interface executada com JavaScript e DOM (JSDOM), consumindo API HTTP local:
  50 linhas, zero preservado visível, outro município atualizado para 22 votos
  sintéticos e aviso de desconexão. Esses números são apenas casos de teste.
- Inspeção do Dockerfile: `COPY . /app` inclui os arquivos adicionados.

## Limites

O navegador Chromium não estava disponível e o download falhou. Portanto não houve
inspeção visual em navegador real nem teste de aparência no celular. O teste JSDOM
confere o comportamento da página, não seu layout visual.

Não há validação da eleição real nesta integração. Os JSONs oficiais utilizados são
da simulação do TSE e não contêm o candidato 70255. As provas de candidato presente,
zero e atualização de votos foram realizadas com dados sintéticos identificados nos testes.

Os arquivos antigos permanecem no disco, mas não são importados automaticamente para
o novo arquivo de valores validados: o parser antigo podia aceitar registros sem as
checagens agora exigidas. Uma nova coleta válida estabelece a base confiável do painel.

Próxima etapa: conferir visualmente a ramificação em ambiente de teste antes de autorizar publicação.
