# Auditoria de integrações externas — agosto/2026

> Issue #818. Auditoria **interna, de código-fonte**, complementar à auditoria externa de
> julho/2026 (`docs/auditoria/`), que foi feita sem acesso ao repositório. Somente leitura:
> nenhuma integração foi ligada, nenhuma chamada externa foi disparada, nada foi implantado.

## Método

Cada integração foi lida no arquivo e conferida contra o padrão declarado em `CLAUDE.md`:
flag de env com default seguro, degradação graciosa, segredo só via `settings`, timeout
explícito na chamada externa, sanitização de PII antes de provedor externo, gravação
transacional e **monitoramento de resultado, não de execução**. Toda afirmação abaixo tem
`arquivo:linha` conferido — onde não houve leitura direta, está dito.

## Quadro geral

| Frente | Flag / default | Timeout | Degradação | Veredito |
|---|---|---|---|---|
| Gateway de IA + providers | `AI_ENABLED=true`, externos por flag | sim | fallback em cadeia | conforme |
| DataJud | `DATAJUD_ENABLED=false` | `DATAJUD_TIMEOUT_SECONDS` | exceção tipada + cache | conforme |
| DJEN / TJMG / LexML (ingestão pública) | ON, sem credencial | sim | retorna vazio | conforme |
| Infosimples | `INFOSIMPLES_ENABLED=false` | sim | cota diária + cache | conforme |
| BCB / BrasilAPI / radar legislativo | ON, público | sim | retorna `None` | conforme |
| Importação de documento por URL | — | sim | guarda SSRF própria | conforme, ressalva A7 |
| E-mail (SMTP) / Push (VAPID) | `EMAIL_ENABLED`/`PUSH_ENABLED=false` | SMTP 15s | falha silenciosa | conforme |
| WhatsApp (Evolution API) | `WHATSAPP_ENABLED=false` | 20s | 502 tratado | **A3, A4** |
| Backup offsite | `BACKUP_ENABLED=false` **e** `BACKUP_REMOTE` | sim | — | **A1, A2, A5** |
| Celery / Redis | `CELERY_ENABLED=false` | ping | cai p/ `BackgroundTasks` | conforme |
| Heartbeats de job | — | — | — | **A8** |

---

## Achados

### A1 — CRÍTICO · Dump do banco sobe ao offsite sem cifra, por um job que nenhuma flag desliga

Existem **dois pipelines de backup vivos ao mesmo tempo**, e só um deles cifra.

O pipeline atual (`app/services/backup_service.py:6`) declara a invariante correta: o artefato é
"cifrado com Fernet (`BACKUP_ENCRYPTION_KEY`) **ANTES** de sair do VPS". Ele é registrado como
`id="backup_drive"` (`app/services/scheduler.py:1320`) e é governado por `BACKUP_ENABLED`, que o
boot valida — `config.py:981-995` exige `BACKUP_ENCRYPTION_KEY` válida quando a flag está ligada.

O pipeline legado convive com ele e não respeita nada disso:

- `app/services/scheduler.py:1307` registra `_backup_banco` **incondicionalmente** — sem checar
  `BACKUP_ENABLED`. O comentário em `scheduler.py:1316` assume a convivência como intencional
  ("Convive com o job legado id=\"backup\"").
- `app/services/scheduler.py:1409-1420` roda `pg_dump -Fc` e grava o dump **em claro** no disco.
- `app/services/scheduler.py:1429-1440` faz `rclone copy` **desse arquivo em claro** para
  `settings.BACKUP_REMOTE`. Não há chamada a `cifrar_arquivo()` em nenhum ponto do caminho.

Consequência: com `BACKUP_REMOTE` preenchido, a base de produção inteira sai do VPS sem
criptografia — mesmo com `BACKUP_ENABLED=false`, isto é, mesmo com o operador acreditando que o
backup está desligado. CPF/CNPJ seguem cifrados em coluna (`services/pii_crypto.py`), mas nome de
cliente, fatos de caso, peças e documentos vão em claro para o destino remoto.

Correção mínima: passar o artefato por `backup_service.cifrar_arquivo()` antes do `rclone copy`,
ou aposentar `_backup_banco` de vez, já que `job_backup_drive` cobre o mesmo terreno com cifra,
rotação e verificação.

### A2 — ALTO · Causa-raiz da divergência `backup_offsite` entre painéis

A auditoria externa registrou `/diagnostico/central` reportando `backup_offsite` ligado e
desligado na mesma resposta, sem conseguir explicar por quê. A causa está no código: **os dois
painéis leem flags diferentes do mesmo conceito.**

- `app/services/integration_status.py:340-341` → `enabled=bool(settings.BACKUP_REMOTE)`
- `app/services/diagnostico_service.py:573` → `habilitado = bool(settings.BACKUP_ENABLED)`

