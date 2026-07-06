# Relatório de Auditoria e Estabilização — EJC — 2026-07-06

_Auditoria cética de estabilidade, segurança e integridade, seguida de correção
mínima por prioridade. Branch: `claude/audit-ejc-stabilization-5jqau0`._

Método: diagnóstico primeiro (baseline real de testes + 3 agentes de leitura em
paralelo: segurança/permissões/LGPD, contrato rotas frontend↔backend, migrations/
schema), depois correção por bloco lógico com teste antes de cada commit. Nenhuma
correção declarada sem evidência de execução.

---

## 1. Resumo executivo

O EJC **já estava em bom estado de estabilidade** ao início desta rodada — fruto
de ciclos de auditoria anteriores (vários `RELATORIO_*.md`/`LAUDO_*.md` no repo).
Esta auditoria **confirmou** isso com execução real e aplicou **endurecimentos
pontuais de baixo risco**, sem redesign nem refatoração ampla.

| Dimensão | Antes (verificado) | Depois |
|---|---|---|
| Backend — suíte pytest | 820 passando, 39 skipped | **828 passando, 39 skipped** (+8 testes novos) |
| Backend — import de `app.main` | OK | OK |
| Frontend — `tsc --noEmit` + `vite build` | limpo | limpo (sem alteração de frontend) |
| Cadeia de migrations | head único `075` | head único **`076`**, íntegra |
| Contrato rotas front↔back | íntegro | íntegro |
| Loop de commits/workflows no GitHub | ausente | ausente (confirmado) |

**Riscos principais encontrados (todos de severidade baixa):** um vazamento de
metadados no Data Room (documento de caso alheio), telefone de titular em log de
aplicação (LGPD), ausência de índice em FK usada no controle de acesso, e um
guard de produção que não recusava CORS `*`. Todos corrigidos e cobertos por
teste. Nível de estabilidade: **sólido antes, sólido e mais endurecido depois.**

---

## 2. Baseline (evidência de execução, não alegação)

- `python -m pytest tests -q` em venv isolada → **820 passed, 39 skipped** (baseline)
  → **828 passed, 39 skipped** (após as correções + testes novos).
- `import app.main` → OK (roda todos os event subscribers/registros de router).
- `npm run build` (tsc + vite) → **limpo**.
- Os testes `*_dblevel.py` (RUN_DB_TESTS) exigem Postgres+pgvector e rodam no CI
  (job `db-validation`); a suíte rápida cobre o restante.
- Nota de ambiente (não é bug do repo): `pip install -r requirements.txt` falha
  localmente ao compilar `http-ece` (dependência de `pywebpush`) por causa do
  setuptools patcheado do Debian deste sandbox. Em venv limpa (setuptools do
  PyPI, como no CI) instala sem erro. **CI não é afetado.**

---

## 3. Rotas (contrato frontend ↔ backend)

Agente de contrato mapeou ~180 chamadas do frontend contra os prefixos montados
em `backend/app/main.py`.

- **Rotas órfãs/quebradas (404 garantido):** 0. Todos os caminhos do frontend
  resolvem, inclusive os ambíguos (`/v1/*`, routers sem prefix, `/ai/*`,
  `/processes/*`, `/veredito_ia/analisar`). Os 404s de auditorias antigas
  (`ia_extra`, `jurimetria_extra`) já estavam montados.
- **Links de menu → rota inexistente:** 0 (41 links de `Layout.tsx` verificados;
  há catch-all `path="*"` → `/`, então nem há tela branca possível).
- **Botões sem ação no fluxo principal** (cliente/caso/documento/prazo/tarefa/
  financeiro): 0. Stub conhecido `Whatsapp.tsx` fica fora do fluxo jurídico.
- **Pendência (baixa, higiene):** 2 routers existem mas não são montados —
  `assistente.py` e `area_modulos.py` — e sua função é servida por outros routers
  (`ai.py`/`cases.py`; endpoints de mapa de módulos). Código morto inofensivo.
  **Deixados intactos de propósito:** remover não traz ganho de estabilidade e
  arrisca quebrar imports; fica como limpeza futura opcional. (O agente reportou
  4, mas confirmei que `precedentes_jurisprudencia` e `advogado_estilo` **estão
  montados** via `include_router` aninhado em `services/event_subscribers.py` —
  são features vivas, não código morto.)

---

## 4. Permissões e segurança jurídica

Auditoria de `auth`, middleware, ownership e routers de maior valor (documentos,
portal, clientes, honorários, extratos, análise bancária, export, visual law).
**Panorama: muito bem protegido.** `AuthMiddleware` exige JWT em todo `/api/*`;
IDOR/ownership consistente via `verificar_acesso_caso`/`_filtro_visibilidade`;
segredos não versionados; uploads com magic bytes + UUID; CORS por env; JWT com
rotação/revogação; 2FA TOTP; anti-brute-force.

