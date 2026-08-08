# Auditoria — Bloco 0 (infraestrutura e dados): Sentry, embeddings/RAG, backup offsite e homologação

**Data:** 2026-08-08 · **Escopo:** itens 0.1 a 0.5 da tabela de pré-lançamento
· **Registro:** Issue #792 / PR #793
· **Método:** leitura do código-fonte na branch `claude/auditoria-infra-dados-2mgrm9`
(base `main` em `f27d54f`), sem acesso ao ambiente de produção (regra 9 de
`docs/GOVERNANCA_IA.md` — o executor não acessa VPS nem banco de produção).

> **Limite central desta auditoria:** o repositório prova o que o *código* faz,
> não o que o `.env` da VPS contém. Para cada item, este relatório separa
> (a) o que já está pronto no código, (b) o que falta **no código** e
> (c) o que é **ato humano de ativação** em produção — que este executor não
> pode e não deve realizar.

## Sumário executivo

| ID  | Item                                | Estado no código                                            | O que falta para o critério de conclusão |
|-----|-------------------------------------|-------------------------------------------------------------|------------------------------------------|
| 0.1 | Ativar Sentry (DSN + release)       | **Decidido 2026-08-08: mantido e ativado** (ver adenda) — integração completa e gated; `release` corrigido | Ato humano: `SENTRY_DSN` no `.env` da VPS |
| 0.2 | Decidir estratégia de embeddings    | **Decisão de fato já tomada e implementada**: local (fastembed/ONNX, `multilingual-e5-large` 1024d) | Ratificação formal do titular (registro da decisão). A dicotomia do item ("Ollama × externo") está desatualizada |
| 0.3 | Religar embeddings + backfill       | **Máquina completa e governada** (workflow de ativação, canário, backfill idempotente, job automático de órfãos) | Ato humano: dispatch de `rag-production-activation.yml` na `main`. O critério do plano cita `modo: vetorial`; a API real responde `modo: "semantica"` |
| 0.4 | Ativar backup offsite               | **Implementado** (Fernet + Google Drive/rclone, rotação, drills de restauração), default OFF | Atos humanos: `BACKUP_ENABLED=true` + chave + credencial na VPS; decisão do titular sobre prazo de retenção; recomendação de `BACKUP_OFFSITE_OBRIGATORIO=true` |
| 0.5 | Ambiente de homologação separado    | **Parcial** — guardas anti-produção, suíte H01–H15 e purga de resíduos existem; **o ambiente em si não existe** | Decisão de infra do titular (onde/como hospedar homolog) + composição da stack; purga dos dados fictícios em produção é ato humano com backup prévio |

Nenhum dos cinco itens exige desenvolvimento grande. Três (0.1, 0.3, 0.4) já têm
a máquina pronta e dependem essencialmente de **atos de ativação em produção**,
que a governança reserva ao titular. As únicas lacunas de código encontradas
estão no 0.1 (release do Sentry) e no 0.5 (não há composição de homologação).

---

## 0.1 — Sentry (DSN + release)

### O que já está pronto no código

- **Integração completa e defensiva** em `backend/app/core/observability.py`:
  `init_sentry()` inicializa o SDK apenas com `SENTRY_DSN` preenchido, com
  `send_default_pii=False`, scrub LGPD de headers/cookies/campos sensíveis
  (`_before_send`, linhas 62–84) e integrações FastAPI + SQLAlchemy
  (`observability.py:107-119`). Chamada no boot em `backend/app/main.py:215`.
- **Dependência pinada:** `sentry-sdk[fastapi]==2.13.0`
  (`backend/requirements.txt:139`).
- **Config pronta:** `SENTRY_DSN` (vazio = desligado), `SENTRY_ENVIRONMENT`,
  `SENTRY_TRACES_SAMPLE_RATE` (`backend/app/core/config.py:683-685`;
  `.env.example:601`).
- **O sistema não mente sobre o coletor:** `coletor_erros_ativo()` reporta o
  estado real do init (não a presença do DSN), e a resposta de 500 só promete
  notificação quando há coletor de fato (`observability.py:129-144`) — corrige
  o achado da auditoria de julho em `/analytics/roi-por-area`.
