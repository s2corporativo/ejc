# 12 — Segurança e LGPD (Fase 12)

> Análise estática sobre o commit `aa65974`, complementada por montagem real do app FastAPI
> (830 rotas) e requisições com JWT forjado. **Nenhum arquivo foi alterado. Nenhum dado de
> produção foi acessado.**

## 0. Veredito

O código está **substancialmente mais duro do que os relatórios históricos indicam**. Os achados
críticos do `LAUDO_AUDITORIA_FORENSE_EJC_2026-06-29.md` estão corrigidos: não há credencial root
em scripts, o RBAC não tem a chave duplicada `socio`, o gate de ownership existe como módulo
canônico e a barreira de PII está ativa.

**Três hipóteses do escopo foram REFUTADAS:**

| Hipótese do escopo | Resultado |
|---|---|
| IDOR em recurso jurídico sigiloso | **nenhum confirmado** nos recursos pedidos (§2) |
| Segredo real versionado | **nenhum** — `git log --all -- .env` vazio (§6) |
| `run_fictitious_smoke.py` cria superadmin em produção | **não cria usuário nenhum** (§8) |

## 1. Resumo por severidade

| # | Achado | Sev. | P |
|---|---|---|---|
| 1 | 2FA desligado por default; segundo fator já cadastrado é neutralizado em runtime | Alto | **risco aceito** (§2.1) |
| 2 | Endpoints de IA caros sem rate limit nem quota — abuso de custo por conta autenticada | Alto | **P1** |
| 3 | `victory_vault` e `document-templates/generate` sem RBAC | Alto | **P1** |
| 4 | `case_partes.cpf_cnpj` em texto puro | Alto | **P1** |
| 5 | Anonimização LGPD art. 17 incompleta | Alto | **P1** |
| 6 | Access token não é invalidado na troca de senha (janela de 2 h) | Médio | P2 |
| 7 | Peça sem `case_id` acessível/editável/apagável por qualquer perfil staff | Médio | P2 |
| 8 | PII (e-mail) em logs; `log_sanitizer` existe mas não está ligado | Médio | P2 |
| 9 | SSRF por DNS rebinding em `document_url_import_service` | Médio | P2 |
| 10 | `audit_logs` "imutável" só por comentário — sem WORM | Médio | P2 |
| 11 | `_is_publica` libera qualquer path fora de `/api/` | Médio | P2 |
| 12 | Listagem de peças expõe casos órfãos que o gate de detalhe nega | Baixo | P3 |
| 13 | Upload lido inteiro em memória antes da checagem de tamanho | Baixo | P3 |
| 14 | Sem antivírus em upload — inclusive no canal externo (portal) | Baixo | P3 |
| 15 | Leitura de caso sigiloso não gera trilha (só download gera) | Baixo | P3 |
| 16 | `X-Frame-Options` conflitante entre as duas camadas nginx; `/api/` sem CSP | Baixo | P3 |
| 17 | `require_roles()` hierárquico é footgun (papel lateral entra por nível) | Baixo | P3 |

## 2. Autenticação

### Confirmado correto

- **Algoritmo fixado.** `core/security.py:151-157` e `core/auth_middleware.py:127-131` passam
  `algorithms=[settings.ALGORITHM]` (`HS256`). `alg=none` e confusão HS/RS são rejeitados. `type`
  do token é conferido explicitamente.
- **Revogação real do refresh.** JTI persiste em `RefreshToken` (`auth.py:311-319`); `/auth/refresh`
  confere no banco (`:354-356`), **rotaciona** (`:446,496-503`) e implementa **detecção de reuso no
  padrão OAuth 2.0 Security BCP §4.14.2**, com revogação em cascata (`:411-425`) e janela de graça
  multi-aba (`:372-388`).
- **Invalidação na troca de senha e no reset:** `auth.py:573-577`, `security_service.py:267-271`.
- **Força de senha:** `security_service.py:108-144` — 10 chars, letra+dígito+especial, blocklist,
  diferente do e-mail. Aplicada só na definição (não trava senha legada no login) — correto.
