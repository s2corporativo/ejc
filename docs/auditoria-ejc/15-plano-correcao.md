# 15 — Plano de correção priorizado (Fase 15)

> **Estado: os quatro P0 e seis itens P1 foram executados**, por autorização do titular
> ("autorizo todos"), na ordem recomendada abaixo. A ordem respeita o grafo de dependências
> (`03-mapa-dependencias.md` §3) e a matriz de impacto: **corrigir o verificador antes do defeito
> que ele deveria ter pego.**
>
> | | Estado |
> |---|---|
> | P0-1 · P0-2 · P0-3 | ✅ **corrigidos e validados** |
> | P0-4 (gate de cobertura no CI) | ✅ **corrigido** — `--cov-fail-under=65` no job `db-validation` |
> | P1-1 · P1-2 · P1-3 · P1-4 (segurança e custo) | ✅ **corrigidos** |
> | P1-5 · P1-6 (LGPD) | ✅ **corrigidos** — migration 127 + anonimização das tabelas satélite |
> | P1-7 (`homolog.qa` em produção) | ⛔ **não executável aqui** — exige o banco de produção, vedado pela regra 9. Procedimento em `00-resumo-executivo.md` §9.1 |
> | P1 de qualidade · P2 · P3 | ⏳ pendentes — inalterados |
>
> **Validação global:** 4 570 testes de backend, 364 no frontend, `ruff check app` limpo,
> `tsc --noEmit` exit 0. A migration 127 foi exercitada contra Postgres 16 real (upgrade →
> conferência linha a linha → reexecução → downgrade).

## Ordem recomendada de execução

```
P0-2 (verificador cego)  →  P0-1 (prefixo /v1)  →  P0-3 (rag/docs)  →  P0-4 (gate de cobertura)
                                                       ↓
                              P1 de segurança (RBAC, rate limit de IA, kill-switch)
                                                       ↓
                              P1 de LGPD (case_partes, anonimização) + P1 operacional (homolog.qa)
                                                       ↓
                              P1 de qualidade (peca_geracao_router, ramos.py) → P2 → P3
```

**Por que P0-2 primeiro:** o `api_contract.py` é o guarda-corpo exato da classe de defeito do
P0-1. Corrigir os routers sem corrigir o checker deixa a regressão livre para voltar.

---

# P0 — Crítico

### P0-1 · Prefixo `/v1` mata 4 módulos de negócio

```
ID:                     P0-1
Prioridade:             P0
Problema:               8 routers declaram prefix="/v1/…" e são montados sob prefix="/api",
                        registrando /api/v1/X. O APIVersionCompatibilityMiddleware reescreve
                        /api/v1/* → /api/* antes do roteamento. Resultado: a rota só responde em
                        /api/v1/v1/X. O interceptor do frontend (api.ts:23) apara o /v1/, de modo
                        que 27 chamadas em 9 páginas caem em 404.
Evidência:              despesas.py:24, office_contracts.py:20, partner_withdrawals.py:10,
                        kanban.py:21, datajud.py:17, regulatorio.py:19, pending_items.py:11,
                        whatsapp.py:34 · api_version_middleware.py:34-42 · main.py:287 ·
                        frontend/src/lib/api.ts:9,23
                        Provado por 4 métodos independentes, incl. requisição no app montado:
                        404 /api/v1/despesas · 500 /api/v1/v1/despesas (rota casou)
Causa provável:         migração para o contrato /api/v1 feita em duas frentes (middleware +
                        interceptor) sem remover o /v1 hardcoded nos 8 routers.
Arquivos afetados:      8 routers + (opcional) frontend/src/lib/api.ts + 9 páginas
Dependências no grafo:  api_version_middleware.py (sistêmico) · lib/api.ts (137 dependentes)
Agentes afetados:       nenhum
Skills afetadas:        nenhuma
Risco:                  ALTO — mudança de contrato público de API (§10 da governança)
Correção proposta:      remover "/v1" do prefix= dos 8 routers. O /api/v1 público continua
                        entregue pelo middleware. Alternativa (pior): remover a poda de /v1/ do
                        interceptor — mantém a inconsistência do contrato.
Testes necessários:     teste de superfície que monte o app e verifique que, para cada chamada
                        api.* do frontend, a URL final resolve numa rota registrada (é o teste
                        que falta — ver P0-2 e T-P0-5)
Critério de aceite:     GET /api/v1/despesas responde 200; /api/v1/v1/despesas deixa de existir;
                        as 9 páginas carregam
Execução independente:  SIM — mas deve vir DEPOIS de P0-2
Autorização:            EXIGE o titular (contrato público de API)
```

