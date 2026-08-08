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

> ⚠️ **Achado de revisão (CodeRabbit/Codex, 2026-08-08): o corpo original
> deste relatório (abaixo) registra o estado ANTES da decisão final do
> titular.** A tabela e as seções 0.1–0.5 foram escritas antes da Adenda; a
> Adenda **revoga** o que estiver em conflito. Quem for agir a partir deste
> documento deve ler o **Sumário executivo** (já atualizado para o estado
> final) e a **Adenda** — não o meio do documento isoladamente. Em especial:
> **a decisão é remover o Sentry**, não ativá-lo — quem ler só a antiga linha
> 0.1 do meio do documento faria exatamente o trabalho que o titular rejeitou.
> **Precisão (achado de revisão, CodeRabbit):** "decisão" e "estado do código
> na `main`" são coisas diferentes — ver a coluna "Estado do código" abaixo.

## Sumário executivo (estado final, pós-adenda — 2026-08-08)

| ID  | Item                                | Decisão                                                      | Estado do código na `main` | Pendências |
|-----|-------------------------------------|-------------------------------------------------------------|-----------------------------|------------|
| 0.1 | Sentry (DSN + release)              | **Aprovada: remover.** O titular reverteu a decisão inicial (manter/ativar) após perguntar sobre custo — aceitou ficar sem qualquer coletor de erro (nem Sentry, nem self-hosted). | **Ainda não removido.** O PR #773 (que remove o Sentry) segue **aberto/draft, não mesclado** — `init_sentry()`, `SENTRY_DSN`, `sentry-sdk` continuam na `main` hoje. O `release=app_version()` chegou a ser implementado no PR #801 e foi revertido no mesmo PR — sem efeito líquido. | Merge do #773 (ato do titular). Risco residual: causa-raiz "500 sem diagnóstico" fica sem solução automatizada quando o merge acontecer (aceito conscientemente). |
| 0.2 | Estratégia de embeddings            | **Ratificada:** local (fastembed/ONNX, `multilingual-e5-large` 1024d) | Já era o comportamento da `main` — nenhuma mudança de código necessária | Nenhuma |
| 0.3 | Religar embeddings + backfill       | — | Máquina completa e governada já na `main`, **ainda não disparada** | Ato humano: dispatch de `rag-production-activation.yml` na `main`. Ver ressalva sobre `modo: "semantica"` não ser prova de retrieval vetorial de fato (abaixo) |
| 0.4 | Backup offsite                      | **Retenção definida em 30 dias** | Pipeline já na `main`; **retenção ainda em 14 dias** até o PR #801 mesclar (também aberto/draft) | Merge do #801; depois `BACKUP_ENABLED=true` + credencial DEDICADA (não `auto`/`inherit`) + chave Fernet fora do servidor + **conferir `BACKUP_RETENCAO_DIAS=30`** explicitamente na ativação, não presumir o default. Ver ressalvas sobre identidade e rotação por destino (abaixo) |
| 0.5 | Ambiente de homologação             | **Topologia decidida** (mesma VPS, compose separado, dados fictícios) | Stack não existe — build em Issue #802, ainda não implementado | Compor a stack; purgar dados fictícios em produção (ato humano, com backup prévio) |

Detalhes de cada decisão e a justificativa completa estão em
`docs/auditoria/decisoes-bloco0-2026-08-08.md` (Issue #800 / **PR #801** —
esse arquivo não existe nesta branch/PR, só na daquele PR irmão) e na
**Adenda**, ao final deste documento. As seções 0.1–0.5 abaixo são a
**auditoria original**, preservada como registro histórico de como o estado
do código era lido antes da decisão — não é mais o guia de ação.

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

   **Correção sugerida (histórica — não aplicada ao final):** passar
   `release=app_version()` no `init_sentry()`. Essa mudança chegou a ser
   implementada no PR #801, mas foi **revertida no mesmo dia** quando a
   decisão sobre o Sentry mudou de "manter" para "remover" (ver Adenda) — não
   faz sentido manter o parâmetro de uma integração que não vai rodar.
   `backend/app/core/observability.py` está, no estado final, idêntico à
   `main` neste trecho: `sentry_sdk.init()` **não** recebe `release`.

   > **Correção a este relatório (versão anterior estava errada):** a versão
   > original deste documento afirmava que `GIT_SHA` também não era exportado
   > no deploy. É falso — `scripts/deploy_vps_safe.sh:162-234` já exporta
   > `GIT_SHA`, usa no `docker compose build` e **verifica o valor publicado
   > contra `/api/health`**, com rollback automático em divergência;
   > `docker-compose.yml:55,144` já encaminha `GIT_SHA` ao container. `app_version()`
   > já recebe um SHA real em produção — isso continua correto independente da
   > decisão sobre o Sentry.

