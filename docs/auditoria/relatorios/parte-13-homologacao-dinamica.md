# EJC — Auditoria Técnica, Parte 13
## Homologação dinâmica: primeira vez com stack real de pé (Docker Compose local)

**Data:** 2026-08-03, 00h15–00h45 UTC · **Sessão:** `homolog-admin@ejc-homologacao-ficticia.adv.br` (superadmin fictício, semeado pelo boot)
**Branch:** `claude/system-homologation-testing-smce7p` (sem commits, sem push)
**Origem:** Issue #653 — fechar a lista "Verificações que exigem ambiente de homologação" que nem a auditoria externa (jul/2026, só API de produção) nem o PR #652 (código sem Postgres/Docker) puderam rodar.
**Método:** subir a stack completa via `docker compose`, autenticar como admin fictício, e para cada item da lista: reproduzir com curl/psql/browser reais, registrar comando + saída bruta, dar veredito.

**Resumo executivo.** A stack sobe e funciona. Os dois defeitos P0 do PR #652 (`/v1/` duplicado, `GET /rag/docs` 500) se confirmam **exatamente como descrito**, com servidor real. A hipótese sobre o gate de citações travar toda peça **não pôde ser testada** — o pipeline de geração falha antes, na seleção de provedor de IA (não há chave de API neste ambiente), e falha de um jeito **inconsistente**: gracioso na geração (SSE com mensagem clara), mas com **500 não tratado na validação jurídica** — o que por si só explica por que nenhuma peça chega a `aprovado`. Dois achados LGPD do PR #652 (CPF em texto puro em `case_partes`; anonimização de cliente não alcança `case_partes`) se confirmam com dado fictício circulando de verdade. A migration 126 corrigiu integralmente o vocabulário de status de casos — `?status=all` não derruba mais o servidor, `?status=ativo` não devolve mais lista vazia silenciosa: ambos agora recusam com 422 e mensagem acionável. Um achado novo, não previsto por nenhuma auditoria anterior: `VAULT_MASTER_KEYS`, exigida no boot em produção, **não existe em `.env.example`** — quem seguir o guia de deploy documentado trava no primeiro boot.

---

## 1. Contexto e método

### 1.1 O que subiu

```bash
cp .env.example .env   # + segredos gerados localmente (Fernet/urlsafe), nunca reaproveitados de produção
docker compose build backend worker frontend
docker compose up -d db redis backend worker frontend
```

Sem `ANTHROPIC_API_KEY`/`GROQ_API_KEY`/`MARITACA_API_KEY` (não fornecidas) — `ANTHROPIC_ENABLED=false` setado explicitamente, Groq/Maritaca sem chave (inelegíveis por design), `OLLAMA_ENABLED=false` fixado no `docker-compose.yml` do serviço `backend` (não sobrepões pelo `.env`). Perfis `observability` e `ia-local` não foram ligados (fora de escopo). Resultado: **nenhum provedor de IA elegível neste ambiente** — decisão deliberada do escopo pedido ("testar o sistema, não a qualidade da geração").

```
$ curl -s http://localhost:8000/api/health
{"status":"ok","version":"dev","commit":"desconhecido","uptime_seconds":33.477,"environment":"production"}

$ docker compose ps
NAME           STATUS
ejc_backend    Up (healthy)
ejc_db         Up (healthy)
ejc_frontend   Up
ejc_redis      Up (healthy)
ejc_worker     Up (healthy)
```

`alembic upgrade head` rodou no boot (`RUN_MIGRATIONS=1`, default do compose local) e o seed do admin/skills/súmulas rodou sem erro após dois ajustes de `.env` (ver §3.6).

### 1.2 Limitação de ambiente — build precisou de workaround, não afeta o veredito do runtime

O container sandbox deste agente não tinha Docker daemon ativo (`service docker start` falhava por `ulimit`) nem rota de rede padrão para `pypi.org`/`registry.npmjs.org`/`deb.debian.org` de dentro de um build Docker (a saída HTTPS deste ambiente passa por um proxy de política que os containers de build não alcançam nem confiam por padrão). Contornado com:
- `dockerd` iniciado manualmente em background;
- confiança temporária na CA do proxy do ambiente (`update-ca-certificates` + `PIP_CERT`/`NODE_EXTRA_CA_CERTS`) adicionada **temporariamente** a `backend/Dockerfile` e `frontend/Dockerfile`, revertida com `git checkout --` assim que os builds terminaram — **nenhuma mudança de código ficou no working tree**.

