# AUDITORIA MESTRE DO CHECKLIST EJC

Data: 2026-06-25
Base analisada: codigo local em `C:\Users\User\EJC` e diagnostico VPS/Contabo ja executado.

## 1. Resumo Executivo

O EJC ja possui nucleo robusto de ERP juridico: clientes, casos, processos, documentos, prazos, tarefas, pecas, financeiro, conhecimento juridico, IA, RAG, portal do cliente e gestao societaria. O maior problema atual nao e ausencia de modulos, mas dispersao funcional: muitos recursos existem em telas, routers e services diferentes, sem uma matriz unica de status, maturidade e prioridade.

Classificacao geral:

| Dimensao | Status | Observacao |
|---|---|---|
| Nucleo juridico operacional | Implementado | Clientes, casos, prazos, tarefas, documentos e pecas existem. |
| Producao juridica com IA | Parcial/avancado | Pipeline de 7 etapas existe, mas precisa persistir melhor em `legal_docs`. |
| Financeiro juridico | Implementado/parcial | Honorarios, despesas, exito/rateio, sociedade e dashboards existem. |
| CRM/atendimento | Implementado/parcial | Leads, atendimentos, relacionamento e dossie existem; funil comercial precisa consolidacao. |
| Conhecimento/RAG | Implementado/parcial | RAG, teses, sumulas, jurisprudencia e biblioteca existem; governanca de fontes e vigencia precisa reforco. |
| Portal do cliente | Implementado/parcial | Paginas de portal existem; precisa homologacao funcional completa. |
| Integracoes externas | Parcial | DataJud, Diario Oficial, Banco Central/analise bancaria e Drive aparecem; API Hub ainda nao esta consolidado. |
| Workflow builder visual | Pendente/futuro | Existe workflow/kanban, mas nao builder visual completo. |
| Permissao por campo | Pendente/futuro | Ha roles e ownership, mas nao controle granular por campo. |

## 2. Legenda

Status:

- Implementado: ha tela, rota/modelo/servico ou evidencia forte de funcionamento.
- Parcial: ha parte relevante implementada, mas falta consolidacao, integracao ou homologacao.
- Pendente: nao ha evidencia suficiente de implementacao.
- Futuro: melhor tratar como expansao, nao como requisito do MVP.

Prioridade:

- P0: essencial para operar com seguranca.
- P1: essencial para rotina juridica.
- P2: melhora produtividade e gestao.
- P3: expansao ou sofisticacao futura.

## 3. Matriz Mestre por Modulo

