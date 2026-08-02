# 10 — Fluxo jurídico ponta a ponta (Fase 10)

> **Limitação declarada:** sem banco, sem stack de pé e sem provedor de IA, o fluxo **não pôde ser
> executado**. O que segue é rastreamento de cada etapa no código — interface, endpoint, service,
> tabela, agente, gate — com classificação por etapa. Onde a conclusão exigiria execução, está
> marcado **[EXIGE HOMOLOGAÇÃO]**.

## 1. Critério de lançamento

> *"Um advogado leva um caso real do início ao protocolo dentro do sistema e considera que foi mais
> fácil do que fazer fora dele."* — `CLAUDE.md`

Nenhum caso passou da triagem até a data da auditoria externa; nenhuma peça foi protocolada.
**A pergunta desta fase é: falta funcionalidade, ou o caminho existe e está obstruído?**

**Resposta: o caminho existe, de ponta a ponta.** As obstruções são de três tipos — rota quebrada
(P0), gate acumulado, e falha silenciosa que faz o sistema parecer vazio.

## 2. Rastreamento por etapa

Legenda: **F** funcional · **FR** funcional com ressalvas · **P** parcial · **Q** quebrada

| # | Etapa | Interface | Endpoint / service | Tabela | Gate / agente | Cls |
|---|---|---|---|---|---|---|
| 1 | Novo atendimento | `Central`, `CRMLeads`, `SalaJuridica` | `/atendimentos`, `/legal-chat` | `atendimentos`, `legal_chat_*` | `_exigir_cliente_visivel` | **F** |
| 2 | Identificação do cliente | `Clientes`, `CadastroManual`, `DossieCliente` | `/clients` · `clients.py` | `clients` (CPF **cifrado** + HMAC cego) | `_pode_ver_cliente` (404, não vaza) | **F** |
| 3 | Importação de documento | `Documentos`, `GestaoDocumental` | `/documents` · `documento_service` | `documents` | magic bytes, UUID, `verificar_acesso_caso` | **F** |
| 3b | OCR | idem | `ocr_service`, `entrada_universal_service` | — | — | **FR** — fora do pipeline RAG |
| 4 | Triagem pela IA | `EntrevistaInteligente`, `SalaJuridica` | `/ficha-triagem`, `/triagem-entrevista`, `/intake` | `fichas_triagem` | `system_prompts/triagem.py` | **F** |
| 5 | Revisão humana | `SalaJuridica` | — | — | **HITL universal** (`is_rascunho` incondicional) | **F** |
| 6 | Criação do caso | `Casos` (wizard), conversão Sala→Caso | `/cases` · `legal_chat_service:893-937` | `cases`, `case_partes` | **transação única** + lock pessimista | **F** |
| 7 | Estratégia | `RaioXProcesso`, `DossieEstrategicoCaso`, `CasoDetalhe` | `/raio-x`, `/dossie`, `/cases/{id}/analisar` | `dossies_estrategicos`, `case_intelligence_snapshots` | `CaseAgent`, `legal_case_orchestrator` | **FR** |
| 8 | Proposta | — | `/fees/propostas` · `fee_proposal` | `fee_proposals` | imutabilidade + versionamento + HITL | **F** |
| 9 | Contrato | `OfficeContracts` | `/v1/office-contracts` | `office_contracts` | `_req_fin` | **Q** — P0 `/v1` |
| 10 | Procuração | — | `/procuracoes` | `procuracoes` | titularidade (teste dblevel) | **FR** — sem consumidor no frontend |
| 11 | Tarefas | `Central`, `Tarefas` | `/tasks` | `tasks` | — | **F** |
| 12 | Prazos | `Central`, `Prazos`, `Intimacoes` | `/deadlines`, `/intimacoes` · `deadline_calculator` | `deadlines`, `djen_comunicacoes` | `analyze_deadline` | **F** |
| 13 | Produção jurídica | `Pecas`, `PecaGeneratorModal` | `/pecas/gerar`, `/legal-docs`, `/document-templates` | `legal_docs` | `LegalWritingAgent`, `motor_peca` | **FR** — §3.2 |
| 14 | Revisão | `Pecas` | `/legal-docs/{id}/revisar` | `legal_docs.status` | `PecaStatus.em_revisao` | **F** |
| 15 | Aprovação | `Pecas` | `/legal-docs/{id}/aprovar`, `/conferir-e-assinar` | idem | **`aplicar_gate_hitl`** (`legal_docs.py:794`) | **F** |
| 16 | **Protocolo** | `Pecas` (`protocoloPeca.ts`) | **`PATCH /legal-docs/{id}/protocolo`** (`:841`) | `legal_docs.numero_protocolo`, `.protocolo_comprovante_doc_id` | `_gates_exportacao_protocolo` (`:985`) | **F** |
| 17 | Andamento | `CasoDetalhe/TabProcessos`, `DiarioOficial` | `/andamentos`, `/processes`, `/datajud` | `processes`, `case_movimentos` | — | **P** — DataJud em **Q** (P0 `/v1`) |
| 18 | Comunicação | `portal/`, `ClientServiceTimeline` | `/portal/mensagens`, `/notifications` | `portal_mensagens` | `ClientCommunicationAgent` | **F** |
| 19 | Financeiro | `FinanceiroWorkspace`, `Despesas` | `/fees` · **`/v1/despesas`** | `fees`, `office_expenses` | `_req_financeiro_mutacao` | **P** — despesas em **Q** (P0 `/v1`) |
| 20 | Encerramento | `Casos` | `DELETE /cases/{id}` (soft) | `cases.deleted_at` | recusa 422 com prazo/honorário/peça pendente | **F** |
| 21 | Base de conhecimento | `KnowledgeGovernancePanel` | `/rag/governanca`, `/rag/docs` | `knowledge_docs`, `knowledge_chunks` | curadoria + `rag_status` | **Q** — §3.3 |