Isso é infraestrutura do ambiente de teste, não do EJC — não é achado, é o preço de ser "a primeira vez que alguém audita o EJC com stack real de pé" dentro deste sandbox específico. Registrado porque a Parte 12 pede transparência sobre limitações.

### 1.3 O que não pôde ser testado

- **Qualidade de geração de IA** — sem chave de provedor externo, por decisão do escopo. Testável apenas o comportamento do sistema *ao redor* da IA (erros, gates, filas).
- **Hipótese do gate de citações bloqueando peças** (RAG_EXIGIR_APROVADO=true + acervo não curado) — não alcançada: o pipeline falha um passo antes (seleção de provedor). Ver §2.3.
- **Ollama local** — perfil `ia-local` fora do escopo pedido.
- **Integrações externas pagas/gated** (Infosimples, NFS-e, DataJud real) — não exercitadas; fora do escopo e sem credenciais.

---

## 2. Item por item — veredito e evidência bruta

### 2.1 P0-1 — prefixo `/v1/` duplicado (8 routers)

**CONFIRMADO**, idêntico ao PR #652, com servidor real (não `TestClient`):

```
$ curl -w '%{http_code}' /api/v1/despesas               → 404
$ curl -w '%{http_code}' /api/v1/v1/despesas             → 200
$ curl -w '%{http_code}' /api/despesas                   → 404
$ curl -w '%{http_code}' /api/v1/office-contracts        → 404
$ curl -w '%{http_code}' /api/v1/v1/office-contracts     → 200
$ curl -w '%{http_code}' /api/v1/partner-withdrawals     → 404
$ curl -w '%{http_code}' /api/v1/v1/partner-withdrawals  → 200
$ curl -w '%{http_code}' /api/v1/kanban-columns          → 404
$ curl -w '%{http_code}' /api/v1/v1/kanban-columns       → 200
$ curl -w '%{http_code}' /api/v1/regulatorio/digest-semanal      → 404
$ curl -w '%{http_code}' /api/v1/v1/regulatorio/digest-semanal   → 200
$ curl -w '%{http_code}' /api/v1/whatsapp/status         → 404
$ curl -w '%{http_code}' /api/v1/v1/whatsapp/status      → 200
$ curl -X POST /api/v1/datajud/cases/<uuid>/sync          → 404 (rota ausente)
$ curl -X POST /api/v1/v1/datajud/cases/<uuid>/sync       → 404 {"detail":"Case not found"}  ← rota EXISTE, 404 é de negócio
```

Os 8 routers do achado original (`despesas`, `office_contracts`, `partner_withdrawals`, `kanban`, `datajud`, `regulatorio`, `pending_items`, `whatsapp`) foram todos exercitados; todos reproduzem. `pending_items` está sob `/v1/clients` (não `/v1/pending-items` como o nome do arquivo sugere) — testado via `/api/v1/v1/clients/<id>/pending-items` → 200.

### 2.2 P0-3 — `GET /api/rag/docs` 500

**CONFIRMADO**, servidor real:

```
$ curl -w '\nstatus=%{http_code}\n' /api/rag/docs -H "Authorization: Bearer $TOKEN"
{"detail":"Erro interno. Se persistir, informe o horário e o que estava fazendo."}
status=500
```

