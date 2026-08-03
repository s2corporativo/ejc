# MAPA DE MODULOS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-08-03, commit `b0472404`.
> Regenerar apos alteracao estrutural. Nao editar as secoes automaticas a mao.

## 1. Estrutura de primeiro e segundo nivel

```
.claude
.claude/agents
.claude/hooks
.claude/skills
.githooks
.github
.github/workflows
backend
backend/alembic
backend/app
backend/scripts
backend/seeds
backend/tests
config
docs
docs/ai
docs/analises
docs/audit
docs/auditoria
docs/auditorias
docs/historico
frontend
frontend/public
frontend/src
frontend/tests
nginx
qa
qa/e2e
qa/evidencias
qa/homologacao
scripts
scripts/audit_2026-07-01
scripts/backup
scripts/governanca
scripts/rag
scripts/tests
vps-tools
```

## 2. Backend — modulos Python

| Caminho | Arquivos .py | Linhas |
|---|---|---|
| `backend` | 1 | 42 |
| `backend/alembic` | 1 | 129 |
| `backend/alembic/versions` | 121 | 8642 |
| `backend/app` | 2 | 578 |
| `backend/app/core` | 28 | 4126 |
| `backend/app/eval` | 4 | 1107 |
| `backend/app/integrations` | 5 | 458 |
| `backend/app/models` | 62 | 4761 |
| `backend/app/modules` | 1 | 0 |
| `backend/app/modules/auditoria` | 2 | 60 |
| `backend/app/modules/case_partes` | 1 | 0 |
| `backend/app/modules/indice_risco` | 1 | 0 |
| `backend/app/modules/score_juridico` | 1 | 0 |
| `backend/app/repositories` | 2 | 98 |
| `backend/app/routers` | 164 | 47202 |
| `backend/app/schemas` | 31 | 2516 |
| `backend/app/seeds` | 10 | 3793 |
| `backend/app/services` | 144 | 46652 |
| `backend/app/services/ai` | 12 | 2218 |
| `backend/app/services/ai/agent` | 4 | 769 |
| `backend/app/services/ai/agent/tools` | 6 | 886 |
| `backend/app/services/ai/core` | 10 | 2233 |
| `backend/app/services/ambiental` | 2 | 338 |
| `backend/app/services/calc` | 8 | 1722 |
| `backend/app/services/conhecimento_ingest` | 4 | 592 |
| `backend/app/services/fiscal` | 3 | 605 |
| `backend/app/services/ingestors` | 8 | 1585 |
| `backend/app/services/juris_import` | 6 | 836 |
| `backend/app/services/nfse` | 3 | 510 |
| `backend/app/services/observability` | 2 | 270 |
| `backend/app/services/providers` | 5 | 765 |
| `backend/app/services/system_prompts` | 35 | 2066 |
| `backend/app/tasks` | 4 | 206 |
| `backend/app/utils` | 4 | 250 |
| `backend/scripts` | 13 | 1869 |
| `backend/seeds` | 2 | 340 |
| `backend/tests` | 345 | 65878 |

## 3. Frontend — estrutura de src

| Caminho | Arquivos .ts/.tsx | Linhas |
|---|---|---|
| `frontend/src` | 4 | 234 |
| `frontend/src/components` | 87 | 34426 |
| `frontend/src/components/__tests__` | 4 | 579 |
| `frontend/src/components/base` | 1 | 97 |
| `frontend/src/components/ui` | 6 | 389 |
| `frontend/src/components/visual` | 4 | 1634 |
| `frontend/src/components/visual/__tests__` | 1 | 96 |
| `frontend/src/config` | 7 | 1766 |
| `frontend/src/config/__tests__` | 1 | 21 |
| `frontend/src/content` | 1 | 820 |
| `frontend/src/contexts` | 1 | 69 |
| `frontend/src/lib` | 27 | 2366 |
| `frontend/src/pages` | 78 | 36541 |
| `frontend/src/pages/CasoDetalhe` | 14 | 4172 |
| `frontend/src/pages/CentralAtividades` | 2 | 527 |
| `frontend/src/pages/EntradaUnica` | 4 | 1208 |
| `frontend/src/pages/__tests__` | 6 | 381 |
| `frontend/src/pages/portal` | 7 | 1746 |
| `frontend/src/pages/ramos` | 9 | 5303 |
| `frontend/src/stores` | 8 | 1307 |
| `frontend/src/types` | 4 | 521 |
| `frontend/src/utils` | 9 | 498 |