- **Brute force:** login limitado por IP **e** por e-mail (`auth.py:184-196`), 5 falhas/15 min;
  o passo "TOTP pendente" tem contador próprio (`:227-236`) para não derrubar o escritório;
  `/totp/desativar` tem chave isolada (`:840-859`) — evita que um token roubado tranque a vítima.
- **IP não é forjável.** `request_context.py:32-51` usa o **último** salto do `X-Forwarded-For`, e
  `nginx/ejc.conf:66-69` só confia em `127.0.0.1`.
- **Middleware fail-closed.** `auth_middleware.py:113-141`: sem Bearer → 401; assinatura inválida →
  401. `_is_publica` normaliza com `posixpath.normpath` antes de comparar (`:38-65`). Tentativas de
  divergência (`/api/cases/../auth/login`, `%2e%2e`) devolvem 401/404 — **nunca acesso**.
  Varredura dos 162 routers: **nenhum endpoint sem autenticação** além dos 7 públicos intencionais.

### 2.1 — 2FA desligado por default: RISCO ACEITO, não achado

`core/two_factor_policy.py:26` — `os.getenv("TWO_FACTOR_AUTH_ENABLED", "false")`. Com a flag
desligada, `:40` esvazia `REQUIRE_2FA_ROLES` e `:43-45` instala um listener `load` do SQLAlchemy
que força `totp_enabled = False` em **todo** `User` carregado. Um usuário que enrolou TOTP
autentica só com senha, **sem aviso**. A variável não aparece em `.env.example`,
`docker-compose.yml` nem nos workflows.

> **Não é reportado como P0 por decisão de governança.** `docs/GOVERNANCA_IA.md:254` registra
> decisão permanente do titular, vigente desde 2026-07-26 e reafirmada em 27/07: *"2FA desligado
> por padrão e o kill-switch preservado. Não alterar `two_factor_policy.py` para forçar
> fail-closed, nem incluir 2FA em auditoria como bloqueador P0. Se uma auditoria apontar o
> fail-open, registre como **risco aceito pelo titular**, não como achado a corrigir."*
>
> Fica o registro do risco residual, **sem recomendação de mudança de código**.

### 2.2 — P2. Access token sobrevive à troca de senha

`core/security.py:119-127` — o payload do access token tem `sub`, `role`, `type`, `exp`, `iat`.
**Não há `jti`, `token_version` nem `password_changed_at`**, e não existe blacklist.
`auth.py:573-577` revoga apenas os `RefreshToken`.

**Cenário:** a vítima percebe o comprometimento e troca a senha; o refresh do atacante morre, mas o
**access token dele continua válido até `exp`** — `ACCESS_TOKEN_EXPIRE_HOURS=2`. Duas horas de
acesso pleno a dossiês **após** a ação corretiva.

*Mitigação existente:* `get_current_user` (`security.py:190-199`) reconsulta o banco a cada request
e filtra `is_active`/`deleted_at` — **desativar** o usuário corta o acesso na hora.
*Correção:* claim `pwd_epoch` comparado a uma coluna `password_changed_at`; ou reduzir
`ACCESS_TOKEN_EXPIRE_HOURS` para 15-30 min (a rotação single-flight do frontend absorve).

## 3. Autorização e IDOR

Método: varredura AST dos 162 routers isolando endpoints com path param que tocam modelos
sensíveis **sem** chamada a gate de propriedade; depois leitura manual. Rodado **duas vezes** — a
segunda **excluindo** `require_roles`/`require_admin`/`is_gestao` da lista de gates, para não
mascarar endpoint protegido só por papel. 27 candidatos, todos revisados.