Achados genuínos e **correções aplicadas**:

| Sev. | Achado | Arquivo | Correção |
|---|---|---|---|
| Baixo | **Vazamento de metadados no Data Room**: vincular/listar `document_id` sem revalidar cofre + ownership do caso do documento → advogado não-dono via título/nome de docs de casos alheios | `routers/data_room.py` | `adicionar_arquivo` valida cofre (`_pode_acessar_confidencial`) + `verificar_acesso_caso` antes de gravar; `obter_data_room` filtra por acesso a cada doc (novo helper `_usuario_ve_documento`). O download real já era protegido em `documents.py`. |
| Baixo | **PII em log de aplicação (LGPD art. 37/46)**: telefone de lead gravado em claro no log | `routers/webhooks.py:82` | Mascarado para `****` + 4 últimos dígitos. A notificação interna ao staff (uso legítimo, no banco) permanece. |
| Info | **Guard de produção não recusava CORS `*`** (perigoso com `allow_credentials=True`) | `core/config.py` | Boot em produção agora falha explicitamente se `CORS_ORIGINS` contém `*`. |
| Info | Link externo do Data Room quebrado (path singular vs plural, fora de `PREFIXOS_PUBLICOS`) — **fail-closed**, não é vuln | `routers/data_room.py:206` | **Não alterado** (mais restritivo que o pretendido; corrigir exigiria abrir prefixo público — fora de escopo). Registrado como pendência. |

**Risco remanescente:** o `AuthMiddleware` valida assinatura/exp do JWT mas não
checa `is_active`/revogação (isso fica no `Depends(get_current_user)`, usado por
praticamente todos os endpoints). Impacto nulo hoje; recomendação: nunca criar
endpoint que dependa só do middleware.

---

## 5. Telas e navegação

Sem alteração de frontend nesta rodada (não era necessário para estabilidade).
Verificação de contrato (seção 3) confirma: menus levam a telas existentes, sem
link morto, sem botão no-op no fluxo principal, catch-all evita tela branca.
`tsc + vite build` limpos. Testes de renderização/navegação já existentes na
suíte permanecem verdes.

---

## 6. Migrations e banco de dados

Agente de schema importou `Base.metadata` (76 tabelas) e simulou as 76 migrations.

- **Cadeia:** head único (`075` → agora `076`), sem down_revision quebrada, sem
  múltiplas heads, sem revisões órfãs, sem IDs duplicados. **OK.**
- **Duplicidade:** nenhuma tabela/coluna criada em conflito. **OK.**
- **Drift model → migration:** toda coluna de model tem DDL. **OK.**
- **Risco de perda de dados:** as 3 migrations com `drop` têm downgrade funcional
  e validação documentada. **OK.**
- **Correção aplicada — índices em FKs de caminho quente** (`076_fk_hot_path_indexes`):
  Postgres não indexa FK automaticamente. A mais relevante,
  `cases.advogado_auxiliar_id`, é usada no gate de visibilidade por advogado em 4
  routers (`fees`, `legal_docs`, `documents`, `search`) — sem índice, seq scan a
  cada filtro. Migration puramente aditiva e reversível (`CREATE INDEX IF NOT
  EXISTS` / `DROP INDEX IF EXISTS`) sobre 6 FKs confirmadas (`cases`, `clients`,
  `case_partes`, `data_rooms` ×2, `processes`). **Validada contra Postgres real**
  (apply → idempotência → downgrade → 0 índices) além do CI.
- **Pendências registradas (não aplicadas, por decisão de risco):**
  1. **Guard de drift do CI é só nível-tabela** (`tests/test_schema_sync.py`
     compara `get_table_names()`, não colunas/índices/FK). Hoje o nível de coluna
     está limpo, mas não há proteção contra regressão futura de coluna. Recomendo
     estender a Camada 2 (Postgres real) para comparar `get_columns()` das tabelas
     de núcleo. **Não implementado** para não arriscar CI vermelho por
     divergências intencionais pré-existentes (ex.: item 2) sem mapeá-las todas.
  2. **Drift reverso** em `documents`: 5 colunas (`sensitivity_level`, `watermark`,
     `access_users`, `download_count`, `last_accessed_at`) criadas pela migration
     `050` e usadas via SQL cru em `novos_modulos.py`, **não mapeadas no model**.
     Não quebra em runtime. Deixadas como estão (padrão SQL-cru intencional, como
     as 30 tabelas da allowlist `_SEM_MODEL_INTENCIONAL`); mapear no ORM traria
     risco de fragilidade de dialeto/`server_default` (JSONB, NOT NULL) sem ganho
     de estabilidade. **Decisão registrada** conforme a alternativa que o próprio
     diagnóstico ofereceu.

