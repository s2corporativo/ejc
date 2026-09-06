# Inventário Arquitetural Completo do EJC — Fase 0

Fingerprint das fontes analisadas: `151548336fdf253a08998b0c8fd60de840ccf8b40c70cc4d304ac2994db2cf94`

> Este inventário é conservador e auditável. Nenhum item pode ser removido apenas por heurística. A classificação `excluir após migração` exige prova de ausência de consumidores, migração/backfill, telemetria, testes e rollback.

## Cobertura efetiva

- **5.493 itens individualizados e classificados**;
- **85 páginas** e **90 componentes** React;
- **58 rotas frontend**;
- **163 routers**, sendo **162 montados** e **1 não montado**;
- **810 endpoints FastAPI**;
- **233 serviços backend**;
- **98 tabelas ORM**;
- **2.098 funções Python** e **1.221 funções TypeScript/TSX**;
- **492 classes Python**.

## Resultado da classificação

| Classificação | Quantidade |
|---|---:|
| manter | 5.053 |
| consolidar | 180 |
| renomear | 25 |
| redirecionar | 5 |
| corrigir | 208 |
| desativar | 0 |
| excluir após migração | 22 |

Todos os **5.493 itens** receberam uma classificação válida. A maioria permanece em `manter` por padrão conservador até revisão funcional específica.

## Achados estruturais prioritários

1. **Caso × Processo:** a entidade `Process` 1:N já é canônica, mas `Case` ainda conserva campos processuais achatados. A ação correta é migrar dependências e dados, não criar novo módulo.
2. **CasoDetalhe:** permanece a principal página de alto acoplamento e deve ser decomposta por abas/domínios sem alterar contratos externos.
3. **Registro central:** `backend/app/main.py` e `frontend/src/config/moduleRegistry.tsx` concentram responsabilidades de montagem, catálogo, RBAC e navegação; devem ser modularizados gradualmente.
4. **IA:** há várias fachadas especializadas. Devem ser consolidados contratos, schemas, HITL, auditoria e fallback no núcleo canônico, sem eliminar capacidades jurídicas especializadas.
5. **Peças:** `legal_docs` deve permanecer como trilha canônica; `peca_geracao`, `peca_geracao_router` e fluxos correlatos precisam convergir para uma máquina de estados única.
6. **Rotas históricas:** `/prazos`, `/tarefas`, `/intimacoes`, `/suspensoes` e `/knowledge-hub` devem permanecer como aliases/redirecionamentos durante a migração.
7. **Implementação não montada:** somente `backend/app/modules/case_partes/router.py` permaneceu realmente sem caminho até o FastAPI. Existe versão canônica montada em `backend/app/routers/case_partes.py`; a versão paralela é candidata à exclusão após migração.

## Famílias objetivas candidatas à consolidação

### Frontend

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/DashboardModern.tsx`

### Backend — routers

- `backend/app/routers/data_room.py`
- `backend/app/routers/data_room_v4.py`
- `backend/app/routers/peca_geracao.py`
- `backend/app/routers/peca_geracao_router.py`
- `backend/app/routers/sala_de_guerra.py`
- `backend/app/routers/sala_de_guerra_v3.py`
- `backend/app/routers/teses.py`
- `backend/app/routers/teses_v4.py`

### Backend — serviços

- `backend/app/services/google_drive.py`
- `backend/app/services/google_drive_service.py`

## Routers com maior superfície

| Router | Endpoints |
|---|---:|
| `backend/app/routers/ramos.py` | 81 |
| `backend/app/routers/ai.py` | 20 |
| `backend/app/routers/cases.py` | 19 |
| `backend/app/routers/raio_x.py` | 17 |
| `backend/app/routers/clients.py` | 14 |
| `backend/app/routers/legal_docs.py` | 14 |
| `backend/app/routers/novos_modulos.py` | 14 |
| `backend/app/routers/users.py` | 14 |
| `backend/app/routers/rag.py` | 13 |
| `backend/app/routers/atendimentos.py` | 12 |
| `backend/app/routers/documents.py` | 12 |

## Decisões explícitas principais

### Manter

- `backend/app/models/process.py` — entidade canônica Processo;
- `backend/app/routers/ai_core.py` — fachada canônica da IA;
- `backend/app/services/ai_gateway.py` e `backend/app/services/ai/core/*` — núcleo/gateway de IA;
- `backend/app/routers/legal_docs.py` — trilha canônica de peças/documentos jurídicos;
- cofre de credenciais: router e service.

### Consolidar

- Jornada do caso no Orquestrador;
- dashboards paralelos;
- fachadas de IA e IA especializada, preservando responsabilidades jurídicas;
- Data Room, Teses, Sala de Guerra e geração de peças;
- serviços paralelos do Google Drive.

### Renomear

- vocabulário interno `Ramos` para `Áreas de Atuação`, preservando aliases de compatibilidade;
- enum/símbolos correlatos durante migração controlada.

### Redirecionar

- `/prazos`, `/tarefas`, `/intimacoes`, `/suspensoes` → Central de Atividades;
- `/knowledge-hub` → Pesquisa e IA.

### Corrigir

- campos processuais legados em `Case`;
- `CasoDetalhe.tsx`;
- montagem monolítica em `main.py`;
- registro central `moduleRegistry`;
- router/service de Processos;
- router `ramos.py`.

### Excluir após migração

- `LegacyClientListAdapter.tsx` e teste associado;
- página histórica `KnowledgeHub.tsx`;
- implementação paralela não montada `backend/app/modules/case_partes/router.py`;
- demais itens históricos identificados no inventário integral somente após verificação de consumidores.

## Critério obrigatório antes de excluir

1. localizar consumidores frontend, imports dinâmicos, scripts, jobs, workers, webhooks, portal e APIs públicas;
2. comprovar ausência de uso por logs/telemetria;
3. criar alias ou camada de compatibilidade quando houver rota histórica;
4. executar migração/backfill dos dados persistidos;
5. validar testes unitários, integração, E2E e rollback;
6. obter aprovação explícita no PR de remoção.

## Artefatos integrais

O workflow `Architecture Inventory — Phase 0` produz:

- `architecture_inventory.json` — inventário integral estruturado;
- `architecture_inventory.csv` — todos os itens, pronto para filtro em planilha;
- `classification_review.csv` — itens dependentes de revisão humana;
- `duplicate_families.json` — famílias objetivas da mesma camada;
- `manifest.json` — contagens, fingerprint e gate de classificação.

Nenhuma alteração funcional, rota, permissão, migration ou dado de produção foi modificada nesta Fase 0.