Não investiguei o traceback interno (o achado do PR #652 já localiza a causa em `ai_core_hardening_patch.py:111-117,188-193` — não há motivo para reabrir essa investigação, só confirmar o sintoma em runtime, o que está feito).

### 2.3 Hipótese do gate de citações bloqueando toda peça

**NÃO VERIFICÁVEL neste ambiente — mas achado adjacente mais grave encontrado e CONFIRMADO (ver §3.2).**

Tentativa de gerar peça via `POST /api/pecas/gerar` (SSE):

```
event: inicio
data: {"pipeline_id": "...", "tipo_peca": "Notificação Extrajudicial", ..., "etapas_total": 7, ...}

event: step
data: {"etapa": 1, "titulo": "Identificando tipo de peça", "status": "em_andamento"}

event: erro
data: {"detail": "IA indisponível no momento. Tente novamente em instantes ou contate o administrador."}
```

O pipeline nunca chega à etapa de recuperação RAG/citação — falha na etapa 1 (seleção de provedor), porque **nenhum provedor está elegível neste ambiente** (decisão de escopo, não bug). A hipótese do PR #652 pressupõe um provedor funcionando e o gate de citações bloqueando depois — isso exigiria uma `ANTHROPIC_API_KEY` real, que não foi fornecida. Não posso confirmar nem refutar; só posso dizer que **existe pelo menos um bloqueio anterior e mais básico** (§3.2) que, sozinho, já impede qualquer peça de chegar a `aprovado` neste ambiente.

Estado do acervo RAG (para registro, já que a lista pede):

```sql
SELECT extra->>'rag_status', count(*) FROM knowledge_docs GROUP BY 1;
 aprovado | 24
SELECT categoria, count(*) FROM knowledge_docs GROUP BY 1;
 sumula_stj | 12
 sumula_tst | 9
 sumula_stf | 3
```

O acervo semeado (24 súmulas, todas `rag_status=aprovado` + `conferido=true`) **está curado e passaria pelo gate** no sentido estrito — mas é estreito demais para cobrir a área/tema de um caso fictício qualquer (só súmulas STF/STJ/TST específicas). Isso não é "gate bloqueando tudo por falta de curadoria" — é "gate funcionando corretamente sobre um acervo pequeno demais para o caso real". Achado distinto do hipotetizado, registrado em §3.3.

### 2.4 `RATE_LIMIT_REDIS_ENABLED` × workers do uvicorn

**COERENTE, sem incoerência a reportar.**

```
$ docker exec ejc_backend ps aux | grep uvicorn
$ tail -1 backend/entrypoint.sh
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers   # sem --workers → default 1
```

`docker-compose.yml` fixa `RATE_LIMIT_REDIS_ENABLED: "true"` no serviço `backend`. Com 1 worker, o rate-limit em memória já seria suficiente — usar Redis aqui é redundante, não incoerente (não há divergência entre "quantos workers o container sobe" e "quantos workers o rate-limit distribuído pressupõe"; o Redis simplesmente não é necessário, mas também não quebra nada).

### 2.5 `qa/e2e/run_fictitious_smoke.py` contra `http://localhost:8000`

Executado com `EJC_E2E_STRICT=true`. Resultado bruto: `qa/e2e/reports/e2e_fictitious_report.json`.

```
total: 47 · passed: 28 · failed: 19 · degradados: 17 · asserts_de_efeito: 1 · checks_nao_cobertos: 3
```

**17 dos 19 "failed" são falso alarme do PRÓPRIO script, não do backend** — confirmado lendo o código-fonte dos routers: a matriz (`fictitious_matrix.json`) já declara `expected: [200, 404]` para esses checks de "módulo presente" (ela sabia que 404 era possível), mas o runner em modo estrito trata qualquer 404 como `DEGRADADO` de qualquer forma. Ao checar o código dos 17 routers apontados, a maioria **não tem rota `GET /` nenhuma por desenho** (ex.: `checklists` só tem `/templates`, `/instanciar`, `/caso/{id}/gerar-ia`; `workflow` só tem `/templates`, `/casos/{id}`; `portal` só tem `/meus-casos`, `/casos/{id}`, `/documentos`...). Além disso, **4 dos 17 caminhos testados pelo script estão com o prefixo errado** (bug do script, não do backend): `financeiro-consolidado` → prefixo real é `/financeiro`; `gestao-societaria` → `/sociedade`; `produtividade` → `/analytics`; `ia-extra` → `/ai`. Testei os prefixos corretos manualmente — também 404 na raiz, pelo mesmo motivo (sem rota `GET /`).

Os **2 falhas reais**:
1. `casos.criar_consumidor_ficticio POST /api/cases/` → **422**, `"Campo 'proxima_acao' é obrigatório para casos abertos"`. A fixture da matriz (`fictional_matrix.json`) não inclui `proxima_acao` — regra de negócio real (G1, `routers/cases.py:60`), a matriz é que está desatualizada em relação a essa regra. Isso derruba em cascata `documentos.upload` (não roda por falta de `case_id`).
2. Consequência do #1: nenhum outro passo dependente de caso roda.

Contornado manualmente via API para os itens 4/5 da lista (ver §3).

### 2.6 pytest com `RUN_DB_TESTS=1` contra o Postgres do compose

```
8 failed, 4683 passed, 3 skipped, 3 warnings, 77 subtests passed in 278.42s
```

Os **8 failed são 100% atribuíveis a diferenças do meu harness de execução em relação ao `ci.yml`, não a regressões de produto** — confirmado comparando com `.github/workflows/ci.yml` linha a linha:

| Teste | Causa raiz | Evidência |
|---|---|---|
| `test_dns_rebinding_entre_validacao_e_post_nao_tem_efeito` | Rodei com `APP_ENV=production` (para validar `Settings` como produção real); o teste usa `callback_url=http://...` (sem TLS), rejeitado só em produção (`callback_url deve usar https em produção`). CI roda com `APP_ENV=development` (`ci.yml:28`). | `assert 422 == 201` |
| `test_nega_commit_na_main`, `test_permite_commit_fora_da_main` | Rodei dentro da imagem `ejc-backend` (produção, sem `git` — deliberadamente enxuta). CI roda em `ubuntu-latest`, que tem `git`. | `FileNotFoundError: [Errno 2] No such file or directory: 'git'` |
| `test_tjmg_fonte_registrada_no_registry`, `test_router_aceita_e_propaga_ano` | Usei `--env-file .env`, que define `JURIS_IMPORT_FONTES=lexml,stj` (idêntico ao `.env.example`, exclui `tjmg` de propósito). CI não usa `.env` nenhum — variável ausente cai no default do CÓDIGO, que é `"lexml,stj,tjmg"` (`app/services/juris_import/__init__.py:29`). | `Fonte 'tjmg' indisponível` |
| `test_paridade_openapi_com_snapshot_anterior`, `test_registro_independe_da_ordem_de_import` | Mesma causa do 1º: `APP_ENV=production` desliga `/api/docs`, `/api/openapi.json`, `/docs/oauth2-redirect` (por desenho, conforme `CLAUDE.md`). CI roda em development, essas 3 rotas existem. | `3 rota(s) DESAPARECERAM` |
| `test_upgrade_head_reconstroi_banco_vazio_real` | Não defini `SCHEMA_CHECK_DATABASE_URL` (só existe no `env:` do job `db-validation`, `ci.yml:27`). | `KeyError: 'SCHEMA_CHECK_DATABASE_URL'` |

**Achado colateral genuíno (não é bug, é uma nota para quem for reproduzir):** `.env.example` traz `JURIS_IMPORT_FONTES=lexml,stj` — quem sobe a stack seguindo esse arquivo literalmente terá TJMG como fonte de importação on-demand desligada, diferente do que o CI valida (CI não usa `.env.example`, herda o default do código que inclui `tjmg`). Não é regressão; é uma divergência de configuração entre "o que `.env.example` documenta como padrão" e "o que o código usa como padrão na ausência da env var". Comentário do próprio `.env.example` já orienta a incluir `tjmg` manualmente se quiser — o ponto é que o default DO ARQUIVO diverge do default DO CÓDIGO, sem aviso.

### 2.7 `GET /api/cases/?status=all` e `?status=ativo`

**REFUTADO — já corrigido pela migration 126, confirmado em runtime.**

```
$ curl /api/cases/?status=all
422 {"detail":"Status de caso inválido: 'all'. Valores aceitos: aberto, em_instrucao, em_producao, protocolado, encerrado, arquivado. Para não filtrar por status, omita o parâmetro."}

$ curl /api/cases/?status=ativo
422 {"detail":"Status de caso inválido: 'ativo'. ..."}

$ curl /api/cases/?status=triagem
422 {"detail":"Status de caso inválido: 'triagem'. ..."}

$ curl /api/cases/?status=arquivado
200 {"data":[],"total":0,"page":1,"page_size":20}
```

Não é mais "500 num caso, vazio silencioso no outro" (achado original da auditoria externa, jul/2026) — os dois agora recusam com **422 e mensagem que já diz os valores aceitos**. Também não encontrei, em `frontend/src/pages/Casos.tsx`, nenhuma chamada com `status=all`/`status=ativo` — o frontend não parece mandar esses valores (não fiz varredura completa do repo frontend, apenas grep dirigido).

### 2.8 Exclusão (soft delete) de caso com peça vinculada

**CONFIRMADO no nível de dado, mas MITIGADO no nível de leitura — mais nuançado do que "órfã" sugere.**

```sql
-- antes:
SELECT id, deleted_at, case_id FROM legal_docs WHERE id='<doc>';
 <doc> | (null) | <case>

-- DELETE /api/cases/<case> (soft delete) → 200

-- depois:
SELECT id, deleted_at, status FROM cases WHERE id='<case>';
 <case> | 2026-08-03 00:36:39 | em_producao        ← soft-deletado

SELECT id, deleted_at, case_id FROM legal_docs WHERE id='<doc>';
 <doc> | (null) | <case>                            ← NÃO cascateou (dado bruto)

SELECT id, deleted_at, case_id FROM documents WHERE case_id='<case>';
 <doc-arquivo> | (null) | <case>                     ← documento também não cascateia
```

No nível de dado bruto, o achado do PR #652 se confirma e se estende: **nem `legal_docs` nem `documents`** têm `deleted_at` cascateado quando o caso pai é soft-deletado (a FK `case_partes_case_id_fkey` tem `ON DELETE CASCADE`, mas isso só dispara em `DELETE` físico — soft delete é um `UPDATE`, a FK nunca vê o evento).

Mas testando o que o **usuário efetivamente vê**:
```
$ curl /api/cases/<case>              → 404 "Caso não encontrado"          (correto — some da UI)
$ curl /api/legal-docs/?case_id=<case> → 200 {"data":[],"total":0}          (correto — peça some junto)
```
As queries de leitura (`filtrar_pecas_visiveis` em `core/status_caso.py`) filtram por `case_id IN (SELECT id FROM cases WHERE deleted_at IS NULL)` — a peça fica **invisível** enquanto o caso está na lixeira, mesmo sem cascade físico. Restaurando o caso (`POST /trash/cases/<id>/restaurar`), as 4 peças do caso **reaparecem intactas** em `GET /legal-docs/?case_id=...`. Ou seja: não há perda de dado nem vazamento de peça órfã visível na UI — o risco real é mais restrito do que "peça órfã" sugere: é higiene de dado (registro nunca some fisicamente, mesmo que o caso seja excluído para sempre pela lixeira/expurgo) e um ponto de atenção para quem for implementar expurgo definitivo da lixeira (se algum job de expurgo só apagar `cases` e não os relacionados, ali sim vira uma perda de referência).

### 2.9 Documento sem caso × documento com case_id — os dois caminhos existem?

**CONFIRMADO — ambos existem e funcionam.**

```
$ curl -F file=@... -F titulo="..." /api/documents/upload                    → 201, case_id: null
$ curl -F file=@... -F case_id=<case> -F titulo="..." /api/documents/upload  → 201, case_id: <case>
$ curl /api/documents/                       → lista os 2 (com e sem caso)
$ curl /api/documents/?case_id=<case>        → lista só o vinculado
```

Ambos os caminhos coexistem sem conflito no GED.

---

## 3. Achados novos (só apareceram com stack real de pé e dado circulando)

### 3.1 `VAULT_MASTER_KEYS` — variável obrigatória em produção, ausente em `.env.example`

Boot falha (`backend/app/core/config.py:965-982`) exigindo `VAULT_MASTER_KEYS`, chave Fernet do Cofre de Credenciais. **Essa variável não existe em `.env.example`** (`grep VAULT_MASTER_KEYS .env.example` → nenhum resultado). Quem seguir literalmente o guia de deploy documentado (copiar `.env.example` para `.env`, preencher os placeholders indicados) trava no primeiro boot com um erro que não tem onde ser corrigido no próprio arquivo-modelo — precisa ler o código-fonte para descobrir a variável. **Severidade: alta para quem faz primeiro deploy; nenhum impacto em produção já rodando** (a VPS certamente já tem a variável setada manualmente, senão nunca teria subido).

### 3.2 `POST /legal-docs/{id}/validar` quebra com 500 não tratado sem provedor de IA — e é ISSO que trava `/aprovar` em `sem_validacao`

Este é o achado mais importante desta rodada porque **substitui a hipótese do gate de citações por uma causa mais básica e mais fácil de confirmar**.

```
$ curl -X POST /api/legal-docs/<doc>/validar
{"detail":"Erro interno. Se persistir, informe o horário e o que estava fazendo."}
HTTP 500
```

Log do backend:
```
File "app/routers/legal_docs.py", line 459, in validar_peca_juridica
    resultado = await validar_rascunho_juridico(payload, db=db, ...)
File "app/services/validador_juridico_service.py", line 545, in validar_rascunho_juridico
    resp = await chat(...)
File "app/services/ai_gateway.py", line 550, in chat
    raise RuntimeError(...)
RuntimeError: Todos os provedores falharam para task=auditoria_peca. Último erro: Nenhum provedor disponível
```

Compare com `POST /pecas/gerar` (§2.3), que trata o MESMO erro (`RuntimeError` de "nenhum provedor elegível") com um `event: erro` gracioso no SSE. `validar_peca_juridica` **não captura essa exceção** — ela sobe crua até o handler genérico do FastAPI e vira 500. Consequência direta, confirmada:

```
$ curl -X PATCH /api/legal-docs/<doc>/aprovar
422 {"detail":"Peca bloqueada por controle de qualidade: para aprovar/finalizar/protocolar, e necessario
     validacao juridica revisada ou aplicada com score minimo de 75/100. Status atual: sem_validacao.
     Execute a validacao juridica da peca e marque o log como revisado ou aplicado."}
```

`GET /legal-docs/<doc>/validacao` confirma: `{"status":"sem_validacao","ai_log_id":null,...}` — o bug do `ai_log_id` nunca sendo gravado (documentado no PR #652) **continua reproduzindo**, e agora sabemos exatamente por quê neste ambiente: a chamada que gravaria o log nunca completa, porque estoura 500 antes de chegar lá. Isso é mais amplo do que "acervo RAG não curado bloqueia o gate de citações" — é "sem NENHUM provedor de IA elegível, a validação jurídica é IMPOSSÍVEL de completar, e sem validação, `/aprovar` está permanentemente trancado". Com um provedor real configurado, é bem possível que `/validar` funcione e o gate de citações da hipótese original entre em jogo depois — mas isso não foi testável aqui.

**Correção sugerida (não implementada, fora do escopo desta tarefa de homologação):** `validar_peca_juridica` deveria tratar `RuntimeError` do `ai_gateway` da mesma forma que `gerar_peca` trata — devolver um erro claro (503, não 500) em vez de deixar a exceção subir crua.

### 3.3 Vocabulário de `tipo_peca` diverge entre dois módulos do mesmo domínio

`app/routers/peca_geracao.py` (`TIPOS_PECA`, geração via IA) usa `"notificacao"`. `app/models/legal_doc.py` (`PecaTipo`, o enum real da coluna no banco) usa `"notificacao_extrajudicial"`. Reproduzido:

```
$ curl -X POST /api/legal-docs/ -d '{"tipo_peca":"notificacao", ...}'
422 {"detail":[{"loc":["body","tipo_peca"],"msg":"Value error, tipo_peca inválido: use um de
     ['contestacao','contrarrazoes','contrato','defesa_ambiental','notificacao_extrajudicial',
     'outro','parecer','peticao_inicial','procuracao','recurso']", ...}]}
```
Se `peca_geracao.py` algum dia persistir a peça gerada com `tipo_peca="notificacao"` direto no `LegalDoc` (não testável aqui sem provedor de IA — a etapa 1 falha antes de chegar lá), o INSERT quebraria com `InvalidTextRepresentationError` do Postgres (o enum SQL não aceita o valor). Não é confirmável como bug ativo sem gerar uma peça de verdade por IA; é um ponto de atenção estrutural — dois vocabulários para o mesmo conceito no mesmo domínio.

### 3.4 `pecas_aguardando_revisao` do dashboard está CORRETO (achado que refina, não confirma, a preocupação da lista original)

Testado deliberadamente por ser item explícito da tarefa. Criei 7 peças (6 auto-geradas por template de caso + 1 manual), sendo 3 vinculadas a um caso soft-deletado:

```sql
SELECT titulo, ai_generated, status FROM legal_docs;
-- 6 com ai_generated=true, status=rascunho; 3 delas do caso soft-deletado; 3 do caso vivo
-- 1 com ai_generated=false (a manual), status=rascunho

$ curl /api/dashboard/
{"pecas_aguardando_revisao": 3, ...}
```

`3` está certo: o filtro (`core/status_caso.py:filtrar_aguardando_revisao`) exige `ai_generated=True` (exclui a manual, corretamente — HITL é sobre peça de IA) **e** `case_id IN CASOS_VIVOS` (exclui as 3 do caso na lixeira, mesmo sem cascade físico — ver §2.8). Contei manualmente no banco e bate. **Este indicador específico não é um falso positivo** — ao contrário do achado análogo na Parte 12 (Seção 1, daquela auditoria, feita contra produção em julho), aqui o contador reflete a realidade operacional com precisão, inclusive compensando a ausência de cascade no soft-delete.

### 3.5 CPF em texto puro em `case_partes` — CONFIRMADO com dado fictício real

```sql
\d case_partes
 cpf_cnpj | character varying(18)     -- SEM criptografia

INSERT via POST /cases/<id>/partes {"cpf_cnpj": "529.982.247-25", ...}

SELECT nome, cpf_cnpj FROM case_partes WHERE id='<parte>';
 E2E-FICTICIO-LGPD Parte Contrária Teste | 529.982.247-25   ← em claro, legível
```

Contraste direto: `clients.cpf` **é** cifrado (`cpf_enc text` + `cpf_hash` HMAC cego, `services/pii_crypto.py`), mas `case_partes.cpf_cnpj` não passa pelo mesmo tratamento — mesma categoria de dado (CPF de pessoa física), dois níveis de proteção diferentes dentro do mesmo sistema.

### 3.6 Anonimização de cliente (LGPD art. 17) não alcança `case_partes` — CONFIRMADO com fluxo real ponta a ponta

```
$ curl /api/clients/<c>/esquecimento/bloqueios
{"pode_anonimizar": false, "bloqueios": ["1 caso(s) em representação ativa (DPT-2026-0002). ..."]}

$ curl -X POST /api/clients/<c>/esquecimento -d '{"forcar": true}'
{"anonimizado_em": "2026-08-03T00:37:45Z", "bloqueios_ignorados": [...]}

-- clients: nome/email/cpf_enc/cpf_hash apagados corretamente
SELECT nome, email, cpf_enc FROM clients WHERE id='<c>';
 [ANONIMIZADO — LGPD ART. 17] |  |            ← funcionou

-- case_partes do mesmo caso: intocado
SELECT nome, cpf_cnpj FROM case_partes WHERE case_id='<caso-do-cliente-anonimizado>';
 E2E-FICTICIO-LGPD Parte Contrária Teste | 529.982.247-25   ← nome e CPF continuam recuperáveis
```

O serviço `client_anonimizacao.py` cobre a tabela `clients`; não toca `case_partes`, mesmo quando a parte é a MESMA pessoa cujo direito ao esquecimento foi exercido (o `case_parte` tem `client_id` apontando para o cliente agora anonimizado, mas o próprio registro da parte carrega nome/CPF em claro, independente do cliente). Efeito prático: um titular que exerce o direito ao esquecimento continua identificável via qualquer caso onde apareça como parte processual.

### 3.7 Erros de validação bem escritos — nota positiva

Vale registrar o oposto de um achado de defeito: as mensagens de 422 encontradas nesta rodada (`proxima_acao` obrigatório, `área inválida` com a lista de valores aceitos, `tipo_peca inválido` com a lista do enum, `status de caso inválido` com os valores aceitos) são **todas acionáveis** — dizem o que está errado e o que fazer. Isso reduziu o tempo de reprodução manual desta auditoria de forma perceptível e é o padrão que deveria se generalizar.

### 3.8 Migrations rodam limpo contra Postgres real

```
$ docker exec ejc_backend python -m alembic heads
126_case_status_quatro_estados (head)
```

`alembic upgrade head` rodou do zero (banco vazio) sem erro, contra `pgvector/pgvector:pg16`. `126` bate com o que `CLAUDE.md` documenta como head em 2026-08-02 — nenhuma migration pendente ou quebrada.

---

## 4. Tabela consolidada

| # | Achado | Severidade | Status | Evidência |
|---|---|---|---|---|
| 1 | Prefixo `/v1/` duplicado em 8 routers (P0-1) | Alta | **CONFIRMADO** | §2.1 |
| 2 | `GET /rag/docs` 500 (P0-3) | Alta | **CONFIRMADO** | §2.2 |
| 3 | `POST /legal-docs/{id}/validar` — 500 não tratado sem provedor de IA; trava `/aprovar` em `sem_validacao` | **Alta (novo)** | **CONFIRMADO** | §3.2 |
| 4 | CPF em texto puro em `case_partes` (P1-5) | Média | **CONFIRMADO** | §3.5 |
| 5 | Anonimização de cliente não alcança `case_partes` (P1-6) | Média | **CONFIRMADO** | §3.6 |
| 6 | `VAULT_MASTER_KEYS` ausente em `.env.example`, exigida no boot produção | Média (novo) | **CONFIRMADO** | §3.1 |
| 7 | `?status=all` derruba servidor / `?status=ativo` some silenciosamente | — | **REFUTADO (já corrigido, migration 126)** | §2.7 |
| 8 | Vocabulário `tipo_peca` diverge entre `peca_geracao.py` e `models/legal_doc.py` | Baixa (novo) | **CONFIRMADO** (estrutural; efeito em produção não testável sem IA) | §3.3 |
| 9 | Soft delete de caso não cascateia para `legal_docs`/`documents` | Baixa (refinado) | **CONFIRMADO no dado, MITIGADO na leitura** | §2.8 |
| 10 | `pecas_aguardando_revisao` do dashboard | — | **REFUTADO — indicador correto** | §3.4 |
| 11 | `JURIS_IMPORT_FONTES` do `.env.example` diverge do default do código (tjmg) | Baixa (novo) | **CONFIRMADO**, é config, não bug | §2.6 |
| 12 | Documento com/sem `case_id` — dois caminhos no GED | — | **REFUTADO — ambos funcionam corretamente** | §2.9 |
| 13 | `RATE_LIMIT_REDIS_ENABLED=true` com 1 worker uvicorn | — | **NÃO É INCOERÊNCIA** — redundante, inofensivo | §2.4 |
| 14 | Hipótese: gate de citações bloqueia toda peça | — | **NÃO VERIFICÁVEL** (sem provedor de IA neste ambiente) | §2.3 |
| 15 | Fixture da suíte E2E (`fictitious_matrix.json`) sem `proxima_acao` no payload de caso | Baixa (dívida de QA) | **CONFIRMADO** — bloqueia a suíte automatizada a partir da criação de caso | §2.5 |
| 16 | 17/19 falhas do smoke E2E são falso alarme do próprio script (rotas-base sem endpoint raiz por desenho + 4 prefixos errados no script) | — | **REFUTADO — não são bugs do backend** | §2.5 |
| 17 | 8/8 falhas do pytest com `RUN_DB_TESTS=1` são artefato do meu harness (não do CI real) | — | **REFUTADO — não são regressões** | §2.6 |

---

## 5. Resultado numérico

**Smoke E2E** (`qa/e2e/run_fictitious_smoke.py`, `EJC_E2E_STRICT=true`, `qa/e2e/reports/e2e_fictitious_report.json`):

| Métrica | Valor |
|---|---|
| Total de checks | 47 |
| Passed | 28 |
| Failed (script reporta) | 19 |
| — dos quais, falso alarme do script (rota-base inexistente por desenho / prefixo errado no script) | 17 |
| — dos quais, falha real (fixture da matriz desatualizada — falta `proxima_acao`) | 1, com 1 efeito em cascata (upload sem `case_id`) |
| Asserts de efeito (escrita relida e conferida) | 1 |
| Checks não cobertos | 3 |

**pytest com `RUN_DB_TESTS=1`** (Postgres real do compose, `python -m pytest tests -q`):

| Métrica | Valor |
|---|---|
| Passed | 4683 |
| Failed | 8 (todos atribuídos a diferença de harness vs. `ci.yml` — nenhuma regressão de produto confirmada) |
| Skipped | 3 |
| Subtests passed | 77 |
| Tempo | 278.42s |

---

## 6. Riscos residuais e limitações

- **Qualidade de geração de IA nunca foi testada** — nenhum provedor elegível neste ambiente (decisão de escopo). A hipótese central do PR #652 sobre o gate de citações permanece não verificada; o achado desta rodada (§3.2) é uma causa alternativa e mais imediata para "nenhuma peça jamais foi protocolada", mas não invalida a hipótese original — só mostra que há pelo menos um bloqueio anterior a ela.
- **Não testei o expurgo definitivo da lixeira** — só soft-delete + restauração. Se existir um job de expurgo físico que apague `cases` sem apagar `legal_docs`/`documents` relacionados, aí sim haveria perda de referência real (ver nuance em §2.8).
- **Não testei 2FA** — o admin semeado não tinha TOTP configurado e o login funcionou sem exigir; `REQUIRE_2FA_ROLES` inclui `superadmin` no `.env.example`, então em produção real esse fluxo provavelmente é exigido no primeiro login (não reproduzido aqui).
- **Skills/templates seedados, mas não exercitados** (48 skills nativas, 34 ferramentas, 22 workflows) — fora do escopo desta rodada.
- **Ambiente derrubado ao final** (`docker compose down`, sem `-v`) — dados fictícios desta rodada não persistem; nenhum dado de produção foi tocado, acessado ou sequer alcançável (sem credenciais, sem rede para a VPS).

---

## Arquivos e evidências desta rodada

- `qa/e2e/reports/e2e_fictitious_report.json` — saída bruta do smoke E2E (não commitado).
- `.env` local (não commitado, `.gitignore` cobre) — segredos gerados localmente, nunca reaproveitados de produção.
- `backend/Dockerfile`, `frontend/Dockerfile` — modificados temporariamente para o build funcionar neste sandbox (proxy/CA), **revertidos** com `git checkout --` antes do encerramento; `git status` limpo.
- Screenshots do browser (login → dashboard → clientes → casos → casos?status=all → casos?status=ativo → peças → conhecimento/IA) em `/tmp/claude-0/-home-user-ejc/219b6648-9d90-5d7f-a519-12a4972c6c1d/scratchpad/screenshots/` (caminho local do agente, não faz parte do repositório).
