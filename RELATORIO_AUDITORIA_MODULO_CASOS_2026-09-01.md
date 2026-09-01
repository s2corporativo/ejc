# Auditoria técnica, saneamento e padronização — Módulo CASOS (EJC)

**Data:** 01/09/2026
**Sistema:** EJC — Ecossistema Jurídico Clovis (De Paula Teixeira)
**Repositório:** `s2corporativo/ejc`
**Base auditada:** cópia local `C:\Users\User\EJC`, branch `reconciliacao/prod-x-auditoria`, HEAD `52c0e6fa`
**Auditor:** sessão Claude (Cowork) — análise estática + correção cirúrgica

---

## 0. Escopo e limitações da evidência

| Item | Situação |
|---|---|
| Clone direto de `github.com/s2corporativo/ejc` | **Indisponível nesta sessão** — repositório privado, sem credencial autorizada no proxy. Tentado duas vezes (`could not read Username`). |
| `git fetch` a partir da máquina do usuário | **Falhou** — o shell da ponte não tem o credential helper do Windows. |
| Base efetivamente auditada | Working tree local em `HEAD 52c0e6fa` (31/07/2026), branch `reconciliacao/prod-x-auditoria`. **Não reflete `origin/main` de ago/2026** (PRs até #763). |
| Execução de `pytest` | **Não executada** — `backend/.venv` é venv Windows (`Scripts/`), inutilizável no shell Linux da ponte; e os testes de banco exigem PostgreSQL/pgvector (`TEST_DATABASE_URL`). |
| `tsc --noEmit` (frontend) | **Executado — 0 erros** após as correções (ver §5). |
| `pyflakes` (backend, módulo Casos) | **Executado — 0 achados** além de dois `# noqa: F401` intencionais em `models/case.py`. |
| `python -m py_compile` | **Executado — OK** em todos os arquivos alterados. |

> **Consequência prática:** achados e correções valem para o estado `52c0e6fa`. Antes de abrir PR, rebasear sobre `origin/main` e reconferir os trechos tocados.

### 0.1 Achado de ambiente (não é bug de código, mas bloqueava a verificação)

A cópia local estava **corrompida em dois pontos** e ambos foram reparados durante a auditoria:

1. **39 arquivos rastreados estavam ausentes do working tree** (`git status` acusava ` D`), incluindo arquivos críticos do próprio módulo auditado:
   `frontend/src/pages/Casos.tsx` (a tela de listagem de casos), `backend/app/core/config.py`,
   `backend/app/services/ai_gateway.py`, `backend/app/services/scheduler.py`,
   `backend/app/services/peca_service.py`, `backend/app/routers/ramos.py`,
   `frontend/src/pages/RaioXProcesso.tsx`, `frontend/src/pages/CentralAtividades.tsx`,
   `frontend/package-lock.json`, fontes, logos e evidências de QA.
   **Reparo:** `git restore -- .` (os objetos estavam íntegros no `.git`). Working tree limpo depois.

2. **`frontend/node_modules` incompleto** — faltavam exatamente os arquivos **grandes** dos pacotes:
   `typescript/lib/_tsc.js`, `typescript/lib/typescript.js`, `lib.dom.d.ts`, `lib.es5.d.ts`,
   `@types/react/index.d.ts`, `@types/react-dom/index.d.ts`, `csstype/index.d.ts` (21 + 2 arquivos).
   Sintoma: `npx tsc` morria com `Cannot find module './_tsc.js'` — ou seja, **`npm run typecheck` e `npm run build` estavam quebrados na máquina**.
   **Reparo:** restauração byte-a-byte a partir de instalação limpa das MESMAS versões pinadas
   (`typescript@5.9.3`, `@types/react@19.2.17`, `@types/react-dom@19.2.3`, `csstype@3.2.3`).

   > O padrão "só os arquivos grandes sumiram" é assinatura típica de antivírus/OneDrive interrompendo o `npm install` no Windows. **Recomendação operacional:** excluir `node_modules` e `.git` da varredura em tempo real e da sincronização de nuvem.

---

## 1. Mapa real do módulo

### Backend
| Camada | Arquivos |
|---|---|
| Model | `models/case.py` (`Case`, `CaseMovimento`, enums `CaseArea`/`CaseStatus`/`CaseFase`/`CasePrioridade`), `models/case_parte.py`, `models/caso_area.py`, `models/case_intelligence.py` |
| Schema | `schemas/case.py` (278 linhas) |
| Domínio | `core/status_caso.py` (fonte única de status/agregados/visibilidade), `core/ownership.py` |
| Router principal | `routers/cases.py` (1.445 linhas) |
| Sub-routers do caso | `caso_areas.py`, `case_partes.py`, `conversao_caso.py`, `jornada_caso.py`, `case_intelligence.py`, `score_juridico.py`, `indice_risco.py`, `orquestrador.py`, `motor_peca.py`, `matriz_teses.py`, `mensagens.py`, `etiquetas.py`, `processes.py`, `kit_documental.py` |
| Testes | 14 arquivos `test_case*`/`test_caso*` |

### Frontend
`pages/Casos.tsx` (1.737 linhas) · `pages/CasoDetalhe.tsx` (1.418) + 8 abas em `pages/CasoDetalhe/` ·
`components/NovoCasoWizard.tsx` (722) · `pages/JornadaCaso.tsx` · `pages/portal/PortalCasos.tsx` ·
`types/caseStatus.ts` (fonte única de status, com trava de CI) · `contexts/useCasoFiltro.ts` · `config/moduleRegistry.tsx`

### Superfície de rotas
**57 rotas** sob `/cases` (inglês) + **38 rotas** sob `/casos` (português), distribuídas em 16 arquivos.

---

## 2. Defeitos corrigidos (aplicados no working tree)

Formato: **problema → causa raiz → solução → impacto → teste recomendado**.

---

### C-01 · `prazos_pendentes` sempre 0 no resumo do caso — **Alta**
**Arquivo:** `backend/app/routers/cases.py` :: `resumo_caso`

**Problema.** O contador de prazos pendentes do resumo do caso retornava `0` em 100% das requisições, inclusive para casos com prazos realmente pendentes.

**Causa raiz.** O predicado era:
```python
DeadlineStatus(Deadline.status) == DeadlineStatus.pendente
```
Isso **chama o Enum passando um objeto de coluna do SQLAlchemy**. `Enum(<InstrumentedAttribute>)` levanta `ValueError` incondicionalmente. A exceção era engolida pelo `except Exception:` do bloco, que gravava `0` e seguia em silêncio. O filtro nunca virou SQL.

**Solução.** Comparação feita **na coluna** (traduzida para SQL) + filtro de exclusão lógica, e remoção do `try/except` que mascarava o erro:
```python
q_pend = select(sqlfunc.count()).select_from(Deadline).where(
    Deadline.case_id == case_id,
    Deadline.deleted_at.is_(None),
    Deadline.status == DeadlineStatus.pendente,
)
```

**Impacto.** Restrito ao payload de `GET /cases/{id}/resumo`. Nenhum outro módulo consome esse campo hoje (ver D-01).

**Teste recomendado.** Caso com 2 prazos pendentes + 1 concluído + 1 na lixeira → `contadores.prazos_pendentes == 2`.

---

### C-02 · Contagens do resumo sem filtro de exclusão lógica — **Média**
**Arquivo:** `backend/app/routers/cases.py` :: `resumo_caso`

**Problema.** As 12 contagens do resumo (processos, documentos, peças, honorários, tarefas...) contavam **registros já excluídos logicamente**; o somatório financeiro de honorários idem.

**Causa raiz.** O filtro era escrito como
```python
.where(col == case_id, model_class.deleted_at.is_(None) if hasattr(...) else True)
```
O `else True` entrega um literal `True` do Python ao `.where()`, coagido a `TRUE` no SQL. Quando a entidade **tinha** `deleted_at`, o `if/else` funcionava; o problema real é que o encadeamento estava dentro de um `try/except Exception` genérico que zerava qualquer falha — e o somatório de `Fee` não filtrava `deleted_at` de forma alguma.

**Solução.** Imports estáticos no lugar dos `__import__("app.models.x", fromlist=[...])` dinâmicos (12 ocorrências), condicional explícita para `deleted_at` e filtro adicionado ao somatório de honorários. Removidos os `except Exception` que transformavam erro em zero.

**Impacto.** `GET /cases/{id}/resumo` passa a devolver números coerentes com as telas. Nenhuma alteração de contrato.

**Teste recomendado.** Excluir logicamente 1 documento e 1 honorário do caso → contadores e `honorarios_valor_total` caem correspondentemente.

---

### C-03 · Jurimetria classificando ganhos como "outro" — **Alta**
**Arquivos:** `backend/app/services/jurimetria.py` (corrigido) ↔ `backend/app/routers/cases.py` :: `EncerrarCasoReq`

**Problema.** `taxa_exito` subestimada e `taxa_improcedencia` **fixa em 0** — todo caso ganho integralmente e todo caso perdido caíam no balde `"outro"`.

**Causa raiz — divergência de vocabulário entre escritor e leitor.**
O **único** ponto que grava `cases.resultado` é `POST /cases/{id}/encerrar`, cujo regex aceita:
```
exito | exito_parcial | acordo | derrota | desistencia | arquivado
```
Já `services/jurimetria.py` classificava por:
```
exito_total | exito_parcial | acordo | improcedente
```
Ou seja: **`exito_total` e `improcedente` nunca são gravados por rota alguma**. Só `exito_parcial` e `acordo` casavam. (O comentário do próprio `models/case.py` documenta o vocabulário do *leitor*, não o do escritor — e `services/case_intel.py` já convivia com os dois via `_EXITO`, evidenciando drift conhecido e não resolvido.)

**Solução (sem migração de dados, reversível).** Mapa de sinônimos em `jurimetria.py` normalizando o vocabulário efetivamente persistido:
`exito → exito_total`, `derrota → improcedente`; `desistencia` e `arquivado` permanecem em `"outro"` **de propósito** (desfecho sem mérito).

**Impacto.** Corrige `GET /jurimetria` e todo painel que o consome. Não altera dados nem o contrato de escrita.

**Teste recomendado.** Encerrar caso com `resultado="exito"` → jurimetria contabiliza em `exito_total` e `taxa_exito > 0`. Encerrar com `derrota` → entra em `improcedente`.

> ⚠️ A **unificação definitiva** do vocabulário (schema + backfill) é decisão de produto — ver P-01.

---

### C-04 · `POST /cases/` derrubava com 500 em `prioridade` inválida — **Média (segurança operacional)**
**Arquivo:** `backend/app/schemas/case.py` :: `CaseCreate`

**Problema.** Assimetria de validação: `CaseUpdate` validava `status`, `fase` e `prioridade` contra os enums; `CaseCreate` validava apenas `area` e `numero_processo`.

**Causa raiz.** `cases.prioridade` é ENUM nativo do Postgres. Valor fora do enum não é rejeitado pelo bind do SQLAlchemy, chega cru ao banco e estoura `InvalidTextRepresentation` → **HTTP 500 na criação do caso** (exatamente a classe de falha que `core/status_caso.py` documenta ter fechado nos filtros).

**Solução.** `field_validator("prioridade")` em `CaseCreate`, espelhando o de `CaseUpdate` → **422 com a lista de valores aceitos**.

**Impacto.** Nenhum cliente legítimo é afetado (o frontend só envia valores válidos). Fecha um vetor de 500.

**Teste recomendado.** `POST /cases/` com `prioridade="urgentissima"` → 422, não 500.

---

### C-05 · Encerrar/arquivar caso por caminho lateral, sem RBAC — **Alta (controle de acesso)**
**Arquivo:** `backend/app/routers/cases.py` :: `atualizar` (PATCH)

**Problema.** Os endpoints canônicos exigem perfil de gestão jurídica:
- `POST /cases/{id}/arquivar` → `require_roles(_ARQUIVAMENTO_ROLES)` = superadmin/admin/socio/advogado
- `POST /cases/{id}/encerrar` → mesma lista, **mais** pós-mortem obrigatório (motivo, provas, lições)

Mas `PATCH /cases/{id}` aceitava `{"status": "encerrado"}` ou `{"status": "arquivado"}` com apenas `get_current_user` — **qualquer usuário autenticado** (secretária, estagiário, advogado auxiliar) produzia o mesmo efeito de estado, sem pós-mortem e sem o gate de perfil.

**Causa raiz.** Duas portas para a mesma transição de estado, com regras diferentes. Clássico de módulo que cresceu por camadas.

**Solução.** O PATCH passa a exigir `_ARQUIVAMENTO_ROLES` **quando e somente quando** o alvo é `encerrado` ou `arquivado` (403 caso contrário). Demais campos e a reabertura (`status="ativo"`, usada por `CasoDetalhe/TabResumo::reabrir`) seguem inalterados.

**Impacto.** Verificado: **nenhum consumidor do frontend faz PATCH de status para encerrado/arquivado** — o único PATCH de status no código é `{status:"ativo"}` em `TabResumo.tsx:234`. Risco de regressão: nulo no fluxo atual.

**Teste recomendado.** Usuário `secretaria` → `PATCH /cases/{id}` com `status="arquivado"` → 403. Usuário `advogado` → 200.

---

### C-06 · Caso reaberto continuava com `data_encerramento` preenchida — **Média (integridade)**
**Arquivo:** `backend/app/routers/cases.py` :: `atualizar` (PATCH)

**Problema.** Reabrir um caso encerrado (`PATCH status="ativo"`) deixava `data_encerramento` preenchida. Resultado: caso operacionalmente **aberto** carregando data de encerramento — estado impossível que contamina relatório de produtividade, tela do caso e qualquer agregação por período de encerramento.

**Causa raiz.** Assimetria entre caminhos: `POST /desarquivar` limpava `archived_at` e `archive_reason`; o PATCH limpava `archived_at` mas **nunca** `data_encerramento`.

**Solução.** Ao mover para qualquer status de `STATUS_ABERTOS` (`triagem|ativo|suspenso|acordo`), `data_encerramento` é zerada. O pós-mortem (`resultado`, `motivo_resultado`, `provas_determinantes`, `licoes_aprendidas`) é **preservado de propósito** — é histórico e já foi ingerido na base institucional/RAG.

**Impacto.** Corrige o fluxo de reabertura de `TabResumo::reabrir`. Ver P-02 sobre o `resultado` residual.

**Teste recomendado.** Encerrar → reabrir → `data_encerramento IS NULL` e `status = 'ativo'`.

---

### C-07 · Risco calculado nunca chegava à interface — **Média**
**Arquivos:** `backend/app/models/case.py`, `backend/app/schemas/case.py`, `frontend/src/types/index.ts`

**Problema.** `CasoDetalhe.tsx:1286` e `CasoDetalhe/TabResumo.tsx:644-647` leem `caso.risco_nivel` do payload de `/cases/{id}`. **Esse campo nunca era enviado** — o badge de risco calculado caía sempre no fallback `caso.risco` (risco manual). Ramo de UI morto desde sempre.

**Causa raiz.** A migration `032_indice_risco` adicionou à tabela `cases` as colunas `indice_risco`, `risco_nivel`, `risco_fatores`, `risco_atualizado_em`. `routers/indice_risco.py` **lê e escreve essas colunas em SQL cru**, mas elas **nunca foram declaradas no model `Case`** nem nos schemas `CaseResponse`/`CaseDetail`. O Pydantic descartava silenciosamente o que não estava declarado.

**Solução.**
- `models/case.py`: colunas declaradas (não altera schema do banco — apenas reconhece o que já existe).
- `schemas/case.py` → `CaseResponse`: expõe `indice_risco`, `risco_nivel`, `risco_atualizado_em`.
- `types/index.ts` → `Case`: campos alinhados ao contrato real.

**Impacto.** Aditivo. Nenhum consumidor quebra por campo novo. O badge de risco calculado passa a funcionar.

**Teste recomendado.** `POST /cases/{id}/indice-risco/recalcular` → `GET /cases/{id}` devolve `risco_nivel` e a tela exibe o badge calculado.

---

### C-08 · Desfecho e pós-mortem gravados e nunca lidos — **Média**
**Arquivo:** `backend/app/schemas/case.py` :: `CaseDetail`

**Problema.** `POST /cases/{id}/encerrar` grava `resultado`, `data_encerramento`, `motivo_resultado`, `provas_determinantes` e `licoes_aprendidas` — e **nenhuma rota devolvia esses campos**. A tela do caso encerrado não conseguia exibir resultado nem lições aprendidas, embora o dado estivesse no banco.

**Causa raiz.** `CaseDetail` nunca foi estendido depois da entrega do Pós-Mortem Jurídico (ECJ).

**Solução.** Campos adicionados a `CaseDetail` (backend) e ao type `Case` (frontend).

**Impacto.** Aditivo. Habilita a exibição do pós-mortem sem nova rota.

**Teste recomendado.** Encerrar caso → `GET /cases/{id}` devolve `licoes_aprendidas` preenchido.

---

### C-09 · Filtro "Tipo" na listagem mostrava resultado errado — **Média**
**Arquivos:** `backend/app/routers/cases.py` :: `listar`, `frontend/src/pages/Casos.tsx`

**Problema.** Ao filtrar por Judicial/Extrajudicial/Consultoria na tela de Casos, o usuário via **apenas os casos daquele tipo que por acaso estavam na página já carregada**, e o total exibido continuava sendo o total sem filtro. Além disso, mudar o filtro **não disparava recarga** (`tipoF` não estava nas dependências do `useEffect`).

**Causa raiz.** A paginação é server-side (`page_size: 50`), mas o filtro de tipo era aplicado no cliente, sobre `data.data` — o array da página corrente. O backend **não tinha** parâmetro `case_type` em `GET /cases/`.

**Solução.**
- Backend: parâmetro `case_type` (`judicial|extrajudicial|consultoria`, vocabulário de `services/case_automacao.py`), aplicado na query. Para `judicial` o filtro também aceita `NULL` — é o default histórico da coluna e havia registro legado sem valor, que sumiria da listagem filtrada.
- Frontend: `case_type` enviado ao backend, `tipoF` incluído nas dependências do efeito, filtro client-side removido.

**Impacto.** Aditivo no backend (parâmetro opcional). O total e a paginação passam a refletir o filtro.

**Teste recomendado.** Base com 60 casos extrajudiciais e 200 judiciais → filtrar Extrajudicial → `total == 60` e paginação coerente.

---

### C-10 · `DELETE /cases/{id}/areas/{area}` mentia sobre o resultado — **Média (UX/confiabilidade)**
**Arquivo:** `backend/app/routers/caso_areas.py` :: `remover_area`

**Problema.** O endpoint devolvia `{"ok": true}` **sempre**, mesmo quando nada era removido. O `DELETE` tinha `AND principal = false` na cláusula: ao tentar remover a área principal, a tela dava sucesso, recarregava — e a área continuava lá, sem explicação. Idem para área não vinculada.

**Causa raiz.** Resposta fixa, desacoplada do efeito real da operação.

**Solução.** O endpoint passa a refletir a realidade: **404** se a área não está vinculada ao caso; **409** com mensagem acionável se é a área principal; `{"ok": true}` apenas quando removeu de fato.

**Impacto.** Ambos os consumidores (`CasoDetalhe/TabResumo.tsx:157-165` e `components/CaseCommandDock.tsx:114-119`) já tratam erro com `toast.error(detail)` — a mensagem aparece corretamente, sem alteração no frontend.

**Teste recomendado.** Tentar remover a área principal → 409 e a mensagem no toast. Remover área secundária → 200 e some da lista.

---

### C-11 · Área do caso gravada sem normalização nem validação — **Média**
**Arquivo:** `backend/app/routers/caso_areas.py` :: `adicionar_area`

**Problema.** `POST /cases/{id}/areas` gravava o texto **cru** recebido no corpo. Duas consequências:
1. `"Ambiental"` e `"ambiental"` entravam como registros distintos, **escapando do índice único** `uq_caso_areas_case_area (case_id, area)`;
2. qualquer string de até 40 caracteres virava "área do caso", sem qualquer aderência à taxonomia canônica.

Enquanto isso, `cases.py::aplicar_extracao` **já normalizava** (`.strip().lower()`) — mesma tabela, duas regras.

**Causa raiz.** Endpoint escrito com SQL cru e sem contrato de entrada tipado.

**Solução.**
- Normalização `.strip().lower()` + limite de 40 caracteres (largura real da coluna);
- validação contra a **taxonomia canônica** (`tabela areas`, servida por `GET /areas`), com 422 e mensagem apontando o catálogo;
- **fail-open deliberado:** se o catálogo estiver vazio (ambiente novo sem seed), o endpoint continua aceitando — para não travar bootstrap;
- removido o `SELECT` redundante em `cases` (o `verificar_acesso_caso` seguinte já resolvia 404/403).

**Impacto.** Escrita mais restrita. Áreas legadas fora do catálogo continuam legíveis e removíveis (o DELETE não valida taxonomia).

**Teste recomendado.** `POST` com `area="Ambiental"` → grava `ambiental` e a segunda tentativa cai no `ON CONFLICT`. `POST` com `area="inexistente"` → 422.

---

### C-12 · Status `acordo` sem tratamento em 3 superfícies de UI — **Baixa/Média**
**Arquivos:** `frontend/src/components/UI.tsx`, `pages/portal/PortalCasos.tsx`, `pages/portal/PortalDashboard.tsx`

**Problema.** `acordo` é um dos **seis** status canônicos (`types/caseStatus.ts`), mas não constava:
- em `UI.tsx`, nem no `STATUS_REGISTRY` nem no `LEGACY_STATUS_TONE` → renderizava como texto cru cinza minúsculo, **sem ícone** — violando a regra WCAG que o próprio arquivo declara ("cor + ícone + texto, nunca só cor");
- nos mapas `STATUS_LABEL` de `PortalCasos.tsx` e `PortalDashboard.tsx` (5 de 6 status) → **o cliente final via "acordo" cru no portal**.

**Causa raiz.** A consolidação documentada em `types/caseStatus.ts` unificou as listas do painel interno, mas **não alcançou** o `StatusBadge` genérico nem as duas telas do portal.

**Solução.** `acordo` adicionado às três superfícies, com ícone `Handshake`, tom `teal` e rótulo "Acordo".

**Impacto.** Puramente visual, aditivo.

**Teste recomendado.** Caso com `status="acordo"` → badge "Acordo" com ícone na listagem interna e no portal do cliente.

---

### C-13 · Higienização e padronização de `routers/cases.py` — **Baixa (dívida técnica)**

| Item | Antes | Depois |
|---|---|---|
| `__import__("app.models.x", fromlist=[...])` | 14 ocorrências dentro de laço, reexecutadas por iteração — invisíveis a lint e type-checker | imports estáticos no topo da função |
| Import duplicado `uuid4` | reimportado dentro de `atualizar()` | removido (já no topo) |
| Import duplicado `Deadline, DeadlineStatus` | reimportado dentro de `excluir()` | removido |
| Import duplicado `CaseParte` | reimportado em `assistente_estrategico_caso()` | removido |
| Import duplicado `verificar_acesso_caso` | reimportado em `analisar_caso_ia()` | removido |
| `from app.services.datajud_service import ...` na linha 849 | import de módulo no meio do arquivo | movido para o bloco de imports (verificado: sem ciclo) |
| Aliases `_BM2` / `_F2` do Pydantic | segundo import de `BaseModel`/`Field` com nomes crípticos | usa os já importados |
| `getattr(case, "descricao", ...)` | **campo fantasma** — `Case` não tem coluna `descricao` (só `descricao_fatos`); resolvia sempre para `None`/`""` em `teses_sugeridas` e `analisar_caso_ia` | removido, com comentário explicando por que o valor permanece vazio (comportamento preservado) |
| `"area": c.area` no `/resumo` | devolvia o objeto Enum enquanto `status`/`fase`/`prioridade` já vinham como `.value` | `.value` |

**Impacto.** Zero mudança de comportamento. Código passa a ser verificável por lint/type-checker.

---

## 3. Obsoletos e código morto (mapeados — **não removidos**)

> Removidos **não** foram, deliberadamente: rota sem consumidor no frontend pode ter consumidor externo (n8n, automação, integração). A remoção exige confirmação sua.

### D-01 · Rotas de `/cases` sem nenhum consumidor no frontend

| Rota | Arquivo | Observação |
|---|---|---|
| `GET /cases/{id}/resumo` | `cases.py` | Docstring diz existir para "evitar N chamadas no CasoDetalhe" — o CasoDetalhe **nunca a chama**. Era onde vivia o bug C-01. |
| `POST /cases/{id}/assistente-estrategico` | `cases.py` | Terceiro endpoint de IA sobre o caso (ver D-02) |
| `GET /cases/{id}/linha-do-tempo` | `cases.py` | Concorre com `GET /casos/{id}/timeline` (`visual_law.py`) |
| `POST /cases/{id}/movimentos/{mov_id}/traduzir` | `cases.py` | |
| `POST /cases/{id}/kit-documental` | `kit_documental.py` | |
| `GET/POST /cases/{id}/matriz-teses` + 2 sub-rotas | `matriz_teses.py` | |
| `POST /cases/{id}/motor-peca/gerar` | `motor_peca.py` | Só `/analisar` é consumido |
| `GET /cases/{id}/inteligencia` + 2 sub-rotas | `case_intelligence.py` | |

**Ação sugerida:** confirmar consumidores externos; o que não tiver, marcar como `deprecated` no OpenAPI por um ciclo antes de remover.

### D-02 · Três endpoints de IA sobre o mesmo caso
`POST /cases/{id}/analisar` · `POST /cases/{id}/assistente-estrategico` · `POST /ai/casos/{id}/assistente`
Três caminhos, três formas de auditoria em `ai_logs`, um só domínio. Consolidação recomendada — decisão de produto.

### D-03 · Schemas declarados e nunca usados
`CasePendencia` e `CasePendenciasResponse` (`schemas/case.py`) documentam o corpo do 422 de `DELETE /cases/{id}`, mas o router monta o dicionário à mão. Ou o router passa a usá-los, ou os schemas saem — hoje são documentação que o código não honra.

### D-04 · Persistência mista no mesmo módulo
Existem models ORM `CaseParte` e `CasoArea`, mas `case_partes.py` e `caso_areas.py` operam **inteiramente em SQL cru** (`text()`), e `conversao_caso.py` insere em `processes`/`case_movimentos` por SQL cru apesar de haver models. Duas camadas de persistência para as mesmas tabelas — cada regra nova precisa ser escrita duas vezes.

### D-05 · Lixo local (não versionado — repositório está limpo)
`frontend/dist` e `__pycache__` estão corretamente no `.gitignore`; **nenhum** `.env`, backup ou `dist` versionado. No disco, porém: **1.894 diretórios `__pycache__`** e um `frontend/dist` antigo com bundles de arquivos que **já não existem** (`Casos-cDCrIi_y.js` etc.) — resíduo de build, inofensivo, mas convém limpar antes de qualquer diagnóstico por inspeção de arquivos.

---

## 4. Pendências que exigem sua decisão (não aplicadas)

### P-01 · Unificar o vocabulário de `cases.resultado` — **Alta**
C-03 corrigiu a **leitura**. A causa permanece: dois vocabulários para o mesmo campo.
**Opções:**
- **(a) Canonizar o que já está gravado** (`exito|exito_parcial|acordo|derrota|desistencia|arquivado`): atualizar comentário do model, `services/case_intel.py` e as categorias da jurimetria. **Zero migração de dados.** — *recomendada.*
- **(b) Canonizar o vocabulário da jurimetria** (`exito_total|...|improcedente`): exige alterar o regex de `EncerrarCasoReq`, o frontend do encerramento e **backfill** de todos os casos já encerrados.

### P-02 · Reabertura e o campo `resultado` residual — **Média**
Após C-06 o caso reaberto fica `ativo` sem `data_encerramento`, mas **mantém `resultado`**. A jurimetria filtra por `status IN (encerrado, arquivado)`, então **hoje não há contaminação de métrica**. Ainda assim, é dado de desfecho num caso em curso. Decidir: limpar `resultado` na reabertura, ou preservá-lo como histórico (posição atual).

### P-03 · Dois namespaces de URL para o mesmo domínio — **Média**
**57 rotas em `/cases`** (inglês) e **38 em `/casos`** (português), em 16 arquivos — `provas` (8), `workflow` (5), `honorarios_oab` (3), `portal` (3), `visual_law` (3), `jornada_caso`, `andamentos`, `teses`, `timesheet`, `checklists`, `export`, `intake`, `sumulas`, `novos_modulos`, `solicitacoes_documentos`, `ai`.
Nenhuma rota está quebrada — o frontend chama cada uma com o prefixo certo. O custo é de manutenção e de erro humano.
**Plano sugerido (não executado):** congelar `/cases` como canônico; novas rotas só em `/cases`; migração das 38 em ondas, cada uma com alias temporário `/casos/*` → 308 e prazo de remoção. **Requer aprovação — é refatoração ampla.**

### P-04 · Rótulo divergente para o status `triagem` — **Baixa**
`types/caseStatus.ts` define `triagem → "Triagem"`; `UI.tsx`, `PortalCasos.tsx` e `PortalDashboard.tsx` exibem **"Em análise"** — e há teste (`UI.test.tsx:25`) fixando esse comportamento.
Não alterei: a divergência parece **decisão de produto** (linguagem voltada ao cliente), não defeito. Decidir se `CASE_STATUS_LABEL` deve ser alinhado ao rótulo real ou se as telas devem passar a consumi-lo.

### P-05 · Adoção parcial da fonte única de status no frontend — **Média**
`types/caseStatus.ts` é a fonte única, com trava de CI (`test_status_caso_paridade_frontend.py`), mas **apenas 2 arquivos a importam** (`Dashboards.tsx`, `DashboardModern.tsx`). `UI.tsx`, `PortalCasos.tsx` e `PortalDashboard.tsx` mantêm mapas próprios — foi exatamente assim que as quatro listas divergentes anteriores nasceram (C-12 é a prova de que já voltou a acontecer). Migrar as três telas para o módulo canônico.

### P-06 · Dois gates de ownership no mesmo módulo — **Baixa (vazamento de informação)**
`cases.py::_filtro_visibilidade` nega acesso via filtro na query → **404**. `core/ownership.verificar_acesso_caso` nega → **403**. O mesmo módulo responde diferente para a mesma condição, e o **403 confirma a existência do caso** para quem não deveria saber. Padronizar em 404 (não vaza existência) ou documentar a diferença como intencional.

### P-07 · `frontend/package-lock.json` — **Média (reprodutibilidade)**
O arquivo **é versionado** (estava apenas ausente do working tree, restaurado em §0.1). Confirme que o pipeline de deploy usa `npm ci` — e não `npm install` — para que build de produção não resolva versões diferentes das homologadas.

---

## 5. Verificação executada

| Verificação | Comando | Resultado |
|---|---|---|
| Sintaxe Python | `python -m py_compile` nos 5 arquivos alterados | **OK** |
| Análise estática Python | `pyflakes` em 11 arquivos do módulo | **0 achados** (fora 2 `# noqa: F401` intencionais) |
| Ciclo de import | inspeção de `services/datajud_service.py` | **sem ciclo** (importa só `core.config` + `models.case`) |
| Existência dos models usados em `resumo_caso` | 8 classes × `case_id`/`deleted_at` | **todas confirmadas** |
| Colunas de risco existem no banco | `alembic/versions/032_indice_risco.py` | **confirmado** (`add_column` idempotente, revisão bem anterior à 131 em produção) |
| Contrato frontend → backend | 31 endpoints `/cases` chamados pelo frontend × rotas registradas | **100% existem** — nenhuma rota quebrada |
| Sintaxe TypeScript | `ts.createSourceFile` nos 6 arquivos tocados | **OK** |
| **Type-check completo do frontend** | `tsc --noEmit -p tsconfig.json` | **EXIT 0 — 0 erros** |
| `pytest` | — | **não executado** (venv Windows + exige PostgreSQL/pgvector) |

**Cobertura de teste existente do módulo:** 14 arquivos (`test_casos`, `test_casos_dblevel`, `test_case_partes_dblevel`, `test_case_subrecursos_ownership_dblevel`, `test_idor_criacao_caso_dblevel`, `test_status_caso_paridade_frontend`, `test_jornada_caso`, `test_case_duplicate_guard`, entre outros).
**Risco de regressão nos testes existentes:** baixo — os testes que tocam `caso_areas` exercitam apenas `listar_areas`; nenhum teste faz PATCH de status para `encerrado`/`arquivado`; nenhum consome `/resumo`.

---

## 6. Arquivos alterados

```
 backend/app/models/case.py                    |  14 +-
 backend/app/routers/cases.py                  | 180 +++++++++++++++--------
 backend/app/routers/caso_areas.py             |  47 ++++++-
 backend/app/schemas/case.py                   |  28 ++++
 backend/app/services/jurimetria.py            |  33 +++-
 frontend/src/components/UI.tsx                |   6 +
 frontend/src/pages/Casos.tsx                  |  25 ++--
 frontend/src/pages/portal/PortalCasos.tsx     |   1 +
 frontend/src/pages/portal/PortalDashboard.tsx |   1 +
 frontend/src/types/index.ts                   |  15 +
 10 arquivos, 265 inserções(+), 85 remoções(-)
```

Aplicadas no working tree de `C:\Users\User\EJC` (branch `reconciliacao/prod-x-auditoria`). **Nada foi commitado, nenhum push foi feito, nada foi executado na VPS** — conforme a governança do repositório (`CLAUDE.md` regras 1/8/9). Patch também disponível em `saneamento-modulo-casos.patch` na raiz do repositório.

---

## 7. Próximos passos recomendados

1. **Rebasear sobre `origin/main`** — a base auditada é de 31/07; `main` avançou em agosto (PRs até #763). Reconferir os trechos tocados.
2. **Abrir branch e PR** a partir de `main` com este conjunto, referenciando este relatório.
3. **Rodar a suíte com banco de teste** (`TEST_DATABASE_URL` apontando para `ejc_test`) — especialmente `test_casos_dblevel`, `test_case_subrecursos_ownership_dblevel` e `test_status_caso_paridade_frontend`.
4. **Decidir P-01** (vocabulário de `resultado`) — é o item de maior impacto ainda aberto: afeta diretamente a jurimetria do escritório.
5. **Confirmar D-01** (rotas sem consumidor) antes de qualquer remoção.
6. **Higiene da estação:** excluir `node_modules` e `.git` da varredura do antivírus e da sincronização de nuvem — foi o que corrompeu a cópia local (§0.1).