## 4. Modelos de dados detectados

```
AILog
AIProviderMetric
AbusividadeIn
AceitarPrazoRequest
AddItemReq
AdicionarArquivoReq
AdminCase
AdminIn
AdversarioReq
AgenteStreamRequest
AiRequest
AiResponse
AlterarSenhaRequest
AmbientalCreate
AnalisarCasoRequest
AnalisarIn
AnalisarUrlRequest
AnaliseCompletaIn
AnaliseTeseRequest
AnaliseTeseResponse
AnexoItemIn
AnexosIn
ApiKey
ApiKeyCreate
AplicarAcoesRequest
ArchiveCaseRequest
ArchiveProcessRequest
AreaModuloCreate
AreaModuloMapping
AreaModuloUpdate
Atendimento
AtendimentoIn
AtendimentoPatch
AtribuirIn
AtualizarValorIn
AuditLog
AuthMiddleware
AuthorityRecord
AvancarEtapaReq
AvancarIn
BancarioCase
BancarioIn
BankAbusiveCharge
BankAnalysis
BankTransaction
BatchIngestRequest
BreakevenIn
BuscaPrecedentesRequest
CARIn
CETIn
CalcularPrazoRequest
CalendarFeedCredential
CampoExtraido
CampoStatus
CancelarIn
Case
CaseChecklist
CaseChecklistItem
CaseCreate
CaseDeleteRequest
CaseIntelligenceSnapshot
CaseMovimento
CaseParte
CasePendencia
CasePendenciasResponse
CaseResponse
CaseUpdate
CaseWorkflow
CasoArea
CasoConversao
CasoExtraido
CenarioOut
CentroCusto
CentroCustoIn
CentroCustoPatch
ChecklistTemplate
ChecklistTemplateIn
ChecklistTemplateItem
CitacaoBloqueante
CivelCase
CivelIn
Client
ClientBase
ClientUpdate
ClienteConversao
ClienteEntrada
ClienteExtraido
ConfiguracaoMolde
ConflitoCheckRequest
ConflitoRequest
ConsistenciaReq
ConsolidacaoOut
ContextualActionItem
ContextualActionsResponse
ContratoHistorico
ContratoIn
ContratoPatch
ContratoSocietario
ConversaoChecklistItem
ConversaoChecklistResponse
ConverterRequest
CoreAnalyzeRequest
CoreChatRequest
CoreGenerateRequest
CoreReportRequest
CoreTaskRequest
CorrecaoIn
CorrecaoOut
CredencialMeta
CriarCasoEntradaRequest
CriarSolicitacaoReq
CriticaAdversarial
CriticaAdversarialRequest
CuradoriaPatch
DDTemplateCreate
DataRoom
DataRoomAcessoLog
DataRoomArquivo
DataRoomIn
DataRoomLink
DataRoomSala
Deadline
DeadlineCreate
DeadlineResponse
DeadlineUpdate
DeepResearchRequest
DemonstrativoRequest
DiarioOficialAlerta
DiarioOficialKeyword
DistribuicaoIn
DistribuicaoLucro
DjenComunicacao
DocTemplate
Document
DocumentIntakeBatch
DocumentIntakeItem
DocumentPatchRequest
DocumentTestRequest
DocumentTypeMaster
DocumentoChunk
DocumentoIntakeResult
DocxExportPayload
DossieEstrategico
EjcSkill
EmitirIn
EmpresarialCase
EmpresarialIn
EncargoOut
EncerrarVigenciaIn
EntrevistaIn
EntryIn
EnvCaseCreate
EnvCaseResponse
EnvCaseUpdate
EnvironmentalCase
EstadoUpdate
EstimativaIn
EtapaIn
EtapaJornada
EtapaPlanoAgente
EtiquetaIn
EventoCreate
EventoIn
EventoPatch
EventoSocietario
EvidenceLink
ExecutarPromptReq
ExtrairJurisprudenciaURLIn
FaixaIn
FaixaOut
FaixasIn
FaqReq
FaturarIn
Fee
FeeCobrancaEnvio
FeeCreate
FeePayment
FeePaymentCreate
FeeProposal
FeeResponse
FeeUpdate
Feriado
FerramentaItem
FichaIn
FichaTriagem
FonteIngestao
FrontendError
GerarDossieReq
GerarIAReq
GerarIn
GerarLinkReq
GerarPecaRequest
GlossarioReq
GoogleDriveCuradoriaApplyRequest
GoogleDriveCuradoriaPreviewRequest
GoogleDriveSyncRequest
GovernanceMetadataPatch
HITLRevisaoRequest
HonorariosCreate
HonorariosIn
HonorariosOut
IaDefensivaRequest
IaDefensivaStatusRequest
ImportItem
ImportResumo
ImportarJurisRequest
IngerirAILogRequest
IngestRequest
IniciarWorkflowReq
InstanciarReq
IntegrationCredential
ItemIn
ItemLote
ItemOABIn
JornadaCasoOut
JulgadoNormalizado
JuriIn
JuriPatch
JurisprudenciaInterna
JurisprudenciaMGIn
JurisprudenciaSuporte
KeywordIn
KitDocumentalIn
KnowledgeChunk
KnowledgeDoc
LegalChatAttachment
LegalChatMessage
LegalChatSession
LegalChatStateVersion
LegalDoc
LegalDocAprovacao
LegalDocCreate
LegalDocProtocolo
LegalDocResponse
LegalDocRevisao
LegalDocUpdate
LegalIssue
LinhaDemonstrativo
LinkIn
LiquidacaoIn
LiquidacaoOut
LoginRequest
MarcarItemReq
MelhorRegraOut
MemoriaCreate
MemoriaUpdate
MensagemCreate
MinutaIn
ModeloDocumentoCreate
ModuleHelp
ModuleHelpCreate
ModuleHelpUpdate
MontarMatrizIn
MovimentoCreate
MsgIn
MsgResponse
NFSePedidoEmissao
NFSeResultado
NFSeTomador
NotaFiscalServico
NotaOut
Notification
NotificationChannelAvailability
NotificationPreference
NotificationPreferenceEnvelope
NotificationPreferenceUpdate
PageResponse
ParcelaIn
ParcelamentoIn
ParteCreate
ParteExtraida
PasswordChange
PasswordResetToken
PecaConversaoIn
PedidoExtraido
PenalCase
PenalIn
PendenciaRevisao
PeriodoOut
PesquisaIn
PrazoEntrada
PrazoExtraido
PrePreencherIn
PrecificacaoCreate
PrepararPacoteRequest
PrescricaoIn
Process
ProcessCreate
ProcessResponse
ProcessUpdate
ProcessoPrincipalSchema
Procuracao
ProcuracaoCreate
ProcuracaoResponse
ProducaoModoPreparada
ProducaoModoRequest
PromptCreate
PromptIn
PromptJuridico
PromptPatch
PropostaIn
Prova
ProvaCreate
ProvaExtraida
ProvaUpdate
ProviderStatus
PublicarArquivoReq
PushSubIn
PushSubscription
PushSubscriptionList
PushSubscriptionSafe
RaioXAcaoRequest
RaioXAnalise
RaioXConverterRequest
RaioXCreate
RaioXDocumento
RaioXUpdate
ReauthReq
ReceitaCNPJIn
ReceitaCPFIn
RecomendacaoOut
ReferenciaDocumento
RefreshRequest
RefreshToken
RegistroCreate
RegistroTratamento
RegistroUpdate
RegraTransicaoOut
RejeitarPropostaIn
RelatorioCitacoes
RescisaoIn
ResetConfirmarRequest
ResetSolicitarRequest
ResolverAlerta
ResumirDocRequest
ResumirIn
RevisaoRequest
RiscoExtraido
RouteUsageMetric
SaidaAlternativaRequest
SalaCreate
SalaResponse
SancoesIn
SchedulerHeartbeat
SensibilidadeUpdate
SessaoCreate
SessaoUpdate
Settings
SignatureRequest
SimulacaoPrevidOut
SimularIn
SinaisDocumento
SkillExecuteRequest
SkillExecuteResponse
SkillListItem
SociedadeCliente
SociedadeCreate
SociedadeUpdate
Socio
SocioCreate
SocioIn
SocioPatch
SocioSociedade
SocioUpdate
SolicitacaoDocumento
SolicitacaoDocumentoItem
SolicitacaoIn
SugerirPropostaIn
SugerirTipoRequest
SugestaoContextualizada
SugestaoIARequest
SugestaoProvaFaltante
SuspensaoIn
SuspensaoTribunal
SystemModuleSetting
SystemModuleSettingList
SystemModuleSettingUpdate
TJMGProcessoIn
TOTPDesativarRequest
TOTPVerificarRequest
TabelaOABHonorario
Task
TaskIn
TaskPatch
TemplateIn
TemplateItemIn
Tese
TeseCasoLink
TeseCreate
TeseIn
TeseJuridica
TeseOut
TesePatch
TeseRenomada
TeseSugerida
TeseVitoriosaCreate
TeseVitoriosaSimilar
TesteResultado
ThesisCandidate
TimeEntry
TokenResponse
TomadorIn
TrabalhistaCase
TrabalhistaIn
TraduzirIn
TransicaoReq
TributoOut
URLImportResult
User
UserCreate
UserKnownIP
UserResponse
UserUpdate
ValidacaoJuridicaRequest
ValidarCitacoesRequest
VerbaIn
VerbaOut
VerificarCitacoesReq
VerificarCitacoesRequest
VincularCasoRequest
WikiPagina
WorkflowEtapa
WorkflowHistorico
WorkflowTemplate
_AreaUpdateBase
_ResolverClienteReq
```

