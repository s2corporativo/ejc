# Relatório de Avaliação de Viabilidade Real — EJC v3

**Data:** 2026-07-22
**Ótica:** advogado detalhista que quer um sistema operacional moderno, preciso, coerente, confiável e simples — com um núcleo de IA que trabalhe como jurista especializado e entregue proposta confiável "a ponto de o advogado só revisar para protocolar".
**Método:** 6 avaliações ao vivo, em paralelo, com teste real (não leitura de relatórios antigos) — suíte de testes executada, stack subida e navegada no browser, Postgres+pgvector real para migrations, auditoria de segurança dos 167 routers, viabilidade do núcleo de IA no código, e coerência das 80 páginas de frontend. Cada achado cita `arquivo:linha`.

---

## 1. Veredito executivo

**O EJC é um sistema real, maduro e viável como plataforma de gestão jurídica — com um núcleo de IA que hoje é um EXCELENTE ASSISTENTE DE MINUTA sob governança HITL genuína, mas que NÃO entrega, hoje, a promessa "a IA resolve e o advogado só revisa para protocolar".**

O gap não é de segurança, de estabilidade nem de modelo (produção usa Claude Opus 4.8). É de **cobertura de conhecimento jurídico e de verificação semântica de citações**. O próprio sistema é honestamente desenhado para **impedir** o carimbo automático — o que é a postura ética correta, mas confirma que a revisão do advogado ainda é **trabalho jurídico substantivo**, não conferência.

| Dimensão | Veredito | Sinal decisivo |
|---|---|---|
| Saúde do código | 🟢 **Saudável** | 3.213 testes backend passam (0 falhas), 186 frontend, `ruff` limpo, build OK |
| Funciona ao vivo | 🟢 **Sim** | 7/7 fluxos ponta a ponta, 476× HTTP 200, **0 erros 5xx** |
| Segurança | 🟢 **Sólida** (1 ressalva comportamental) | PII cifrada exemplar, JWT maduro; 2FA **ainda obrigatório** |
| Banco / migrations | 🟢 **Confiável** (ressalvas) | `upgrade head` limpo; drift ORM↔banco sem rede de CI |
| Frontend / UX | 🟡 **Coerente, mas inchado** | 17/17 testes de rota; poda feita ocultando, não removendo |
| **Núcleo de IA** | 🟠 **PARCIAL → aspiracional no que mais importa** | **base jurisprudencial vazia; citação verificada só por formato** |

**Resposta direta à pergunta central:** hoje, **não**. O EJC entrega um primeiro rascunho formalmente correto, ancorado nos fatos/provas reais do caso e na **lei seca**, com anti-alucinação e HITL de verdade. Mas **a jurisprudência não sai pronta** (a base está vazia e o próprio gate de protocolo bloqueia citações não validadas), e a "verificação" de citação confirma que o número existe, **não** que ele sustenta a tese. O caminho técnico para chegar ao "revisar-e-protocolar" está mapeado no próprio código — mas exige popular a base jurisprudencial validada e fechar a verificação semântica.

---

## 2. Resultados por dimensão

### 2.1 Saúde do código — 🟢 saudável (medido, não presumido)

- **Backend:** `3213 passed, 0 failed, 0 erros de coleta, 114 skipped` (os skips são a camada de banco `*_dblevel.py`, gated por `RUN_DB_TESTS`, por design). `ruff check app` → **limpo**.
- **Frontend:** typecheck (`tsc --noEmit`) verde, **186 testes** (vitest) passam, `vite build` gera bundle, `npm ci` sem vulnerabilidades.
- **Ressalva de ambiente (não de código):** `pip install -r requirements.txt` **não completa** num Debian limpo por `http-ece`/`pywebpush` + pacotes de sistema sem RECORD; exige `SETUPTOOLS_USE_DISTUTILS=stdlib` + venv isolado. É fragilidade de **empacotamento**, mas atrapalha onboarding/CI e merece correção.

> Isto refuta favoravelmente o ceticismo inicial: os relatórios internos alegavam números altos "com o CI offline"; a suíte, rodada de forma independente agora, **passa integralmente**.

### 2.2 Funciona ao vivo — 🟢 sim, ponta a ponta

Stack subida sem Docker (montei Postgres 16 + pgvector 0.6.0 à mão) — `alembic upgrade head` (112 migrations, 132 tabelas), seed do admin, uvicorn + Vite. **476 respostas 200, zero 5xx, zero tracebacks Python.**

