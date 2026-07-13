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
| `modelos_vol3.jsonl` | Compêndio de Modelos Processuais **Volume III**: 48 modelos em 24 pares (iniciativa + reação) — bancário, consumidor, empresarial, licitações/contratos administrativos, trabalhista empresarial, ambiental | `modelo_documento_juridico` |

## Como ingerir (produção, dentro do container backend)

```bash
python scripts/seed_biblia_ejc.py              # com embeddings inline
python scripts/seed_biblia_ejc.py --sem-vetores  # adia vetorização
python scripts/vetorizar_documentos.py           # vetoriza os pendentes depois
```

Idempotente: dedup por `chave_origem` (`biblia_ejc:*`); reexecutar não duplica
e edições futuras do corpus geram novas versões (histórico preservado).

> **Nota — sufixos `-2`/`-3` nas chaves são POSICIONAIS.** Quando títulos se
> repetem (ex.: "MODELO A"), o parser desambigua na ordem de aparição no DOCX
> (`chave`, `chave-2`, `chave-3`…). Reordenar, inserir ou remover seções de
> mesmo título em uma nova edição DESLOCA essas chaves: o conteúdo que era
> `-2` pode virar `-3`, e o seed tratará como documento com `chave_origem`
> diferente — criando versões novas (sem duplicar, mas com histórico das
> chaves antigas). Ao regenerar o corpus, confira o diff dos `.jsonl` antes
> de commitar.

## Como regenerar o corpus (nova edição do DOCX)

1. Extraia os parágrafos do DOCX para JSON (lista de pares `[estilo, texto]`,
   UTF-8 — ex.: com python-docx, fora do container).
2. `python scripts/parse_biblia_ejc.py <biblia_paras.json>` (reescreve os
   .jsonl deste diretório).
3. Rode `pytest tests/test_biblia_ejc_seed.py` e commite os .jsonl alterados.

### Volume III (Compêndio de Modelos Processuais)

O `modelos_vol3.jsonl` vem de um DOCX próprio, convertido por
`scripts/parse_volume3.py` (lê o `.docx` direto via python-docx, incluindo as
tabelas de ficha de adaptação e matriz tese–prova):

```bash
python scripts/parse_volume3.py <Compendio_Modelos_Processuais_Volume_III.docx>
```

Segmenta pelos títulos "NN - ..." da seção "5. MODELOS" (48 modelos), deriva a
área do sumário e marca `iniciativa` (ímpar) / `reação` (par). Chaves estáveis
`biblia_ejc:vol3:<NN>-<slug>`. Mesmo aviso fictício e categoria
`modelo_documento_juridico` dos demais modelos.
