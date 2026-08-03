# 16 — Matriz de rastreabilidade (Fase 15)

> **Estado:** os três P0 **e** os itens P0-4/P1-1/P1-2/P1-3/P1-4/P1-5/P1-6 foram **corrigidos** neste mesmo PR (ver `00-resumo-executivo.md`). O texto das linhas segue no tempo do diagnóstico; a coluna Status já reflete a correção. Continuam pendentes: o P1 de qualidade, o P1 operacional (`homolog.qa`, que exige o banco de produção) e todo o P2/P3.


> Encadeamento **Requisito → Tela → Endpoint → Service → Tabela → Agente → Skill → Teste** para as
> funções essenciais do EJC. Nenhuma função essencial pode ser declarada concluída sem esse
> encadeamento completo.
>
> Legenda de status: ✅ completo · ⚠️ completo com ressalva · ❌ elo faltando ou quebrado

## 1. Fluxo jurídico central

| Requisito | Tela | Endpoint | Service | Tabela | Agente | Skill | Teste | Status |
|---|---|---|---|---|---|---|---|---|
| Registrar atendimento | `Central`, `SalaJuridica` | `POST /api/atendimentos`, `/api/legal-chat` | `legal_chat_service` | `atendimentos`, `legal_chat_*` | — | — | `test_sala_juridica.py` | ⚠️ 2 dos 3 testes são `inspect.getsource` |
| Cadastrar cliente com CPF protegido | `Clientes`, `CadastroManual` | `POST /api/clients` | `clients.py`, `pii_crypto` | `clients` (`cpf_enc`, `cpf_hash`) | — | — | `test_client_pii_cutover_dblevel.py` | ✅ |
| Consultar cliente sem vazar existência | `DossieCliente` | `GET /api/clients/{id}` | `_pode_ver_cliente` | `clients` | — | — | `test_clients_sigilo_titularidade_dblevel.py` | ✅ 404, não 403 |
| Importar documento com validação real | `GestaoDocumental` | `POST /api/documents` | `documento_service` | `documents` | — | — | `test_documento_service.py` | ✅ magic bytes + UUID |
| Triagem assistida por IA | `EntrevistaInteligente` | `POST /api/ficha-triagem`, `/api/triagem-entrevista` | `ficha_triagem_service` | `fichas_triagem` | `system_prompts/triagem` | — | — | ⚠️ `triagem_entrevista` **sem teste** |
| Revisão humana obrigatória | `SalaJuridica`, `Pecas` | todos os de IA | `hitl_policy` | `ai_logs` | **todos os 37** | `mark_as_draft` | `test_eval_agent_trajectory.py` (gate de CI) | ✅ `is_rascunho` incondicional |
| Criar caso | `Casos` (wizard) | `POST /api/cases` | `cases.py` | `cases`, `case_partes` | — | — | `test_casos_dblevel.py` | ✅ persistência real |
| Converter Sala Jurídica → Caso | `SalaJuridica` | `POST /api/legal-chat/{id}/converter` | `legal_chat_service:893-937` | `clients`, `cases`, anexos | — | — | `test_sala_juridica.py` | ✅ **transação única** + lock |
| Estratégia do caso | `RaioXProcesso`, `DossieEstrategicoCaso` | `POST /api/cases/{id}/analisar`, `/api/raio-x` | `legal_case_orchestrator`, `raio_x_service` | `dossies_estrategicos` | `CaseAgent` | `build_case_context`, `retrieve_rag` | — | ⚠️ **sem rate limit** (P1) |
| Proposta de honorários | — | `POST /api/fees/propostas` | `fee_proposal` | `fee_proposals` | `FinanceAgent` | `analyze_financial_case` | `test_fee_proposal.py` (690 l.) | ⚠️ sem teste de **valor** |
| **Contrato do escritório** | `OfficeContracts` | `/api/office-contracts` | `office_contracts.py` | `office_contracts` | — | — | `test_prefixo_v1_e_deps_rota.py` | ✅ **P0-1 corrigido** (segue sem teste funcional próprio — T-P0-2) |
| Procuração | — | `/api/procuracoes` | — | `procuracoes` | — | — | `test_procuracoes_titularidade_dblevel.py` | ⚠️ **sem tela** |
| Tarefas | `Central` | `/api/tasks` | — | `tasks` | — | — | parcial | ⚠️ |
| Prazo com contagem correta | `Central`, `Prazos` | `/api/deadlines` | `deadline_calculator` | `deadlines` | `ProcessAgent` | `analyze_deadline` (handler `None`) | `test_deadline_calculator.py`, `test_prazos_vencidos_dblevel.py` | ✅ datas concretas |
| Intimação → prazo sugerido | `Intimacoes` | `/api/intimacoes/{id}/prazo-sugerido` | `scheduler` (DJEN) | `djen_comunicacoes` | — | — | parcial | ⚠️ heartbeat afere execução, não resultado |
| **Gerar peça** | `Pecas`, `PecaGeneratorModal` | `POST /api/pecas/gerar`, `/api/document-templates/generate` | `peca_service`, `motor_peca_service` | `legal_docs` | `LegalWritingAgent` | `generate_legal_draft`, `validate_citations` | `test_motor_peca.py`, `test_p1_rbac_e_rate_limit_ia.py`, **`test_peca_geracao_router_dblevel.py`** | ✅ **T-P0-1 e P1-2 corrigidos** — gerador com teste funcional contra banco real (render, sandbox anti-SSTI, 404/400, piso de advogado) |
| Revisar peça | `Pecas` | `POST /api/legal-docs/{id}/revisar` | `legal_docs.py` | `legal_docs.status` | — | — | `test_peca_conferir_assinar.py` | ✅ |
| **Aprovar peça com gate de citações** | `Pecas` | `POST /api/legal-docs/{id}/aprovar` | **`citation_gate.aplicar_gate_hitl`** (`:794`) | `ai_logs`, `audit_logs` | — | `validate_citations` | `test_citation_gate.py` (281 l.) | ✅ fail-secure, 409/503 |
| **Protocolar** | `Pecas` (`protocoloPeca.ts`) | **`PATCH /api/legal-docs/{id}/protocolo`** (`:841`) | `_gates_exportacao_protocolo` (`:985`) | `legal_docs.numero_protocolo` | — | — | — | ⚠️ 3 gates cumulativos; **depende da base RAG curada** |
| Andamento processual | `TabProcessos`, `DiarioOficial` | `/api/processes`, `/api/datajud` | `datajud_service` | `processes`, `case_movimentos` | — | — | parcial, `test_prefixo_v1_e_deps_rota.py` | ⚠️ **P0-1 corrigido** — a rota responde; o monitoramento por resultado (não por heartbeat) segue pendente |
| Comunicar o cliente | `portal/`, `ClientServiceTimeline` | `/api/portal/mensagens` | `portal.py` | `portal_mensagens` | `ClientCommunicationAgent` | `build_case_context` | `test_portal_idor_matrix*.py` | ✅ |
| **Lançar despesa** | `Despesas` | `/api/despesas` | `despesas.py` | `office_expenses` | — | — | `test_prefixo_v1_e_deps_rota.py` | ✅ **P0-1 corrigido** (segue sem teste funcional próprio — T-P0-2) |
| Encerrar caso | `Casos` | `DELETE /api/cases/{id}` | `cases.py:613-691` | `cases.deleted_at` | — | — | `test_casos_dblevel.py` | ✅ soft + 422 protetivo |
| **Alimentar base de conhecimento** | `KnowledgeGovernancePanel` | `GET /api/rag/docs`, `/api/rag/governanca` | `ingestion_service`, `knowledge_governance` | `knowledge_docs`, `knowledge_chunks` | — | `modulo_conhecimento` | `test_rag_gate_governanca_dblevel.py`, `test_prefixo_v1_e_deps_rota.py` | ✅ **P0-3 corrigido** — e o escopo de visibilidade, que nunca havia executado, passou a executar |