| Fluxo | Status |
|---|---|
| Login → troca de senha forçada → dashboard | ✅ |
| Cliente criar/listar (PII cifrada round-trip) | ✅ (autofill CEP dá 404 — cosmético) |
| Caso (NovoCasoWizard) → **gera procuração + contrato automáticos** como rascunho `human_reviewed=false` | ✅ |
| Prazo/agenda (bucketing "≤7d" correto) | ✅ |
| Peça / IA | 🟡 UI completa, **degrada graciosamente** (IA off → sem crash); geração real precisa de provedor |
| Financeiro/Honorários (consolidado, KPIs, Estimador OAB) | ✅ |
| Portal do cliente (isolamento em 3 vias, zero vazamento staff) | ✅ |

**Armadilha crítica de go-live:** `ADMIN_EMAIL` com domínio reservado (`.local`) faz o login retornar **422** (`EmailStr` rejeita `.local`) → **o admin fica travado** apesar de o sistema subir. `auth.py::login` (~L167).

### 2.3 Segurança — 🟢 sólida e madura (1 ressalva comportamental decisiva)

**Esclarecimento importante:** o **2FA NÃO está desativado**. Continua **obrigatório** para `superadmin/admin/socio` (`config.py:49` `REQUIRE_2FA_ROLES`, fail-secure sem `.env`; enforcement em `auth.py:271` + `auth_middleware.py:111-129`). O commit recente **só adicionou um workflow de CI** (`temporary-disable-2fa-remediation.yml`) que *gera* o patch de desativação — **e ele não foi mesclado** (a branch nem existe no origin).

**Muito bem-feito (crédito devido):** guardas de boot fail-closed (aborta com `SECRET_KEY` fraca, CORS `*`, chaves PII ausentes); JWT HS256 com JTI revogável, rotação com detecção de replay (OAuth BCP) e cookie httpOnly; **PII cifrada em repouso exemplar** (Fernet + HMAC índice cego, colunas em claro removidas na migration 112); **barreira LGPD da IA não-contornável** (provider externo só recebe conteúdo pseudonimizado; PII residual pula o provider; `LOCAL_COMPLETO` nunca sai do VPS); uploads validados por magic bytes (sem path traversal); superfícies "públicas" na verdade autenticadas por API key/capability token.

**Achados a endereçar:**
- 🔴 **Latente (ALTO):** se o kill switch de 2FA for ativado como está, ele nasce **fail-open** e **contorna até o TOTP de quem já cadastrou** — senha vazada bastaria para acesso pleno. **Não ativar antes do go-live.**
- 🟠 **M-2 caso órfão:** `ownership.py:64-65` libera sub-recursos de caso sem responsável a **qualquer usuário interno** (estagiário/secretaria leem/gravam documentos "normais" de casos não atribuídos).
- 🟠 **M-3:** `advogado`/`advogado_auxiliar` **não** são obrigados a 2FA por padrão, apesar de acessarem dossiês sigilosos.
- 🟡 Uploads sem antivírus; lockout por IP compartilhado (NAT do escritório); workflow que enfraquece auth vivendo no repo (remover após decisão).

### 2.4 Banco / migrations — 🟢 confiável com ressalvas gerenciáveis

Testado em Postgres 16 + pgvector real: **cadeia íntegra (1 head, 1 base, 107 revisions, branch reconciliado por merge)**; `alembic upgrade head` **aplica limpo do zero** (131 tabelas, 404 índices); embeddings na dimensão certa (`vector(1024)`, e5-large); migração destrutiva de PII (112) **exemplar** (backfill antes do drop, keyset, sem perda de dados); índices dos caminhos quentes cobertos (HMAC cego, FTS português, trgm, HNSW 1024).

**Ressalvas:** (1) **downgrade profundo trava** nas migrations 032/033 por `try/except: pass` em DDL (sem risco de dados, mas quebra "downgrade funcional" → usar `DROP ... IF EXISTS`); (2) **drift ORM↔banco significativo** — um `autogenerate` cego dropariam 13 colunas **vivas** e removeria a unicidade de `ix_users_email`; a guarda `include_name` protege **tabelas, não colunas**, e a Camada 2 de `test_schema_sync.py` está **desligada no CI**; (3) débito da coluna `embedding_legacy_768` + índice HNSW não usados.

### 2.5 Frontend / rotas / UX — 🟡 coerente, mas inchado

**17/17 testes de integridade de rota** passam, typecheck verde. O **fluxo central do advogado** mapeia 1:1 as 9 rotas essenciais; `NovoCasoWizard` completo; RBAC separa staff/cliente de forma limpa (nenhuma rota staff alcançável por `cliente_externo`).