### Conflito de decisão (histórico — RESOLVIDO): PR #773 propõe REMOVER o Sentry

O PR draft **#773 — "Remover Infosimples, Sentry e Ollama do EJC"** estava
aberto no momento desta auditoria, caminhando na direção **oposta** ao que o
item 0.1 pedia originalmente (ativar Sentry). **Resolvido na Adenda: o
titular decidiu pela remoção** — o #773 segue como estava proposto, sem a
exclusão do Sentry ter sido bloqueada.

### Atos humanos (histórico — não se aplica mais)

~~- Resolver o conflito com o PR #773.
- Criar o projeto no Sentry e preencher `SENTRY_DSN` no `.env` da VPS.~~

Nenhum ato de ativação do Sentry é necessário — a decisão final foi não usar
nenhuma ferramenta de rastreamento de erro (nem Sentry, nem alternativa
self-hosted). Ver risco residual registrado no Sumário executivo.

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

- **LGPD/soberania atendidas por construção — sob a configuração atual
  (`EMBEDDINGS_PROVIDER=local`, o default):** nenhum conteúdo jurídico sai do
  VPS para gerar embeddings nesse modo. **Ressalva (achado de revisão):** essa
  garantia depende do provider efetivamente configurado, não é uma propriedade
  incondicional do código. `EMBEDDINGS_PROVIDER=http` existe e, se ativado,
  envia `textos` para `EMBEDDINGS_API_URL` — hoje sem nenhum serviço
  `embeddings` definido em `docker-compose.yml` correspondendo ao default
  `http://embeddings:8010/embed` (não é um destino comprovadamente interno; é
  só um valor placeholder). `disponivel()` só valida que a URL não está vazia,
  não que ela aponta para dentro do VPS. Não afirmar "rota de saída" como algo
  testado — é uma opção de código não implantada.
- **A dependência de terceiro não é zero, é adiada:** o primeiro uso baixa
  ~2,3 GB de pesos do modelo de um host externo (`_get_model()`,
  `embedding_service.py:86-94` — mesmo ponto citado adiante, §0.3). A
  ativação depende de acesso de saída à internet e da disponibilidade desse
  host até o cache (`fastembed_cache`) estar populado; depois disso, sim, a
  inferência roda 100% local.
  (Para *geração* de texto a política é outra — `docs/ai/EJC_AI_PROVIDER_POLICY.md`,
  com sanitização de PII e `AI_EXTERNAL_PROVIDERS_ALLOWED` — e não se confunde
  com embeddings.)
- A decisão está **registrada tecnicamente** em três lugares:
  `embedding_service.py` (cabeçalho), `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`
  (migração 768d→1024d, migration 096) e
  `scripts/rag/provar_ativacao.py` (`EXPECTED_PROVIDER = "local"`,
  `EXPECTED_MODEL = "intfloat/multilingual-e5-large"`, `EXPECTED_DIM = 1024`) —
  o workflow de ativação **recusa** outra configuração.
