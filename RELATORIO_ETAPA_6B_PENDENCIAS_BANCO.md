# RELATÓRIO ETAPA 6B — RESOLUÇÃO DAS PENDÊNCIAS DO BANCO DE DADOS

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`
Continuação de `RELATORIO_ETAPA_6_BANCO_DE_DADOS.md` (seções 5 e 9 — riscos remanescentes e próximos passos).

## Resultado direto

Ao investigar as pendências, descobri um **risco destrutivo latente mais grave** que os próprios itens pendentes: o `alembic env.py` tem `target_metadata = Base.metadata` (autogenerate ligado) **sem nenhuma guarda**. Com 30 tabelas existentes no banco mas fora da metadata (acesso SQL cru), um `alembic revision --autogenerate` geraria `op.drop_table(...)` para todas elas — perda de dados catastrófica se aplicado. Corrigi isso, que também **torna segura** a decisão de não modelar as 30 tabelas agora. Itens genuinamente destrutivos (M8, remoção de coluna órfã) foram **mantidos em espera** por exigirem backup + sua aprovação — regra absoluta que não pode ser contornada.

Todas as mudanças: **zero DDL, zero migration nova, zero alteração de dados**. Validação: **98 testes passam**, 1 pula (Camada 2, depende de banco vivo), 1 bloqueado por libmagic no Windows (pré-existente).

## Pendências CORRIGIDAS (seguras)

### P1 — Foot-gun destrutivo do autogenerate (novo achado, o mais grave) — `backend/alembic/env.py`
- **Problema:** autogenerate ativo sem guarda `include_name`/`include_object`. Geraria drops das ~30 tabelas SQL cru.
- **Correção:** adicionada função `include_name` que restringe o autogenerate às tabelas presentes em `Base.metadata`. Migrations existentes (upgrade/downgrade) **não são afetadas** — só a geração de novas revisões.
- **Efeito colateral positivo:** com essa guarda, **não modelar as 30 tabelas SQL cru deixou de ser risco** — o autogenerate nunca vai tentar dropá-las. Modelá-las vira melhoria opcional futura, não correção urgente.

### P2 — Guarda de drift em CI (achado C4) — `.github/workflows/ci.yml` + `backend/tests/test_schema_sync.py`
- O teste de drift (Camada 1) **já roda no CI** via o passo `pytest tests` existente — não precisou de mudança estrutural. Corrigi só o nome defasado do job (`73 testes` → `pytest (inclui guarda de drift de schema)`).
- Adicionei `test_autogenerate_tem_guarda_include_name`: trava por inspeção de fonte que a proteção P1 não pode ser removida sem quebrar o teste (env.py não é importável fora do Alembic).

### P3 — 30 tabelas sem model ORM (ampliação do C3/C4)
- **Decisão consciente:** NÃO modelar em massa agora. Justificativa técnica: (a) com o autogenerate ligado, um model com tipo impreciso geraria ALTER espúrio — modelar sem um Postgres local para validar tipos seria arriscado; (b) a guarda P1 já elimina o risco destrutivo; (c) o drift test já rastreia as 30 via allowlist e acusa qualquer tabela NOVA. Modelá-las (priorizando as mais usadas) segue como melhoria futura, não pendência de risco.

## Pendências MANTIDAS EM ESPERA (exigem backup + aprovação explícita)

Estas **não foram executadas** por serem destrutivas ou mexerem em dados de produção — proibido sem confirmação dupla e backup validado (regra absoluta do projeto; além disso não há banco local, o banco real está só na VPS).

### H1 — M8: campos legados duplicados `cases` × `processes`
- `cases.numero_processo`/`tribunal`/`comarca`/`vara`/`valor_causa` duplicam `processes.*`, sincronizados só pelo backfill único da migration 048.
- **Mitigação já existente (verificada):** o caminho de leitura já usa `processes` como fonte de verdade via `services/processo_service.py::numero_processo_efetivo()`. O risco residual é só edição direta dos campos legados em `cases`.
- **Opções para resolução (a decidir com você):**
  1. Remover as colunas legadas de `cases` (migração destrutiva — exige backup + confirmação; irreversível na prática).
  2. Trigger de sincronização no Postgres (migração de schema — exige teste em cópia).
  3. Não fazer nada (a mitigação de leitura já cobre o caso comum).
- **Recomendação:** opção 3 no curto prazo; opção 1 só num bloco dedicado com backup.

### H2 — `cases.linked_judicial_case_id` (coluna órfã pós-048)
- Substituída por `processes`, não referenciada em código recente.
- Remoção é `DROP COLUMN` (destrutivo). **Mantido** até decisão explícita + backup.

### H3 — Camada 2 do teste de schema (comparação com banco vivo)
- Requer Postgres **com pgvector + pg_trgm + gen_random_uuid** (as migrations 001/009/048 dependem dessas extensões). Um `postgres:16` puro no CI falharia no `alembic upgrade head`.
- **Não adicionei ao CI às cegas** para não entregar um CI vermelho não validável localmente. Passo correto: rodar uma vez contra uma cópia de dev do banco da VPS (imagem `pgvector/pgvector:pg16` + `CREATE EXTENSION`) e, comprovando verde, então adicionar ao CI.

## Comandos executados
```
.venv-codex/Scripts/python.exe -m py_compile alembic/env.py    -> OK
.venv-codex/Scripts/python.exe -m pytest tests -k "not monta_com_rotas"
  -> 98 passed, 1 skipped (Camada 2), 1 deselected (libmagic)
```
Nenhum comando de banco (DDL/DML/migration/deploy) foi executado.

## Riscos eliminados
- **Drop destrutivo via autogenerate** (P1) — era o maior risco latente; eliminado.
- **Regressão da proteção** (P2) — travada por teste.

## Riscos remanescentes (documentados)
- H1/H2 (destrutivos/dados) — aguardando decisão + backup.
- H3 — validação plena de schema contra banco vivo, pendente de ambiente com pgvector.
- 30 tabelas sem model — agora seguras (P1), mas ainda sem ORM (melhoria futura).

## Próximo passo recomendado
Prosseguir para a próxima etapa do roteiro (integração frontend/backend / IA-RAG, conforme o `PLANO_ETAPA_4`). Os itens H1/H2/H3 entram num bloco de banco dedicado quando você autorizar backup e, para H3, houver um Postgres com pgvector acessível.

## Critério de aceite
- Pendências seguras corrigidas: **ATENDIDO** (P1, P2, P3).
- Sem alteração destrutiva: **ATENDIDO** — itens destrutivos explicitamente mantidos em espera com plano.
- Riscos mapeados e testes verdes: **ATENDIDO** (98 passed).