**Atenção:** (1) **1 órfão real** — `NotasFiscais.tsx` é código morto e o redirect `/nfse → /financeiro?tab=nfse` cai numa **aba inexistente** (NFS-e some em silêncio); o teste de rota não pega porque ignora o `?tab=`; (2) **cluster "Conhecimento" com 7 superfícies** sobrepostas; (3) `CasoDetalhe.tsx` com **4.293 linhas**; (4) **a poda do menu foi feita ocultando (30 rotas ocultas), não removendo** — o usuário vê algo enxuto, mas a manutenção herda ~77 mil linhas de TSX; (5) 403 de permissão sem tratamento global em `api.ts` → UX inconsistente ao esbarrar em RBAC.

---

## 3. A pergunta central: "a IA resolve e o advogado só revisa e protocola?"

**Hoje: PARCIAL, tendendo a aspiracional no ponto juridicamente decisivo.**

### O que a IA REALMENTE entrega (com evidência)
- **Gateway central disciplinado** (`ai_gateway.py`): nenhuma tela chama modelo direto; roteamento por tarefa, fallback, kill-switch de soberania e **barreira LGPD** antes de qualquer provedor externo. Toda saída nasce `is_rascunho=True, requer_revisao=True`.
- **Peça = LLM + RAG-grounded, não template-fill** (`peca_service.py:772`): 7 etapas com estrutura processual correta por tipo (CPC art. 319, contestação arts. 335-342…), ancorada às **provas reais do caso** ("não invente documentos"), com prompts FIRAC nos níveis altos.
- **HITL genuíno e com gates duros** (`legal_docs.py`): para virar `aprovada/final/protocolada` exige score ≥ 75, **bloqueio de protocolo** se houver citação jurisprudencial não validada, e citation gate com override auditado. **Não há caminho de auto-aprovação por IA.**
- **Verificador de citação estruturalmente robusto** (`verificador_jurisprudencia.py`): valida dígito verificador CNJ (módulo 97/ISO 7064) e faixa de súmulas — pega **número inventado** e **súmula fora de faixa**.

### Onde ela PARA (o gap real)
1. **A base jurisprudencial nasce vazia.** Os ingestores STJ/TJMG/DJEN/LexML vêm **todos desligados** (`base_juridica_seed.py:53-59`). Consequência dupla: a etapa "baseado exclusivamente no RAG" não tem precedentes reais, e o gate `_bloquear_jurisprudencia_nao_validada` **bloqueia qualquer peça que cite julgado** — logo a peça **não sai com jurisprudência pronta**. Essa é justamente a parte intelectualmente mais cara.
2. **A "verificação" confere existência, não sentido.** `_existe_sumula`/`_existe_artigo` confirmam que "Súmula 7 do STJ existe" e "Art. 186 do CC existe" — **não** que sustentem a tese. Citação real porém impertinente **passa** no gate.
3. **A base de conhecimento (`bíblia_ejc`) é 100% FICTÍCIA por design** (~398 registros; README: "Todo o material é FICTÍCIO"; `ficticio=true`). É usada só como **esqueleto estrutural** (excluída da fundamentação) — ótimo para estilo/estrutura, **nulo como autoridade jurídica**.
4. **`score_juridico` e `indice_risco` estão vazios** (só `__init__.py`); o score que libera o protocolo é **heurística por regex**, não jurimetria de desfechos reais.
5. **Dependência de provedor externo pago:** produção roda `anthropic,maritaca,groq,ollama` com `OLLAMA_ENABLED=false`; **sem `ANTHROPIC_API_KEY`, o núcleo de IA fica indisponível** (degrada, mas não produz). PII sai do VPS **pseudonimizada**, não "nunca sai".

### Riscos jurídicos do uso atual
- **Falsa sensação de fundamentação:** a lei seca É recuperada, a jurisprudência NÃO → a peça pode parecer completa e ser rasa.
- **Citação existente porém impertinente** passa no gate — a pertinência é 100% humana.
- **Modo estrito desligado** (`CITACOES_MODO_ESTRITO=False`) porque, com base incompleta, ligá-lo bloquearia citações reais ainda não ingeridas — ou seja, o gate opera na configuração mais permissiva.

---

## 4. Pontos críticos de atenção (priorizados)

### P0 — decisivos / antes do go-live
1. **Alinhar a expectativa da IA à realidade.** Comunicar (produto + UI) que a entrega é "estrutura + lei; **jurisprudência, pertinência e tese a cargo do advogado**". Sem isso, o risco é o advogado subestimar a revisão.
2. **NÃO ativar o kill switch de 2FA** como está (fail-open + contorna TOTP já cadastrado). Manter 2FA ligado.
3. **Corrigir a validação de `ADMIN_EMAIL`** no seed/config (rejeitar domínio reservado no cadastro, não no login) para não travar o admin com 422.