## 2. Requisitos transversais de segurança e LGPD

| Requisito | Tela | Endpoint | Service | Tabela | Teste | Status |
|---|---|---|---|---|---|---|
| Autenticar com JWT revogável | `LoginModern` | `POST /api/auth/login`, `/refresh` | `security.py`, `auth.py` | `refresh_tokens` | `test_bloco6_auth.py` | ✅ rotação + detecção de reuso (OAuth BCP §4.14.2) |
| Segundo fator | `Configurar2FA` | `/api/auth/totp/*` | `two_factor_policy` | `users.totp_secret` (cifrado) | `test_2fa_enforcement_hard.py` | ⚠️ **desligado por default — risco aceito pelo titular** (`GOVERNANCA_IA.md:254`) |
| Isolar caso por responsável | todas | todos os sub-recursos | **`core/ownership.py`** (99 dependentes) | `cases.advogado_*_id` | `test_idor_subrecursos_403_dblevel.py` | ⚠️ cobre **escrita**; peça sem `case_id` fica sem gate (P2) |
| Isolar o cliente externo | `portal/` | `/api/portal/*` | 3 camadas | `users.client_id` | `test_portal_idor_matrix_dblevel.py` | ✅ **melhor cobertura do repo** |
| Cifrar CPF/CNPJ em repouso | — | — | `pii_crypto` (Fernet + HMAC) | `clients.cpf_enc/hash`, `case_partes.cpf_cnpj_enc/hash` | `test_client_pii_cutover_dblevel.py`, `test_case_parte_pii_encriptado.py` | ✅ **P1-5 corrigido** — migration 127 conclui o cutover em `case_partes` |
| Sanitizar PII antes de IA externa | — | todos os de IA | `sanitizer`, `ai_gateway:_chamar_com_barreira` | — | `test_ai_gateway_barreira.py` | ⚠️ nome próprio só com `entidades` (P2) |
| Isolar o RAG por cliente | — | retrieval | `ai_service:_FILTRO_ESCOPO_RAG` | `knowledge_docs.client_id` | `test_rag_isolation_dblevel.py` | ✅ **fail-closed, 4 consultas, row-level** |
| Direito ao esquecimento (art. 17) | `Clientes` | `POST /api/clients/{id}/anonimizar` | `client_anonimizacao` | `clients`, `case_partes`, `sociedades_cliente`, `socios_sociedade`, `users` | `test_client_anonimizacao_dblevel.py` | ⚠️ **P1-6 corrigido** — alcança as 5 tabelas; campos LIVRES (observações de caso, anexos) seguem fora (P2) |
| Trilha de auditoria imutável | `Auditoria` | `/api/audit` | `criar_audit_log` | `audit_logs` | parcial | ❌ **sem WORM — apagável (P2)** |
| Limitar custo de IA | — | `/api/ai/*` | `ai_gateway` | `ai_logs` | `test_p1_rbac_e_rate_limit_ia.py` | ✅ **P1-1 corrigido** — 14 rotas com teto + teste de varredura que reprova rota nova sem limite |
| Kill-switch de IA | `GovernancaIA` | — | `ai_gateway:_exigir_ia_ligada` | — | `test_ai_killswitch_gateway.py` | ✅ **P1-3 corrigido** — gate nas 3 entradas do gateway, 503 |
| Assinatura eletrônica | `Assinaturas` | `/api/signatures` | `signatures.py` | `signature_requests` | `test_signatures_ownership.py` + **`_dblevel.py`** | ✅ **T-P1-1 corrigido** — par comportamental com dois clientes; provado por sabotagem que o teste de fonte fica 3/3 verde com o filtro morto |