| Endpoint | Query | Filtro de propriedade? |
|---|---|---|
| `GET/PATCH /cases/{id}` | `cases.py:333,433` | **Sim** — `_filtro_visibilidade` (`:74-85`): abaixo de sócio exige ser responsável ou auxiliar |
| `DELETE /cases/{id}` | `cases.py:636` | sem filtro na query, mas `require_roles(["admin","socio"])` (`:620`) = gestão, que vê tudo. **Sem IDOR** |
| `GET /documents/{id}/download` | `documents.py:599-608` | **Sim** — `_verificar_acesso_documento` + `_pode_acessar_confidencial` |
| `DELETE/PATCH /documents/{id}` | `:662,701` | **Sim** |
| `GET /documents/drive/{file_id}/download` | `:959-990` | **Sim** — `_gate_drive_doc` cobre doc com e sem `case_id` |
| `GET /legal-docs/{id}` | `legal_docs.py:396-405` | **Parcial** — §3.2 |
| `PATCH/DELETE /fees/{id}`, pagamentos | `fees.py:193,233,289` | sem filtro por caso, mas `_req_financeiro_mutacao` (`:37-44`) é **conjunto explícito** `{superadmin,admin,socio,financeiro}`, sem fallback hierárquico. **Sem IDOR** |
| `GET /clients/{id}` | `clients.py:534-542` | **Sim** — `_pode_ver_cliente`, com **404** (não vaza existência) |
| `GET /data-rooms/{id}` | `data_room.py:376` → `_gate_room` (`:212-234`) | **Sim** — valida caso e cliente, 404 uniforme |

### 3.1 Portal do cliente — isolamento comprovado

Três camadas independentes:

1. **Middleware** (`auth_middleware.py:191-204`): `cliente_externo` só alcança `/api/portal/`,
   `/api/auth/`, `/api/health`, `/api/notifications`, `/api/signatures`, `/api/users/me`.
2. **Gate por endpoint**: `_exigir_cliente` (`portal.py:26-30`, `portal_documentos.py:50-57`).
3. **Filtro em toda query**: `portal.py:41` (casos), `:88` (`Case.client_id == client_id`),
   `:131-134` (documentos, e **só** `confidencialidade == normal`), `:151-152` (financeiro),
   `:175-181` (mensagens, SQL parametrizado), `portal_documentos.py:143` (upload).

As duas rotas fora de `/portal` liberadas ao papel também filtram: `notifications.py:45,130`
(`user_id == cu.id`) e `signatures.py:129-130,201-208` (`client_id` + dono da solicitação).
**Estratégia interna do caso (tese, pontos fortes/fracos) nunca é serializada no portal.**
→ **Sem vazamento cross-tenant.**

### 3.2 — P2. Peça sem `case_id` é livre para qualquer staff

O gate das peças é **condicional** — verificado por mim, ocorre em `legal_docs.py:404,420,435,469`
e também em `/validacao`, `/validar`, `/revisar`, `/aprovar`, `/pdf`, `/exportar-docx`,
`:958` (delete):

```python
if d.case_id:
    await verificar_acesso_caso(db, cu, d.case_id)
```

`LegalDoc.case_id` é **`nullable=True`** (`models/legal_doc.py:71`) e `POST /legal-docs/` aceita
`case_id=None` (`:369-370`). **Para peças avulsas não sobra gate nenhum** — o endpoint depende só
de `get_current_user`, sem piso de papel.

**Exploração:** um `secretaria` (2), `estagiario` (3) ou `financeiro` (4) que descubra ou enumere
um `doc_id` de minuta avulsa **lê o conteúdo integral, edita, exporta em PDF/DOCX e apaga**.
Minutas avulsas são exatamente as peças em elaboração **antes de o caso existir**, com a narrativa
do cliente dentro.
*Correção:* para `case_id IS NULL`, exigir `created_by == cu.id` ou `is_gestao(cu)`, e aplicar
`requer_advogado()` (já existe em `security.py:40-49`) nas escritas.

### 3.3 — P1. `victory_vault` e `document-templates/generate` sem RBAC

Ver `08-backend.md` §6.3. `POST /api/victory_vault/teses` e `/modelos`
(`victory_vault_router.py:8,11,19`) gravam no **cofre institucional** só com JWT — sem RBAC, sem
rate limit, sem audit log, sem service. `POST /api/document-templates/generate`
(`peca_geracao_router.py:28-30`) **gera documento jurídico sem gate de advogado**, enquanto o
caminho gêmeo exige (`kit_documental.py:58`, `cases.py:698-704`).

### 3.4 — P3. Listagem de peças contradiz o gate de detalhe

`legal_docs.py:319-326` inclui na listagem, para não-gestão, peças de casos **sem responsável nem
auxiliar**. Mas `verificar_acesso_caso` (`core/ownership.py:67-74`) foi endurecido justamente para
**negar** caso órfão a quem não é gestão. Resultado: qualquer staff lista título/tipo/status das
peças de casos órfãos e recebe **403 ao abrir**. Vazamento limitado a metadados
(`LegalDocResponse` não traz `conteudo`), mas a incoerência é real.