---

## 7. Testes

- **Existentes:** 820 passando (suíte rápida) + suíte `*_dblevel` no CI.
- **Criados (8):** `tests/test_estabilizacao_auditoria.py` — gate de acesso do
  Data Room (`_usuario_ve_documento`: cofre, caso alheio, caso próprio, sem caso)
  e guard de CORS de produção (recusa `*`, aceita origem explícita, dev livre).
- **Atualizado:** `tests/test_smoke.py` — head esperado `075` → `076` (é o guard
  de head único, atualizado por design ao adicionar migration de head).
- **Resultado:** **828 passed, 39 skipped**, `tsc + vite build` limpos.
- **Falhas remanescentes:** nenhuma.

---

## 8. Fluxo real do usuário (E2E)

O fluxo cliente → caso → documento → análise → prazo → tarefa → financeiro já é
coberto por testes na suíte (incl. `test_e2e_fictitious_matrix.py` com dados
fictícios) e foi validado em rodadas anteriores (`RELATORIO_VALIDACAO_FUNCIONAL`).
Esta rodada não alterou esses fluxos; a suíte que os exercita permanece verde.
Itens `P0`/CRÍTICOS de rodadas antigas (Veredito IA com jurisprudência fake;
Dossiê/Diplomacia com valores hardcoded) foram **verificados por leitura direta
do código como já corrigidos** (`core/veredito_ia.py` usa jurimetria+RAG reais;
`diplomacia_v3.py` puxa Selic do BCB com fallback documentado).

---

## 9. Segurança jurídica / LGPD / OAB

- **Corrigido:** PII (telefone) fora do log de aplicação; vazamento de metadados
  entre casos no Data Room fechado.
- **Confirmado saudável:** PII cifrada em repouso (Fernet+HMAC), sanitização de
  PII antes de provedor externo de IA, HITL obrigatório com `AILog`, isolamento
  RAG por cliente/caso (testado), uploads/downloads com gate de cofre.
- **Recomendação obrigatória:** manter o princípio "nenhum endpoint sensível
  depende só de bloqueio no frontend" — verificado hoje, deve ser regra de
  revisão contínua.

---

## 10. GitHub / workflows (anti-loop)

- **Branch única:** `claude/audit-ejc-stabilization-5jqau0`. Nenhuma branch extra.
- **Commits:** agrupados por bloco lógico (segurança; banco), teste antes de cada.
- **Workflows revisados:** `ci.yml` roda testes/build em push→main e PRs; **não
  faz commit/push de volta** → sem risco de loop. `deploy.yml`/`deploy-vps.yml`
  fazem deploy via SSH (não commitam no repo) → sem loop.
- **Achado operacional (não é loop):** `deploy.yml` dispara auto-deploy na VPS em
  push para a branch **obsoleta** `claude/ejc-design-overhaul-2t4pb1` (ainda
  existe no origin), em vez de `main`. `deploy-vps.yml` já cobre `main`
  corretamente. Recomendo apontar `deploy.yml` para `main` ou removê-lo —
  **não alterado** aqui por ser infraestrutura outward-facing (requer decisão do
  time), mas é a pendência operacional de maior relevância.

---

## 11. Pendências (o que ainda pode ser feito)

| # | Pendência | Prioridade | Risco se não feito | Próxima ação |
|---|---|---|---|---|
| 1 | `deploy.yml` aponta para branch obsoleta, não `main` | Média | Deploy de produção pode disparar de branch errada / não disparar do esperado | Apontar para `main` ou remover (decisão do time) |
| 2 | Guard de drift do CI só nível-tabela | Média | Regressão futura de coluna/índice passa despercebida (verde enganoso) | Estender `test_schema_sync` p/ `get_columns()` das tabelas de núcleo |
| 3 | 5 colunas de `documents` não mapeadas no model | Baixa | Inconsistência model↔schema (sem quebra runtime) | Mapear no ORM ou registrar na allowlist de colunas |
| 4 | Link externo do Data Room com path quebrado | Baixa | Compartilhamento externo não funciona como documentado | Corrigir path + incluir em `PREFIXOS_PUBLICOS` com cuidado |
| 5 | 2 routers não montados (`assistente`, `area_modulos`) | Baixa | Peso morto no repo | Remover após mapear que nada os importa |
| 6 | `AuthMiddleware` não checa `is_active`/revogação | Baixa | Usuário desativado usa access token até expirar (8h) se um endpoint depender só do middleware | Regra de revisão: sempre usar `get_current_user` |

---

_Relatório gerado a partir de execução real (pytest, build, Postgres para a
migration) e leitura de código — não de lista de desejos. Correções mínimas,
por prioridade, sem redesign, sem duplicação, sem loop de GitHub._
