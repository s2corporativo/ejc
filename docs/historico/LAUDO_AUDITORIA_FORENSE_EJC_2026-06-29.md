> **Metodologia:** auditoria forense read-only conduzida por 10 auditores especializados em paralelo (38 agentes, 647 leituras de arquivo), com verificação adversarial de todos os achados de severidade alta/crítica. Nenhum arquivo foi alterado, criado, renomeado ou apagado. Os achados abaixo foram corroborados de forma independente nos pontos mais graves (credencial vazada, cadeia de migrations, prefixo de API).

**Ajustes de severidade aplicados pela verificação adversarial:**
- `langchain` órfão: alto → médio
- `requirements-ml.txt`/sentence-transformers: alto → médio
- `anthropic` ausente: alto → médio
- Cluster IA backend (7 routers): alto → médio
- Bug súmulas-seed RAG: alto → médio
- `create_all` ausente: crítico → info (by-design)

# Relatório de Auditoria Forense — Sistema EJC

## 1. Resumo Executivo

O EJC tem um **núcleo de código genuinamente bem concebido**, mas opera hoje sobre **três fundações quebradas que se sustentam apenas por inércia de produção**. A camada de segurança de aplicação é sólida (AuthMiddleware JWT global, RBAC hierárquico sem a escalada do v2, CORS por `.env`, anti-brute-force, 2FA, validação de upload por magic bytes, fail-closed em webhooks) e a arquitetura anti-alucinação da IA é madura (regras OAB explícitas, HITL onipresente, verificador de citações local). Porém a **honestidade técnica obriga a registrar**: (a) há um **vazamento de credencial root de produção** em texto puro em 5 scripts; (b) o **mecanismo de criação de schema está duplamente quebrado** — Alembic inoperante (sem `alembic.ini`/`env.py`, cadeia de migrations apontando para a revisão fantasma `048_processes`, pasta `alembic/` nem copiada para a imagem) e sem `create_all` de fallback; (c) **PII bruta de clientes vaza para a nuvem Groq (EUA) sem sanitização** em dois fluxos e o **RAG não tem qualquer isolamento por cliente/caso**, misturando peças e dossiês de clientes distintos na mesma base recuperável por qualquer usuário.

Somam-se a isso quebras funcionais sistêmicas de prefixo de API (`/api/v1/auth/*` e `/api/v1/pecas/*` inexistentes → login-refresh, logout, recuperação de senha e geração de peças retornam 404), duplicação arquitetural pesada (workspaces guarda-chuva + páginas autônomas concorrentes no frontend; 7 routers de IA, 4 de honorários, 4 superfícies de análise estratégica no backend), e dependências mortas/divergentes. O sistema "funciona em produção" porque o banco foi populado fora do versionamento e a chave Groq está configurada — **mas não é reprodutível nem auditável a partir do repositório**. O grau de contaminação é **alto, beirando o crítico em segurança/LGPD e em banco de dados**.

## 2. Grau de Contaminação do Sistema

**ALTO** (com dois subsistemas em nível CRÍTICO).

Ponderação objetiva por área (nível declarado pelos auditores):
- **Crítico (2 áreas):** Estrutura/higiene (senha root vazada) e Banco de dados (schema não reprodutível).
- **Alto (5 áreas):** Frontend-rotas, Frontend-código, IA, RAG, Dependências.
- **Médio (3 áreas):** Backend-rotas, Backend-profundidade, Segurança.

Com 7 das 10 áreas em alto ou crítico e nenhuma em baixo, o sistema não está "quase pronto": está **operacional porém frágil**. Os defeitos críticos não são de runtime cotidiano (o sistema roda), mas de **reprodutibilidade, conformidade legal (LGPD/EOAB art. 25) e contenção de segredos** — exatamente as dimensões que um escritório de advocacia não pode ter comprometidas. Por isso a classificação fecha em **ALTO**, e não médio.

## 3. Principais Riscos Encontrados

Ordenados por severidade (apenas achados confirmados):

**CRÍTICOS**
- **Senha root da VPS de produção hardcoded** em 5 scripts (`vps-tools/*.js`) — acesso total ao servidor exposto a qualquer cópia/backup/sync.
- **PII bruta de documentos do cliente enviada ao Groq (EUA) sem sanitização** (`documento_service.extrair_e_analisar` → `ai_gateway.chat`) — violação direta da LGPD.
- **RAG sem isolamento por cliente/caso** — peças e dossiês de um cliente recuperáveis por qualquer usuário em consulta de outro caso (EOAB art. 25 + LGPD).
- **Indexação automática de peças sem proteção de nomes próprios** — peça inteira com nomes identificáveis vetorizada na base global.
- **Cadeia de migrations Alembic quebrada** (revisão `048_processes` inexistente) e **Alembic totalmente inoperante** (sem `alembic.ini`/`env.py`/`script.py.mako`).
- **Refresh/logout de sessão quebrados** (`/api/v1/auth/*` não existe) — 401 desloga o usuário em vez de renovar; refresh token não revogado no logout.