### 3.5 — P3. `require_roles()` admite papel lateral pelo nível

`core/security.py:209-218`: quando o papel não está na lista, o fallback compara com o **mínimo**
dos permitidos. Logo `require_roles(["financeiro"])` (4) admitiria `advogado` (6) e `socio` (7) —
não é "quem é financeiro", é "quem é ≥ financeiro".

**Hoje não é explorável**: nenhum endpoint financeiro usa esse padrão (`fees.py` usa conjunto
explícito), e os usos com papel baixo (`dashboard.py:47`, `qualidade.py:69,76,92`) querem mesmo
"e acima". Fica o footgun: um endpoint futuro escrito esperando exclusividade **nasce furado**.
Vale documentar a semântica ou oferecer `require_roles_exatos()`.

## 4. Upload e arquivos

**Confirmado correto:** magic bytes vs extensão com **persistência do MIME detectado**, nunca o
`content_type` do cliente (`documents.py:66-83`, reusado por `portal_documentos.py:42,167` e
`legal_chat.py:238`); allowlist **sem formato ativo** (`documents.py:19` — sem `.svg`, `.html`,
`.js`); **path traversal impossível por construção** (caminho derivado de UUID,
`documents.py:394-396`); **uploads fora do webroot** (nenhum `StaticFiles`/`mount`; nenhum `alias`
para `uploads` no nginx); header de download sanitizado com `filename*` RFC 5987
(`documents.py:1049-1060`) — response splitting fechado; **IDOR de escrita fechado no upload**:
o `client_id` é **derivado do caso**, nunca aceito do formulário (`:322-333`).

**P3 —** corpo inteiro em memória antes do teto (`documents.py:379-384`,
`portal_documentos.py:160-165`): `await file.read()` e **depois** mede. Mitigado por
`client_max_body_size 50m` no nginx, mas o backend isolado é derrubável por exaustão — agravado
pela premissa de worker único.

**P3 —** sem antivírus. O canal mais exposto é o **portal do cliente**
(`portal_documentos.py:121`), onde um usuário **externo** grava arquivo que depois será aberto por
advogados. Magic bytes barram troca de extensão, não PDF com JS ou DOCX com macro.

## 5. Injeção

| Vetor | Resultado |
|---|---|
| **SQL** | **nenhuma injeção**. Auditados os 28 pontos com `text(f"…")`: o interpolado são fragmentos estáticos ou nomes de coluna de allowlist literal; valores sempre em bound params. Conferidos individualmente os construtores de `SET` dinâmico (`office_contracts.py:122-128`, `pending_items.py:96-106`, `memoria_institucional.py:149-160`, `agenda_eventos.py:208-212`) — todos com tupla literal. Termos de busca do RAG viram `:t0..:t7` (`ai_service.py:419-423`) |
| **Command** | `subprocess.run` sempre com lista e sem `shell=True` (`google_drive.py:58`, `backup_service.py:183,262`, `ocr_service.py:163`, `scheduler.py:1365-1379`). Nenhum `os.system`/`eval`/`exec` sobre entrada de usuário |
| **XSS** | **zero** `dangerouslySetInnerHTML` em `frontend/src` — `components/Markdown.tsx:4` documenta a escolha de construir elementos React. Nenhum `innerHTML`. CSP `script-src 'self'` em `frontend/nginx.conf:26` |
| **SSRF** | `rag_public.validar_callback_url` (`:103-141`) é **exemplar**: resolve o host, bloqueia privado/loopback/link-local/multicast/reservado **e fixa o IP validado no POST** (`:198-206`), fechando rebinding. `rag.py:238-254` reusa, desabilita `follow_redirects` e **revalida cada salto** |

### 5.1 — P2. DNS rebinding em `document_url_import_service`

`services/document_url_import_service.py:143-154` valida corretamente (resolve, bloqueia IP
interno, revalida redirect em `:189`), **mas `_fetch_bytes_seguro` (`:182-184`) faz a requisição
pelo hostname**:

```python
async with httpx.AsyncClient(...) as client:
    resp = await client.get(atual)      # nova resolução DNS, sem pinagem
```

TOCTOU clássico: um domínio sob controle do atacante responde IP público na validação e IP interno
(`169.254.169.254`, `10.x`, o container do Postgres) na conexão. Alcançável por **qualquer usuário
autenticado** via `POST /api/documentos-ia/analisar-url` (`documento_ia.py:207-228`), e **o conteúdo
buscado volta na resposta** — SSRF com leitura.
*Correção:* aplicar o padrão de `rag_public._url_com_ip_fixado` — conectar ao IP validado
preservando `Host`/SNI. **O código de referência já existe no repositório.**

## 6. Configuração e segredos

**Confirmado correto:** CORS por `.env` com `allow_credentials` e boot que **falha em produção com
`*`** (`main.py:299-304`, `config.py:887-895`, reforçado por `ci_guard.sh`); boot fail-closed
exigindo `SECRET_KEY` ≥32 sem prefixo `TROCAR`, `PII_ENCRYPTION_KEY` validada como Fernet real,
`PII_HASH_KEY`, `VAULT_MASTER_KEYS` (`config.py:867-940`); docs desabilitadas em produção
(`main.py:276-278`); cookie de refresh `httponly` + `secure` + `samesite=lax`
(`auth.py:79-88` — o Lax fecha CSRF no `/auth/refresh` sem token anti-CSRF); exception handler sem
stack trace em produção (`main.py:554-575`).

**Rate limit — login coberto:** slowapi registrado (`main.py:282-283`) com `/login` 10/min,
`/refresh` 20/min, `/recuperar-senha` 3/h, `/redefinir-senha` 10/h, TOTP 10/min. Backend Redis
atômico via Lua (`rate_limit.py:120-124`).

### 6.1 — P1. Endpoints de IA caros sem rate limit nem quota

Verificado por mim: **`routers/ai.py` tem 14 rotas POST e apenas 3 com `rate_limit`.** Sem limite,
cada uma dispara chamada ao `ai_gateway`:

`/ai/analisar-caso` (`:55`) · `/ai/resumir-documento` (`:105`) · `/ai/teses-ocultas` (`:383`) ·
`/ai/auditar-peca` (`:409`) · `/ai/preparar-audiencia` (`:451`) ·
`/ai/casos/{id}/assistente` (`:552` — monta dossiê completo + RAG) ·
**`/ai/casos/{id}/dual` (`:672` — duas inferências por request)** ·
`/ai/caso/{id}/visual-law` (`:792`) · `/ai/caso/{id}/estrategia` (`:834`) ·
`/ai/analisar-contrato` (`:943`) · `/ai/detectar-prazos` (`:970`).

**Não há limite global compensando:** confirmei que **`SlowAPIMiddleware` não é registrado** — só o
`app.state.limiter` e o exception handler (`main.py:282-283`). Logo **não existe `default_limits`**.
E o controle de custo é apenas alerta: `config.py:686` — `AI_BUDGET_ALERTA_BRL: float = 0.0`
(desligado por default).

**Exploração:** qualquer conta staff comprometida — inclusive `estagiario`, que `ai.py:559-560`
admite no assistente — roda um laço contra `/dual` e **queima o orçamento Anthropic/Groq do
escritório**; sob worker único, ainda satura o event loop e degrada o sistema inteiro. É o tipo de
abuso que só aparece na fatura.
*Correção:* aplicar `Depends(rate_limit("<nome>", N))` nessas rotas (o padrão já existe e é usado
em 3 rotas do próprio arquivo) e transformar `AI_BUDGET_ALERTA_BRL` em **teto rígido**.

### 6.2 Segredos — verificado e limpo

- `git ls-files | grep .env` → apenas `.env.example` e `vps-tools/.env.example`.
- **`git log --all -- .env backend/.env vps-tools/.env` → vazio.** Nunca houve commit.
- `.gitignore:2-11` cobre `.env`, `*.env`, `**/.env`, `.env.bak*`, `.env.save`.
- Varredura por `chave = "valor≥12 chars"` em `backend/app`, `frontend/src`, `scripts`,
  `docker-compose.yml`, `.github`, `vps-tools`, `qa`: **zero** fora de placeholders.
