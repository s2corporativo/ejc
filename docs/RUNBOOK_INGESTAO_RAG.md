# RUNBOOK — Ingestão de fontes jurídicas no RAG

Como o EJC popula a base de conhecimento (RAG) puxando as fontes jurídicas
oficiais, e como disparar/monitorar a ingestão completa.

## Princípio: a ingestão roda em PRODUÇÃO (VPS), não em sessões de dev

Os ingestores baixam conteúdo de `planalto.gov.br`, `*.jus.br`, `*.leg.br`,
`lexml.gov.br` etc. **A busca real só funciona onde há internet aberta e o
banco de produção** — ou seja, no VPS (`ejc.depaulateixeira.adv.br`). Sessões de
desenvolvimento Claude Code têm o egress restrito por política de rede (o proxy
responde `403` a `.gov.br`/`.jus.br`), então a ingestão **não** roda a partir
delas — e não se deve contornar esse bloqueio. Os testes dos ingestores são
offline (mocks/fixtures); a coleta viva é sempre no VPS.

## Estado dos gates (produção)

Todos ligados por default (`backend/app/core/config.py`). Para desligar uma
fonte, defina a flag `=false` no `.env` do VPS e reinicie o backend
(`get_settings()` é cacheado — editar o `.env` sem reiniciar não tem efeito).

| Flag | Default | Fonte |
|------|---------|-------|
| `ENABLE_SCHEDULER` | `true` | liga o APScheduler (todos os jobs abaixo) |
| `DJEN_INGEST_ENABLED` | `true` | DJEN (intimações; OABs em `DJEN_OABS_MONITORADAS`, ex.: `251174/MG`) |
| `TJMG_INGEST_ENABLED` | `true` | crawler de jurisprudência do TJMG |
| `LEXML_INGEST_ENABLED` | `true` | **federação LexML** (ver cobertura abaixo) |
| `CONHECIMENTO_INGEST_ENABLED` | `true` | ANPD + Normas RFB |
| `RAG_SUMULAS_SEED_ENABLED` | `true` | seed de súmulas (STJ/TST/STF) no boot |

> Premissa de worker único: com vários workers `uvicorn`, deixe
> `ENABLE_SCHEDULER=false` nos workers extras (só um agenda os jobs).

## 1) Ingestão automática (scheduler)

Com `ENABLE_SCHEDULER=true`, os jobs rodam sozinhos (horários UTC):

| Job | Cadência | Puxa |
|-----|----------|------|
| `ing_planalto` | domingo 03h | Códigos/leis federais (Planalto, catálogo de 36 diplomas) |
| `ing_stj` | sábado 03h | Acórdãos/jurisprudência STJ |
| `ing_camara` | diário 04h00 | Proposições da Câmara |
| `ing_senado` | diário 04h20 | Matérias do Senado |
| `ing_tjmg` | sábado 04h30 | Jurisprudência TJMG |
| `ing_djen` | diário 05h00 | Intimações DJEN (OABs monitoradas) |
| `ing_lexml` | sábado 05h00 | Federação LexML (jurisdições + temas) |
| `ing_conhecimento` | domingo 03h | ANPD + Normas RFB |

Súmulas (STJ/TST/STF) e a legislação federal inicial também são semeadas no
**boot** (`seeds/seed_all.py` + `base_juridica_seed`, idempotentes).

## 2) Ingestão manual sob demanda (endpoints)

Ambos exigem papel **superadmin/admin/socio** e são rate-limited. Rodam em
background (idempotentes — reexecutar não duplica; dedup por `chave_origem`).

### Passo 1 — autenticar (obter access token)

```bash
BASE=https://ejc.depaulateixeira.adv.br
TOKEN=$(curl -sS -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"SEU_EMAIL_ADMIN","password":"SUA_SENHA"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```
> Se a conta tiver 2FA ativo, inclua `"totp_code":"123456"` no corpo.

### Passo 2 — disparar as fontes oficiais (ANPD + RFB + federação LexML)

```bash
curl -sS -X POST "$BASE/api/rag/ingest-fontes-oficiais" \
  -H "Authorization: Bearer $TOKEN"
# 202 Accepted → { "fontes": ["anpd","normas_rfb","lexml"], ... }
```

### Passo 3 — semear/atualizar a base do escritório (opcional)

```bash
# base institucional (README, checklists, padrão-ouro de peças) +
# ?incluir_jurisprudencia agenda uma importação inicial LexML/STJ
curl -sS -X POST "$BASE/api/rag/seed?incluir_jurisprudencia=true" \
  -H "Authorization: Bearer $TOKEN"
```

## 3) Acompanhamento

O resultado durável fica na tabela **`fontes_ingestao`** (última execução,
status `ok`/`parcial`/`erro`, contagem por slug — `planalto`, `stj`, `lexml`,
`anpd`, `normas_rfb`, ...). Consulte pelo painel de fontes da aplicação ou via
SQL no banco de produção.

## 4) Verificar que o RAG está recuperando

Após a ingestão, uma consulta jurídica deve trazer contexto. O retrieval tem
**fallback textual** (pg_trgm/FTS) quando os embeddings ainda não foram
preenchidos, então a busca já funciona; os vetores (`intfloat/multilingual-e5-large`,
1024d) melhoram o ranqueamento e são preenchidos pelo job/serviço de
reindexação de embeddings.

## Cobertura de fontes

| Pedido | Como é coberto |
|--------|----------------|
| Leis federais (Planalto) | job `ing_planalto` + seed de boot |
| Súmulas STJ/TST/STF | seed de súmulas + job `ing_stj` |
| STJ / Câmara / Senado | jobs dedicados |
| TJMG | job `ing_tjmg` + federação LexML |
| DJEN (intimações) | job `ing_djen` (OAB `251174/MG`) |
| **TRT-3 / TRF-6** | **federação LexML** (jurisdição nominal) |
| **Juizados especiais** | **federação LexML** (turmas recursais) |
| **Assembleia MG (ALMG) / legislação estadual** | **federação LexML** (esfera estadual) |
| **Município de Betim (leis municipais)** | **federação LexML** (localidade `minas.gerais;betim`) |
| ANPD + Normas RFB | job `ing_conhecimento` |

A **federação LexML** (`services/ingestors/lexml.py`) usa o federador oficial
`lexml.gov.br` (mantido pelo Senado) como fonte única — legislação
estadual/municipal grava em `referencia_legislativa` e jurisprudência em
`jurisprudencia` (nunca `legislacao%`, para não afrouxar o gate anti-alucinação
de citações). Toda URL gravada passa pela allowlist de domínios oficiais.

> Limitação conhecida: a API pública do LexML (`buscar_lexml`) é por
> palavra-chave — as jurisdições nominais (ALMG, Betim, TRT-3, TRF-6, juizados)
> são miradas por consulta explícita e o URN é gravado como metadado de
> proveniência. Portais dedicados (ALMG, Câmara de Betim, TRT-3/TRF-6 diretos)
> exigiriam ingestor próprio validado com `.gov`/`.jus` liberado.