**ALTOS**
- **Recuperação/redefinição de senha inoperantes** (404 em `/api/v1/auth/recuperar-senha|redefinir-senha`), com sucesso falso silencioso na recuperação.
- **Geração de peças jurídicas (feature core de IA) quebrada** (`/api/v1/pecas/gerar` → 404).
- **Documentos e peças jurídicas (`documents.py`, `legal_docs.py` GET) sem checagem de ownership por caso** — IDOR; download/listagem/export de material de casos alheios.
- **CRUD genérico de `ramos.py` lê/edita/remove casos alheios** sem ownership e vaza `_sa_instance_state`.
- **`Dockerfile` não copia `alembic`/seeds para a imagem**; **seed `seeds/seed_all.py` referenciado no deploy não existe** → deploy limpo fica sem admin/migrations.
- **Tabela `processes` consultada mas nunca criada** por ORM nem migration versionada.
- **Ausência total de testes** (backend e frontend) em sistema jurídico com cálculos sensíveis.
- **Duplicação arquitetural de IA no frontend** (workspace + rotas autônomas) com **bypass de RoleOnly** em abas (`Conhecimento`, `DashboardIA`).

**MÉDIOS** (resumo): IA-especializada e gateway sem sanitização/base anti-alucinação em todas as tarefas; prompts duplicados em ~20 lugares; duas arquiteturas de IA paralelas; bug que impede ingestão das súmulas-seed no RAG; LangChain/fastembed/sentence-transformers/anthropic mal alinhados no `requirements.txt`; `.venv-codex` (522MB) versionado; tokens JWT em localStorage; spoof de X-Forwarded-For.

## 4. Módulos Mais Contaminados

1. **Banco de dados & migrations** (crítico) — schema não reprodutível; Alembic inoperante; cadeia quebrada; tabelas sem ORM; seed inexistente; Dockerfile incompleto.
2. **Estrutura/higiene** (crítico) — senha root vazada; `.venv-codex` 522MB; `_session_componentes_bronze`; `vps-tools/generated` (22 patches); docs `.md` contraditórios.
3. **RAG** (alto) — zero isolamento por cliente; PII textual na base global; súmulas-seed não ingeridas; taxonomia fragmentada (`peca_interna`/`precedente_interno`/`peca_escritorio`).
4. **IA jurídica** (alto) — PII à nuvem sem sanitizar; 7 routers fragmentados; prompts duplicados/divergentes em ~20 arquivos; fallback silencioso Anthropic→Groq.
5. **Frontend** (rotas + código, alto) — bug sistêmico de prefixo `/api/v1`; duplicação workspace+rota; componentes órfãos mockados que fabricam teses/súmulas.
6. **Backend-rotas** (médio) — fragmentação funcional severa (honorários×4, dossiê×3, análise estratégica×4, bancário×3), versionamento inconsistente.

## 5. Módulos Aparentemente Saudáveis

- **Camada de auth/segurança de aplicação:** `core/security.py` (RBAC hierárquico, bcrypt rounds=12), `auth_middleware.py` (JWT global), `config.py` (falha em produção sem SECRET_KEY), CORS por `.env`.
- **Registro de rotas:** 96/96 routers importados e incluídos exatamente uma vez; **zero colisão exata (método+path)**; zero router órfão de registro.
- **Anti-alucinação base:** `system_prompts/base.py` (16 regras OAB), `citation_check.py` (verificador local), AVISO_RASCUNHO/HITL em todos os retornos, `legal_docs.py` bloqueia avanço de peça IA sem revisão humana.
- **Frontend coeso:** Tailwind puro + `@layer`, sem libs de UI duplicadas; `package-lock` v3 com React único; uso amplo e correto de `lib/api` (77 arquivos); `Markdown.tsx` seguro (sem `dangerouslySetInnerHTML`).
- **Infra Docker:** `docker-compose.yml` (Postgres sem porta exposta, healthchecks, volumes nomeados); `scripts/deploy_vps_safe.sh` (backup+rollback+health check); `backup.sh`/`restore.sh`.
- **Modelos núcleo:** `User`/`Case` com PK UUID, FKs explícitas, unique/index, soft-delete.
- **Pipeline RAG (mecânica):** pgvector Vector(768) coerente com e5-base; protocolo E5 (query:/passage:); ingestão idempotente por hash; soft-delete respeitado.

## 6. Arquivos Duplicados