- `docker-compose.yml` usa só interpolação. `vps-tools/ssh-config.js:38-47` lê do ambiente e falha
  se ausente.
- Cofre de credenciais guarda só hash SHA-256 + prefixo, com comparação constant-time e piso
  `superadmin`.

> **O vazamento de credencial root do laudo de 2026-06-29 está corrigido.**

*(Ressalva de escopo: a chave DataJud hardcoded está numa **skill do Claude Code**, não no produto —
ver `05-skills.md` §A4.)*

### 6.3 — P3. Headers divergentes entre as duas camadas nginx

`nginx/ejc.conf:50-53` (host) define HSTS, `nosniff`, `Referrer-Policy` e
**`X-Frame-Options: SAMEORIGIN`**; `frontend/nginx.conf:20` (container) define
**`X-Frame-Options: DENY`**. As respostas de `/` carregam os **dois valores conflitantes**. Além
disso, o host não define CSP própria: as respostas de `/api/` (host → backend, sem tocar o
container) **não têm CSP**. Consolidar numa camada só e alinhar em `DENY`.

## 7. LGPD

**Confirmado correto:** CPF/CNPJ cifrados em repouso (Fernet não determinístico + HMAC-SHA256 como
índice cego, `pii_crypto.py:52-87`), com `RuntimeError` explícito na ausência da chave (`:43-48`)
e boot que não sobe sem ela; **segredo TOTP também cifrado** com re-cifragem oportunista
(`auth.py:114-152`); **PII não sai em claro para provedor externo**
(`ai_gateway.py:768-812` — mascaramento + `validar_sem_pii` + pseudonimização reversível com o mapa
**só em memória**, nunca logado nem persistido); trilha nos pontos certos (download local e via
Drive, exportação art. 18 II e V, `PORTAL_ACESSO_CRIADO`, assinatura com IP/UA/hash); direitos do
titular implementados (acesso PDF, portabilidade JSON, esquecimento com verificação de bloqueios,
`clients.py:892-919`).

### 7.1 — P1. `case_partes.cpf_cnpj` em texto puro

Ver `07-banco-de-dados.md` §5.1. **`models/case_parte.py:20`** — `cpf_cnpj = Column(String(18))`,
ao lado de `nome`, `email`, `telefone`. É a **única** tabela onde CPF/CNPJ de pessoa natural
persiste em claro depois do cutover da migration 112, que dropou `clients.cpf`/`cnpj`.
**Tem `client_id` FK (`:27`)** — o próprio cliente frequentemente é uma `case_parte`, e o mesmo
CPF cifrado em `clients` está legível ao lado.

### 7.2 — P1. Anonimização do art. 17 incompleta

Ver `07-banco-de-dados.md` §5.2. `services/client_anonimizacao.py` importa **apenas `Client` e
`User`** (`:19,21`) — **`CaseParte` não é sequer importado**. Não toca em `case_partes`,
`sociedades_cliente`, `users.email`/`full_name`, `cases.descricao_fatos`, nem
`audit_logs.dados_antes/depois`.
**Depois de "anonimizar", o CPF e o nome do titular continuam recuperáveis por consulta a
`case_partes`.**

### 7.3 — P2. PII em logs; sanitizador existe mas não está ligado

`core/log_sanitizer.py` tem os regexes certos (CPF, CNPJ, e-mail, Bearer, `token=`), mas **não há
`logging.Filter` instalado**: `core/logging_config.py:51-66` monta handler e formatter **sem
nenhum filtro**. `sanitize_log_value`/`safe_exception_log` são chamados manualmente em apenas 4
arquivos.

E-mails de titulares indo em claro para `docker logs`:
- `services/security_service.py:173` — `logger.info(f"[Email OFF] {assunto} → {destinatario}")`
- `services/security_service.py:189` — `logger.info(f"Email enviado: {assunto} → {destinatario}")`
- `services/scheduler.py:1688` — `logger.warning(f"DJEN {a.email}: {e}")`

*Correção de uma linha estrutural:* instalar um `logging.Filter` em `setup_logging` que aplique
`sanitize_log_value` sobre `record.msg`/`record.args` — vira defesa em profundidade para **todo**
`logger.*` novo, em vez de depender de disciplina em ~40 call sites.