### P0-2 · O verificador de contrato está cego para o P0-1

```
ID:                     P0-2
Prioridade:             P0
Problema:               _final_url() concatena AXIOS_BASE_URL + raw sem reproduzir a poda de
                        prefixo do interceptor. Para "/v1/despesas" calcula /api/v1/v1/despesas,
                        que _internal_api_url converte em /api/v1/despesas — e casa. O checker
                        valida a URL que o navegador deixou de enviar.
Evidência:              backend/app/utils/api_contract.py:83-93 vs frontend/src/lib/api.ts:21-23
                        tests/test_api_contract.py passa (39 testes) com o defeito vivo
Causa provável:         o checker foi escrito antes do interceptor de request.
Arquivos afetados:      backend/app/utils/api_contract.py, tests/test_api_contract.py
Risco:                  ALTO — é o guarda-corpo desta classe exata de defeito
Correção proposta:      espelhar em _final_url a lógica de api.ts:21-23 (poda de /api/v1/, /api/,
                        /v1/ antes de aplicar o baseURL). Idealmente, extrair a regra para um só
                        lugar e derivá-la, em vez de duplicar.
Testes necessários:     caso de regressão com raw="/v1/despesas" que DEVE falhar antes do P0-1
Critério de aceite:     com o P0-1 ainda não corrigido, test_api_contract.py FALHA apontando as
                        27 chamadas
Execução independente:  SIM — e deve ser a PRIMEIRA
```

### P0-3 · `GET /api/rag/docs` retorna 500 sempre

```
ID:                     P0-3
Prioridade:             P0
Problema:               O monkeypatch troca route.endpoint por uma função cuja assinatura tem
                        db=None, cu=None SEM Depends. include_router roda depois e reconstrói o
                        dependant: db e cu viram query params, get_db e get_current_user somem.
                        A rota estoura AttributeError('NoneType' has no 'execute') — e o
                        hardening de escopo que o patch existe para instalar nunca executa.
Evidência:              app/services/ai_core_hardening_patch.py:111-117 (assinatura) e :188-193
                        (atribuição) · main.py:424 · introspecção do app montado:
                        QUERY_PARAMS=['page','page_size','categoria','db','cu'], SUBDEPS=[]
                        Requisição real com JWT: 500
Causa provável:         patch por atribuição direta, sem considerar que include_router reconstrói
                        o dependant a partir da assinatura.
Arquivos afetados:      app/services/ai_core_hardening_patch.py
Risco:                  ALTO — rota morta E controle de visibilidade nominal
Correção proposta:      declarar db: AsyncSession = Depends(get_db) e cu: User =
                        Depends(get_current_user) na assinatura de _listar_docs_escopado.
                        Melhor ainda: abandonar o monkeypatch e aplicar o escopo no próprio
                        rag.listar_docs — patch em tempo de import é frágil por natureza.
Testes necessários:     request real a GET /api/rag/docs com JWT (200 + escopo aplicado) e
                        teste de que db/cu NÃO aparecem como query params
Critério de aceite:     rota responde 200; gestão vê tudo; não-gestão vê só o escopo
Execução independente:  SIM
```

### P0-4 · CI não tem gate de cobertura

```
ID:                     P0-4
Prioridade:             P0
Problema:               pytest-cov está instalado, mas não há --cov nem limiar em nenhum ponto do
                        ci.yml. Um PR que apague 500 testes passa verde.
Evidência:              .github/workflows/ci.yml — grep -c '--cov' → 0
Risco:                  ALTO — nenhuma proteção contra erosão da suíte
Correção proposta:      adicionar --cov=app --cov-report=term-missing --cov-fail-under=<baseline>
                        ao passo de pytest. Medir o baseline primeiro e travar nele, sem exigir
                        aumento imediato.
Testes necessários:     o próprio gate
Critério de aceite:     PR que remova testes reprova
Execução independente:  SIM
Autorização:            EXIGE o titular (CI/CD)
```

---

# P1 — Alto

### Segurança e custo