| Duplicação | Situação |
|---|---|
| `pages/Login.tsx` vs `pages/LoginModern.tsx` | Login.tsx é órfão (App usa LoginModern) |
| `components/EscritaAssistida.tsx` (mock) vs `AssistedWritingMode.tsx` (real) | EscritaAssistida fabrica tese/peça falsa |
| `frontend/Dockerfile` vs `Dockerfile.bak` | Diferem só na linha de cache-busting do sw.js |
| `frontend/public/sw.js` vs `sw.js.bak` | .bak sem limpeza de cache |
| `ejc_frontend_current.tgz` (raiz) | Snapshot duplicado de `frontend/src` |
| `_session_componentes_bronze/RichText.tsx` vs `components/Markdown.tsx` | Mesma finalidade |
| Honorários: `fees.py` / `honorarios_calc.py` / `honorarios_oab.py` / `exito_rateio.py` | 4 prefixos para o mesmo domínio |
| Dossiê: `ai.py` `/ai/dossie` / `dossie_estrategico.py` / `dossie_cliente.py` | 3 superfícies |
| Análise estratégica: `cases.py /analisar` / `ai.py /caso/{id}/estrategia` / `ai.py /analisar-caso` / `dossie_estrategico.py /gerar` | 4 endpoints concorrentes |
| Prompts: `ai_service.py SYSTEM_*` vs `system_prompts/*` vs inline em `ai.py`/`ia_extra.py` | Regras OAB reescritas em ~20 lugares |
| `python-jose` vs `PyJWT` / `passlib` vs `bcrypt` / `fastembed` vs `sentence-transformers` | Duas libs para o mesmo fim |
| Chunking: `ingestion_service.chunk_texto` vs `rag.py _chunk_texto` | Algoritmos divergentes |

## 7. Arquivos Órfãos

**Frontend:** `pages/Login.tsx`; `components/DashboardModernLuxury.tsx`, `MarketIntelligencePanel.tsx`, `EscritaAssistida.tsx`, `RadarLegislativo.tsx`, `RadaresEspecializados.tsx`, `PortalClientePlatinum.tsx`, `WhatsAppChatbot.tsx`, `FocusToday.tsx`; `styles/theme-bronze-elegance.css`, `styles/visual-law-premium.css`; imports lazy mortos em `App.tsx` (Documentos, FinanceiroDashboard, DataRoom); `pages/Agenda.tsx` (sem menu/link).

**Backend:** `services/_logo_b64.py` (sem importador); súmulas-seed nunca chegam ao `knowledge_chunks` (bug de assinatura); docs via `case_intel` presos em `status_indexacao='pendente'`; categoria `peca_interna` sem busca dedicada; routing Ollama inativo (`OLLAMA_ENABLED=False`); `anthropic_provider` ausente de `providers/__init__.py __all__`; tabelas `pricing_rules`/`inadimplencia_alerts`/`case_ambiental`/`due_diligence_templates`/`document_access_log` só em SQL bruto.

**Estrutura:** `_session_componentes_bronze/`; `frontend/src/{pages,components,stores,lib,types}` (brace-expansion literal); `deploy/` (vazia); `vps-tools/generated/` (22 patches); `backend/.venv-codex` (522MB); `requirements-ml.txt` referenciado mas inexistente.

## 8. Rotas Quebradas (frontend)

- **`/whatsapp`** → `<Navigate to="/">`: botão "WhatsApp" no CRM joga o usuário para a Dashboard (UX quebrada).
- **Navegação morta `/agenda`**: roteada mas sem menu nem link interno; o menu "Agenda" aponta na verdade para `/atividades` (CentralAtividades).
- **Páginas só por URL direta** (sem menu/link): `/office-contracts`, `/partner-withdrawals`, `/knowledge-hub`, `/despesas-recorrentes`, `/prompts`, `/suspensoes`, `/ajuda`, `/conteudo-juridico`, `/ia-saude`.
- **Não são links quebrados**, mas **bypass de RoleOnly**: abas `conhecimento`/`saude` dentro de `/inteligencia` expõem componentes a roles não autorizados na rota autônoma equivalente.

> Observação: nenhum import lazy em `App.tsx` aponta para arquivo inexistente; todos os 38 itens de menu resolvem para rotas registradas. O problema é duplicação/acesso, não link morto.

## 9. Endpoints Quebrados / Não Registrados (backend)

O problema **não é registro** (96/96 routers ativos, zero shadowing). São **chamadas do frontend a prefixos inexistentes** e **uma tabela sem criação**:

- `POST /api/v1/auth/refresh` e `/api/v1/auth/logout` (real: `/api/auth/*`) → **404**; sessão cai, refresh não revogado.
- `POST /api/v1/auth/recuperar-senha` e `/api/v1/auth/redefinir-senha` (real: `/api/auth/*`) → **404**; reset de senha inoperante.
- `POST /api/v1/pecas/gerar` (real: `/api/pecas/gerar`) → **404**; geração de peças nunca funciona.
- Tabela **`processes`** consultada em `processo_service.py:13` mas **sem model ORM e sem migration** que a crie → quebra em banco recriado.
- `task_type='redacao_peca'` em `ia_especializada.py` **não existe** em `TASK_ROUTING` → cai no default sem base anti-alucinação.

## 10. Dados Mockados

Concentrados em **componentes órfãos não roteados** (risco latente se reativados):
- `EscritaAssistida.tsx` — **fabrica tese e peça hardcoded** citando "Tema 69 STF" (viola "NUNCA inventar jurisprudência").
- `RadaresEspecializados.tsx` — array fixo com **"Nova Súmula TST" inventada**.
- `RadarLegislativo.tsx` — `mockLegislacoes`/`mockAlertas`.
- `MarketIntelligencePanel.tsx` — **concorrentes fictícios** ("Advocacia Silva & Associados") com wins fabricados.
- `FocusToday.tsx` — comentário "Simulação de carregamento".