### 7.4 — P2. `audit_logs` sem WORM real

Ver `07-banco-de-dados.md` §5.3. O model diz *"IMUTÁVEL — nunca editar/deletar (LGPD art. 37)"*
(`models/audit_log.py:2`), mas **nenhuma migration cria trigger, RULE, REVOKE ou RLS** — confirmei
que a busca nas 121 migrations retorna **um único arquivo**, e o trigger dele é de outra coisa. A
reserva `127_audit_log_worm` consta como **Revogada**. **Qualquer papel com acesso ao banco apaga a
trilha.**

### 7.5 — P3. Leitura de dado sigiloso não gera trilha

`GET /cases/{id}` (`cases.py:327-345`) devolve o `CaseDetail` completo e **não** chama
`criar_audit_log`. Idem `GET /clients/{id}` (`clients.py:528-544`) e `GET /legal-docs/{id}`
(`legal_docs.py:390-409`). Só **download** e escritas são auditados.

Para responder a *"quem consultou o dossiê deste cliente?"* a trilha atual não serve. Não é
violação direta da LGPD, mas enfraquece o art. 46 e o art. 48 num sistema com dado sob segredo de
justiça. *Sugestão pragmática:* auditar `VIEW` apenas em caso/documento com
`confidencialidade != normal`, para não inflar a tabela.

## 8. `homolog.qa` — REFUTADO no código

Os dois runners foram lidos. **Nenhum cria usuário, muito menos superadmin.**

- `qa/e2e/run_fictitious_smoke.py`: credenciais do ambiente (`EJC_TEST_EMAIL`/`_PASSWORD`,
  `:319-333`); cria só cliente/caso/documento marcados **`E2E-FICTICIO`** (`:50`), com `RUN_ID`
  único e cleanup idempotente no `finally` (`:735-739`); **guarda de produção** em `:711-716`
  (aborta salvo URL com `staging`/`homolog`/`localhost` ou opt-in explícito); redação de segredos
  no relatório.
- `qa/homologacao/run_homologacao.py`: mesma guarda (`:495-502`), credenciais por env, e é a
  **verdadeira** origem do prefixo `HOMOLOG-FICTICIO-` (`:176`) — aplicado a **nome de
  cliente/caso/documento** (`:180-205`), não a conta. Recusa URL com credenciais embutidas.

Confirmei independentemente: `grep -rn "homolog.qa"` em `.py`/`.json`/`.ts` → **zero ocorrências**.

> **Conclusão:** se a conta `homolog.qa` superadmin existir em produção, foi criada **manualmente
> ou por procedimento fora deste repositório**. **A correção de código já está implementada** nos
> dois runners; **a correção pendente é operacional.**
>
> **Ação para o titular:**
> `SELECT id, email, role, is_active, last_login_at FROM users WHERE email LIKE '%homolog%' OR email LIKE '%qa%';`
> e, se existir, desativar e auditar `audit_logs` por esse `user_id`.
> **`CLAUDE.md:265` deve ser corrigido** — atribui a origem ao runner errado.
> **[NÃO CONFIRMADO]** — exige consulta ao banco de produção, vedada pela regra 9.

## 9. Confirmado × potencial

**Confirmado por leitura de código** (comportamento determinado pelo fonte): achados 2-17, e o
achado 1 (comportamento confirmado, risco formalmente aceito).

**Riscos potenciais, não confirmáveis por análise estática:**
- Efetividade da cadeia nginx **em produção** — o `ejc.conf` versionado pode divergir do instalado.
- Presença da conta `homolog.qa` e dos dados `HOMOLOG-FICTICIO-*` em produção (§8).
- Se `TWO_FACTOR_AUTH_ENABLED` está definido no `.env` do VPS (não versionado).
- **Se `RATE_LIMIT_REDIS_ENABLED` e a contagem de workers uvicorn são coerentes em produção.** A
  premissa de worker único vale para o rate limit em memória **e** para o anti-brute-force de
  `security_service.py:33`, que **não tem backend Redis nenhum** — com >1 worker, o teto de 5
  falhas vira 5×N.