## 3. Onde o fluxo quebra

### 3.1 — P0: quatro etapas mortas pelo prefixo `/v1`

Diagnóstico completo em `08-backend.md` §3. Impacto **no fluxo jurídico**:

| Etapa | Módulo | Consequência para o advogado |
|---|---|---|
| 9 — Contrato | `OfficeContracts` (página inteira) | **não consegue registrar o contrato do escritório** |
| 17 — Andamento | `DataJudBusca` (página inteira) | **não consegue consultar/sincronizar o processo no DataJud** |
| 19 — Financeiro | `Despesas`, `DespesasRecorrentes`, exportação CSV | **não consegue lançar despesa nem exportar** |
| 19b — Societário | `Sociedade` (retiradas) | não consegue registrar retirada de sócio |
| — | `Kanban`, pendências do `DossieCliente`, `RadarRegulatorio` | quadro de casos e pendências não carregam |

**E o advogado não vê erro** — vê "falha ao carregar" ou lista vazia. Isso explica, em parte, por
que o sistema é percebido como incompleto: **partes dele foram construídas, testadas e estão
inacessíveis.**

### 3.2 — P1: o citation gate não roda na geração da peça

Etapa 13. Confirmado por mim: `routers/peca_geracao.py` e `peca_geracao_router.py` têm **zero**
referência a `citation_gate`. O gate só roda na **aprovação** (`legal_docs.py:794`, `ai.py:216`,
`ia_defensiva.py:163`).

**É por desenho** — a peça nasce rascunho e o gate morde na aprovação. Mas significa que **quem
consumir a peça fora do fluxo HITL não passa pelo gate**. É a costura a fechar antes do primeiro
protocolo real.

Agrava: **`peca_geracao_router.py` não tem nenhum teste** (`14-testes.md` T-P0-1) e
`POST /document-templates/generate` **não tem gate de advogado** (`08-backend.md` §6.3) — enquanto
o caminho gêmeo (`kit_documental.py:58`) exige.

### 3.3 — P0: a base de conhecimento não lista

Etapa 21. `GET /api/rag/docs` retorna **500 sempre** — o monkeypatch de
`ai_core_hardening_patch.py:188-193` perde os `Depends`, e `db`/`cu` viram query params
(`08-backend.md` §5). O painel de governança do RAG não carrega, **e o escopo de visibilidade que
o patch deveria instalar nunca executa**.

### 3.4 — P1: o RAG pode estar mudo, e ninguém saberia

Duas causas independentes, ambas silenciosas:

1. **Sem embeddings, o RAG vira `ILIKE`** (`ai_service.py:415-450`) — warning único por processo,
   **sem monitoramento de resultado**.
2. **`RAG_EXIGIR_APROVADO=true` é o default.** Com acervo não curado, o retrieval retorna **vazio**
   — legitimamente. **[EXIGE HOMOLOGAÇÃO]** — verificar com
   `SELECT rag_status, count(*) FROM knowledge_docs GROUP BY 1`.

Casa exatamente com a armadilha conhecida: **"monitoramento afere execução, não resultado"**.