Todos referenciados apenas por `DashboardModernLuxury.tsx` (órfão). **Risco jurídico real** caso promovidos a produção sem ligação a endpoints reais.

## 11. Riscos de IA

- **[CRÍTICO]** PII bruta (CPF/CNPJ/nomes/processo/endereço) de documentos do cliente enviada ao **Groq (EUA) sem `sanitizar_pii`** em `documento_service`; sem AILog → quebra rastreabilidade HITL.
- **[ALTO]** `ia_especializada.py` envia pergunta do usuário ao gateway **sem sanitização e sem AILog** (contraria o padrão de `ai_service.py`/`ia_extra.py`).
- **[ALTO]** **Três arquiteturas de prompts** (system_prompts moderna, ai_service legada Groq-hardcoded, PromptJuridico em banco); regras OAB/anti-alucinação reescritas em ~20 arquivos — corrigir uma regra não propaga.
- **[MÉDIO]** `ai_gateway.chat` só injeta `BASE_IDENTIDADE` em 3 tarefas; demais dependem de o caller lembrar.
- **[MÉDIO]** Verificador de citações **não acoplado** aos fluxos de geração (só endpoint manual `/qualidade`).
- **[MÉDIO]** Fallback Anthropic→Groq silencioso em matéria criminal/família, sem flag de fallback no retorno.
- **[MÉDIO]** Sanitizador frágil para nomes (só com `nomes_proteger`) e datas; `validar_sem_pii` checa só 4 tipos.
- **[BAIXO]** Custo da IA zerado para todo tráfego Groq (governança financeira).
- **[MÉDIO/observação]** `anthropic` é o provider **default de ~12/14 tarefas** mas está **ausente do `requirements.txt`** → primeira tarefa cai em fallback Groq (provider Anthropic efetivamente morto).

## 12. Riscos de RAG

- **[CRÍTICO]** **Ausência total de isolamento**: `knowledge_docs`/`knowledge_chunks` sem `client_id`/`case_id`/`user_id`; `buscar_contexto_rag` e `/rag/buscar` filtram só por categoria — vazamento cruzado entre clientes.
- **[CRÍTICO]** **Indexação de peças sem `nomes_proteger`** (`case_intel.py:292`) → nomes/endereços identificáveis vetorizados na base global; `indexar_peca_rag` nem chama `validar_sem_pii`.
- **[MÉDIO]** **Súmulas-seed nunca ingeridas no `knowledge_chunks`** por bug de assinatura (`referencia_id` inexistente, `chave_origem` ausente), silenciado por `except` amplo (só `logger.debug`). Base semântica sem o corpus curado.
- **[MÉDIO]** `buscar_contexto_rag` **sem limiar mínimo de similaridade** (vs `>=0.60` em `/rag/buscar`) → "fontes" fracas de outros clientes entram como contexto.
- **[MÉDIO]** Taxonomia fragmentada (`peca_interna` não consultada por busca dedicada, só pela global) — canal de exposição.
- **[BAIXO]** Docs via `case_intel` presos em `status_indexacao='pendente'`; comentários divergentes sobre o modelo de embeddings.

## 13. Riscos de Banco de Dados

- **[CRÍTICO]** **Cadeia de migrations quebrada**: só existem 049 e 050; `049.down_revision="048_processes"` (inexistente); 001–048 ausentes → schema não versionado/reprodutível.
- **[CRÍTICO]** **Alembic inoperante**: sem `alembic.ini`, `env.py`, `script.py.mako`; `alembic upgrade head` falha antes de resolver o grafo.
- **[ALTO]** **Dockerfile não copia `alembic/` nem seeds** (`COPY app ./app` apenas) → comandos de deploy falham dentro do container.
- **[ALTO]** **`seeds/seed_all.py` não existe** mas é chamado no deploy → sem admin inicial pós-deploy limpo (sistema inacessível).
- **[ALTO]** **Tabela `processes` sem ORM/migration** → quebra de processos em banco recriado.
- **[MÉDIO]** 5 tabelas da 050 só em SQL bruto, invisíveis ao `Base.metadata` (autogenerate poderia tentar DROP).
- **[MÉDIO]** `models/__init__.py` registra só ~25/42 models → `Base.metadata` depende da ordem de imports de routers.
- **[INFO]** Ausência de `create_all` é **by-design** (Alembic é o caminho intencional) — não é defeito isolado, mas agrava o quadro porque o Alembic está quebrado.

## 14. Riscos de Segurança

