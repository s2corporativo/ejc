# Status do benchmark de fontes jurídicas

**Benchmark:** `rag_source_curated.jsonl`  
**Itens:** 14  
**Origem:** fichas versionadas em `docs/biblioteca_juridica` com `gerado_por_IA=false`, URL oficial, data de verificação e snapshot local.

## Execução

A execução contra `run_eval.py` foi iniciada com `k=6`. O resultado foi `recall@6=0` em todos os 14 itens, mas esse número **não é uma medição válida de qualidade do RAG** neste ambiente.

A busca encontrou duas falhas operacionais:

1. Falha de conexão com a base de dados/RAG (`gaierror`).
2. Falha de reconstrução do modelo ONNX/embedding no cache do `fastembed`, com erro de caminho de dados externo (`model.onnx_data`).

O ambiente de auditoria não possui `.env` operacional, banco EJC ou contêineres ativos. Portanto, o benchmark foi implementado e validado estruturalmente, mas precisa ser executado no ambiente do sistema com banco, embeddings e configuração reais.

## Comando de reprodução

```bash
cd backend
python -m app.eval.build_source_benchmark
python -m app.eval.run_eval \
  --gold app/eval/benchmarks/rag_source_curated.jsonl \
  --k 6 \
  --out /tmp/rag-source-baseline.json
```

Antes da execução, confirme o serviço de banco, a tabela de chunks/embeddings e a instalação íntegra do modelo configurado. Um resultado com erro de conexão ou falha de embedding deve ser classificado como `infraestrutura_indisponivel`, nunca como baixa precisão jurídica.
