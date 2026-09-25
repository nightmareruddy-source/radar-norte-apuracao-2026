# Correções antes da auditoria independente

1. Intervalo mínimo do coletor contínuo alterado para 2,5 s (config e proteção no código).
2. Nome monitorado ajustado para `Rafael Eik Ferreira` conforme definição do projeto.
3. Dados MOCK e dados TSE separados fisicamente: `data_mock/` e `data/`.
4. Saídas antigas geradas por MOCK foram retiradas de `data/` e preservadas em `evidencia_mock_anterior/` para não serem confundidas com coleta TSE.
5. Painel identifica explicitamente o ambiente `SIMULADO_TSE_2026 — DADOS DE TESTE, NÃO É PRODUÇÃO`.
6. Se 403/429 interromper um ciclo, o sistema não inventa linhas restantes nem votos zero.
7. Um ciclo parcial não substitui `data/raw_atual.csv`; o histórico/SQLite registram o que efetivamente foi observado.
8. Auditoria real continua separada de `--mock`; cada execução cria pasta própria com JSON bruto e SHA-256.

## Validações locais desta revisão
- `python -m py_compile radar_norte.py auditar_tse.py`: OK.
- `python radar_norte.py --mock --once`: 50 registros, todos `CANDIDATO_AUSENTE_NO_SIMULADO`, sem voto zero inventado.
- `python auditar_tse.py --mock`: 50/50 estruturalmente válidos em modo explicitamente `mock`.

Nenhuma dessas validações é apresentada como coleta real do TSE.