- **[CRÍTICO]** **Senha root da VPS hardcoded** em `run.js:18`, `upload.js:62`, `pull-file.js:19`, `sync.js:64`, `deploy-rebrand.js:109` (credencial root + IP do servidor em texto puro — **valor redigido neste laudo**). `.dockerignore` não cobre `vps-tools/*.js`.
- **[ALTO]** **Logout/refresh não chegam ao backend** (mismatch `/api/v1/auth`) → refresh token válido por até 7 dias após logout (OWASP Session Management).
- **[ALTO]** **IDOR em `documents.py`/`legal_docs.py`/`ramos.py`**: leitura/download/export/edição de casos alheios apenas com gate de perfil, sem `verificar_acesso_caso`.
- **[MÉDIO]** **Spoof de X-Forwarded-For** (`obter_ip_real` confia no 1º IP) → contorna anti-brute-force e throttle de reset por IP.
- **[MÉDIO]** **JWT (access+refresh) em localStorage** → exfiltração via XSS; sem CSP verificada no repo.
- **[BAIXO]** Container backend **roda como root** (sem `USER`).
- **[BAIXO]** Logs de acesso ao cofre (`/cofre/documentos/{id}/logs`) sem gate de socio+.
- **[BAIXO]** `ejc_frontend_current.tgz` não coberto por `*.tgz` no `.dockerignore` (hoje sem segredos, padrão perigoso).

> Positivo: nenhuma injeção SQL explorável; segredos de app centralizados em `config.py` via env; webhooks fail-closed com `hmac.compare_digest`.

## 15. Riscos Visuais

- **Tema "bronze/dark" abandonado**: `theme-bronze-elegance.css` e `visual-law-premium.css` nunca importados, conflitam esteticamente com o tema claro real — confusão sem impacto ativo (não importados).
- **Divergência local↔produção**: `_session_componentes_bronze` foi deployado direto na VPS (`deploy-rebrand.js`) sem ficar na cópia local — **fonte de verdade visual ambígua**.
- **Handler vazio** em `CardMemoria` (Biblioteca.tsx:532) com `cursor-pointer`/`hover` → beco sem saída de UX.
- **Cache-busting do PWA frágil**: `sed s/ejc-v3/.../ sw.js` depende da string literal; `Dockerfile.bak` não tem o passo (regressão silenciosa se usado).

## 16. Riscos Operacionais

- **Deploy não reprodutível**: migrations + seed quebrados, artefatos não embarcados na imagem → impossível subir ambiente limpo a partir do repo.
- **Ausência total de testes** (backend e frontend) durante refatoração ampla (db.ts→22 módulos, routers→15 arquivos) — refatoração cega.
- **Documentação `.md` contraditória** (README diz "95 routers/49 services/migration 048"; real: 98/56/050) → decisões com base em estado falso.
- **`.venv-codex` (522MB)** e `vps-tools/generated` (22 patches) inflam workspace e poluem buscas.
- **Dependências de dev em produção** (pytest/ruff/pre-commit no `requirements.txt`); LangChain+fastembed (peso morto); `groq` pinado em 0.9.0 antigo.
- **Busca semântica desligada de fato**: `sentence-transformers` ausente do requirements e `requirements-ml.txt` inexistente (mitigado por `EMBEDDINGS_ENABLED=False` default).

## 17. O Que Pode Ser Aproveitado

A **maior parte do código** é reaproveitável:
- Toda a camada `core/` de segurança (security, auth_middleware, config, sql_safe, rate_limit).
- `cases.py` com `_filtro_visibilidade` (modelo correto de ownership a replicar nos demais).
- Pipeline anti-alucinação: `system_prompts/`, `legal_base.py`, `citation_check.py`, `sanitizer.py`, AILog/HITL.
- `ai_service.py` como **referência de pipeline correto** (sanitiza→dupla barreira→RAG→AILog).
- Frontend: `lib/api.ts`, `stores/auth.ts`, `useTheme.ts`, `Markdown.tsx`, camada Tailwind, roteamento de ramos (`ramosConfig.ts`), portal do cliente.
- Infra: `docker-compose.yml`, `deploy_vps_safe.sh`, `backup.sh`/`restore.sh`.
- Mecânica RAG (pgvector, E5, ingestão idempotente, ingestores externos).

## 18. O Que Deve Ser Isolado

- **`vps-tools/*.js`** — após rotação da senha, isolar credenciais em env/chave SSH fora do repo.
- **`_session_componentes_bronze/`, `vps-tools/generated/`, `.venv-codex`, `ejc_frontend_current.tgz`, `*.bak`** — arquivar/remover (com confirmação dupla).
- **Componentes órfãos mockados** (DashboardModernLuxury + satélites + CSS bronze) — marcar explicitamente como protótipos fora de produção ou remover.
- **`peca_interna`/peças de clientes no RAG** — isolar do canal de busca global até haver escopo por cliente + anonimização verificada.
- **Provider Anthropic** — isolar do roteamento default até a dependência ser instalada.
- **Documentos `.md` desatualizados** — marcar como snapshots históricos; manter um único documento de estado vivo.

## 19. O Que Deve Ser Refeito

