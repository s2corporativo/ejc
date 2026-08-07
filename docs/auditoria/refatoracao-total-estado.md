# Refatoração Total — o que o repositório já resolve e o que continua aberto

Confronto item a item entre o **Prompt Mestre de Refatoração Total** (derivado da
auditoria integral de produção) e o **código atual** do repositório, verificado em
2026-08-07 sobre `origin/main` (`8b11007`).

**Por que este documento existe.** O prompt mestre e o `plano-correcao-v2.md` foram
escritos **sem acesso ao código-fonte** — a auditoria só viu a API de produção e os
bundles publicados. Vários achados já tinham sido corrigidos no repositório antes da
auditoria terminar, e outros têm causa diferente da suposta. Executar o prompt ao pé da
letra refaria trabalho pronto e, em alguns pontos, **desfaria correção existente**. O que
segue é a verificação, com a evidência no arquivo.

> Regra de uso: um item marcado **RESOLVIDO** não deve ser reaberto sem nova evidência de
> produção. Um item **[INVESTIGAR]** continua sendo hipótese da auditoria — confirme antes
> de agir.

---

## ONDA 0 — Fundação

| Item | Estado | Evidência |
|---|---|---|
| Ativar Sentry | **Código pronto; falta o DSN** | `backend/app/core/observability.py` (init gated, scrub LGPD, `send_default_pii=False`), `SENTRY_DSN` em `app/core/config.py`. Sem DSN é no-op silencioso. **Ato de ambiente do titular**, não de código. |
| Religar embeddings + backfill | **Aberto** | Modelo e dimensão configurados (`EMBEDDINGS_MODEL`, `vector(1024)`); o backfill é operação de dados em produção. Ver `RUNBOOK_MIGRACAO_EMBEDDING_1024.md` e `backend/scripts/reparar_conhecimento_rag.py`. |
| Backup offsite | **Código pronto; ativação é de ambiente** | `docker-compose.yml` monta a config do rclone no container; `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`. |
| Ambiente de homologação | **Aberto — ato de ambiente** | Fora do alcance do executor técnico (regra 9 do `CLAUDE.md`: sem deploy nem acesso a produção). |

**Conclusão da Onda 0:** nada aqui é trabalho de código pendente. São quatro atos de
ambiente do titular. O executor pode preparar o terreno (feito), não pode ligar.

---

## ONDA 1 — Bugs críticos

| Item | Estado | Evidência |
|---|---|---|
| Dossiê do cliente 500 → degradar por seção | **CORRIGIDO neste PR** | `app/core/degradacao.py` (padrão único) + `app/routers/dossie_cliente.py`. Testes: `tests/test_degradacao_por_secao.py`. |
| `relatorio-financeiro` 500 | **CORRIGIDO neste PR** | `app/routers/relatorio_cliente.py` — honorários e despesas isolados. |
| Sala Jurídica: barra final → "Failed to fetch" | **CORRIGIDO neste PR** | Causa real: `--proxy-headers` sem `--forwarded-allow-ips`. Ver seção "A barra final" abaixo. `backend/entrypoint.sh`, testes em `tests/test_proxy_headers_redirect.py`. |
| Acentuação nos documentos gerados | **CORRIGIDO neste PR** | A causa **não** era o pipeline PDF/DOCX (`document_format.py` já preserva acento desde a remoção da dobra ASCII). Eram as strings de origem em `app/services/documental.py` e os avisos de rascunho. Testes: `tests/test_acentuacao_documentos.py`. |
| Placeholder `[CEP - preencher em .env]` no timbre | **CORRIGIDO neste PR** | `Settings.escritorio_*` devolve vazio e o consumidor descarta o segmento; pendência vai para `escritorio_pendencias()` + log de boot. |
| Unificar a fonte (PDF DejaVu × DOCX Times) | **Decisão pendente do titular** | `pdf_service.py` usa DejaVu Sans; `docx_service.py` usa Times New Roman 12pt. Ambas suportam pt-BR — não é bug, é escolha tipográfica institucional. Não unificado aqui para não decidir identidade visual sem o titular. |
| CNPJ do timbre resolve para outra razão social | **[INVESTIGAR] — exige conferência externa** | `ESCRITORIO_CNPJ = "32.491.468/0001-12"` em `app/core/config.py:837`. Conferir na Receita e corrigir no `.env`; não é alteração de código. |
| Processamento assíncrono (Celery) para Raio-X, Sala e peças | **Aberto** | Celery existe (`app/core/celery_app.py`, `app/tasks/`), mas `app/routers/raio_x.py` não despacha para a fila. Mudança arquitetural — merece onda própria. |
| Remover conta QA superadmin de produção | **Aberto — ato de ambiente** | Nenhum seed versionado cria `homolog.qa`; a conta veio de `qa/e2e/run_fictitious_smoke.py` rodado contra produção. Remoção é operação no banco de produção. |
| Ocultar módulos sem backend (Leads, Workflows, Prompts) | **RESOLVIDO — premissa desatualizada** | Os três têm backend registrado: `app/routers/workflow.py`, `prompts.py`, `produtividade.py` (todos em `main.py`); "Leads" é `CRMLeads.tsx`, que consome `/clients/?status=lead`. Ocultá-los agora removeria funcionalidade existente. |