- Existe um caminho de código para provider HTTP (`EMBEDDINGS_PROVIDER=http` +
  `EMBEDDINGS_API_URL`, `config.py:511-514`, com validação de dimensão e
  contagem na resposta) — mas, como acima, sem um serviço implantado
  correspondente hoje. Não tratar como "rota de saída pronta".

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
  (ou `"textual"` no fallback) — `backend/app/routers/rag.py:371-374`.
  **Ressalva importante (achado de revisão):** `modo` em `rag.py:371` vem de
  `"semantica" if emb_disponivel() else "textual"` — ou seja, reflete se o
  **provider está configurado**, não se aquela consulta específica de fato
  usou busca vetorial. `buscar_contexto_rag` pode cair para o fallback textual
  em runtime (falha ao gerar o embedding da query, erro do pgvector, zero
  resultados vetoriais — `ai_service.py:354-415`) e a resposta **continua**
  dizendo `"modo": "semantica"`. Portanto: **não usar o campo `modo` de uma
  chamada isolada como prova de ativação** — ele mostra intenção de
  configuração, não resultado real. Usar a prova governada
  (`scripts/rag/provar_ativacao.py`, modo `proof`) ou o harness de avaliação
  abaixo, que medem o comportamento de fato.
- **O número 59.444 trechos não é verificável no repositório** (é contagem do
  banco de produção).
- **A validação de "zero órfãos" precisa do mesmo escopo do backfill, não uma
  contagem crua (achado de revisão):** `reembedar_chunks_orfaos.py` só
  processa documentos `deleted_at IS NULL AND vigente = true`
  (`_SQL_DOCS_COM_ORFAO`, linhas 48-58) — chunks de documentos excluídos ou
  não-vigentes nunca são tocados por design. A consulta correta é:
  ```sql
  SELECT count(*) FROM knowledge_chunks kc
  JOIN knowledge_docs kd ON kd.id = kc.doc_id
  WHERE kc.embedding IS NULL
    AND kd.deleted_at IS NULL AND kd.vigente = true;
  ```
  Rodar `SELECT count(*) FROM knowledge_chunks WHERE embedding IS NULL;` sem
  esse filtro pode nunca chegar a zero mesmo com o corpus ativo 100%
  vetorizado, declarando falsamente uma ativação incompleta. Usar também o
  harness `app.eval.run_eval --gold app/eval/gold_set.jsonl` como segunda
  fonte.

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
  (`BACKUP_ENCRYPTION_KEY`) → envio offsite para **Google Drive** **ou**
  qualquer remote **rclone** (`BACKUP_DESTINO=rclone`, ex. OneDrive/B2 —
  `config.py:724-732`); guard de execução única.
- **Identidade do Drive NÃO é dedicada por garantia de código (achado de
  revisão) — depende de configuração explícita:** `BACKUP_GOOGLE_DRIVE_AUTH_MODE`
  tem default `"auto"` (`backup_drive_auth.py:31`); em `auto`/`inherit`, sem
  credencial `BACKUP_GOOGLE_DRIVE_*` dedicada configurada, o serviço reusa a
  credencial herdada `GOOGLE_DRIVE_*` (a mesma do RAG) — **re-escopando-a para
  escrita**, não preservando o escopo somente-leitura. O boot em produção só
  valida a chave Fernet (`config.py:981-996`), não o modo de autenticação.
  Ligar `BACKUP_ENABLED=true` sem antes configurar credencial dedicada pode
  ampliar silenciosamente o acesso da credencial do RAG. **Ação recomendada:**
  exigir `BACKUP_GOOGLE_DRIVE_AUTH_MODE` dedicado (não `auto`/`inherit`) como
  pré-condição da ativação — o próprio script `scripts/backup/ativar_backup.sh`
  já recusa prosseguir sem isso (linhas 260-270 do script; ver mais abaixo).