- **Subsistema Alembic completo**: criar `alembic.ini`, `env.py` (com `from app.models import *` e `target_metadata=Base.metadata`), migration inicial consolidada (`down_revision=None`) cobrindo todo o schema atual; reintroduzir `processes` e as 5 tabelas SQL-only como ORM; copiar `alembic/` no Dockerfile.
- **Esquema de isolamento do RAG**: adicionar `client_id`/`case_id`/visibilidade em `knowledge_docs` e propagar o filtro em **toda** consulta; política explícita (conhecimento público = global; peças/precedentes = restritos ou anonimizados irreversivelmente).
- **Camada de prefixo de API do frontend**: corrigir `/api/v1/auth/*` e `/api/v1/pecas/gerar`; auditar todos os `fetch` crus.
- **Ownership por caso** em `documents.py`, `legal_docs.py` (GET) e `ramos.py` (listar/atualizar/remover); serializar via Pydantic (eliminar `r.__dict__`).
- **Sanitização obrigatória no gateway** para qualquer provider de nuvem (não confiar no caller).
- **Consolidação de domínios duplicados**: IA (7→1-2 routers), honorários (4→1), dossiê (3→nomes distintos), análise estratégica (4→1 canônico), versionamento (/api vs /api/v1).
- **`seeds/seed_all.py`** idempotente (admin com `must_change_password`, feriados, súmulas) ou remoção da chamada do deploy.
- **Suíte de testes mínima** (security, cálculos, ai_gateway fallback; vitest no frontend).

## 20. Tabela Consolidada de Achados