### 3.5 — P2: falha silenciosa faz o caso parecer vazio

41 ocorrências de `.catch(() => {})` no frontend, concentradas nas abas de `CasoDetalhe`
(`TabPartes`, `TabScore`, `TabRisco`, `TabProcessos`, `TabMemoria`, `TabResumo`) — ver
`09-frontend.md` §5.

**No contexto jurídico isso é material:** o advogado não distingue *"o caso não tem partes"* de
*"a chamada falhou"*. Numa etapa de conferência pré-protocolo, concluir que não há prazo, parte ou
prova quando há é erro com consequência processual.

### 3.6 — O funil de gates até o protocolo

`_gates_exportacao_protocolo` (`legal_docs.py:985-1027`) exige, cumulativamente:

1. se `ai_generated` → **`human_reviewed` registrado** (422 caso contrário);
2. status ∈ {aprovada, final, protocolada} **e** validação jurídica apta com score mínimo;
3. **toda jurisprudência citada validada na base** (`_auditar_jurisprudencia_peca`).

**Os três gates são corretos e desejáveis** — é o que impede protocolar peça alucinada. Mas
**empilhados sobre um RAG que pode estar vazio (§3.4)**, o gate 3 é intransponível: sem base
curada, nenhuma citação valida, e nenhuma peça chega ao protocolo.

> **Esta é, provavelmente, a explicação central para "nenhuma peça foi protocolada".** Não é
> funcionalidade faltando — é um gate legítimo alimentado por uma base vazia, sem mensagem que
> diga isso ao usuário.
> **[EXIGE HOMOLOGAÇÃO para confirmar.]**

**Ponto positivo já resolvido:** existe `GET /{doc_id}/pdf-minuta` (`legal_docs.py:1030+`) — PDF de
**leitura**, sem gate. O comentário registra o porquê: *"até aqui o único PDF era o de protocolo,
atrás dos gates de validação — ou seja, era preciso aprovar para poder ler, o que inverte a ordem
do ato profissional"*. É exatamente o tipo de correção de atrito que o critério de lançamento pede.

## 4. Hipóteses da auditoria externa reavaliadas

| Hipótese | Veredito |
|---|---|
| "Conversão Sala Jurídica → Caso perde `descricao_fatos`" | **[NÃO CONFIRMADO no backend]** — `legal_chat_service.py:906` grava `descricao_fatos=payload.descricao` explicitamente. O campo é `Optional` no schema (`schemas/legal_chat.py:107`); uma perda observada viria do **frontend não enviá-lo** |
| "Exclusão de caso não cascateia para as peças" | **[NÃO CONFIRMADO como defeito vivo]** — o DELETE é **soft** e **recusa 422** com prazo/honorário/peça pendente (`cases.py:646-681`); a visibilidade é herdada na leitura (`legal_docs.py:310-321`) |
| "Gravação não transacional é classe recorrente" | **Parcialmente refutada.** Os dois fluxos centrais (`converter-judicial`, Sala→Caso) são **atômicos, com um único commit**. Resta `entrada_universal.processar` com **6 commits** (P2) |
| "Vocabulário de status inconsistente" | **RESOLVIDO** — migration 126 + `core/status_caso.py` como fonte única |
| "Validação que não vincula ao documento" | **[NÃO REAUDITADO]** — fora do alcance sem banco |

## 5. Conclusão

**O fluxo jurídico está implementado do início ao protocolo.** Nenhuma etapa é "NÃO LOCALIZADA".
A máquina de estados é coerente (`CaseStatus` de 4 estados de trabalho + 2 terminais; `PecaStatus`
de rascunho a protocolada), os gates de proteção são corretos e a transacionalidade dos dois
fluxos centrais é atômica.

**O que impede o critério de lançamento não é ausência de funcionalidade.** É, em ordem de peso:

1. **P0 `/v1`** — contrato, DataJud, despesas e Kanban inacessíveis, **sem erro visível**;
2. **P0 `/rag/docs`** — governança da base de conhecimento não abre;
3. **gate de citações sobre base possivelmente vazia** — bloqueia o protocolo sem explicar;
4. **41 falhas silenciosas** — o caso parece vazio quando a chamada falhou;
5. **`peca_geracao_router` sem teste** — a rota do critério de lançamento é a menos protegida.

**Os itens 1, 2 e 5 são corrigíveis em dias.** O item 3 exige decisão de produto (curar a base ou
relaxar o gate) e o item 4 é trabalho mecânico de 41 pontos.
