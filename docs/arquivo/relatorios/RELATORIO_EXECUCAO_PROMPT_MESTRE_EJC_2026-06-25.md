# RELATORIO DE EXECUCAO DO PROMPT MESTRE EJC

Data: 2026-06-25
Escopo executado: rodada 1 de estabilizacao local do codigo em `C:\Users\User\EJC`.

## 1. Resultado Direto

Foi executada a primeira rodada do Prompt Mestre com foco em:

- mapear a arquitetura real do EJC;
- identificar divergencias estruturais P0;
- aplicar uma correcao local segura no fluxo de producao juridica com IA;
- validar sintaxe Python possivel na copia local;
- registrar pendencias que exigem banco, migrations, ambiente completo ou aprovacao de producao.

Nao foram alterados `.env`, banco de dados, VPS/producao ou arquivos sensiveis.

## 2. Correcao Aplicada

### P0 - Geracao de pecas por IA agora entra no fluxo formal de Pecas

Antes:

- o pipeline `/api/pecas/gerar` gerava a peca;
- gravava `AILog`;
- retornava o texto no modal;
- mas nao criava automaticamente um registro em `legal_docs`;
- a peca ficava operacionalmente "solta" ate alguem copiar/salvar manualmente.

Depois:

- ao concluir a geracao IA, o backend cria tambem um `LegalDoc`;
- `ai_generated=True`;
- `human_reviewed=False`;
- status inicial herdado do modelo: `rascunho`;
- `case_id` e `created_by` preservados;
- o evento SSE final retorna `legal_doc_id`;
- o modal passa a exibir que a peca foi salva em Pecas e exige revisao HITL.

Arquivos alterados:

- `backend/app/services/peca_service.py`
- `frontend/src/components/PecaGeneratorModal.tsx`

Impacto:

- fecha o fluxo IA -> Peca -> Revisao humana -> Aprovacao -> PDF/protocolo;
- reduz perda de rastreabilidade;
- reforca LGPD/OAB/HITL;
- evita duplicar funcionalidades em outro gerador paralelo.

## 3. Validacoes Executadas

| Validacao | Resultado |
|---|---|
| `python -m py_compile backend/app/services/peca_service.py` | OK |
| `python -m compileall -q backend/app` | OK |
| Verificacao de manifests locais | `frontend/package.json` ausente; `backend/requirements.txt` ausente |
| Build frontend local | Nao executado pela ausencia de `frontend/package.json` na copia local |
| Testes backend completos | Nao executados: copia local nao contem ambiente/dependencias completas |

Observacao: a pasta local parece ser uma copia parcial do codigo-fonte (`backend/app` e `frontend/src`), nao o projeto completo com manifests.

## 4. Diagnostico da Arquitetura Atual

### 4.1 Cliente -> Caso -> Processo

Status: parcial/transicional.

Evidencias:

- `Case` existe como entidade operacional principal.
- `Process` existe via `routers/processes.py`, permitindo N processos por caso.
- Frontend de detalhe do caso ja consome:
  - `GET /cases/{case_id}/processes`
  - `POST /cases/{case_id}/processes`
  - `DELETE /processes/{pid}`

Problema:

- `Case` ainda possui campos legados de processo:
  - `numero_processo`
  - `tribunal`
  - `comarca`
  - `vara`
  - `linked_judicial_case_id`
  - `has_judicial_process`
- `Casos.tsx` ainda cria/edita dados processuais direto no caso.
- alguns services ainda leem `case.numero_processo`.

Conclusao:

- a separacao Caso x Processo ja comecou;
- ainda nao pode remover campos legados sem migration e plano de compatibilidade;
- proximo passo correto e criar modo read-through/write-through de `Process` como fonte principal e deprecar campos em `Case`.

### 4.2 Ramos do Direito

Status: parcial, com risco de fragmentacao.

Evidencias:

- `cases` possui area principal.
- `case_legal_areas`/`CasoArea` existe para multiplas areas.
- ha tabelas/modelos satelites por ramo:
  - `EnvironmentalCase`
  - `EmpresarialCase`
  - `CivelCase`
  - `PenalCase`
  - `TrabalhistaCase`
  - `AdminCase`
  - `BancarioCase`

Risco:

- o prompt mestre recomenda nao ter uma tabela de caso por ramo.
- o EJC usa satelites 1:1 por ramo. Isso pode ser aceitavel em transicao, mas tende a aumentar manutencao.

Recomendacao:

- nao apagar agora;
- congelar criacao de novas tabelas por ramo;
- migrar novos requisitos para campos configuraveis: area, subarea, tags, checklists, templates e formularios dinamicos.

### 4.3 Atividade Unica

Status: parcial.

Evidencias:

- existem `tasks`, `deadlines`, `agenda_eventos`, `suspensoes`, `atividades`.
- existe tela `CentralAtividades.tsx`.

Problema:

- ainda nao ha uma entidade ORM unica `Activity` centralizando tudo conforme o prompt.
- prazos, tarefas e agenda continuam entidades separadas.