## 3. Elos faltantes — resumo

| Elo | Ocorrências | Referência |
|---|---|---|
| **Endpoint existe, tela não alcança** | 4 módulos (Contratos, DataJud, Despesas, Kanban) + `entrada_universal`, `procuracoes`, `search` | P0-1, `03` §5.2 |
| **Endpoint quebrado** | `GET /rag/docs` | P0-3 |
| **Rota sem teste** | 23 routers — `peca_geracao_router`, `pix` e `api_keys` **fechados** (T-P0-1 e T-P0-3); o teste do PIX ainda achou um BR Code corrompido em produção | `14-testes.md` |
| **Teste que não exercita** | 29 `inspect.getsource` + 14 sem asserção — os 3 de assinatura ganharam par comportamental (T-P1-1) | T-P2-1/2 |
| **Skill declarada, handler não executado** | 16 de 17 | `05-skills.md` §B2 |
| **Agente sem prompt próprio** | `RAGResearchAgent` (exige fonte) | `04-agentes.md` B5.4 |
| **Tabela sem cobertura de anonimização** | ~~`case_partes`, `sociedades_cliente`, `users`~~ — **corrigido (P1-6)** | `12-seguranca-lgpd.md` |
| **Verificador cego** | ~~`api_contract.py` não modela o interceptor~~ — **corrigido (P0-2)** | `08-backend.md` |

## 4. Como usar esta matriz

1. **Nenhuma linha com ❌ pode ser declarada concluída.** Eram 12 no diagnóstico; sobrou 1 depois das correções deste PR — trilha de auditoria sem WORM (P2).
2. **As linhas ⚠️ exigem decisão explícita** — ou se fecha a ressalva, ou se registra como risco
   aceito (com o precedente do 2FA em `GOVERNANCA_IA.md:254`).
3. **Ao corrigir, atualize a coluna Teste antes da coluna Status.** Os três P0 desta auditoria
   sobreviveram porque o encadeamento tinha teste em toda parte, **menos no elo que quebrou**.
