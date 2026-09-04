# RELATÓRIO ETAPA 3 — AUDITORIA TÉCNICA COMPLETA DO SISTEMA EJC

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`
Metodologia: 8 auditorias paralelas (subagentes read-only), apoiadas no grafo Graphify (`graphify-out/graph.json`, 4.335 nós / 422 comunidades) e leitura direta de código. Nenhuma correção foi aplicada nesta etapa.
Fontes anteriores usadas como base: `RELATORIO_ETAPA_1_SEGURANCA_E_DIAGNOSTICO.md`, `RELATORIO_ETAPA_2_GRAPHIFY_MAPEAMENTO.md`, `RELATORIO_AUDITORIA_INCREMENTAL_GRAPHIFY_EJC_2026-07-02.md`.

**Nota de honestidade:** duas frentes de auditoria (Backend e Estrutura Geral) avaliaram o mesmo achado (`ia_extra.py` não montado) com severidades diferentes (LEVE vs CRÍTICO). Neste relatório consolidado, quando isso ocorre, uso a classificação mais severa e explico o motivo — é mais seguro superestimar risco do que subestimá-lo numa etapa de auditoria.

---

## 1. FALHAS CRÍTICAS (10)

| # | Falha | Área | Arquivo(s) | Descrição |
|---|-------|------|-----------|-----------|
| C1 | Router `ia_extra.py` (e `assistente.py`) nunca montado em `main.py` | Backend/Estrutura | `backend/app/routers/ia_extra.py`, `assistente.py`, `backend/app/main.py` | Endpoints de tradução de andamento, geração de minuta e pesquisa de jurisprudência ficam 404 silencioso. O grafo mostra `ia_extra` como comunidade desconectada do caminho até `main.py`. Node `traduzir_movimento` aparece isolado no `GRAPH_REPORT.md` — indício de que pode haver dependência frontend quebrada. |
| C2 | IDOR na criação de documento | Backend | `backend/app/routers/documents.py` (endpoint de upload) | `case_id`/`client_id` não são validados contra ownership do usuário na escrita (só na leitura, via `_gate_drive_doc`). Usuário pode enviar `case_id` de caso alheio e o documento é criado lá. |
| C3 | Tabela `processes` sem modelo ORM | Banco de dados | `backend/app/routers/processes.py`, `backend/app/services/processo_service.py`, ausente em `backend/app/models/__init__.py` | Tabela criada via migration 048 e usada só via SQL cru. Sem lazy-loading, sem validação ORM, sem proteção contra drift de schema. Risco alto em disaster recovery (banco limpo + migrations não garante integração com o resto do código). |
| C4 | Drift histórico model↔banco sem validação contínua | Banco de dados | `backend/alembic/versions/038, 053, 056`, `backend/tests/test_smoke.py` | Já ocorreram 3 episódios de colunas/tabelas criadas manualmente fora do Alembic, reconciliadas retroativamente (038, 053, 056). O único teste de schema (`test_alembic_cadeia_integra`) valida só a topologia da cadeia de migrations, não compara `Base.metadata` com o banco real. Sem CI que pegue isso, o padrão tende a se repetir. |
| C5 | Isolamento do RAG por cliente/caso nunca é aplicado na prática | RAG | `backend/app/services/ai_service.py:124-128` (assinatura `scope_client_id`), 20+ chamadas em `ai_service.py`, `rag.py`, `ai.py`, `teses.py`, `ai_tools.py`, `ai_skills.py`, `peca_service.py`, `documento_service.py`, `validador_juridico_service.py`, `dossie_service.py` | A função de busca RAG tem parâmetro de isolamento por cliente, mas **nenhuma chamada real o passa** — sempre fica `None`/vazio. Resultado líquido: conteúdo privado (peças internas, precedentes) nunca vaza entre clientes (por acidente, não por design correto), mas também **nunca é recuperado para ninguém** — o RAG "seguro" está funcionalmente quebrado. É uma armadilha: se alguém corrigir só a chamada sem entender a lógica de filtro completa, pode vazar dados entre clientes de verdade. |
| C6 | CPF/CNPJ armazenados em texto puro, sem criptografia em repouso | Segurança/LGPD | `backend/app/models/client.py` (`cpf`, `cnpj`) | Nenhum mecanismo de criptografia (Fernet, pgcrypto) protege esses campos. Qualquer vazamento de acesso ao banco expõe PII diretamente. |
| C7 | Ausência total de endpoint de "direito ao esquecimento" (LGPD art. 17) | Segurança/LGPD | `backend/app/routers/clients.py` | Existem endpoints de acesso e portabilidade (relatório LGPD PDF, JSON), mas nenhum mecanismo de exclusão/anonimização a pedido do titular. |
| C8 | Página `Whatsapp.tsx` vazia, visível no menu para todos os perfis | Frontend | `frontend/src/pages/Whatsapp.tsx` | Card estático "Integração WhatsApp em desenvolvimento". Usuário clica no menu e cai numa tela morta — parece bug, não é. |
| C9 | Erros de API silenciados (`.catch(() => {})`) em múltiplas páginas | Frontend | `Casos.tsx`, `Dashboard.tsx`, entre outras | Se a chamada falha, o usuário não recebe nenhum aviso — parece que "não aconteceu nada", sem indicação de erro real. |
| C10 | Tratamento de erro inconsistente: `alert()` vs `toast.error()` vs silêncio, em 39+ páginas | Frontend | `Honorarios.tsx`, `Sociedade.tsx`, e outras | Componente `Toast.tsx` existe e é usado bem em `CasoDetalhe.tsx` (23 chamadas) e `Clientes.tsx` (4), mas a maioria das páginas usa `alert()` (obsoleto/disruptivo) ou não avisa nada. |

---

## 2. FALHAS MÉDIAS (15)

| # | Falha | Área | Arquivo(s) |
|---|-------|------|-----------|
| M1 | Duplicação de responsabilidade em serviços de IA (`ai_service.py`, `ai_gateway.py`, `ai_skill_service.py`, `ia_defensiva_service.py`) — gateway existe mas é subutilizado | Backend | `backend/app/services/` |
| M2 | 7 routers de IA/AI (`ai`, `ia_extra`, `ia_especializada`, `ia_defensiva`, `ia_governanca`, `ia_saude`, `documento_ia`) sem consolidação | Backend/Estrutura | `backend/app/routers/` |
| M3 | Duplicação em serviços de conflito de interesses (`conflito_interesses.py` vs `conflito_service.py`) | Estrutura | `backend/app/services/` |
| M4 | Fragmentação em honorários (`honorarios_calc.py`, `honorarios_oab.py`, `fees.py`, `veredito_ia_router.py`) | Backend/Estrutura | `backend/app/routers/` |
| M5 | Schemas Pydantic ausentes para models principais (`ai_log`, `audit_log`, `notification`, `workflow`) | Backend | `backend/app/schemas/` |
| M6 | Sem blacklist de refresh token — logout é só client-side, servidor aceita token até expirar | Backend | `backend/app/core/security.py` |
| M7 | Silêncios de erro em `notification_service.py` (push VAPID) e `documents.py` (Google Drive delete) sem log | Backend | `backend/app/services/notification_service.py`, `backend/app/routers/documents.py` |
| M8 | Campos legados duplicados entre `cases` e `processes` (`numero_processo`/`numero_cnj`, tribunal, comarca, vara) sem sincronização contínua, só backfill único na migration 048 | Banco de dados | `backend/app/models/case.py`, `backend/alembic/versions/048*` |
| M9 | `clients.responsavel_id` tem FK no schema (migration 001) mas não no model ORM | Banco de dados | `backend/app/models/client.py:65` |
| M10 | Operações destrutivas em migrations (036 `DROP COLUMN`, 048 `DROP TABLE` no downgrade) — idempotentes, mas presentes | Banco de dados | `backend/alembic/versions/036*, 048*` |
| M11 | Embeddings desabilitados por padrão (`EMBEDDINGS_ENABLED=False`) — RAG semântico dormente em produção; status fica "pendente" para sempre em vez de "sem_embeddings" | RAG | `backend/app/core/config.py:73`, `backend/app/services/ingestion_service.py:182-185` |
| M12 | Truncamento silencioso de documento em 18.000 caracteres antes de enviar à IA, sem avisar o usuário | IA | `backend/app/services/documento_service.py:96` |
| M13 | Sem bloqueio técnico impedindo peça com `status_hitl=gerado` (não revisada) de ser considerada "pronta" — depende só do frontend | IA | `backend/app/services/peca_service.py`, `backend/app/routers/ai.py:123-145` |
| M14 | Fallback entre provedores de IA (Ollama→Groq→Anthropic) não é comunicado ao frontend/usuário | IA | `backend/app/services/ai_gateway.py:195-211` |
| M15 | Rate limiting só em login/reset de senha; listagens (`/clients/`, `/documents/`) sem limite | Segurança | `backend/app/routers/auth.py`, `search.py` |
| M16 | Endpoint `bank_analysis.py` DELETE tem gate de ownership frágil quando análise não tem `case_id` | Segurança | `backend/app/routers/bank_analysis.py:118-127` |
| M17 | SQL dinâmico via f-string em `despesas.py`, `atividades.py`, `agenda_eventos.py` — seguro hoje (nomes de coluna vêm de Pydantic validado), mas design frágil | Segurança | `backend/app/routers/despesas.py:90-98`, outros |
| M18 | Componentes frontend órfãos (6): `DashboardModernLuxury.tsx`, `EscritaAssistida.tsx`, `FocusToday.tsx`, `MarketIntelligencePanel.tsx`, `PortalClientePlatinum.tsx`, `WhatsAppChatbot.tsx` | Frontend | `frontend/src/components/` |
| M19 | Validações de formulário inconsistentes (alguns usam `alert()`, outros toast, cobertura irregular) | Frontend | `Casos.tsx`, `Honorarios.tsx` |
| M20 | Módulos Processos, Portal do Cliente e Relatórios sem tela frontend dedicada (só acesso indireto via Casos/Dashboard) | Módulos jurídicos | `frontend/src/pages/` (ausência) |
| M21 | Dependência `langfuse` no `requirements.txt` sem nenhum uso detectado no código | Estrutura | `backend/requirements.txt` |

*(Numeração consolidada; alguns achados dos relatórios de origem foram agrupados por afinidade.)*

---

## 3. FALHAS LEVES (resumo — lista completa nos relatórios de origem por agente)

- Componentes `Guia*.tsx` (13 arquivos) — padrão repetitivo intencional, não é duplicação problemática.
- `teses.py` vs `teses_v4.py` — dois models para o mesmo conceito, possivelmente migração em andamento não documentada.
- Falta índice em `knowledge_chunks.categoria`.
- `boto3`/`botocore` no requirements sem uso direto (provável dependência transitiva do `langchain-community`).
- Frontend: zero testes E2E (Playwright/Cypress) e zero testes unitários (Jest/Vitest).
- Backend: 17 testes cobrindo pontos críticos (ownership, RAG isolation, sanitização), mas sem cobertura ampla dos 115+ routers.
- Inconsistência visual pontual: uso de `bg-zinc-*` em `Produtividade.tsx` em vez do design system (`bronze`/`slate`).
- `_QUARENTENA/` bem documentada e reversível, mas ocupa espaço (~770 KB) sem prazo de expurgo definido.
- Uso consistente de soft-delete (`deleted_at`) e UUID como PK em quase todos os models.

---

## 4. MÓDULOS FUNCIONAIS (13 de 15 solicitados + 3 adicionais)

Clientes, Casos, Documentos, Prazos/Suspensões/Intimações, Agenda, Tarefas (Workflow+Checklists), Financeiro Consolidado, Honorários, Sacas de Sócios, Peças Jurídicas, Banco de Teses, Jurisprudência (Interna+Externa), Analytics/Jurimetria, Data Room, Legal Docs — todos com router montado, tela frontend consumindo, e integração real (não mockada) verificada.

## 5. MÓDULOS INCOMPLETOS (3)

- **Processos**: backend funcional (6 endpoints), sem tela dedicada — só visível dentro de `CasoDetalhe.tsx`.
- **Portal do Cliente**: backend com isolamento RBAC efetivo, sem dashboard frontend dedicado — acesso só via login.
- **Relatórios**: endpoints `/mensal` e `/relatorio-financeiro` existem, sem tela consolidada — acesso via `FinanceiroDashboard`/`DossieCliente`.

## 6. MÓDULOS APENAS APARENTES (1)

- **WhatsApp** (`Whatsapp.tsx`): tela existe, visível no menu, mas é 100% placeholder estático. (Ver C8.)

## 7. MÓDULO SOLICITADO QUE NÃO EXISTE

- **Visual Law**: a Etapa 3 pediu para auditar este módulo (visual_law, visual_law_pdf, visual_law_templates), mas não foi encontrada nenhuma tela frontend nem router ativo consumido — só nomes de arquivo em `backend/app/services/` sem integração completa confirmada. Não incluído nos 15 "funcionais" acima; precisa de verificação dedicada antes da Etapa 4 se for prioridade de produto.

---

## 8. ROTAS QUEBRADAS

Já corrigidas nos commits anteriores desta branch (ver `RELATORIO_AUDITORIA_INCREMENTAL_GRAPHIFY_EJC_2026-07-02.md`): prefixo `/v1/` inexistente em `CasoDetalhe.tsx`, `AgenteIA.tsx`, `IA.tsx`. Nenhuma rota quebrada adicional confirmada nesta auditoria — mas ver C1 (endpoints inacessíveis, que é diferente de "rota quebrada": aqui a rota nem existe no servidor).

## 9. ENDPOINTS SEM USO / TELAS SEM BACKEND

- **Endpoints sem uso (não montados)**: `ia_extra.py`, `assistente.py` — ver C1.
- **Telas sem backend correspondente**: nenhuma confirmada — toda página frontend auditada tem endpoint real por trás (mesmo que incompleta em UX).
- **Backend sem tela**: Processos, Portal do Cliente, Relatórios (ver seção 5).

## 10. DUPLICIDADES

Ver M1, M2, M3, M4, M8 (banco), M18 (frontend). Resumo: a maior fonte de duplicidade é a fragmentação de IA em 7 routers e 3+ serviços sobrepostos, seguida por honorários (4 routers) e os campos legados de Caso×Processo.

---

## 11. RISCOS JURÍDICOS

1. **C7 (LGPD art. 17)** — falta de direito ao esquecimento é exposição direta a reclamação/multa ANPD.
2. **C6 (PII em texto puro)** — em caso de vazamento de banco, CPF/CNPJ de clientes ficam expostos; risco LGPD + dano reputacional para o escritório.
3. **C5 (RAG sem isolamento efetivo)** — apesar de não vazar hoje (por acidente), qualquer manutenção futura no código do RAG pode reintroduzir vazamento de peças/precedentes entre clientes — violação direta do sigilo profissional (EOAB art. 25).
4. **M12 (truncamento silencioso)** — se um documento jurídico de 25 páginas é cortado em 18k caracteres sem aviso, o advogado pode assumir que a análise da IA é completa quando não é — risco de responsabilidade profissional (EOAB art. 34).
5. Achado positivo relevante: os prompts de IA (auditoria da frente "IA") têm **excelente conformidade textual** com EOAB art. 34 e Provimento OAB 205/2021 — nenhuma promessa de resultado, HITL obrigatório, anti-alucinação em camadas. Isso reduz o risco jurídico da IA como um todo, mesmo com as lacunas médias identificadas.

## 12. RISCOS TÉCNICOS

1. **C3/C4 (banco)** — tabela sem ORM e ausência de validação de schema contínua é o maior risco de regressão silenciosa do sistema.
2. **C1 (routers não montados)** — se o frontend depender de algum desses endpoints (precisa verificar antes de decidir remover vs. montar), há funcionalidade quebrada em produção agora mesmo.
3. **Zero testes E2E no frontend** — qualquer correção de UI é feita "no escuro", sem rede de segurança automatizada.
4. **M17 (SQL dinâmico frágil)** — seguro hoje, mas um único PR mal revisado pode introduzir SQL injection real.

## 13. RISCOS DE IA

Nenhum crítico. Os 3 médios (M12, M13, M14) são lacunas de UX/observabilidade, não de segurança ou ética — a auditoria de IA teve o melhor resultado entre todas as frentes.

## 14. RISCOS DE BANCO DE DADOS

C3, C4, M8, M9, M10 — ver seções acima. Resumo: a arquitetura é sólida, mas o histórico mostra um padrão recorrente de "corrigir depois que quebra" em vez de prevenir drift. Isso é o maior risco estrutural de médio prazo do projeto.

---

## 15. PRIORIDADE DE CORREÇÃO (visão executiva — detalhamento completo na Etapa 4)

**Bloqueadores de confiança/segurança (corrigir primeiro):**
C2 (IDOR documentos), C5 (RAG isolamento), C6 (PII sem criptografia), C7 (direito ao esquecimento)

**Bloqueadores de integridade técnica:**
C3/C4 (banco — modelo ORM de processes + validação de schema em CI)

**Bloqueadores de confiança do usuário (UX quebrada visível):**
C8, C9, C10 (frontend — Whatsapp placeholder, erros silenciosos, alert/toast)

**Investigar antes de decidir:**
C1 (ia_extra/assistente — confirmar se frontend depende antes de montar ou remover)

**Demais médios/leves:** tratados na Etapa 4 em blocos por área, sem urgência de segurança.

---

## 16. RECOMENDAÇÃO TÉCNICA PARA A PRÓXIMA ETAPA

Avançar para a **Etapa 4 — Plano de Correção Segura e Priorizada**, organizando os 10 críticos + 21 médios acima em blocos pequenos e testáveis, na ordem: (1) erros que impedem build/funcionamento básico, (2) segurança/LGPD crítica, (3) banco de dados, (4) integração frontend/backend, (5) IA/RAG, (6) demais médios, (7) leves/limpeza. Nenhuma correção foi aplicada nesta etapa.

**Critério de aceite desta etapa: ATENDIDO** — auditoria completa entregue, nenhuma refatoração aplicada, riscos classificados por prioridade, base pronta para o plano de correção.
