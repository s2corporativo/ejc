# Relatório — FASE 3A: Ownership / IDOR (EJC)

**Data:** 2026-06-29 · **Escopo:** fechar vazamentos de acesso entre casos/clientes (IDOR) em documentos, peças e ramos. Código puro (sem schema, sem banco).
**Regra cumprida:** nenhuma execução contra banco; nada apagado; sem novas funcionalidades. Apenas gates de autorização.

> Esta é a **parte A** da Fase 3. A **parte B (isolamento do RAG por cliente/caso + correção de PII na indexação)** envolve migration de schema + decisão sobre dados existentes e é tratada num passo dedicado (ver §5).

---

## 1. Problema (do laudo, EOAB art. 25 + LGPD)

Qualquer usuário interno autenticado conseguia **ler/baixar/exportar/editar/remover** material de casos de que NÃO participa, porque os endpoints checavam apenas perfil/confidencialidade, não **ownership do caso**.

## 2. Gate canônico reutilizado

`app/core/ownership.py → verificar_acesso_caso(db, cu, case_id)`: 404 se o caso não existe; **gestão (socio+)** passa; **equipe** (responsável/auxiliar) passa; **salvaguarda anti-lockout** (caso sem dono → liberado p/ interno); senão **403**. Toda a Fase 3A espelha exatamente essa semântica (fonte única de verdade).

## 3. Correções aplicadas

### `routers/documents.py`
| Endpoint | Antes | Depois |
|---|---|---|
| `GET /` (listar) | filtrava só confidencialidade | + escopo por caso: não-gestão vê só docs dos seus casos / sem dono / sem caso |
| `GET /{id}/download` | só `_pode_acessar_confidencial` | + `verificar_acesso_caso` se houver `case_id` |
| `DELETE /{id}` | **sem ownership** | + `verificar_acesso_caso` se houver `case_id` |

### `routers/legal_docs.py` (escritas já estavam protegidas)
| Endpoint | Correção |
|---|---|
| `GET /` (listar) | + escopo por caso (mesma semântica) |
| `GET /{id}` (detalhe) | + `verificar_acesso_caso` |
| `GET /{id}/pdf` (export) | + `verificar_acesso_caso` |

### `routers/ramos.py` (helpers compartilhados pelos 6 ramos)
| Item | Antes | Depois |
|---|---|---|
| `_get_case` | só `advogado_responsavel_id` (ignorava auxiliar, sem anti-lockout) | delega a `verificar_acesso_caso` (consistência + corrige auxiliar) |
| `_crud_listar` | `r.__dict__` (vaza `_sa_instance_state`) + sem escopo | `_serialize()` + escopo por caso para não-gestão |
| `_crud_atualizar` | **sem ownership** + `__dict__` | + `verificar_acesso_caso(obj.case_id)` + `_serialize()` |
| `_crud_remover` | **sem ownership** | + `verificar_acesso_caso(obj.case_id)` |
| 6 endpoints de criação | `return X.__dict__` | `_serialize(X)` (elimina vazamento de `_sa_instance_state`) |

Novos helpers em `ramos.py`: `_serialize()` (serializa ORM sem `_sa_instance_state`) e `_casos_visiveis_subq()` (subquery de casos visíveis).

## 4. Validação executada (sem banco)

- ✅ `py_compile` OK em documents.py, legal_docs.py, ramos.py, ownership.py.
- ✅ Import dos 3 routers resolve o wiring de ownership.
- ✅ **App completo sobe**: `app.main:app` monta com **453 rotas** (nenhum import/NameError).
- ✅ **Zero** `.__dict__` restante em ramos.py.

## 5. Pendente — FASE 3B (isolamento do RAG) — passo dedicado

Exige cuidado próprio (schema + dados reais), por isso NÃO foi feita aqui:
- **Schema (migration 051):** `client_id`/`case_id`/visibilidade em `knowledge_docs`/`knowledge_chunks` (hoje sem isolamento → vazamento cruzado entre clientes).
- **PII na indexação (CRÍTICO, RAG-02):** `case_intel.indexar_peca_rag` chama `sanitizar_pii` **sem** `nomes_proteger` → nomes identificáveis vetorizados na base global. Fix forward-only (seguro).
- **Filtro de escopo** em `ai_service.buscar_contexto_rag` e `rag.py /buscar`.
- **Decisão de dados (requer revisão):** como tratar os chunks já indexados na base global (backfill de `client_id` vs. política "conhecimento público = global; peças/dossiês = restritos"). Não fazer backfill às cegas.

## 6. Observação importante

Como as Fases 1–3A estão no **código local**, só valem em produção após **rebuild + deploy** (que depende do `vps-tools/.env` com credenciais rotacionadas — Fase 0). A mudança de ownership **altera comportamento de acesso**: recomenda-se validar em staging que a equipe continua vendo seus próprios casos (a salvaguarda anti-lockout e a inclusão de auxiliar foram desenhadas para evitar bloqueios indevidos).
