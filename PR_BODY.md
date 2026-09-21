# feat(teses): pinned + fluxo de aprovação do sócio + fork + injeção no prompt

## O que muda

Estende o **Banco de Teses existente** (`teses`) com 4 capacidades que faltavam para a IA das `ai_skills` ser orientada pela doutrina do escritório:

1. **`pinned` (#)** — tese inegociável que entra **sempre** no `system_prompt` das skills, mesmo sem seleção explícita.
2. **Fluxo de aprovação do sócio** — `revisor_id` + `revisao_em`. Uma tese só é injetada no prompt quando `status='ativa'` **E** `revisor_id IS NOT NULL` (carimbo do sócio responsável). Editar `conteudo_estruturado` de tese aprovada reverte para `rascunho` (re-aprovação obrigatória).
3. **`TeseFork`** — cada advogado personaliza uma tese aprovada sem mexer no original; o fork do usuário é preferido na montagem do prompt.
4. **`TeseVersion`** — auditoria automática de cada edição de conteúdo (alinhado ao critério 6 do acceptance gate: "IA controlada, verificável").

E a integração que fecha o ciclo: **`ai_skill_service` injeta as Teses aprovadas no `system_prompt`** das skills — camada de doutrina do escritório, complementar ao RAG (que traz o fato do caso) e à Skill (que define a operação).

## Arquitetura: 3 layers de IA que se complementam

| Layer | Origem | Onde entra no prompt | Confiança |
|---|---|---|---|
| **Skill** (`EjcSkill.system_prompt`) | Catálogo de operações | `system` (já existe) | Autoral do EJC |
| **Tese** (`Tese.conteudo_estruturado`, pinned + aprovada) | **Este PR** | `system` (novo) | Autoral do escritório (carimbada por sócio) |
| **RAG** (`buscar_contexto_rag`) | Base de conhecimento (ingestão externa) | `user` com token delimitador | Não confiável — anti-injeção |

As Teses são conteúdo **autoral do escritório** (gravado por sócio), então podem ir no `system` — diferentemente do RAG, que vai no `user` por segurança (pente fino 03/09).

## Arquivos

### Aditivos (não quebram nada existente)

- `alembic/versions/162_teses_pinned_flow_prompt.py` — migration: 5 colunas novas em `teses` + 2 tabelas novas (`tese_forks`, `tese_versions`). `downgrade()` completo.
- `app/models/tese.py` — adiciona `pinned`, `experiencia_minima`, `revisor_id`, `revisao_em`, `conteudo_estruturado` em `Tese` + classes `TeseFork`, `TeseVersion`.
- `app/schemas/tese_governanca.py` — Pydantic: `TeseGovernancaUpdate`, `TeseSubmitReview`, `TeseApprove`, `TeseForkIn/Out`, `TeseVersionOut`, `TeseGovernancaOut`.
- `app/services/tese_governanca_service.py` — regras de domínio: `editar_conteudo_estruturado` (reverte para rascunho + versiona), `enviar_para_revisao`, `aprovar_tese` (RBAC sócio), `toggle_pinned`, `upsert_fork`, `listar_versoes`, `listar_para_prompt`, `injetar_no_prompt`.
- `app/routers/teses_governanca.py` — router novo (prefix `/teses`): `PATCH /{id}/governanca`, `POST /{id}/submit`, `POST /{id}/approve`, `POST /{id}/fork`, `GET /{id}/fork`, `GET /{id}/versions`.
- `app/seeds/teses_seed.py` — 15 teses jurídicas estruturadas (CPC 300, CLT 483, CDC 18, LEP 112, DJEN, etc.), já aprovadas. Idempotente.
- `tests/test_tese_governanca.py` — testes de inspeção de fonte (sem banco) + lógica pura + 1 teste DB (sob `RUN_DB_TESTS=1`).

### Modificações pontuais

- `app/main.py` — registra `teses_governanca.router` (2 linhas: import + include_router).
- `app/services/ai_skill_service.py` — 2 pontos de integração (linhas 208 e 463): chamam `injetar_no_prompt` envolto em try/except (Teses = enriquecimento, não fatal). ~12 linhas por ponto.

## Segurança e governança

- **RBAC**: só role `socio`/`admin`/`socio_diretor` aprova (`tese_governanca_service._pode_aprovar`).
- **Anti-injeção preservada**: Teses vão no `system` porque são autorais; RAG continua no `user` com token delimitador (não tocado).
- **Auditoria**: `TeseVersion` registra cada edição de conteúdo; `revisor_id`+`revisao_em` carimbam quem aprovou e quando.
- **Re-aprovação obrigatória**: editar conteúdo de tese aprovada reverte para `rascunho` — nada entra no prompt sem carimbo fresco do sócio.
- **Fail-open controlado**: se `injetar_no_prompt` falha, a skill executa sem Teses (log warning) — não derruba a chamada de IA.

## Testes

```bash
# Sem banco (CI rápido)
python -m pytest tests/test_tese_governanca.py -v

# Com banco (CI completo)
RUN_DB_TESTS=1 python -m pytest tests/test_tese_governanca.py -v
```

Testes de inspeção de fonte travam regressão: se alguém remover a migration, o model, o router, o registro no main, ou o ponto de integração no `ai_skill_service`, o teste denuncia.

## Seed

```bash
python -m app.seeds.teses_seed
```

Cria 15 teses cobrindo Cível, Trabalhista, Tributário, Consumidor, Família, Penal e Procedimento (DJEN). Cada uma com `conteudo_estruturado` em 6 seções: Fundamentação / Tese central / Requisitos / Riscos e armadilhas / Procedimento passo a passo / Checklist de peças e documentos.

## Compatibilidade

- Migration **aditiva**: não altera/remove colunas existentes. Safe em produção.
- Router **novo**: não toca no `teses.py` existente (897 linhas) — endpoints de governança ficam isolados.
- `TeseIn`/`TeseOut` legados **não modificados** — reads existentes continuam funcionando.
- Integração no `ai_skill_service` é **opt-in via try/except** — se o serviço de Teses falhar, as skills continuam funcionando.

## Checklist

- [x] Branch criada a partir de `main` atualizada
- [x] Migration aditiva com `downgrade()` completo
- [x] Model segue convenções do repo (`Column` style, `Base` de `app.core.database`)
- [x] Router novo (não mexe no `teses.py` existente)
- [x] Testes de inspeção de fonte + lógica pura (passam sem banco)
- [x] Teste DB sob `RUN_DB_TESTS=1` (mesmo padrão do repo)
- [x] Seed idempotente
- [x] RBAC de sócio no approve
- [x] Anti-injeção preservada (Teses no system, RAG no user)
- [x] Fail-open controlado (try/except no ponto de integração)