- **Rotação automática só existe no destino Google Drive, não no rclone
  (achado de revisão):** `_rotacionar_sync` (que apaga só artefatos com
  prefixo `ejc_backup_` além de `BACKUP_RETENCAO_DIAS`) só é chamado no ramo
  `gdrive` de `backup_service.py`; no ramo `rclone` o próprio código comenta
  "Retenção no remote rclone é gerida fora do ciclo (ver runbook) — nada é
  apagado automaticamente aqui" (`backup_service.py:567-568`). Quem migrar
  para OneDrive/rclone (como sugerido em conversa anterior desta sessão)
  precisa de rotação manual ou script externo — a retenção de 30 dias definida
  em 0.4 **não se aplica sozinha** nesse destino.
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
2. **Retenção:** default `BACKUP_RETENCAO_DIAS=14` offsite / 7 dias local —
   **decidido em 30 dias offsite** na Adenda (ver `decisoes-bloco0-2026-08-08.md`
   §0.4). Essa mudança só existe no PR #801 (`BACKUP_RETENCAO_DIAS=14→30` em
   `config.py`), **ainda aberto/draft, não mesclado** — hoje a `main` continua
   com `14`. Na ação humana de ativação: mesclar o #801 e depois **conferir
   explicitamente** `BACKUP_RETENCAO_DIAS=30` no `.env` da VPS antes de assumir
   que o valor decidido está em vigor — não presumir que o default do código
   já reflete a decisão. Para destino rclone (OneDrive), mantenha também a
   exigência de rotação externa manual/script, já que `_rotacionar_sync` não
   cobre esse ramo (achado acima). Fonte legal citada: Lei nº 13.709/2018 (LGPD), art. 46 (dever de
   segurança do controlador) — o artigo não fixa um prazo numérico de retenção
   de backup; a leitura de que o prazo fica a critério do controlador é
   interpretação deste executor, não parecer jurídico formal, e deve ser
   conferida contra o texto oficial vigente
   (`planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm`) antes de
   virar política definitiva. **Nota de terminologia:** "titular" nesta seção
   segue a convenção do repositório (o dono/decisor do escritório, `CLAUDE.md`),
   diferente do sentido técnico de "titular de dados" na própria LGPD (a
   pessoa a quem os dados se referem) — os backups tratam dados de titulares
   (clientes), mas quem decide o prazo de retenção do *backup* é o
   controlador (o escritório).
