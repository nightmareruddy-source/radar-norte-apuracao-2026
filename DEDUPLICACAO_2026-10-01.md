# Deduplicação de evidências — 01/10/2026

Integrada ao `record_response` do coletor Python do painel. Node/jsdom é ferramenta de teste da interface, não o coletor. A auditoria isolada `coletor_actions.py` conserva sua saída histórica sem alteração.

## Garantias

- SHA256 dos bytes originais, sem remover nem reordenar campos. gzip é reversível.
- Cada consulta gera uma linha com horários, URL, HTTP, cabeçalhos, erro, hash e referência ao corpo.
- Corpo é gravado atomicamente e sincronizado antes de registrar consulta bem-sucedida.
- Corpo repetido reutiliza o arquivo, inclusive após reinício ou sequência A→B→A.
- Diretórios isolados por ambiente/eleição/configuração já existente, dentro de RADAR_DATA_DIR quando definido. A chave inclui código TSE do município e identidade da URL; IBGE não é intercambiável com TSE.
- Corpo ausente/corrompido é regravado. Sem cache global apenas por município.
- Metadados são aninhados e não podem substituir hash/bytes/referência.
- Um processo escritor por diretório. Logs continuam crescendo; não há remoção automática.
- Arquivos `.body` e metadados da versão anterior não são migrados nem apagados automaticamente. O novo formato é `evidencias/<codigo>-<urlhash>/<sha256>.body.gz` e `consultas.jsonl`.

## Comparação real

Ibiporã, eleição oficial 6259, cargo 7: consultas em 01/10/2026 às 08:52:23 e 08:52:33 de Brasília, ambas HTTP200. Corpos idênticos: 133.527 bytes cada, SHA256 `4a08d219f832d74cb3bc2b37cf3fa84c0864f03e6fb7b3728490808323a52099`. Geração em ambas: 29/09/2026 19:29:14. gzip: 21.269 bytes.

A amostra não mostrou alteração em dg/hg; nenhum campo foi ignorado. Não prova que todos os ciclos futuros serão iguais. Caso o TSE mude apenas o horário, o novo corpo será preservado. Remover esses campos evitaria reconstituir exatamente a resposta associada ao hash bruto.

Corpo e metadados disponíveis em `test/fixtures/comparacao2026/`. É dado oficial de preparação, com apuração não iniciada.

## Testes

`python -m unittest -v test_coletor_actions test_painel`: 29 testes passam, incluindo nove testes de armazenamento/integração. A suíte atual do Render inclui esses testes.

`NODE_PATH=<diretório com jsdom> node test/painel_nonzero.cjs`: integra mock Python → parser → API → DOM, mostra 123 votos/cidade, total 6.150, PARCIAL e DEMONSTRAÇÃO. Esse teste é sintético, não usa resultados reais de 2022.

`python test/validar_2022.py`: BLOQUEADO por falta dos três JSONs reais e dos totais independentes para conferência. Retorna erro, não aprovação. Os três endereços históricos consultados retornaram 404; ver `test/fixtures/2022/fontes.json`. A documentação histórica descreve EA01/EA02/EA04, mas sem os corpos não foi possível validar campos nem garantir compatibilidade com o parser atual. Não foram inventados fixtures nem alterado o parser para acomodar suposições.

## Limitação operacional

Deduplicação reduz uso de disco; não impede suspensão do Render grátis nem preserva arquivos quando o disco efêmero é perdido. Hospedagem paga e disco persistente ainda não foram contratados. O orçamento anterior de 10 GB deve ser reavaliado à luz do volume comprimido e da retenção desejada; isso não muda automaticamente o plano.