Recomendacao:

- criar `Activity` como camada agregadora primeiro, sem deletar tabelas atuais;
- usar `source` e `metadata`;
- depois migrar telas para ler a timeline unificada.

### 4.4 Documentos -> Conhecimento -> IA

Status: parcial/avancado.

Evidencias:

- `documents`, `data_room`, `rag`, `knowledge_chunks`, `embedding_service`, `documento_ia`.
- documentos podem ter OCR/texto extraido.
- RAG e busca semantica existem.

Problemas:

- `Document` nao possui `process_id`.
- versionamento documental completo nao esta claro no model principal.
- data room, documentos e RAG ainda parecem fluxos separados, nao uma esteira documental unica.

Recomendacao:

- adicionar `process_id` e versionamento por migration futura;
- criar evento: upload -> OCR -> classificacao -> indexacao -> disponibilidade RAG;
- IA deve consumir o indice documental, nao salvar copias paralelas.

### 4.5 RBAC/LGPD

Status: parcial.

Evidencias:

- `AuthMiddleware` registrado.
- `ROLE_LEVEL`, `require_roles`, ownership por caso em alguns routers.
- `audit_logs`, `AI logs`, sanitizacao PII.

Problema:

- nao ha matriz formal `perfil x rota x acao`.
- autorizacao granular por documento/caso/campo ainda nao esta consolidada.

Recomendacao:

- gerar matriz RBAC automatica por rota;
- classificar rotas por modulo e acao;
- implementar testes de permissao para rotas P0.

## 5. Frontend e Telas

Telas principais existentes:

- Dashboard
- Clientes
- Casos
- CasoDetalhe
- Prazos
- Tarefas
- Agenda
- Documentos/GestaoDocumental
- Pecas
- Honorarios/Financeiro
- CRMLeads
- CentralRelacionamento
- Portal do Cliente
- IA/Conhecimento/RAG
- Auditoria
- Usuarios
- Sociedade
- Produtividade
- DiarioOficial/DataJud/Intimacoes

Possiveis telas orfas ou substituidas:

- `AgenteIA.tsx`
- `Ambiental.tsx`
- `DashboardExecutivo.tsx`
- `DataRoom.tsx`
- `Documentos.tsx`
- `WhatsApp.tsx`

Observacao:

- algumas podem estar intencionalmente substituidas por redirects ou novas telas;
- nao devem ser removidas sem auditoria de imports e historico.

## 6. Problemas/Pendencias P0 Identificados

| Item | Status | Acao recomendada |
|---|---|---|
| Login/admin documentado anteriormente falhou na VPS | Pendente | confirmar/resetar credencial admin com aprovacao |
| `Case` ainda mistura dados de processo | Pendente | plano de deprecacao dos campos legados e centralizacao em `processes` |
| Atividade unica ainda nao consolidada | Pendente | criar agregador `Activity` sem remover `tasks/deadlines` |
| Documento sem `process_id` | Pendente | migration futura para vinculo documento-processo |
| Build frontend local indisponivel | Pendente | sincronizar manifests ou rodar build no ambiente completo |
| RBAC sem matriz formal | Pendente | gerar matriz rota x perfil x acao |

## 7. Proximos Passos Recomendados

### Proximo P0 tecnico

Criar inventario automatizado:

- rotas backend;
- chamadas frontend;
- telas;
- models;
- possiveis endpoints sem tela;
- possiveis telas sem rota backend;
- possiveis arquivos orfaos.

Saida sugerida:

- `AUDITORIA_ROTAS_TELAS_EJC.md`

### Proximo P0 arquitetural

Consolidar Caso x Processo:

1. manter `processes` como fonte principal;
2. adaptar `Casos.tsx` para nao coletar processo no cadastro inicial do caso, ou criar processo principal automaticamente;
3. adaptar templates, DataJud, portal e busca para preferirem `processes.numero_cnj`;
4. manter campos legados em `cases` apenas como compatibilidade;
5. planejar migration de remocao futura.

### Proximo P1 operacional

Criar `Activity` agregadora:

- deadline;
- task;
- agenda_evento;
- audiencia;
- diligencia;
- publicacao;
- follow-up;
- suspensao.

Sem deletar tabelas atuais nesta fase.

## 8. Percentual Estimado Apos Esta Rodada

Estimativa tecnica:

- nucleo existente: 70-80%;
- arquitetura ideal do prompt mestre: 50-60%;
- prontidao para uso real sem ressalvas: 55-65%;
- prontidao apos corrigir login, Caso x Processo, Activity, RBAC e testes: 75-85%.

O EJC esta bem avancado, mas ainda nao deve ser considerado 100% pronto enquanto:

- Caso x Processo estiver em transicao;
- Activity nao estiver consolidada;
- RBAC nao tiver matriz/testes;
- build/testes completos nao forem executados no ambiente integral;
- fluxo documental nao estiver totalmente integrado a processo/RAG/IA.