Como A1 mostra, essas flags governam pipelines distintos. Um ambiente com `BACKUP_REMOTE`
preenchido e `BACKUP_ENABLED=false` produz, corretamente do ponto de vista de cada função e
incorretamente do ponto de vista do operador, "Backup offsite: ligado" num painel e
"Backup offsite: desligado" no outro. Enquanto A1 não for resolvido, unificar os painéis numa só
fonte esconderia o problema em vez de corrigi-lo — A1 vem primeiro.

### A3 — ALTO · `WHATSAPP_ENABLED` não governa o WhatsApp

`WHATSAPP_ENABLED` nasce `false` (`config.py:354`), mas `app/routers/whatsapp.py` **nunca lê essa
flag**. Todo o router (`/whatsapp/status`, `/qrcode`, `/send`, `/chats`, `/messages`) fala com a
Evolution API independentemente dela. Os únicos consumidores da flag em todo o backend são o
painel (`integration_status.py:287`) e um comentário no scheduler (`scheduler.py:232`).

Duas consequências. A integração externa não obedece ao padrão "flag default OFF" do repositório —
basta `EVOLUTION_API_URL`/`EVOLUTION_API_KEY` no ambiente para haver tráfego de saída com dados de
cliente. E o painel reporta o valor da flag, não o comportamento real: exibe "WhatsApp desligado"
enquanto `/whatsapp/send` funciona.

O RBAC do router está correto (`_exigir_envio`/`_exigir_gestao`, checagem explícita por conjunto,
`whatsapp.py:21-31`) e o timeout de 20s existe (`whatsapp.py:52`, `whatsapp.py:59`) — o problema é
só o gate.

### A4 — MÉDIO · Configuração do WhatsApp lida por `os.getenv` no import, fora do `settings`

`app/routers/whatsapp.py:38-42` lê `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`,
`EVOLUTION_INSTANCE` e `EVOLUTION_INSTANCE_KEY` com `os.getenv` em escopo de módulo, com fallback
para nomes legados. Fica fora do `pydantic-settings`: sem validação de boot, sem participar das
guardas de produção de `config.py`, e invisível para quem audita a configuração pelo `Settings`.
Também congela os valores no import — mudança de ambiente exige restart.

### A5 — MÉDIO · `BACKUP_REMOTE` é uma flag legada viva e ambígua

`config.py:694` mantém `BACKUP_REMOTE` ao lado de `BACKUP_DESTINO` (`config.py:726`) e
`BACKUP_RCLONE_REMOTE` (`config.py:730`). O serviço atual usa as duas últimas
(`backup_service.py:95`, `:474`, `:555`); a primeira só sobrevive no caminho legado e no painel.
Um operador que preencha `BACKUP_REMOTE` achando que está configurando o backup cifrado está, na
verdade, ligando exatamente o caminho sem cifra de A1.

### A6 — BAIXO · Chamada HTTP sem timeout explícito

`app/routers/noticias.py:86` abre `httpx.AsyncClient()` sem `timeout`. O httpx aplica 5s por
padrão, então não há travamento indefinido, mas é a única chamada externa do backend que foge à
convenção de timeout explícito — as demais que o grep apontou (`ingestion_service.py:118`,
`radar_legislativo.py:85`, `radar_poder.py:52`) passam `timeout` e eram falso-positivo do padrão
de busca.

### A7 — BAIXO · Janela de DNS rebinding na importação de documento por URL

`app/services/document_url_import_service.py` tem guarda SSRF própria e bem construída: valida
esquema (`:107`), bloqueia `localhost`/`.local` (`:149`), resolve o hostname e recusa IP privado,
loopback, link-local, multicast e reserved (`:117-155`), usa `follow_redirects=False` e timeouts
curtos (`:180-182`). A ressalva é estrutural: `validar_url_importavel` resolve o DNS e o httpx
resolve de novo ao conectar, então um domínio hostil que troque a resposta entre as duas
resoluções passa. `follow_redirects=False` reduz muito a exploração prática. Registrado como
resíduo conhecido, não como falha de implementação.

### A8 — MÉDIO · O monitoramento por resultado existe, mas cobre 2 dos 41 jobs

A armadilha central da auditoria externa — "heartbeat afere execução, não resultado; a captura
DJEN reporta ok há meses sem ter capturado nada" — **foi corrigida**, e bem. `avaliar_job`
(`heartbeat_service.py:209-250`) cruza cadência com o veredito de `ingestao_saude` e rebaixa para
`sem_resultado` o job que roda em dia mas cuja fonte está crítica: "rodar sem entregar não é ok"
(`heartbeat_service.py:222`). O DJEN ainda ganhou normalização dedicada
(`_normalizar_resultado_djen`, `:105-148`) e teste próprio (`tests/test_heartbeat_resultado.py`).