```
ID: P1-1 · Endpoints de IA sem rate limit nem quota
Problema:    routers/ai.py tem 14 rotas POST e apenas 3 com rate_limit. SlowAPIMiddleware NÃO é
             registrado (só o exception handler), logo não há default_limits. AI_BUDGET_ALERTA_BRL
             = 0.0 (desligado) e é alerta, não teto.
Evidência:   ai.py:55,105,383,409,451,552,672,792,834,943,970 · main.py:282-283 · config.py:686
Risco:       conta staff comprometida (inclusive estagiário, admitido em ai.py:559) roda laço
             contra /dual (2 inferências por request) e queima o orçamento; sob worker único,
             satura o event loop.
Correção:    Depends(rate_limit("<nome>", N)) nas rotas caras + AI_BUDGET_ALERTA_BRL como teto
             rígido por período.
Aceite:      11 rotas com limite; teste de que a 21ª chamada em 60s recebe 429.

ID: P1-2 · victory_vault e document-templates/generate sem RBAC
Evidência:   victory_vault_router.py:8,11,19 · peca_geracao_router.py:28-30 (contraste:
             kit_documental.py:58 e cases.py:698-704 exigem)
Risco:       secretaria/estagiário grava no cofre institucional e gera documento jurídico.
Correção:    aplicar _req_advogado_kit (ou equivalente) + rate limit + audit log.

ID: P1-3 · AI_ENABLED não é aplicado no gateway
Evidência:   ai_gateway.py:291 (chat) e :903 (executar_tarefa_ia) sem checagem; routers provas,
             teses, jurisprudencia_interna, prompts_juridicos, ia_saude com grep AI_ENABLED = 0
Risco:       o kill-switch de IA não desliga a IA.
Correção:    mover o gate para dentro de chat()/executar_tarefa_ia()/chat_agentico().
Autorização: EXIGE o titular — muda comportamento de endpoints hoje funcionais.

ID: P1-4 · /prompts protegido só no frontend
Evidência:   moduleRegistry restringe a ROLES.juridico; prompts_juridicos.py:113-118 exige apenas
             >= estagiario, e financeiro(4) > estagiario(3) em security.py:27-37
Correção:    alinhar o backend à matriz do registry.

ID: P1-5 · case_partes.cpf_cnpj em texto puro
Evidência:   models/case_parte.py:20 — String(18) sem cifra, enquanto clients.cpf foi dropado em
             claro pela migration 112. case_partes tem client_id FK (:27): o mesmo CPF cifrado em
             clients está legível ao lado.
Correção:    migration espelhando o padrão da 061 (cpf_enc Fernet + cpf_hash HMAC) + backfill.
Autorização: EXIGE o titular (migration).

ID: P1-6 · Anonimização LGPD art. 17 incompleta
Evidência:   services/client_anonimizacao.py importa apenas Client e User (:19,21) — CaseParte
             não é sequer importado. Não toca case_partes, sociedades_cliente, socios_sociedade,
             users.email/full_name, cases.descricao_fatos, audit_logs.dados_antes/depois.
Risco:       depois de "anonimizar", o CPF e o nome do titular continuam recuperáveis.
Correção:    estender a anonimização às tabelas satélite; decidir política para campos livres e
             para os snapshots do audit_log (a LGPD art. 37 e o art. 17 colidem aqui — é decisão
             jurídica do titular, não técnica).

ID: P1-7 · Superadmin homolog.qa legado em produção  [OPERACIONAL, não código]
Evidência:   grep -rn "homolog.qa" em .py/.json/.ts → ZERO. Nenhum runner cria usuário. O
             marcador HOMOLOG-FICTICIO vem de qa/homologacao/run_homologacao.py:177, não de
             qa/e2e/run_fictitious_smoke.py como diz CLAUDE.md:265. Ambos abortam contra produção.
Ação:        SELECT id,email,role,is_active,last_login_at FROM users
             WHERE email LIKE '%homolog%' OR email LIKE '%qa%';
             Se existir: desativar, rebaixar e auditar audit_logs por esse user_id.
             Corrigir CLAUDE.md:265 (atribui a origem ao runner errado).
Execução:    pelo titular — regra 9 veda acesso ao banco de produção.
```

### Qualidade e cobertura