| Modulo | Status | Prioridade | Evidencias no sistema | Lacuna principal | Recomendacao |
|---|---:|---:|---|---|---|
| Arquitetura central | Implementado | P0 | `clients`, `cases`, `processes`, `documents`, `tasks`, `fees`, `rag`, `ai_log`; paginas Clientes, Casos, Documentos, Tarefas, Financeiro, Conhecimento | Relacionamentos precisam ser auditados por integridade real no banco | Criar painel tecnico de entidades e relacionamentos |
| Atendimento | Parcial | P1 | `atendimentos.py`, `CentralRelacionamento.tsx`, `DossieCliente.tsx`, `mensagens.py`, `notifications.py` | Historico unificado de contato e pendencias ainda precisa validacao ponta a ponta | Consolidar linha do tempo unica do cliente |
| CRM juridico | Parcial | P1 | `CRMLeads.tsx`, `funil.py`, `conversao_caso.py`, `clients.py` | Indicadores CAC, receita por canal e ticket medio nao estao claramente consolidados | Transformar leads -> proposta -> contrato -> caso em fluxo unico |
| Casos | Implementado | P0 | `cases.py`, `case.py`, `CasoDetalhe.tsx`, `DossieCliente.tsx`, `SalaDeGuerra.tsx`, `kanban.py` | Kanban juridico pode estar separado da vida real do caso | Definir status padrao do caso e transicoes permitidas |
| Processos | Parcial/implementado | P0 | `processes.py`, `processo_service.py`, `datajud.py`, `datajud_service.py`, `movimentos.py`, `intimacoes.py` | Importacao CNJ/DataJud precisa homologacao com casos reais | Criar checklist de homologacao DataJud/processos |
| Prazos | Implementado | P0 | `deadlines.py`, `tasks.py`, `agenda_eventos.py`, `suspensoes.py`, `deadline_calculator.py`, paginas Prazos, Tarefas, Agenda, Suspensoes | Central unica de prazos/tarefas/reunioes pode estar fragmentada | Criar "Agenda Juridica Unificada" como tela principal |
| Producao juridica | Parcial/avancado | P0 | `legal_docs.py`, `peca_geracao.py`, `peca_service.py`, `templates.py`, `Pecas.tsx`, `PecaGeneratorModal.tsx` | Geracao IA retorna texto/log, mas nao salva automaticamente como `LegalDoc` revisavel | Ajustar pipeline para salvar rascunho IA em `legal_docs` |
| Data room/GED | Parcial | P1 | `data_room.py`, `documents.py`, `documental.py`, `GestaoDocumental.tsx`, `DataRoom.tsx`, Google Drive service | Versionamento/compartilhamento/assinatura precisam comprovacao operacional | Consolidar GED + Data Room em uma experiencia unica |
| Ramos do direito | Implementado/parcial | P2 | `RamosHub.tsx`, `RamoBase.tsx`, `ramosConfig.ts`, guias por ramo, calculadoras | Risco de virar codigo hardcoded por ramo | Migrar guias/checklists/templates para dados configuraveis |
| Ferramentas por ramo | Parcial | P2 | Guias, links e calculadoras; `calculadoras.py`, `tax_tables.py`, `trabalhista.py`, `custas_tjmg.py` | Muitas ferramentas sao links/orientacoes, nao integracoes reais | Separar "link externo" de "integracao automatizada" |
| APIs externas | Parcial | P2 | DataJud, Diario Oficial/DJEN, Banco Central/analise bancaria, Google Drive/rclone | Falta API Hub unico com status, credenciais, logs e limites | Criar Central de Integracoes antes de novas APIs |
| Financeiro | Implementado/parcial | P0 | `fees.py`, `despesas.py`, `financeiro_consolidado.py`, `honorarios_calc.py`, `exito_rateio.py`, `pix.py`, `FinanceiroWorkspace.tsx` | NFSe/faturamento formal nao evidenciado; categorias podem precisar padronizacao | Normalizar plano de contas e fluxo de recebimento |
| Sociedade | Implementado/parcial | P1 | `Sociedade.tsx`, `socio.py`, `gestao_societaria.py`, `partner_withdrawals.py`, `ExtratoSocio.tsx` | Regras societarias precisam travas e relatorios formais | Criar extrato societario por periodo com aprovacao |
| Honorarios de exito | Implementado/parcial | P1 | `exito_rateio.py`, `fees.py`, `Honorarios.tsx`, `ExtratoSocio.tsx` | Regra 50/50 precisa parametrizacao por contrato/caso | Tornar regras de rateio configuraveis por contrato |
| Gestao do conhecimento | Implementado/parcial | P1 | `rag.py`, `tese.py`, `sumulas.py`, `jurisprudencia_*`, `Biblioteca.tsx`, `Conhecimento.tsx`, `KnowledgeHub.tsx` | Governanca de fonte, vigencia, tribunal e confiabilidade precisa reforco | Criar curadoria de fontes com validade e classificacao |
| IAs especializadas | Parcial | P2 | `ai.py`, `ai_tools.py`, `ia_especializada.py`, `ai_gateway.py`, prompts por tarefa | Falta catalogo administrativo das IAs e custos por tarefa | Criar painel "Modelos e Custos de IA" |
| Licitacoes separado | Parcial/futuro | P2/P3 | `GuiaLicitacoes.tsx`, ramo administrativo, referencias PNCP/SICAF/Compras.gov | Nao parece haver modulo completo de operacao licitatoria | Manter basico autorizado; se crescer, separar como produto/modulo proprio |

## 4. Itens Criticos do Texto Original Reavaliados

| Item citado como faltante | Status real estimado | Evidencia | Comentario |
|---|---:|---|---|
| Assinatura eletronica nativa | Parcial | `signatures.py`, `Assinaturas.tsx`, portal assinaturas | Existe fluxo interno; precisa confirmar validade juridica/assinador externo. |
| Workflow Builder visual | Pendente/parcial | `workflow.py`, `Workflow.tsx.bak`, Kanban | Ha workflow/kanban, mas nao builder visual completo. |
| Portal do Cliente | Implementado/parcial | `PortalDashboard`, `PortalCasos`, `PortalFinanceiro`, `PortalAssinaturas`, `PortalMensagens` | Ja existe no frontend; precisa homologacao de login/permissoes. |
| Portal do Parceiro/Correspondente | Pendente | sem evidencia clara | Pode ficar futuro. |
| Gestao de Procuracoes | Implementado/parcial | `procuracoes.py`, `procuracao.py` | Existe base; precisa validar fluxo completo. |
| Permissoes por campo | Pendente | roles/ownership existem | Campo-a-campo e complexo; deixar futuro. |
| Auditoria LGPD completa | Parcial | `audit.py`, `audit_log.py`, middleware auditoria, `sanitizer.py` | Ha estrutura, mas precisa matriz LGPD formal. |
| Gestao documental com versionamento | Parcial | `documents.py`, `legal_doc.versao`, GED/DataRoom | Versionamento de pecas existe; GED precisa confirmar granularidade. |
| BI avancado multidimensional | Parcial/futuro | dashboards, analytics, jurimetria, produtividade | Avancar so depois de dados limpos. |
| Faturamento e NFSe | Pendente/futuro | financeiro existe, NFSe nao evidente | Nao e P0 se escritorio emite fora do EJC. |
| Contratos internos do escritorio | Implementado/parcial | `office_contracts.py`, `OfficeContracts.tsx` | Existe. |
| Produtividade por colaborador | Implementado/parcial | `produtividade.py`, `timesheet.py`, `Produtividade.tsx` | Existe base. |
| Central de integracoes/API Hub | Pendente/parcial | integracoes espalhadas em services | Recomendado criar antes de adicionar novas APIs. |

