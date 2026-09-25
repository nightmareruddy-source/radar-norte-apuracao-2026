# Auditoria independente solicitada — R2

Não altere os arquivos. Audite o pacote e informe achados por severidade.

Confirme especificamente:
1. escrita atômica de `raw_atual.csv` e comportamento se o painel ler durante uma coleta;
2. ausência de `innerHTML`/injeção de HTML com dados do TSE;
3. piso real de 2,5 s em `radar_norte.py` e `auditar_tse.py`, inclusive com `--interval 0.1`;
4. 403/429 interrompem sem inventar zeros nem sobrescrever snapshot completo com parcial;
5. `cdabr`, cargo 7 e caminho `carg -> agr -> par -> cand`;
6. associação candidato/partido e uso de `vap`/`pvap` sem denominador inventado;
7. separação física `data/` e `data_mock/`;
8. servidor padrão limitado a `127.0.0.1`; Docker expõe `0.0.0.0`, portanto avalie risco antes de deploy público;
9. histórico sem deduplicação é deliberado para trilha de auditoria — avalie impacto de volume, mas não trate como correção já aplicada;
10. verifique se existe ou NÃO existe evidência real do TSE. Não aceite resultados `modo=mock` como validação externa.

Se possível, execute apenas os testes locais/mock. Não faça coleta real automaticamente sem decisão explícita do operador.
