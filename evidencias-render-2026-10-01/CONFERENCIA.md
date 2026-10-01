# Conferência do Radar Norte no Render — 01/10/2026

Versão publicada: `1769209d402e3b29cfdb1a740d1f437fd9436732`.

Painel: https://radar-norte-validado.onrender.com
API: https://radar-norte-validado.onrender.com/api/latest

A API do servidor informou uma coleta de 08h24min09s a 08h26min27s de Brasília, em 01/10/2026:

- 50/50 municípios consultados, HTTP 200 em todos.
- Candidato 70255 presente nos 50 municípios.
- Eleição oficial estadual 6259, cargo 7.
- 3.782 seções totais, coincidentes com a soma conferida em 30/09.
- Apuração NÃO INICIADA em todos; votos zero são preparação, não votação apurada.
- Nenhum bloqueio ou erro informado pelo worker.

Evidência: `api_final.json.gz` contém, comprimida com gzip, a resposta HTTP recebida do serviço publicado. `api_final_metadados.json` registra horário, URL e SHA256 do JSON descomprimido. A confirmação desta passagem se baseia na resposta do próprio servidor; os 50 corpos brutos gravados pelo coletor no Render não foram baixados neste dossiê. O código preserva esses corpos e metadados no diretório evidencias do servidor, ainda efêmero.

## Validação e limites

20 testes passaram localmente. O Render publicou a versão após executar a mesma suíte no build. DOM verificado com jsdom: filtros, zero, texto de preparação, colunas e proteção contra HTML de dados. Não houve validação visual no iPhone de Ruddy nem teste após 15 minutos ocioso.

O serviço permanece grátis, sem disco persistente. A coleta pode parar por inatividade e os arquivos podem ser perdidos. Não está liberado para depender exclusivamente dele na eleição.

Proposta ainda NÃO contratada: serviço de US$ 7/mês + disco de 10 GB a US$ 0,25/GB/mês = US$ 9,50/mês de base, sujeito a impostos, câmbio e uso excedente. Disco em /var/data e RADAR_DATA_DIR=/var/data/radar. Somente definir a variável não cria um disco. Preços conferidos em https://render.com/pricing em 01/10/2026.

Estimativa com os arquivos observados: cerca de 1,3 GB/dia de JSON bruto. Acompanhar ocupação e exportar evidências; não há descarte automático.