## 5. Riscos de Peso e Obsolescencia

| Risco | Impacto | Criticidade | Recomendacao |
|---|---|---:|---|
| Muitos routers e services sem mapa funcional | Dificulta manutencao e testes | Alta | Criar inventario automatizado de rotas e owners por modulo |
| IA/embeddings no build do backend | Build pesado, deploy lento e obsolescencia rapida | Alta | Separar embeddings/worker de IA do backend web |
| Modelos de IA fixos no codigo/env | Modelos mudam rapido | Alta | Centralizar configuracao de modelos por tarefa |
| Ramos do direito hardcoded no frontend | Crescimento vira manutencao cara | Media/alta | Migrar guias/checklists para tabelas configuraveis |
| Integracoes externas espalhadas | Mudancas de API quebram pontos isolados | Alta | Criar API Hub com logs, status, credenciais e retries |
| BI antes de saneamento de dados | Indicadores bonitos, mas pouco confiaveis | Media | Priorizar qualidade de dados e eventos |
| Gerador de pecas sem persistencia formal imediata | Perde rastreabilidade operacional | Alta | Salvar rascunho IA em `legal_docs` com HITL |

## 6. Prioridades Recomendadas

### P0 - Estabilizacao essencial

1. Corrigir fluxo de login/admin para permitir homologacao funcional completa.
2. Ajustar gerador de pecas para salvar automaticamente em `legal_docs`.
3. Unificar status de casos, prazos, tarefas e agenda.
4. Criar smoke tests de rotas principais: login, dashboard, clientes, casos, documentos, pecas, prazos.
5. Corrigir erro de `ai_logs.id` observado no Postgres.

### P1 - Rotina juridica de alto valor

1. Linha do tempo unica do cliente/caso.
2. Dossie consolidado por caso com documentos, prazos, pecas, financeiro e IA.
3. Auditoria automatica pos-geracao de peca.
4. Portal do cliente homologado ponta a ponta.
5. Extrato financeiro por caso e por socio.

### P2 - Escala e inteligencia

1. Central de integracoes/API Hub.
2. Governanca de RAG: fonte, validade, tribunal, vigencia e confiabilidade.
3. Painel de custos/modelos de IA.
4. CRM com indicadores reais: origem, conversao, receita por canal e ticket medio.
5. Produtividade por colaborador com regras claras.

### P3 - Futuro

1. Workflow Builder visual.
2. Permissoes por campo.
3. NFSe/faturamento completo.
4. Portal de parceiro/correspondente.
5. Modulo licitatorio avancado separado.

## 7. Recomendacao Arquitetural

Nao adicionar novos modulos grandes antes de consolidar o nucleo. O EJC deve ser organizado em quatro camadas:

1. Nucleo: clientes, casos, processos, documentos, prazos, pecas, financeiro, auditoria.
2. Operacao: atendimento, CRM, portal, pendencias, kanban, produtividade.
3. Inteligencia: IA, RAG, BI, jurisprudencia, teses, auditoria de pecas.
4. Especializacao: ramos do direito, licitacoes, bancos, ambiental, tributario e ferramentas externas.

Regra de decisao: toda nova funcionalidade deve provar em qual camada entra, qual entidade central usa e qual fluxo operacional melhora.

## 8. Proxima Acao Sugerida

Executar uma auditoria automatizada de rotas e telas, gerando uma tabela:

- Tela frontend
- Rota backend chamada
- Modelo/tabela relacionada
- Status: OK, sem rota, rota sem tela, duplicada, obsoleta
- Prioridade de correcao

Isso transforma a auditoria de produto em plano tecnico de refatoracao e evita aumentar o peso do sistema sem controle.