```
ID: T-P0-1 · peca_geracao_router.py sem nenhum teste
Problema:    é a rota do fluxo "caso → peça → protocolo" — o critério de lançamento declarado.
             test_motor_peca.py cobre o orquestrador, não este router.
Correção:    teste de integração com rota montada, cobrindo geração, gate de advogado (P1-2) e
             vínculo ao caso.

ID: T-P0-3 · pix.py e api_keys.py sem teste  (dinheiro e credencial)

ID: P1-8 · ramos.py — 4 519 linhas, 82 endpoints, regra jurídica com vigência no router
Evidência:   ramos.py:63-105 (TETOS_DEPOSITO_RECURSAL, art. 899 §§1º-4º CLT), uso em :1262;
             o próprio arquivo declara "ATUALIZAÇÃO ANUAL OBRIGATÓRIA" (:57-59)
Risco:       colide com a regra 5 do CLAUDE.md (fonte oficial, vigência e teste).
Correção:    extrair as tabelas legais para service com fonte, vigência datada e teste de valor.

ID: T-P1-1 · test_signatures_ownership.py é 100% inspect.getsource (3/3), sem par comportamental
Correção:    teste que EXECUTE sig.listar/sig.assinar com dois clientes distintos.

ID: T-P1-2 · Honorários/financeiro sem teste de cálculo nem de persistência
             (honorarios_calc.py, despesas.py, financeiro_consolidado.py)

ID: P1-9 · Citation gate não roda na geração de peça
Evidência:   routers/peca_geracao*.py sem citation_gate; aplicar_gate_hitl só em ai.py:216,
             ia_defensiva.py:163, legal_docs.py:794
Decisão:     é por desenho (peça nasce rascunho). O titular decide se o gate deve morder também
             na geração — hoje quem consumir a peça fora do fluxo HITL não passa pelo gate.

ID: P1-10 · Sem embeddings, o RAG vira ILIKE sem alarme
Evidência:   ai_service.py:343-353 (warning único por processo), :415-450 (fallback)
Correção:    heartbeat que afere RESULTADO (a busca semântica está ativa?), não execução.
             Casa com a armadilha conhecida "monitoramento afere execução, não resultado".

ID: A4.5 · Bypass do guarda de comandos por aspas
Evidência:   comprovado nesta auditoria: `rm -rf /home/user/ejc/backend` → DENY;
             `bash -c "rm -rf …"` → passa; `ssh vps "rm -rf /opt/ejc"` → passa
Correção:    aplicar os padrões destrutivos também ao conteúdo entre aspas quando o comando
             externo for bash -c, sh -c, ssh ou eval.
```

---

# P2 — Médio

| ID | Achado | Referência |
|---|---|---|
| P2-1 | 41 `.catch(() => {})` — falha indistinguível de "sem dados" (6 abas de `CasoDetalhe`) | `09` §5 |
| P2-2 | `DashboardModern`/`PortalDashboard`: `allSettled` sem sinalizar widget que falhou | `09` §5 |
| P2-3 | Peça sem `case_id` acessível/editável/apagável por qualquer staff | `12` §3.2 |
| P2-4 | Access token sobrevive à troca de senha (janela de 2 h) | `12` §2.2 |
| P2-5 | PII em logs; `log_sanitizer` existe e não está ligado ao `logging` | `12` §7.3 |
| P2-6 | SSRF por DNS rebinding em `document_url_import_service` (o padrão correto já existe em `rag_public`) | `12` §5.1 |
| P2-7 | `audit_logs` sem WORM real (reserva `127` revogada) | `07` §5.3 |
| P2-8 | 27 FKs/lookups sem índice; `processes.numero_cnj` sem UNIQUE | `07` §3 |
| P2-9 | 11 colunas `*_id` sem FK (destaque: comprovante de protocolo) | `07` §3.2 |
| P2-10 | Migrations 040-043 inexistentes — paridade prod × fresh não verificável | `07` §1.2 |
| P2-11 | `skill_pipeline` declarativo: 16 de 17 handlers nunca invocados | `05` §B2 |
| P2-12 | `SkillRouter` é segundo classificador concorrente ao `intent_classifier` | `04` B5.6 |
| P2-13 | 17 skills duplicadas em `~/.claude/skills/`; as 4 "playbook" divergem e a global prevalece | `05` §A3 |
| P2-14 | 5 fachadas em `/ai`; `bank_analysis` vs `analise_bancaria` sem `deprecated` | `08` §7.1 |
| P2-15 | `_is_publica` libera qualquer path fora de `/api/` | `08` §6.1 |
| P2-16 | 95 endpoints com SQL cru + 555 `select()` em routers | `08` §7.4 |
| P2-17 | `entrada_universal.processar` — 6 commits, lote parcialmente gravável | `08` §7.5 |
| P2-18 | `/produtividade` sem `roles` no registry vs sócio+ no backend | `09` §6 |
| P2-19 | 6 call sites do RAG sem `scope_client_id` — perda de recall (não vazamento) | `06` §5 |
| P2-20 | `gemma3:9b` provavelmente inexistente — degradação de soberania sem alarme | `06` §6 |
| P2-21 | Zero retries no gateway; 429/529 vira fallback lateral | `06` §1 |
| P2-22 | `validar_sem_pii` omite CARTAO e CHAVE_PIX; nome próprio só com `entidades` | `06` §2 |
| P2-23 | Instalação de `graphifyy` sem pin nem checksum no `SessionStart` | `05` §A4.6 |
| P2-24 | Skills com `DROP DATABASE` e caminhos `/opt/ejc` (contra a regra 9) | `05` §A4 |
| P2-25 | Chave DataJud hardcoded em `integrador-apis-externas-ejc/SKILL.md:35` | `05` §A4 |
| P2-26 | 12 agentes de ramo sem skill nativa; prompts duplicados; `RAGResearchAgent` sem prompt próprio | `04` B5 |
| P2-27 | 8 agentes só com cobertura estrutural | `04` B5.5 |
| P2-28 | `--maxfail=25` trunca diagnóstico; `npm audit` ignora `high`; ruff só em `app/` | `14` §4 |
| P2-29 | 5 routers registrados por side-effect | `08` §1 |
| P2-30 | Zero tenant, responsáveis nullable, sem RLS — autorização 100 % em Python | `07` §4 |