- **Erros de frontend chegam ao backend:** o ErrorBoundary reporta crashes de
  render a `POST /observabilidade/frontend-error`
  (`backend/app/routers/observabilidade.py`), que entram no mesmo funil.

### Lacunas de código (achado desta auditoria)

1. **`release` não é enviado ao Sentry.** O item 0.1 pede "DSN + release";
   `sentry_sdk.init()` em `observability.py:112-119` não passa o parâmetro
   `release`, e `SENTRY_RELEASE` não existe em lugar nenhum do repositório.
   Existe `app_version()` (env `APP_VERSION`/`GIT_SHA`, senão `"dev"` —
   `observability.py:44-46`) usada só no healthcheck. Sem release, o painel do
   Sentry não correlaciona erro ↔ versão implantada, nem marca regressões.

   **Correção:** passar `release=app_version()` no `init_sentry()`.

   > **Correção a este relatório (versão anterior estava errada):** a versão
   > original deste documento afirmava que `GIT_SHA` também não era exportado
   > no deploy. É falso — `scripts/deploy_vps_safe.sh:162-234` já exporta
   > `GIT_SHA`, usa no `docker compose build` e **verifica o valor publicado
   > contra `/api/health`**, com rollback automático em divergência;
   > `docker-compose.yml:55,144` já encaminha `GIT_SHA` ao container. `app_version()`
   > já recebe um SHA real em produção. A única lacuna de código era mesmo o
   > parâmetro `release` ausente — corrigida separadamente (ver PR de execução
   > vinculado a este relatório).

### Conflito de decisão em aberto: PR #773 propõe REMOVER o Sentry

O PR draft **#773 — "Remover Infosimples, Sentry e Ollama do EJC"** está aberto
e caminha na direção **oposta** ao item 0.1 desta tabela (ativar Sentry). As
duas coisas não podem prosseguir ao mesmo tempo: ou o titular ratifica a
ativação (0.1) e o #773 perde a parte de Sentry, ou ratifica a remoção e o
item 0.1 sai da tabela (e a "causa-raiz nº 1 — falhas sem diagnóstico" precisa
de outra resposta, ex. o funil `/observabilidade/frontend-error` + logs).
**Decisão do titular antes de qualquer PR de execução no 0.1.**

### Atos humanos de ativação

- Resolver o conflito com o PR #773 (acima).
- Criar o projeto no Sentry (SaaS free tier ou self-hosted) e preencher
  `SENTRY_DSN` (e opcionalmente `SENTRY_TRACES_SAMPLE_RATE`) no `.env` da VPS;
  reiniciar o backend. Sem isso o init é no-op por desenho.
- O critério "erro do dossiê visível no painel" só é verificável **após** essa
  ativação, em produção — fora do alcance desta auditoria.

---

## 0.2 — Estratégia de embeddings (decisão de negócio)

### Achado principal: a decisão de fato já foi tomada — e não é nenhuma das duas opções do enunciado

O enunciado propõe "Ollama local × provedor externo". O código implementou uma
**terceira via, local e mais leve**: embeddings in-process via **fastembed**
(ONNX, sem torch, sem GPU), modelo `intfloat/multilingual-e5-large` (1024d),
com pin de reprodutibilidade (`fastembed==0.8.0`, `requirements.txt:116`) e
protocolo E5 `query:`/`passage:` documentado
(`backend/app/services/embedding_service.py:1-39`).

Consequências práticas dessa escolha:

- **LGPD/soberania atendidas por construção:** nenhum conteúdo jurídico sai do
  VPS para gerar embeddings; não há custo por token nem dependência de terceiro.
  (Para *geração* de texto a política é outra — `docs/ai/EJC_AI_PROVIDER_POLICY.md`,
  com sanitização de PII e `AI_EXTERNAL_PROVIDERS_ALLOWED` — e não se confunde
  com embeddings.)
- A decisão está **registrada tecnicamente** em três lugares:
  `embedding_service.py` (cabeçalho), `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`
  (migração 768d→1024d, migration 096) e
  `scripts/rag/provar_ativacao.py` (`EXPECTED_PROVIDER = "local"`,
  `EXPECTED_MODEL = "intfloat/multilingual-e5-large"`, `EXPECTED_DIM = 1024`) —
  o workflow de ativação **recusa** outra configuração.