O que resta é alcance. `FONTE_POR_JOB` mapeia **dois** jobs (DJEN e DataJud,
`heartbeat_service.py`), `JOBS_MONITORADOS` cobre **sete**, e o scheduler registra **41**
(`grep -c "s.add_job" app/services/scheduler.py`). Os 39 restantes — backup, cobrança, expurgo
LGPD, sincronizações — continuam avaliados só por execução, e a própria docstring reconhece:
"Sem `saude_fonte`, comportamento por execução preservado". A classe de defeito está fechada onde
foi aplicada; o trabalho pendente é estendê-la.

---

## O que está conforme (verificado, não presumido)

**Gateway de IA.** A barreira LGPD é real e centralizada: provider externo só recebe conteúdo
sanitizado e, se sobra PII estrutural depois da sanitização, `_ProviderPulado` interrompe o envio
e a cadeia pula para o próximo provider — "o conteúdo NUNCA foi enviado ao provider externo"
(`ai_gateway.py:246-252`, `:255-289`, `:515-521`). O modo de sanitização é decidido pelo
`task_type` original, antes de qualquer roteamento (`ai_gateway.py:319-338`), e
`LOCAL_COMPLETO` restringe a cadeia a providers locais (`:419-420`). O que sai para o Langfuse é o
traço pseudonimizado, nunca o `str(e)` cru do provider (`:528-535`). Não há bypass: o grep por
`api.anthropic.com|api.groq.com|chat.maritaca.ai|import anthropic` fora de `services/providers/`
só encontra `credential_testers.py` (teste de credencial, sem conteúdo de cliente) e leitura de
nome de modelo em `ia_saude.py`/`config.py`.

**DataJud.** Flag e chave checadas antes de qualquer chamada, com exceção tipada
(`datajud_service.py:253-256`); timeout de settings e retry com backoff só em erro transitório
(`:128-134`); chave só em header, nunca em log (`:271`); cache com TTL (`:83-120`).

**Infosimples.** O arquivo trata segredo como requisito de projeto, não como detalhe: o token vai
**apenas no corpo form-urlencoded**, nunca em query string — portanto não cai em log de acesso —
e as exceções carregam URL e status, nunca o corpo (`infosimples_service.py:28`, `:338-341`). O
hash de cache exclui o token (`:85-87`) e há mascaramento explícito de token e CPF antes de
qualquer registro (`:92-104`). Cota diária e cache por dia UTC evitam martelar a API paga
(`:22`, `:313-319`).

**Notificações.** `EMAIL_ENABLED` gate real com falha silenciosa (`notification_service.py:57-60`),
SMTP com `timeout=15` (`:69`), envio em thread para não travar o event loop. O push tem guarda
SSRF por allowlist de endpoint, porque o endpoint vem do cliente (`:83-97`, `:140`). O envio de
WhatsApp automático foi removido e degrada explicitamente (`:41-48`). Preferências do destinatário
são respeitadas antes de cada canal externo (`:236`, `:243`).

**Celery/Redis.** `CELERY_ENABLED=false` por default e o despacho exige **flag ligada E Redis
respondendo ao ping** antes de enfileirar, caindo para `BackgroundTasks` caso contrário
(`tasks/dispatcher.py:41`, `tasks/raio_x_tasks.py:297`) — Redis fora do ar não derruba a API.

**Cobertura de testes.** Existe suíte dedicada às integrações: `test_ai_gateway_barreira.py`,
`test_sanitizer.py`, `test_log_sanitizer.py`, `test_datajud_sync.py`, `test_infosimples.py`,
`test_djen_observabilidade_v2.py`, `test_heartbeat_resultado.py`, `test_backup_offsite.py`,
`test_backup_restore_encrypted.py`, `test_integration_status.py`, `test_nfse.py`,
`test_notificar_dispatch.py`, entre outros.

## Riscos residuais e limitações

- **Nada foi executado.** É auditoria de código: não subi a stack, não chamei nenhuma API externa
  e não inspecionei o ambiente de produção. Se `BACKUP_REMOTE` está ou não preenchido no `.env` do
  VPS é o que decide se A1 é exposição ativa ou risco latente — e isso só se confirma no host.
- **NFSe e cofre de credenciais ficaram sem leitura direta** (`services/nfse/`,
  `credential_vault_service.py`, `vault_crypto.py`, `processo_eletronico_credential_service.py`).
  A frente que os cobriria não concluiu; não afirmo nada sobre eles nesta auditoria.
- A frente de tribunais foi coberta por DataJud e pelos heartbeats de ingestão; `mni_connector.py`,
  `diario_oficial_service.py` e `crawler_precedentes.py` não foram lidos linha a linha.

## Encaminhamento sugerido

A1 é o único item que pede ação imediata e não deveria esperar bloco de plano: é exposição de
dados pessoais fora do VPS, disparada por uma flag que ninguém associa a backup. A2 e A5 saem
junto, porque são a mesma raiz. A3/A4 são uma correção pequena e contida no router de WhatsApp.
A8 é trabalho incremental — estender `FONTE_POR_JOB` conforme cada job ganhe métrica de resultado.
A6 e A7 podem entrar de carona em qualquer PR que toque os arquivos.
