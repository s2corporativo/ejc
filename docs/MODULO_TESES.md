# Módulo Teses — Banco de Teses + Governança + Injeção no Prompt

> **Status**: `feat/teses-pinned-flow-prompt` (PR #1774). Documentação canônica
> do módulo, alinhada ao critério 10 do
> [EJC 10/10 Acceptance Gate](./EJC_10_10_ACCEPTANCE_GATE.md) — "operação
> documentada e homologada".

## 1. O que é

O **Módulo Teses** é o repositório institucional de teses jurídicas do
escritório. Cada Tese é **conteúdo curado e auditável** que orienta a IA ao
redigir peças — tese central, fundamentação, requisitos, riscos, procedimento
e checklist. Diferente do RAG (que traz o **fato do caso**) e da `EjcSkill`
(que define a **operação** de IA), a Tese traz a **doutrina do escritório**.

### 1.1 Três layers de IA que se complementam

| Layer | Origem | Onde entra no prompt | Confiança |
|---|---|---|---|
| **Skill** (`EjcSkill.system_prompt`) | Catálogo de operações | `system` | Autoral do EJC |
| **Tese** (`Tese.conteudo_estruturado`, pinned + aprovada) | **Este módulo** | `system` | Autoral do escritório (carimbada por sócio) |
| **RAG** (`buscar_contexto_rag`) | Base de conhecimento (ingestão externa) | `user` com token delimitador | Não confiável — anti-injeção |

As Teses são conteúdo **autoral do escritório** (gravado por sócio
responsável), então podem ir no `system` — diferentemente do RAG, que vai no
`user` por segurança (ver pente fino 03/09 em
[`ai_skill_service.py`](../backend/app/services/ai_skill_service.py)).

## 2. Modelo de dados

Localização: [`backend/app/models/tese.py`](../backend/app/models/tese.py).
Migration: [`162_teses_pinned_flow_prompt.py`](../backend/alembic/versions/162_teses_pinned_flow_prompt.py).

### 2.1 `Tese` (extensão da tabela existente)

A tabela `teses` já existia no EJC (com `titulo`, `descricao`,
`fundamentacao`, `jurisprudencia`, `area_juridica`, `tipo`, `status`,
`vezes_usada`/`venceu`/`perdeu`). O módulo adiciona 5 colunas:

| Coluna | Tipo | Descrição |
|---|---|---|
| `pinned` | `Boolean` (default `false`) | Tese inegociável — entra **sempre** no prompt, mesmo sem seleção. Equivalente ao `#` do catálogo de habilidades. |
| `experiencia_minima` | `String(30)` (default `"geral"`) | `júnior` \| `pleno` \| `sênior` \| `geral`. Gating de uso por experiência. |
| `revisor_id` | `String(36)` FK `users.id` | Sócio que carimbou a tese. `NULL` = ainda não aprovada. |
| `revisao_em` | `DateTime(timezone=True)` | Momento do carimbo. |
| `conteudo_estruturado` | `Text` | Markdown em 6 seções (§3). É o que entra no prompt. Separado de `descricao`/`fundamentacao` legados para preservar reads existentes. |

### 2.2 `TeseFork` (nova tabela)

Cópia pessoal de uma Tese aprovada, editável pelo advogado **sem mexer no
original**. Constraint unique `(tese_id, user_id)` — um fork por usuário por
tese. Na montagem do prompt, o fork do usuário é **preferido** sobre o
`conteudo_estruturado` da Tese.

### 2.3 `TeseVersion` (nova tabela)

Histórico auditável de cada edição de `conteudo_estruturado`. Salva o
conteúdo **anterior** a cada `PATCH` que o altera. Incrementa `version` na
Tese. Alinhado ao critério 6 do acceptance gate ("IA controlada,
verificável").

## 3. Estrutura do `conteudo_estruturado`

Markdown com 6 seções obrigatórias:

```markdown
# <Título da tese>

## Fundamentação
- (dispositivos legais: CF/88, CPC/2015, CC/2002, leis especiais)
- (jurisprudência: STF, STJ, TJs — formato "REsp 1.234.567/SP, Rel. Min. X, 3ª Turma, STJ")
- (doutrina: autor, obra, edição)

## Tese central
(uma frase que resume o pedido e o fundamento)

## Requisitos
- pressupostos processuais
- pressupostos materiais
- provas necessárias

## Riscos e armadilhas
- (teses contrárias consolidadas)
- (prescrição/decadência aplicáveis)
- (órgãos divergentes)

## Procedimento passo a passo
1. 
2. 
3. 

## Checklist de peças e documentos
- [ ] procuração
- [ ] comprovante de protocolo
- [ ] documentos de partes
```

As seções `## Riscos e armadilhas` e `## Procedimento passo a passo` são o que
tornam a tese **pregável** e não um resumo teórico.

## 4. Fluxo de aprovação

```
draft  ──(autor envia)──▶  in_review  ──(sócio aprova)──▶  approved (ativa + revisor_id)
  ▲                          │                              │
  │                          └──(sócio pede ajustes)──▶  draft (com nota)
  │
  └──(editado depois de aprovado)──  volta para in_review (re-aprovação obrigatória)
```

### 4.1 Estados (`Tese.status` combinado com `revisor_id`)

| `status` | `revisor_id` | Comportamento |
|---|---|---|
| `rascunho` | `NULL` | **Draft / em revisão** — não entra no prompt |
| `ativa` | `NULL` | **Inconsistência** — não entra no prompt (precisa de carimbo) |
| `ativa` | preenchido | **Aprovada** — elegível para o prompt |
| `arquivada` | — | **Obsoleta** — não entra no prompt |

**Regra de ouro**: só Teses com `status='ativa'` **E** `revisor_id IS NOT NULL`
 entram no prompt (ver `listar_para_prompt` no service).

### 4.2 RBAC

| Role | Cria | Edita | Envia p/ revisão | Aprova | Personaliza (Fork) |
|---|---|---|---|---|---|
| `estagiario` | ✗ | ✗ | ✗ | ✗ | ✗ |
| `advogado` | ✓ | suas | ✓ | ✗ | ✓ |
| `socio` / `socio_diretor` / `admin` | ✓ | todas | ✓ | ✓ | ✓ |

A aprovação (`revisor_id`, `revisao_em`) é o **carimbo de ortodoxia** do
escritório. Sem isso, a Tese não passa de rascunho.

## 5. API

Router: [`backend/app/routers/teses_governanca.py`](../backend/app/routers/teses_governanca.py).
Prefix: `/teses`. Tag: "Banco de Teses — Governança".

| Método | Endpoint | Descrição | RBAC |
|---|---|---|---|
| `PATCH` | `/{id}/governanca` | Atualiza `pinned`, `experiencia_minima`, `conteudo_estruturado` | advogado+ |
| `POST` | `/{id}/submit` | Envia tese para revisão do sócio | advogado+ |
| `POST` | `/{id}/approve` | Sócio carimba — `status=ativa` + `revisor_id` + `revisao_em` | **sócio+** |
| `POST` | `/{id}/fork` | Cria/upsert fork pessoal do advogado | advogado+ |
| `GET` | `/{id}/fork` | Recupera fork do usuário | advogado+ |
| `GET` | `/{id}/versions` | Histórico auditável de edições | advogado+ |

O CRUD principal (`GET /teses`, `POST /teses`, etc.) continua no router
legado [`teses.py`](../backend/app/routers/teses.py) — não modificado.

## 6. Injeção no prompt

Localização: [`backend/app/services/tese_governanca_service.py`](../backend/app/services/tese_governanca_service.py)
→ função `injetar_no_prompt`.

A integração acontece em `ai_skill_service.py`, em **2 pontos**:
`executar_skill` e `executar_skill_documento_longo`. Antes de montar as
`messages`, o service anexa o bloco de Teses ao `system_prompt`:

```python
system_prompt = skill.system_prompt
# ── Teses do escritório (migration 162) ──
try:
    from app.services.tese_governanca_service import injetar_no_prompt
    system_prompt = await injetar_no_prompt(
        db, system_prompt, area=skill.area, user_id=user_id
    )
except Exception as _exc_teses:  # Teses = enriquecimento, não fatal
    logger.warning("Teses indisponíveis no prompt: %s", type(_exc_teses).__name__)
```

### 6.1 Regras de seleção (`listar_para_prompt`)

1. Todas as `pinned` aprovadas (sempre entram — inegociáveis).
2. As da área do caso/skill (aprovadas), até o limite.
3. As explicitamente selecionadas pelo usuário (aprovadas).
4. Para cada uma, **prefere o fork do usuário** se existir.

Limite padrão: 8 teses. Não retorna teses `rascunho`/`arquivada` nem sem
`revisor_id`.

### 6.2 Fail-open controlado

Se `injetar_no_prompt` falhar (ex: DB indisponível), a skill executa **sem
Teses** (log warning). A chamada de IA não derruba — Teses são enriquecimento,
não requisito funcional.

## 7. Segurança e governança

Alinhado ao [acceptance gate 10/10](./EJC_10_10_ACCEPTANCE_GATE.md):

- **Anti-injeção preservada**: Teses vão no `system` (autoral do escritório);
  RAG continua no `user` com token delimitador (pente fino 03/09).
- **RBAC**: só role `socio`/`admin`/`socio_diretor` aprova
  (`_pode_aprovar` no service).
- **Re-aprovação obrigatória**: editar `conteudo_estruturado` de tese aprovada
  reverte para `rascunho` — nada entra no prompt sem carimbo fresco do sócio.
- **Auditoria**: `TeseVersion` registra cada edição; `revisor_id` +
  `revisao_em` carimbam quem aprovou e quando.
- **Soft-delete**: `Tese.deleted_at` (legado) — `listar_para_prompt` filtra.
- **Próximo passo (roadmap)**: registrar no `AILog` quais Teses entraram em
  cada chamada (critério 6 completo — "IA controlada, verificável").

## 8. Seed

[`backend/app/seeds/teses_seed.py`](../backend/app/seeds/teses_seed.py).

```bash
python -m app.seeds.teses_seed
```

Cria 15 teses cobrindo 7 áreas, cada uma com `conteudo_estruturado` em 6
seções:

| Área | Teses |
|---|---|
| Cível | Tutela de urgência (CPC 300), Cumulação de pedidos (CPC 327), Honorários sucumbenciais (CPC 85), Exceção de pré-executividade |
| Trabalhista | Justa causa rescisória (CLT 483), Verbas rescisórias |
| Tributário | Repetição de indébito, Exceção de pré-executividade fiscal |
| Consumidor | Vício do produto (CDC 18), Dano moral por atraso de voo |
| Família | Divórcio consensual extrajudicial (Lei 11.441), Ação de alimentos (Lei 5.478/68) |
| Penal | Progressão de regime (LEP 112), Habeas corpus (CPP 647) |
| Procedimento | Ajuizamento eletrônico via DJEN/CNJ |

Idempotente: pula teses com mesmo `titulo`. As teses nascem `status=ativa` +
`revisor_id` preenchido (se houver sócio com email `socio@ejc.local`) ou
`revisor_id=NULL` (admin deve carimbar manualmente antes de usar em produção).

## 9. Testes

[`backend/tests/test_tese_governanca.py`](../backend/tests/test_tese_governanca.py).

### 9.1 Testes de inspeção de fonte (sem banco)

Travam regressão por inspeção do código — baratos, rodam em qualquer CI:
- `test_migration_162_existe_e_encadeia` — migration existe, encadeia na 161, cria as 2 tabelas.
- `test_model_tese_tem_novos_campos_e_classes` — model tem `pinned`, `revisor_id`, etc. + `TeseFork` + `TeseVersion`.
- `test_router_governanca_existe_com_endpoints` — router tem os 6 endpoints.
- `test_router_governanca_registrado_no_main` — `main.py` registra o router.
- `test_integracao_injetada_no_ai_skill_service` — `ai_skill_service` chama `injetar_no_prompt` nos 2 pontos.

### 9.2 Testes de lógica pura

- `test_pode_aprovar_restringe_a_socio` — RBAC: só `socio`/`admin`/`socio_diretor` aprovam.
- `test_conteudo_para_prompt_prefere_fork` — fork do usuário > `conteudo_estruturado` > `descricao`.
- `test_slugify_do_seed_normaliza_acentos` — slug normaliza acentos/espaços.

### 9.3 Testes de banco (`RUN_DB_TESTS=1`)

- `test_editar_conteudo_aprovada_reverte_para_rascunho` — editar tese
  aprovada reverte para `rascunho` + salva versão anterior.

```bash
# Sem banco (CI rápido)
python -m pytest tests/test_tese_governanca.py -v

# Com banco (CI completo)
RUN_DB_TESTS=1 python -m pytest tests/test_tese_governanca.py -v
```

## 10. Integrações futuras (roadmap)

Módulos vizinhos no EJC que conversam com Teses:

| Módulo | Conexão planejada |
|---|---|
| [`prompt_juridico.py`](../backend/app/models/prompt_juridico.py) | Prompts salvos referenciam Tese por id — ao regenerar, re-injeta a Tese atualizada |
| [`jurisprudencia_interna.py`](../backend/app/models/jurisprudencia_interna.py) | Tese `pinned` puxa julgados da jurisprudência interna como `## Fundamentação` dinâmica |
| [`matriz_teses.py`](../backend/app/models/matriz_teses.py) | `ThesisCandidate` aprovada vira `Tese` em `rascunho` automaticamente |
| [`advogado_estilo.py`](../backend/app/models/advogado_estilo.py) | Tese + estilo do advogado = par completo ("o quê" + "como" dizer) |
| [`wiki.py`](../backend/app/models/wiki.py) | Wiki interna referencia Teses (link bidirecional) |
| [`diario_oficial.py`](../backend/app/models/diario_oficial.py) | Alerta quando ementa nova contradiz Tese `pinned` |
| `docs/biblioteca_juridica/` | Script `importar_biblioteca` lê `.md` e cria Teses em `rascunho` |

## 11. Métricas de eficácia (roadmap)

O `Tese` legado já tem `vezes_usada`, `vezes_venceu`, `vezes_perdeu`,
`taxa_sucesso` — mas o módulo de governança (este PR) ainda não incrementa
esses contadores. Próximo passo:

- Quando uma `ai_skill` roda com uma Tese injetada e a peça vira `LegalDoc`
  com `PecaStatus.aprovada` → incrementar `vezes_usada`.
- Quando o caso é julgado procedente (via `TeseCasoLink.resultado='procedente'`)
  → incrementar `vezes_venceu`.
- UI de Teses passa a ranquear por **taxa de sucesso real do escritório**, não
  por ordem alfabética.

## 12. Referências

- [EJC 10/10 Acceptance Gate](./EJC_10_10_ACCEPTANCE_GATE.md) — critérios de certificação.
- [Governança de IA](./GOVERNANCA_IA.md) — papéis, limites, fluxo e merge dos agentes de IA.
- [Backup & Restore Runbook](./BACKUP_RESTORE_RUNBOOK.md) — continuidade.
- PR de origem: #1774 (`feat/teses-pinned-flow-prompt`).