3. **Recomendação:** a prova de ativação (`scripts/backup/ativar_backup.sh`)
   só é uma prova real do envio offsite se `BACKUP_OFFSITE_OBRIGATORIO=true`
   no momento em que rodar (achado de revisão) — com o default `false`, o
   próprio contrato do script aceita `status="parcial"` (falha só local
   detectada) como `ok=True`, então "prova integral concluída" pode aparecer
   mesmo com o envio ao Drive/rclone falhando. **Ativar com
   `BACKUP_OFFSITE_OBRIGATORIO=true` na primeira ativação** (não só "depois de
   estabilizar") é a única forma de a prova realmente comprovar o offsite;
   depois de confirmado, decidir se relaxa.
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

> Esta seção também é **histórica** (escrita antes da decisão final sobre o
> Sentry). Ver o Sumário executivo no topo para o estado real.

**Trabalho de código pendente (estado final, não o que esta seção dizia antes):**

1. ~~*(0.1)* Passar `release=app_version()` no `sentry_sdk.init()`~~ —
   implementado no PR #801 e depois **revertido no mesmo PR**: a decisão
   virou "remover o Sentry", então manter o parâmetro não fazia sentido.
   `observability.py` está, ao final, sem mudança líquida em relação à `main`.
2. *(0.5)* Compor a stack de homologação **após** o titular decidir a topologia
   — topologia decidida na adenda; composição da stack é Issue própria
   (**#802**).
3. *(0.3, menor)* Se desejado, alinhar vocabulário: ou o plano passa a citar
   `modo: semantica`, ou a rota passa a responder `vetorial` — recomenda-se
   ajustar o plano (mudar contrato de API é custo sem benefício). Reforço: o
   campo `modo` não prova retrieval vetorial de fato (ver ressalva na §0.3).

**Atos humanos de ativação (titular/operação — regras 8 e 9 da governança):**

- ~~Preencher `SENTRY_DSN` na VPS e reiniciar (0.1)~~ — **não se aplica**: o
  Sentry foi decidido como removido, não ativado.
- Ratificar formalmente a estratégia de embeddings local/fastembed (0.2) —
  já ratificada por escrito (ver adenda).
- Disparar `rag-production-activation.yml` e validar zero órfãos **com o
  filtro `vigente=true`/`deleted_at IS NULL`** (0.3, ver ressalva acima).
- Configurar credencial **dedicada** (não `auto`/`inherit`) + chave +
  `BACKUP_ENABLED=true`; disparar a prova de `backup-gdrive-activation.yml`
  **com `BACKUP_OFFSITE_OBRIGATORIO=true`** para que a prova seja real (0.4).
  Retenção já decidida: 30 dias (só se aplica automaticamente ao destino
  Google Drive; rclone precisa de rotação externa).
- Decidir topologia da homologação — **já decidida** (mesma VPS, compose
  separado); falta compor a stack (Issue #802) e, depois, executar a purga
  dos dados fictícios em produção com backup prévio (0.5).

## Riscos residuais e limitações

- Tudo que depende do `.env` e do banco de produção foi classificado como "não
  verificável daqui"; as afirmações deste relatório valem para o código na
  branch auditada.
- O grafo `graphify-out/` estava mais antigo que o último commit durante a
  auditoria; todos os achados foram confirmados por leitura direta dos arquivos
  citados (caminho:linha).
- Painéis internos de diagnóstico divergem entre si (armadilha documentada);
  as validações pós-ativação devem usar as fontes indicadas em cada item.
- ~~Conflito de governança entre o modelo de pull request e a trava
  `governanca.yml`~~ — **retratado (achado de revisão, Codex):** conferido de
  novo, `.github/pull_request_template.md` **já contém** as seções
  "## Riscos residuais e limitações" e "## Rollback" (linhas 84-90 no commit
  auditado). A hipótese original deste relatório estava errada — não há
  conflito. O que de fato aconteceu ao preparar o PR #793 foi um lapso deste
  executor ao preencher o corpo a partir do modelo (seções omitidas na
  primeira versão do PR, não ausência no modelo) — corrigido ali, sem
  achado de governança a registrar.

## Adenda — decisões e execução (mesmo dia, 2026-08-08)

Após a leitura deste relatório, o titular autorizou por chat a resolução das
cinco pendências acima. As decisões, justificativas e o código correspondente
estão em `docs/auditoria/decisoes-bloco0-2026-08-08.md`, registrados na
**Issue #800 / PR #801**. **Nota (achado de revisão, Codex):** esse arquivo
**não existe nesta branch** (`claude/auditoria-infra-dados-2mgrm9`, a deste
PR #793) — ele foi criado na branch irmã `claude/bloco0-decisoes-execucao-9k4p2m`
(PR #801). Quem quiser conferir o conteúdo citado abaixo precisa olhar aquele
PR, não este. As afirmações resumidas aqui foram checadas contra aquele
arquivo no momento da escrita, mas não são auto-verificáveis só com o diff
deste PR:

- **0.1** — **Decisão revista no mesmo dia.** Primeira resposta: Sentry
  mantido e ativado. Ao apresentar os comandos de ativação, o titular
  perguntou sobre custo; a resposta reabriu a decisão de fundo, e perguntado
  se aceitava ficar **sem qualquer ferramenta de rastreamento de erro** (nem
  Sentry, nem self-hosted como GlitchTip), confirmou que sim. **Decisão final:
  Sentry removido — o PR #773 segue como estava proposto.** O comentário
  anterior desta sessão em #773 (pedindo excluir a remoção) foi retratado.
  Consequência aceita: a causa-raiz nº 1 ("500 sem diagnóstico") continua sem
  solução automatizada — risco residual registrado, não pendência esquecida.
  Histórico completo das duas versões em
  `docs/auditoria/decisoes-bloco0-2026-08-08.md`, seção 0.1.
  (A afirmação original deste relatório sobre `GIT_SHA` não ser exportado no
  deploy estava **errada** — corrigida acima; isso continua valendo
  independente da decisão do Sentry.)
- **0.2** — Estratégia de embeddings ratificada por escrito (local/fastembed).
- **0.4** — Retenção offsite definida em 30 dias (`BACKUP_RETENCAO_DIAS`).
- **0.5** — Topologia de homologação decidida (mesma VPS, compose separado,
  dados fictícios); build da stack em **Issue #802**, fora desta rodada.

Os atos humanos de ativação (`BACKUP_ENABLED=true` + credencial, disparar
`rag-production-activation.yml`, subir a homologação na VPS) continuam
pendentes — nenhum deles foi nem podia ser executado por este executor
(regra 9 da governança).