# P3 — Baixo

Higiene e documentação. Destaques: **corrigir o `CLAUDE.md`** nos 12 pontos divergentes
(`01-arquitetura-atual.md` §4) — em especial "163 routers", "ruff/pip-audit informativos", o job
`eval-smoke` ausente, a origem do `homolog.qa` e o grafo "versionado"; remover `teses_v4` e
`data_room_v4` (já `deprecated=True` e delegando); 4 rotas `/legado/*` sem link; aba `ia_cliente`
inalcançável; `MIGRATION_RESERVATIONS.md:5` com head desatualizado; `_modelos_cache` do Ollama
nunca invalidado; `ai_cost.py` sem modelos novos; `require_roles()` hierárquico como footgun;
`X-Frame-Options` conflitante; leitura de dado sigiloso sem trilha; upload lido inteiro em
memória; sem antivírus; `/victory_vault` em snake_case; documentar venv limpo para `http-ece`.

---

## Riscos aceitos — não corrigir

| Item | Justificativa |
|---|---|
| **2FA desligado por default** | Decisão permanente do titular, vigente desde 2026-07-26 e reafirmada em 27/07 (`docs/GOVERNANCA_IA.md:254`): *"registre como risco aceito pelo titular, não como achado a corrigir"*. **Não alterar `two_factor_policy.py`.** |
| Isolamento do RAG por cliente e não por advogado | Coerente com escritório pequeno — mas é decisão consciente a registrar |
| Branch legado das migrations `101` | Já na allowlist da guarda; caso novo reprova |

## Decisões que exigem o titular

1. **P0-1** — remover `/v1` dos 8 routers é mudança de contrato público de API.
2. **P0-4** — alterar o CI.
3. **P1-3** — `AI_ENABLED` como kill-switch real muda comportamento de endpoints funcionais.
4. **P1-5/P1-6** — migration de cifra em `case_partes` e política de anonimização (colisão art. 17
   × art. 37 é decisão jurídica).
5. **P1-7** — verificação e desativação da conta `homolog.qa` no banco de produção.
6. **P1-9** — o citation gate deve rodar também na geração de peça?
7. **Produto** — 393 endpoints (48 %) sem tela: expor, arquivar ou remover, módulo a módulo, com
   `route_usage_metrics` como critério.

## Verificações que exigem ambiente de homologação

Não puderam ser feitas nesta auditoria e **não são achados** — são lacunas de verificação:

- executar o fluxo jurídico completo até o protocolo;
- os 161 testes DB-level;
- testes adversariais dos 37 agentes (entrada contraditória, RAG indisponível, prompt injection,
  tentativa de acesso a outro caso);
- `SELECT rag_status, count(*) FROM knowledge_docs GROUP BY 1` — se o acervo não estiver curado,
  `RAG_EXIGIR_APROVADO=true` faz o RAG retornar vazio e **nenhuma peça chega ao protocolo**;
- se `gemma3:9b` existe no registry Ollama do VPS;
- se `RATE_LIMIT_REDIS_ENABLED` e a contagem de workers uvicorn são coerentes (com >1 worker, o
  anti-brute-force de `security_service.py:33`, que não tem backend Redis, vira 5×N tentativas);
- se o `nginx/ejc.conf` versionado corresponde ao instalado em produção.