### P1 — confiabilidade / hardening
4. **Endurecer o gate de caso órfão** (`ownership.py:64`) → limitar a `is_gestao`/estado de triagem.
5. **Incluir `advogado,advogado_auxiliar` em `REQUIRE_2FA_ROLES`.**
6. **Popular jurisprudência real e validada** (STJ/TJMG/LexML/DJEN com `fonte_validada=true`) — maior alavanca isolada para o "revisar-e-protocolar".
7. **Verificação semântica de pertinência** de citação (recuperar inteiro teor e checar se sustenta a tese).
8. **Banco:** tornar downgrades 032/033 idempotentes (`IF EXISTS`) e **ligar a Camada 2 de `test_schema_sync.py` no CI** (imagem `pgvector/pgvector:pg16`) + alinhar `ix_users_email` unique, `clients.numero(20)`, nullability.
9. **Corrigir `/nfse`** (aba inexistente) e o órfão `NotasFiscais.tsx`; endurecer o teste de rota para validar `?tab=`.
10. **Empacotamento:** resolver `http-ece`/`pywebpush` para `pip install` reprodutível.

### P2 — qualidade / simplicidade / dívida técnica
11. Consolidar o cluster "Conhecimento" (7 → 1); quebrar `CasoDetalhe.tsx`; converter rotas ocultas em **remoção real**, não ocultação.
12. Interceptor global de 403 em `api.ts` (UX coerente de permissão).
13. Limpar coluna/índice `embedding_legacy_768` após validar a reindexação 1024.
14. Antivírus em uploads; teto de lockout por IP compartilhado; **remover o workflow que desliga 2FA** após a decisão.
15. Substituir o "score" heurístico por rubrica auditável por seção; deixar claro na UI que é controle de qualidade **formal**, não predição de êxito.

---

## 5. Melhores alternativas — roteiro para o "revisar-e-protocolar confiável"

O sistema já tem a arquitetura (núcleo único, reranker, harness `app/eval/`, agente tool-use). O que falta é **conhecimento e verificação**, nesta ordem (ciclo *eval-driven*, uma variável por vez, sempre medindo com o gold set):

1. **Base jurisprudencial validada** (destrava a etapa 4 e o gate de protocolo).
2. **Verificação semântica de citação** (fecha o buraco "número existe, sentido errado").
3. **Ampliar súmulas + trazer temas repetitivos/doutrina**; garantir seed de legislação no boot (hoje só no deploy).
4. **Postura de provedor explícita:** assumir Anthropic (documentar custo/DPA/LGPD art. 33) **ou** investir no stack `ia-local` com modelos maiores — e sinalizar ao advogado quando a minuta veio de modelo local (qualidade distinta).
5. **Rubrica de qualidade auditável** no lugar do score heurístico.
6. **Ops:** capturar o caminho de subida local como skill de projeto (hoje inexistente); corrigir empacotamento; endurecer validações de seed.

---

## 6. Conclusão de viabilidade

**O EJC é viável e está em bom estado real** como sistema operacional jurídico moderno: sobe limpo, é testado (3.213+186 testes verdes), seguro (PII cifrada, JWT maduro, LGPD na IA, 2FA ligado), com banco confiável e um fluxo central do advogado que funciona ponta a ponta com governança HITL visível em toda parte. **Não é protótipo — é produto.**

A ressalva é precisa e honesta: **o sonho específico — "a IA resolve o caso e eu só reviso para protocolar" — não se realiza hoje**, e não por imaturidade de engenharia, mas porque **falta a base jurídica real e a verificação semântica** que tornariam a proposta confiável o suficiente para dispensar a pesquisa do advogado. O sistema, aliás, foi corretamente construído para **impedir** esse carimbo enquanto a fundamentação não estiver validada — postura eticamente certa (OAB/anti-alucinação) e que confirma o diagnóstico. Endereçados os P0/P1 — sobretudo popular a jurisprudência validada e fechar a verificação de pertinência — o EJC tem caminho concreto para se aproximar de verdade da promessa; até lá, é um **assistente de minuta de altíssimo nível sob revisão jurídica substantiva**, não um jurista autônomo.

---

*Avaliação somente-leitura sobre o código; nenhum comportamento de produção foi alterado. Números e fluxos verificados ao vivo em ambiente de desenvolvimento efêmero (Postgres+pgvector real, browser Chromium).*