| ID | Área | Problema | Evidência | Severidade | Risco | Recomendação |
|----|------|----------|-----------|------------|-------|--------------|
| EST-01 | Estrutura | Senha root VPS hardcoded em 5 scripts | `run.js:18`, `upload.js:62`, `pull-file.js:19`, `sync.js:64`, `deploy-rebrand.js:109` | Crítico | Acesso root total ao servidor exposto a cópia/backup/sync | Rotacionar senha; migrar p/ chave SSH; ler de env; auditar destinos |
| IA-01 | IA | PII bruta de doc do cliente ao Groq sem sanitizar | `documento_ia.py:56`→`documento_service.py:88-106`→`ai_gateway.chat` (0 sanitiz) | Crítico | Transferência internacional de PII (LGPD arts. 33-36) | `sanitizar_pii` antes do gateway; sanitização obrigatória no gateway |
| RAG-01 | RAG | RAG sem isolamento por cliente/caso | `models/rag.py:12-54` (sem case/client_id); `ai_service.py:150-160`; `rag.py:243-257` | Crítico | Vazamento cruzado entre clientes (EOAB art.25/LGPD) | Adicionar escopo client/case e filtrar em toda consulta |
| RAG-02 | RAG | Indexação de peça sem `nomes_proteger` | `case_intel.py:292` `sanitizar_pii(conteudo)` sem nomes | Crítico | Nomes/endereços identificáveis na base global | Passar `nomes_proteger`; não indexar sem revisão/anonimização |
| DB-01 | Banco | Cadeia de migrations quebrada (048 inexistente) | `versions/` só 049/050; `049:13 down_revision="048_processes"` | Crítico | Schema não versionado/reprodutível; `upgrade head` falha | Migration inicial consolidada (`down_revision=None`) |
| DB-02 | Banco | Alembic inoperante (sem ini/env.py/mako) | `find` vazio; `deploy.sh:31`, `deploy_vps_safe.sh:52` chamam upgrade | Crítico | Passo de migrations nunca funcionou | Criar `alembic.ini` + `env.py` + validar local |
| SEC-01 | Segurança | Logout/refresh não revogam sessão (`/api/v1/auth`) | `api.ts:36,58`; backend em `/api/auth` (`main.py:172`,`auth.py:28`) | Alto | Refresh token válido 7d após logout; 401 desloga | Corrigir URLs p/ `/api/auth/*`; validar revogação |
| FRT-01 | Frontend | Recuperação/redefinição de senha quebradas | `RecuperarSenha.tsx:10`, `RedefinirSenha.tsx:24` (`/api/v1/auth`) | Alto | Reset inoperante; sucesso falso na recuperação | Usar cliente `api` em `/auth/*`; remover `.catch` vazio |
| FRT-02 | Frontend | Geração de peças (IA core) 404 | `PecaGeneratorModal.tsx:173` `/api/v1/pecas/gerar`; backend `/api/pecas` | Alto | Botão de gerar peça nunca funciona | Ajustar p/ `/api/pecas/gerar`; auditar fetch crus |
| BKD-01 | Backend | `documents.py` sem ownership por caso (IDOR) | `documents.py:229,187` só `_pode_acessar_confidencial` | Alto | Download/listagem de docs de casos alheios | `verificar_acesso_caso(d.case_id)` + filtro de visibilidade |
| BKD-02 | Backend | `legal_docs.py` GET sem ownership | escritas protegidas; `:48,:103,:234` GET sem `verificar_acesso_caso` | Alto | Leitura/export de peças de casos alheios | Aplicar `verificar_acesso_caso` em detalhe/pdf/listar |
| BKD-03 | Backend | `ramos.py` CRUD lê/edita casos alheios + vaza ORM state | `_crud_listar:62-70` (`r.__dict__`), `_crud_atualizar/remover` sem `_get_case` | Alto | Exposição/alteração de casos alheios; `_sa_instance_state` no JSON | Resolver case_id e `verificar_acesso_caso`; serializar via Pydantic |
| DB-03 | Banco | Dockerfile não copia alembic/seeds | `Dockerfile:13-17` só `COPY app ./app` | Alto | Migrations/seed falham no container | `COPY alembic`/`alembic.ini`/seeds |
| DB-04 | Banco | `seeds/seed_all.py` inexistente, chamado no deploy | `deploy.sh:34-35`; arquivo não existe | Alto | Sem admin pós-deploy limpo | Criar seed idempotente ou remover chamada |
| DB-05 | Banco | Tabela `processes` sem ORM/migration | `processo_service.py:13` `FROM processes`; sem `__tablename__` | Alto | Quebra de processos em banco recriado | Reintroduzir migration + model ORM |
| DEP-01 | Dependências | Ausência total de testes | sem `test_*`/`conftest`/`vitest`; pytest instalado | Alto | Refatoração cega em sistema jurídico | Suíte mínima backend+frontend; mover dev deps |
| FRT-03 | Frontend | Duplicação IA workspace+rota com bypass RoleOnly | `InteligenciaWorkspace.tsx:11-17` vs rotas autônomas; abas sem guard | Alto | UX inconsistente + bypass de RBAC em abas | Eleger entrada única; replicar guards nas abas |
| BKD-04 | Backend | Cluster IA fragmentado (7 routers) | `ai.py`/`ia_extra.py` mesmo `/api/ai`; `ai_tools.py` `/api/v1/ai`; +4 | Médio | Manutenção confusa; risco de colisão futura | Consolidar `/api/ai` ou subdomínios explícitos |
| BKD-05 | Backend | 4 superfícies de análise estratégica | `cases.py:666`, `ai.py:549/24`, `dossie_estrategico.py:62` | Alto | HITL/log de PII divergentes (LGPD/ética) | Eleger endpoint canônico; gateway único c/ log/HITL |
| IA-02 | IA | `ia_especializada` sem sanitização/AILog | `ia_especializada.py:64-84`; sem `sanitizar_pii` | Alto | PII ao Groq sem máscara/auditoria | Sanitizar + AILog padronizado |
| IA-03 | IA | Prompts duplicados/divergentes (~20 arquivos) | `ai_service.py` SYSTEM_* vs `system_prompts/*` vs inline | Alto | Correção de regra OAB não propaga | Fonte única de prompts + base inviolável |
| DEP-02 | Dependências | LangChain+fastembed peso morto | `requirements.txt:54-58`; 0 imports | Médio | Imagem inflada; superfície CVE | Remover do requirements |
| DEP-03 | Dependências | sentence-transformers ausente; `requirements-ml.txt` inexistente | `embedding_service.py:31`; `config.py:72` | Médio | Busca semântica nunca roda no container | Criar requirements-ml real ou mover dep |
| DEP-04 | Dependências | `anthropic` ausente do requirements | `anthropic_provider.py:18`; default de ~12/14 tarefas | Médio | Provider Anthropic morto; cai em fallback Groq | Adicionar `anthropic` pinado ou remover do roteamento |
| RAG-03 | RAG | Súmulas-seed não ingeridas (bug assinatura) | `sumulas_ingestion.py:103-110` (`referencia_id`, sem `chave_origem`) | Médio | Base semântica sem corpus curado; falha silenciosa | Corrigir chamada; elevar log p/ warning |
| RAG-04 | RAG | `buscar_contexto_rag` sem limiar de similaridade | `ai_service.py:150-170` vs `rag.py:249` (`>=0.60`) | Médio | Fontes fracas de outros clientes citadas | Aplicar piso; contexto vazio se nada passar |
| SEC-02 | Segurança | Spoof de X-Forwarded-For | `security_service.py:46-52`; `nginx.conf:47` append | Médio | Contorna anti-brute-force/throttle por IP | Sobrescrever XFF no nginx host; `set_real_ip_from` |
| SEC-03 | Segurança | JWT em localStorage | `api.ts:7,38,39,57` | Médio | Exfiltração via XSS (refresh 7d) | Refresh em cookie HttpOnly+Secure; CSP estrita |
| IA-04 | IA | `BASE_IDENTIDADE` só em 3 tarefas | `legal_base.py:22`; `redacao_peca` inexistente | Médio | Respostas sem reforço anti-alucinação | Injeção padrão p/ toda tarefa de prosa |
| IA-05 | IA | Verificador de citações não acoplado | `citation_check.py:64` só via `/qualidade` | Médio | Citações alucinadas passam à revisão | Acoplar ao fim dos fluxos de geração |
| BKD-06 | Backend | 4 routers de honorários, 3 prefixos | `fees`/`honorarios-calc`/`honorarios-oab`/`v1/honorarios-exito` | Médio | Descoberta difícil; reimplementação acidental | Unificar `/api/honorarios/*` |
| DB-06 | Banco | 5 tabelas só em SQL bruto (sem ORM) | `050_novos_modulos.py`; sem `__tablename__` | Médio | Autogenerate pode propor DROP | Criar models e registrar em `__init__` |
| EST-02 | Estrutura | `.venv-codex` 522MB versionado | `backend/.venv-codex` | Médio | Workspace inflado; risco de captura por sync | Remover (confirmação dupla) |
| EST-03 | Estrutura | Docs `.md` contraditórios | README "95/49/048" vs real "98/56/050" | Baixo | Decisões com base em estado falso | Marcar históricos; manter doc vivo único |
| SEC-04 | Segurança | Container backend roda como root | `Dockerfile` sem `USER` | Baixo | Escalada em caso de RCE | Adicionar usuário não-root |
| FRT-04 | Frontend | Componentes órfãos fabricam tese/súmula | `EscritaAssistida.tsx:9-18`, `RadaresEspecializados.tsx:60-80` | Médio | Risco jurídico se reativados | Remover/marcar como protótipo |

