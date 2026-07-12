# Corpus — Bíblia de Conhecimento EJC (Edição Integral v2)

Corpus tratado da "Bíblia de Conhecimento EJC — Edição Integral v2" para a base
de conhecimento RAG. **Todo o material é FICTÍCIO** (exemplos didáticos para
treinamento/RAG — o próprio documento veda o uso como caso real): cada doc leva
`extra.ficticio=true`, aviso no início do conteúdo e `confidence_level=media`.

Arquivos (1 documento RAG por linha JSONL: `chave_origem`, `titulo`,
`categoria`, `conteudo`, `extra`):

| arquivo | conteúdo | categoria |
|---|---|---|
| `situacoes.jsonl` | 84 situações SIT-01..84 (Parte A, Vol. I e II) | `referencia_interna` |
| `instrucoes.jsonl` | AVISO FUNDAMENTAL (I/II), INTRODUÇÃO METODOLÓGICA, NOTAS FINAIS (I/II) | `referencia_interna` |
| `governanca.jsonl` | Parte B: mapa SIT→modelo, Relatório de Auditoria, Índice Mestre, Padrão de Integração, avisos/apêndices dos volumes | `referencia_interna` |
| `modelos.jsonl` | Parte B: 221 modelos de peça (Volumes I–V) | `modelo_documento_juridico` |

## Como ingerir (produção, dentro do container backend)

```bash
python scripts/seed_biblia_ejc.py              # com embeddings inline
python scripts/seed_biblia_ejc.py --sem-vetores  # adia vetorização
python scripts/vetorizar_documentos.py           # vetoriza os pendentes depois
```

Idempotente: dedup por `chave_origem` (`biblia_ejc:*`); reexecutar não duplica
e edições futuras do corpus geram novas versões (histórico preservado).

## Como regenerar o corpus (nova edição do DOCX)

1. Extraia os parágrafos do DOCX para JSON (lista de pares `[estilo, texto]`,
   UTF-8 — ex.: com python-docx, fora do container).
2. `python scripts/parse_biblia_ejc.py <biblia_paras.json>` (reescreve os
   .jsonl deste diretório).
3. Rode `pytest tests/test_biblia_ejc_seed.py` e commite os .jsonl alterados.