### A barra final — a causa que a auditoria não podia ver

A auditoria registrou `/sala-juridica/` → "Failed to fetch" e `/sala-juridica` → 200, e
sugeriu alinhar front/endpoint ou mexer em `redirect_slashes`. Com o código à mão, a causa
é outra e é **de infraestrutura**:

1. Os 163 routers divergem: uns declaram a coleção como `""` (`/api/sala-juridica`),
   outros como `"/"` (`/api/clients/`). Nos dois casos a forma "errada" gera um **307**.
2. O `Location` do 307 é **absoluto**, montado a partir do esquema que o app enxerga.
3. O uvicorn subia com `--proxy-headers`, mas o default de `--forwarded-allow-ips` é
   `127.0.0.1`. O Nginx roda no **host** e chega pela porta publicada — o Docker reescreve
   a origem para o gateway da bridge, nunca `127.0.0.1`.
4. Logo o `X-Forwarded-Proto: https` era **descartado** e o redirect saía como
   `Location: http://…`. Numa página https o browser bloqueia o downgrade: "Failed to fetch".

Mexer em `redirect_slashes` trataria o sintoma numa rota. A correção de origem vale para
**todas** as rotas e também conserta qualquer outra URL absoluta gerada pelo app.

---

## ONDA 2 — Limpeza

| Item | Estado | Observação |
|---|---|---|
| Excluir dados de teste (13 clientes fictícios) | **Ato de ambiente** | Operação no banco de produção, via Lixeira. Fora do alcance do executor. |
| Chamadas mortas do front (404): `produtividade/`, `workflow/`, `lead/` | **RESOLVIDO — premissa desatualizada** | Os routers existem e estão registrados (ver Onda 1). |
| `clients/{id}/pending-items` 404 | **[INVESTIGAR]** | O front chama `/v1/clients/${id}/pending-items` (`DossieCliente.tsx`) — caminho que já traz `/v1` e escapa da poda do interceptor, virando `/api/v1/v1/…`. É a mesma classe do prefixo duplicado. |
| Ingestores duplicados (`stj` × `juris_import_stj`) | **Aberto** | Consolidação de fonte — onda própria. |
| Ferramentas + Mapa de Módulos → um inventário | **Aberto** | Decisão de produto. |
| Radar de Compliance + Radar Regulatório → uma tela | **Aberto** | Decisão de produto. |
| Relógio/citação no cabeçalho; rótulo "PADRÃO VISUAL LAW EJC" nas peças | **Aberto** | UX — verificar contra o bundle atual antes de agir. |

---

## ONDAS 3 a 7 — não iniciadas

Nenhuma foi tocada neste PR. Ordem e conteúdo permanecem os do prompt mestre. Três
ressalvas registradas na verificação:

- **Onda 5 (unificar Casos + Raio-X + Sala num pipeline de Triagem)** cruza o
  `plano-lancamento-v3.md`, que já descreve a mesma consolidação em outros termos
  (blocos 3.1–3.3). Reconciliar os dois planos **antes** de executar, para não produzir
  duas entradas únicas diferentes.
- **Onda 7 — refresh token em cookie httpOnly: já feito.** O backend emite o refresh em
  cookie httpOnly com JTI revogável (`CLAUDE.md`, seção Backend). O item pode sair do
  backlog.
- **Onda 7 — CSP: confirmado ausente.** Nenhum `Content-Security-Policy` em
  `backend/app` ou `nginx/ejc.conf`. É lacuna real e ainda aberta.

---

## O que este PR mudou

| Frente | Arquivos |
|---|---|
| Degradação por seção (padrão único) | `app/core/degradacao.py`, `app/routers/dossie_cliente.py`, `app/routers/relatorio_cliente.py`, `frontend/src/pages/DossieCliente.tsx` |
| Acentuação das minutas | `app/services/documental.py`, `app/services/document_format.py` |
| Timbre sem placeholder | `app/core/config.py`, `app/services/pdf_service.py`, `app/services/docx_service.py`, `app/services/system_prompts/templates_documentos.py`, `app/main.py` |
| Redirect atrás do proxy | `backend/entrypoint.sh`, `.env.example` |
| Testes | `tests/test_degradacao_por_secao.py`, `tests/test_acentuacao_documentos.py`, `tests/test_proxy_headers_redirect.py` (+ ajustes em `test_documento_marca_ia.py`, `test_procuracao_poderes.py`, `test_kit_documental.py`, `test_document_format.py`) |