## 21. Plano de Saneamento em Fases

**Fase 0 — Contenção imediata (segurança/segredos)** — *antes de qualquer outra coisa*
- Rotacionar a senha root da VPS; migrar `vps-tools` para chave SSH/`process.env`; remover segredo dos 5 scripts e do README; auditar para onde já foi sincronizado.
- Confirmar PII a parar de vazar: sanitização obrigatória no `ai_gateway` para qualquer provider de nuvem (corta IA-01 e IA-02 de uma vez).

**Fase 1 — Quebras funcionais visíveis (404 sistêmicos)**
- Corrigir prefixos `/api/v1/auth/*`, `/api/v1/pecas/gerar` no frontend; auditar todos os `fetch` crus.
- Restaurar logout/refresh server-side; validar revogação do refresh token.

**Fase 2 — Reprodutibilidade de banco**
- Reconstruir Alembic (`alembic.ini`, `env.py`, migration inicial consolidada); reintroduzir `processes` + 5 tabelas como ORM; `COPY alembic`/seeds no Dockerfile; criar `seed_all.py` idempotente.

**Fase 3 — Isolamento de dados (LGPD/EOAB)**
- Escopo `client_id`/`case_id` no RAG + filtro em toda consulta; política de promoção a base institucional só com anonimização verificada.
- Ownership por caso em `documents.py`, `legal_docs.py` (GET), `ramos.py`.

**Fase 4 — Consolidação arquitetural**
- Unificar domínios duplicados (IA, honorários, dossiê, análise estratégica); padronizar versionamento; fonte única de prompts.

**Fase 5 — Higiene e qualidade**
- Remover órfãos/duplicados/venv/patches; corrigir dependências; suíte de testes mínima; atualizar docs; XFF/CSP/usuário não-root; limiar de similaridade RAG; súmulas-seed.

## 22. Conclusão Obrigatória

**Decisão: OPÇÃO 2 — NÚCLEO LIMPO COM REAPROVEITAMENTO.**

**Justificativa técnica.** A opção 1 (saneamento in loco) subestima dois defeitos estruturais que não são "bugs a corrigir", mas **fundações ausentes**: o schema do banco não é reprodutível a partir do repositório (Alembic inoperante, cadeia quebrada, tabelas sem ORM/migration, seed inexistente, artefatos não embarcados) e o RAG foi construído **sem o eixo de isolamento por cliente** — algo que, num escritório de advocacia, é requisito de projeto (EOAB art. 25), não um ajuste. Tentar "consertar no lugar" essas duas frentes equivale a refazê-las de qualquer modo, com o risco adicional de carregar o passivo de duplicação arquitetural (7 routers de IA, 4 de honorários, 3 arquiteturas de prompts, workspaces concorrentes).

A opção 3 (reconstrução total) é **desproporcional e destrutiva de valor**: a camada de segurança de aplicação, o pipeline anti-alucinação, o cliente de API, a infra Docker e a mecânica RAG são **de boa qualidade e verificadamente corretos**. Jogar fora 96 routers, o RBAC hierárquico e o pipeline HITL para reescrever do zero violaria o princípio "Controle > Velocidade" e introduziria regressões onde hoje há acertos.

A opção 2 captura o melhor dos dois mundos: **promove o código saudável (Fases 1, 4 e 5) para um núcleo limpo, enquanto reconstrói deliberadamente apenas as duas fundações quebradas** — o subsistema de migrations/schema (Fase 2) e o isolamento de dados RAG/ownership (Fase 3) — sob revisão humana e com a contenção de segredos/PII feita primeiro (Fase 0). É a rota que respeita "Caixa > Crescimento" (não desperdiça o investimento já feito) e "Legalidade > Conveniência" (trata LGPD/EOAB como gate, não como ajuste opcional). O sistema atual **funciona por inércia**; o núcleo limpo o torna **reprodutível, auditável e juridicamente conforme** sem descartar o que já está certo.

Relatório completo acima. Arquivos de evidência mais críticos (caminhos absolutos): `C:\Users\User\EJC\vps-tools\run.js`, `upload.js`, `pull-file.js`, `sync.js`, `deploy-rebrand.js` (senha root); `C:\Users\User\EJC\backend\app\services\documento_service.py` e `routers\ia_especializada.py` (PII); `C:\Users\User\EJC\backend\app\models\rag.py` e `services\case_intel.py` (isolamento RAG); `C:\Users\User\EJC\backend\alembic\` (Alembic incompleto) e `backend\Dockerfile`; `C:\Users\User\EJC\frontend\src\lib\api.ts` e `components\PecaGeneratorModal.tsx` (prefixo /v1).