> Nem toda tabela possui model ORM: ~30 tabelas do EJC existem apenas em SQL bruto
> (ver `backend/alembic/env.py`, guarda `include_name()`). Esta lista NAO e o schema completo.

## 5. Migrations

Total de arquivos: 121

Ultimas 15 por ordem de numeracao:

```
backend/alembic/versions/112_client_pii_drop_plaintext.py
backend/alembic/versions/113_calendar_feed_revocation.py
backend/alembic/versions/114_consolidar_dataroom_teses_v4.py
backend/alembic/versions/115_case_proxima_acao.py
backend/alembic/versions/116_ai_log_risco_ia.py
backend/alembic/versions/117_knowledge_revisao.py
backend/alembic/versions/118_doc_versionamento.py
backend/alembic/versions/119_base_rag_enum.py
backend/alembic/versions/120_chunk_pagina.py
backend/alembic/versions/121_sala_juridica_chat.py
backend/alembic/versions/122_route_usage_metrics.py
backend/alembic/versions/123_legal_doc_ai_log_vinculo.py
backend/alembic/versions/124_data_room_public_link_hardening.py
backend/alembic/versions/125_fonte_ingestao_execucoes_zeradas.py
backend/alembic/versions/126_case_status_quatro_estados.py
```

Reserva de numeracao: `backend/alembic/MIGRATION_RESERVATIONS.md`.
A trava automatica esta em `.github/workflows/governanca.yml`.

## 6. Responsabilidade por modulo — PREENCHIMENTO HUMANO

| Modulo | Responsabilidade funcional | Depende de | Nao pode ser duplicado por |
|---|---|---|---|
| | | | |

> Esta secao nao e extraivel do codigo. Define o contrato de responsabilidade
> que impede duplicacao de componentes entre agentes.