- Existe rota de saída sem re-arquitetura: `EMBEDDINGS_PROVIDER=http` +
  `EMBEDDINGS_API_URL` para um container dedicado de embeddings
  (`config.py:511-514`), com validação de dimensão e contagem na resposta.

### O que falta para "decisão registrada"

Apenas a **ratificação do titular** — sugere-se registrar na Issue desta
auditoria (ou em decisão permanente, §11 da governança) que o provedor de
embeddings do EJC é local/fastembed com `multilingual-e5-large` 1024d, para que
o item 0.2 não reabra a cada rodada. Não há trabalho de código pendente.

---

## 0.3 — Religar embeddings e backfill do corpus

### O que já está pronto no código

- **Flag ligada por default no código:** `EMBEDDINGS_ENABLED: bool = True`
  (`config.py:511`). Se o RAG está sem vetores em produção, é estado do `.env`
  de lá (não verificável daqui) — e a *ativação governada* existe exatamente
  para mudar isso com prova.
- **Workflow de ativação auditável e reversível:**
  `.github/workflows/rag-production-activation.yml` (dispatch manual na `main`,
  `environment: production`, governado pela Issue #563) → executa
  `scripts/rag/ativar_embeddings.sh`, que: trava lock, valida runtime e SHA,
  faz backup antes, roda **preflight** (provider/banco/coluna `vector(1024)`),
  altera **somente** `EMBEDDINGS_ENABLED` no `.env`, roda **canário** (N docs)
  e emite **prova agregada sem PII** (`provar_ativacao.py`, modos
  `runtime|preflight|canary|proof`).
- **Backfill em três camadas, idempotente:**
  1. Job automático horário `reembed_rag_orfaos` (`RAG_AUTO_REEMBED_ENABLED`
     default true — ver `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`, passo 5): reembeda
     órfãos sozinho, sem passo manual;
  2. `backend/scripts/reembedar_chunks_orfaos.py` — manual, com `--dry-run`,
     só toca chunk com `embedding IS NULL`, tudo-ou-nada por documento, e só
     marca `indexado` quando **todos** os chunks têm vetor;
  3. `backend/scripts/vetorizar_documentos.py` — docs sem nenhum chunk vetorizado.
- **A causa-raiz dos órfãos foi fechada no código:** `gerar_embeddings()`
  rejeita lote com contagem de vetores ≠ contagem de textos
  (`embedding_service.py:195-206`), eliminando o `zip` parcial que gerou os
  chunks órfãos com doc "indexado" (achado da auditoria RAG).

### Observações de precisão sobre o critério de conclusão

- **O critério cita `modo: vetorial`; a API real responde `modo: "semantica"`**
  (ou `"textual"` no fallback) — `backend/app/routers/rag.py:371-374`. Quem for
  validar a ativação deve procurar `"modo": "semantica"`, senão declarará falha
  onde há sucesso.
- **O número 59.444 trechos não é verificável no repositório** (é contagem do
  banco de produção). A validação de "zero órfãos" do runbook
  (`SELECT count(*) FROM knowledge_chunks WHERE embedding IS NULL;`) é o
  critério operacional correto, junto com o harness
  `app.eval.run_eval --gold app/eval/gold_set.jsonl`.

### Atos humanos de ativação

Disparar `rag-production-activation.yml` na `main` (o deploy/ativação é ato do
titular — regra 9), acompanhar canário e prova, e rodar a validação de órfãos.
O primeiro carregamento do modelo baixa ~2,3 GB (ONNX) — prever espaço em disco
na VPS, como alerta o runbook.

---

## 0.4 — Backup offsite

### O que já está pronto no código

- **Pipeline completo** em `backend/app/services/backup_service.py`: `pg_dump`
  + uploads → tar → **cifra Fernet antes de sair do VPS**
  (`BACKUP_ENCRYPTION_KEY`) → envio offsite para **Google Drive** (identidade
  dedicada `BACKUP_GOOGLE_DRIVE_*`, preservando o escopo somente-leitura do
  RAG) **ou** qualquer remote **rclone** (`BACKUP_DESTINO=rclone`, ex.
  OneDrive/B2 — `config.py:724-732`). Rotação apaga só artefatos com prefixo
  `ejc_backup_`; guard de execução única.
- **Boot valida a ativação:** com `BACKUP_ENABLED=true` em produção, chave
  ausente/placeholder ou inválida **derruba o boot** (`config.py:981-996`) —
  não existe backup "ligado" sem cifra.
- **Honestidade sobre resultado parcial:** falha do envio offsite vira status
  `"parcial"` quando `BACKUP_OFFSITE_OBRIGATORIO=false` (`backup_service.py`
  cabeçalho; `config.py:736`).
- **Tooling de operação e prova:** `scripts/backup/` (`ativar_backup.sh`,
  `check_backup_health.py`, `diagnostico_backup.sh`, `restaurar_backup.sh`,
  **drills de restauração** `restore_drill.py`/`drill_local_backup_restore.py`,
  `validar_restauracao_cifrada.py`) + workflow
  `.github/workflows/backup-gdrive-activation.yml` (valida em PR; prova
  integral cifrada na VPS via dispatch manual na `main`) +
  `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`.

### Lacunas e pontos de decisão

1. **Default OFF por desenho** (`BACKUP_ENABLED=false`, `.env.example:644`):
   ligar é configuração da VPS + credencial do destino + chave Fernet guardada
   **fora** do servidor (perder a chave = perder os backups). Ato humano.
2. **Retenção:** default `BACKUP_RETENCAO_DIAS=14` offsite / 7 dias local.
   O critério pede "retenção conforme prazo legal" — a LGPD (art. 46) não fixa
   dias; o prazo é **decisão do titular** (sugere-se registrá-la junto com a
   ativação). Lacuna de decisão, não de código.
3. **Recomendação:** após período de estabilização, `BACKUP_OFFSITE_OBRIGATORIO=true`,
   para que backup sem cópia externa deixe de contar como sucesso.
4. **Ao validar em produção, não usar `/diagnostico/central`** como fonte — a
   auditoria de julho registrou que ele reporta `backup_offsite` ligado e
   desligado na mesma resposta (armadilha documentada no `CLAUDE.md`). Usar
   `check_backup_health.py`/a prova do workflow, que verificam **resultado**
   (artefato produzido), não apenas execução.

---

## 0.5 — Ambiente de homologação separado da produção

### O que já existe (mitigações reais, posteriores à auditoria de julho)

- **O smoke E2E não roda mais em produção por acidente:**
  `qa/e2e/run_fictitious_smoke.py:1024-1030` recusa `EJC_BASE_URL` que não
  contenha `staging`/`homolog`/`localhost`, salvo `EJC_ALLOW_PRODUCTION_E2E=true`
  explícito. A suíte `qa/homologacao/run_homologacao.py` (H01–H15, com modelo
  de capacidades) tem a mesma guarda.
- **Ferramenta de limpeza dos resíduos já deixados em produção:**
  `backend/scripts/purga_dados_homologacao.py` — dry-run por padrão,
  **soft-delete** apenas (Lixeira), desativa a conta `homolog.qa` sem apagá-la
  (trilha de auditoria), recusa rodar sem `deleted_at` nas tabelas-alvo e exige
  confirmação digitada. Pré-requisito obrigatório: backup do banco.
- Testes de isolamento (`backend/tests/test_e2e_smoke_isolamento.py`,
  `test_purga_dados_homologacao.py`) protegem esses comportamentos.

### Lacuna principal: o ambiente de homologação **não existe no repositório**

Há apenas `docker-compose.yml` (produção) e um `docker-compose.override.example.yml`
para montar segredos. Não há composição, config de nginx, subdomínio ou pipeline
para uma stack de homologação. Os próprios runbooks pedem "teste em STAGING
antes da produção" (`RUNBOOK_MIGRACAO_EMBEDDING_1024.md`) — hoje esse staging
não está definido em lugar nenhum.

**Decisões que são do titular antes de qualquer implementação:**

- **Topologia:** stack paralela na mesma VPS (compose com projeto/portas/banco
  distintos + subdomínio, ex. `homolog.ejc...`) × segunda VPS × ambiente
  efêmero local. Envolve custo e capacidade da VPS atual (o modelo de
  embeddings sozinho ocupa ~2,3 GB).
- **Dados:** homologação com massa fictícia gerada pela própria suíte (mais
  simples e seguro sob LGPD) × cópia sanitizada de produção (exige rotina de
  anonimização que hoje não existe).
- **Quando purgar produção:** a purga dos registros `HOMOLOG-FICTICIO-*`/conta
  `homolog.qa` está pronta, mas é execução humana na VPS com backup prévio.

O critério "72% dos clientes são teste" refere-se ao banco de produção e não é
verificável a partir do repositório.

---

## Consolidação — quem faz o quê

**Trabalho de código pendente (cabe a Issues/PRs de execução, não a esta auditoria):**

1. ~~*(0.1)* Passar `release=app_version()` no `sentry_sdk.init()` e exportar
   `GIT_SHA` no `deploy-vps.yml`~~ — **feito** (ver adenda; `GIT_SHA` já estava
   exportado, só o `release` precisou de correção).
2. *(0.5)* Compor a stack de homologação **após** o titular decidir a topologia
   — topologia decidida na adenda; composição da stack é Issue própria.
3. *(0.3, menor)* Se desejado, alinhar vocabulário: ou o plano passa a citar
   `modo: semantica`, ou a rota passa a responder `vetorial` — recomenda-se
   ajustar o plano (mudar contrato de API é custo sem benefício).

**Atos humanos de ativação (titular/operação — regras 8 e 9 da governança):**

- Preencher `SENTRY_DSN` na VPS e reiniciar (0.1).
- Ratificar formalmente a estratégia de embeddings local/fastembed (0.2).
- Disparar `rag-production-activation.yml` e validar zero órfãos (0.3).
- Configurar credenciais/chave e `BACKUP_ENABLED=true`; disparar a prova de
  `backup-gdrive-activation.yml`; **decidir o prazo de retenção** (0.4).
- Decidir topologia da homologação; executar a purga dos dados fictícios em
  produção com backup prévio (0.5).

## Riscos residuais e limitações

- Tudo que depende do `.env` e do banco de produção foi classificado como "não
  verificável daqui"; as afirmações deste relatório valem para o código na
  branch auditada.
- O grafo `graphify-out/` estava mais antigo que o último commit durante a
  auditoria; todos os achados foram confirmados por leitura direta dos arquivos
  citados (caminho:linha).
- Painéis internos de diagnóstico divergem entre si (armadilha documentada);
  as validações pós-ativação devem usar as fontes indicadas em cada item.
- **Conflito de governança encontrado na execução:** a trava
  `.github/workflows/governanca.yml` (linhas 102–108) exige as seções
  "Riscos residuais" e "Rollback" no corpo do PR, mas o template oficial
  `.github/pull_request_template.md` não as contém — todo PR que segue o
  template à risca reprova no CI. Corrigir o template é mudança de governança
  e fica como apontamento (fora do escopo deste PR de auditoria).

## Adenda — decisões e execução (mesmo dia, 2026-08-08)

Após a leitura deste relatório, o titular autorizou por chat a resolução das
cinco pendências acima. As decisões, justificativas e o código correspondente
estão em `docs/auditoria/decisoes-bloco0-2026-08-08.md`, registrados na
**Issue #800 / PR #801**:

- **0.1** — Sentry mantido e ativado; PR #773 comentado pedindo revisão para
  excluir a remoção do Sentry daquele escopo. `release=app_version()`
  adicionado ao `init_sentry()`. A afirmação original deste relatório sobre
  `GIT_SHA` não ser exportado no deploy estava **errada** — corrigida acima.
- **0.2** — Estratégia de embeddings ratificada por escrito (local/fastembed).
- **0.4** — Retenção offsite definida em 30 dias (`BACKUP_RETENCAO_DIAS`).
- **0.5** — Topologia de homologação decidida (mesma VPS, compose separado,
  dados fictícios); build da stack em **Issue #802**, fora desta rodada.

Os atos humanos de ativação (preencher `SENTRY_DSN`, `BACKUP_ENABLED=true` +
credencial, disparar `rag-production-activation.yml`, subir a homologação na
VPS) continuam pendentes — nenhum deles foi nem podia ser executado por este
executor (regra 9 da governança).
