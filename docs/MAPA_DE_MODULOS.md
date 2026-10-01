# MAPA DE MODULOS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-10-01, commit `54c7fc4e`.
> Regenerar apos alteracao estrutural. Nao editar as secoes automaticas a mao.

## 1. Estrutura de primeiro e segundo nivel

```
.claude
.claude/agents
.claude/hooks
.claude/skills
.vscode
backend
backend/.ruff_cache
backend/alembic
backend/app
backend/scripts
backend/seeds
backend/tests
config
docs
docs/ai
docs/ajuizamento
docs/analises
docs/arquitetura
docs/arquivo
docs/audit
docs/auditoria
docs/auditorias
docs/biblioteca_juridica
docs/ci
docs/consolidacao
docs/decisoes
docs/engineering
docs/estrategia
docs/financeiro
docs/ia
docs/operacao
docs/performance
docs/seguranca
frontend
frontend/public
frontend/scripts
frontend/src
frontend/tests
infra
infra/host-automation
infra/monitoring
infra/nginx
infra/omniroute
infra/renovate
infra/selfhosted
infra/woodpecker
nginx
ops
ops/agents
qa
qa/e2e
qa/evidencias
qa/homologacao
scripts
scripts/backup
scripts/governanca
scripts/hooks
scripts/inventory
scripts/lib
scripts/rag
scripts/tests
vps-tools
```

## 2. Backend — modulos Python

| Caminho | Arquivos .py | Linhas |
|---|---|---|
| `backend` | 1 | 149 |
| `backend/alembic` | 1 | 198 |
| `backend/alembic/versions` | 159 | 12281 |
| `backend/app` | 2 | 685 |
| `backend/app/core` | 34 | 5582 |
| `backend/app/eval` | 9 | 3082 |
| `backend/app/integrations` | 14 | 1985 |
| `backend/app/models` | 73 | 6420 |
| `backend/app/modules` | 1 | 0 |
| `backend/app/modules/auditoria` | 2 | 60 |
| `backend/app/modules/dpt360` | 14 | 2641 |
| `backend/app/modules/legacy_verticals` | 4 | 158 |
| `backend/app/repositories` | 2 | 173 |
| `backend/app/routers` | 162 | 56722 |
| `backend/app/routers/financeiro` | 6 | 3358 |
| `backend/app/schemas` | 33 | 3373 |
| `backend/app/seeds` | 12 | 4563 |
| `backend/app/services` | 202 | 64938 |
| `backend/app/services/ai` | 16 | 3828 |
| `backend/app/services/ai/agent` | 4 | 803 |
| `backend/app/services/ai/agent/tools` | 6 | 1249 |
| `backend/app/services/ai/core` | 13 | 3095 |
| `backend/app/services/ajuizamento` | 12 | 2098 |
| `backend/app/services/ajuizamento/conectores` | 7 | 1060 |
| `backend/app/services/ambiental` | 2 | 338 |
| `backend/app/services/calc` | 8 | 1722 |
| `backend/app/services/conhecimento_ingest` | 4 | 800 |
| `backend/app/services/document_intelligence` | 3 | 393 |
| `backend/app/services/fiscal` | 3 | 593 |
| `backend/app/services/ingestors` | 8 | 2042 |
| `backend/app/services/jurimetria_tribunais` | 5 | 990 |
| `backend/app/services/juris_import` | 7 | 1017 |
| `backend/app/services/legal_brain` | 13 | 2018 |
| `backend/app/services/nfse` | 3 | 620 |
| `backend/app/services/observability` | 2 | 270 |
| `backend/app/services/providers` | 5 | 908 |
| `backend/app/services/saneamento` | 8 | 1615 |
| `backend/app/services/system_prompts` | 40 | 2612 |
| `backend/app/tasks` | 7 | 1061 |
| `backend/app/utils` | 4 | 272 |
| `backend/scripts` | 32 | 5896 |
| `backend/seeds` | 3 | 725 |
| `backend/tests` | 737 | 135541 |

## 3. Frontend — estrutura de src

| Caminho | Arquivos .ts/.tsx | Linhas |
|---|---|---|
| `frontend/src` | 5 | 287 |
| `frontend/src/components` | 112 | 40031 |
| `frontend/src/components/__tests__` | 5 | 722 |
| `frontend/src/components/base` | 1 | 97 |
| `frontend/src/components/visual` | 4 | 1653 |
| `frontend/src/components/visual/__tests__` | 1 | 96 |
| `frontend/src/config` | 15 | 3462 |
| `frontend/src/config/__tests__` | 1 | 21 |
| `frontend/src/content` | 1 | 806 |
| `frontend/src/contexts` | 2 | 157 |
| `frontend/src/lib` | 49 | 4924 |
| `frontend/src/pages` | 114 | 46905 |
| `frontend/src/pages/CasoDetalhe` | 27 | 7195 |
| `frontend/src/pages/CentralAtividades` | 3 | 728 |
| `frontend/src/pages/EntradaUnica` | 8 | 2614 |
| `frontend/src/pages/__tests__` | 6 | 383 |
| `frontend/src/pages/casos` | 7 | 1297 |
| `frontend/src/pages/dpt360` | 26 | 3912 |
| `frontend/src/pages/pecas` | 9 | 1215 |
| `frontend/src/pages/portal` | 7 | 2022 |
| `frontend/src/pages/ramos` | 23 | 7585 |
| `frontend/src/services` | 3 | 343 |
| `frontend/src/stores` | 10 | 1466 |
| `frontend/src/types` | 6 | 1042 |
| `frontend/src/utils` | 6 | 355 |

## 4. Modelos de dados detectados

```
AILog
AIProviderMetric
AbusividadeIn
AceitarPrazoRequest
ActivityAlertState
ActivityAlertStateUpdate
AddItemReq
AdicionarArquivoReq
AdminCase
AdminIn
AdversarioReq
AdvogadoIn
AgenteStreamRequest
AiRequest
AiResponse
AlterarSenhaRequest
AmbientalCreate
AnalisarCasoRequest
AnalisarIn
AnaliseCompletaIn
AnaliseTeseRequest
AnaliseTeseResponse
AnexoItemIn
AnexosIn
ApiKey
ApiKeyCreate
AplicarDedupIn
AplicarDivergenciaIn
AprovarReq
ArchiveCaseRequest
ArchiveProcessRequest
AreaModuloCreate
AreaModuloMapping
AreaModuloUpdate
AssinarReq
AssuntoIn
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
CancelarReq
Case
CaseChecklist
CaseChecklistItem
CaseCreate
CaseDeleteRequest
CaseDespesa
CaseIntelligence
CaseIntelligenceSnapshot
CaseMovimento
CaseParte
CasePendencia
CasePendenciasResponse
CaseReceiptAllocation
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
CommissionAdjustmentIn
CommissionBatchIn
CommissionCloseIn
CommissionRule
CommissionRuleIn
CommissionRulePatch
ConfidenceMetadata
ConfiguracaoMolde
ConfirmarManualReq
ConflitoCheckRequest
ConflitoRequest
ConsistenciaReq
ConsolidacaoOut
ConsultaIaEspecializadaReq
ContextualActionItem
ContextualActionsResponse
ContractBase
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
CredencialCreateReq
CredencialMeta
CredencialMetaResp
CredencialProcessoEletronico
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
DatajudSnapshot
Deadline
DeadlineCreate
DeadlineResponse
DeadlineUpdate
DecidirIndicativoIn
DeepResearchRequest
DemonstrativoRequest
DespesaIn
DiarioOficialAlerta
DiarioOficialKeyword
DistribuicaoIn
DistribuicaoLucro
Divergencia
DjenComunicacao
DocTemplate
Document
DocumentHashRescanBatch
DocumentHashRescanItem
DocumentIntakeBatch
DocumentIntakeItem
DocumentPatchRequest
DocumentPublicacaoPortalRequest
DocumentTestRequest
DocumentTypeMaster
DocumentoChunk
DocumentoIn
DocumentoIntakeResult
DocumentoProcessoEletronicoDedup
DocxExportPayload
DossieEstrategico
DptActionRequest
DptActionResponse
DptCaseSummary
DptCicloVidaMudarEstadoRequest
DptCicloVidaMudarEstadoResponse
DptCompanyProfile
DptCompanySummary
DptDashboardMetrics
DptDashboardResponse
DptDeadlineSummary
DptDiagnosticAreaReadiness
DptDiagnosticEvidence
DptDiagnosticReadiness
DptDiagnosticRun
DptHealthArea
DptInboundOpportunity
DptInboundOpportunityOut
DptOpportunityQueueItem
DptPrepareShareRequest
DptPrepareShareResponse
DptPriorityItem
DptTwinDimension
EjcSkill
EmitirIn
EmpresarialCase
EmpresarialIn
EncargoOut
EncerrarCasoSimplesReq
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
EtapaPlanoAgente
EtiquetaIn
EventoCreate
EventoIn
EventoPatch
EventoSocietario
EvidenceItem
EvidenceLink
ExcecaoNumero
Execucao
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
FeeEstorno
FeeEstornoCreate
FeeEstornoResponse
FeePayment
FeePaymentCreate
FeeProposal
FeeReference
FeeResponse
FeeUpdate
Feriado
FerramentaItem
FichaIn
FichaTriagem
FilingBase
FinanceCloseIn
FinancePolicyPatch
FonteIngestao
FrontendError
GerarDocsClienteIn
GerarDossieReq
GerarIAReq
GerarIn
GerarLinkReq
GerarPecaRequest
GerarRecorrentesIn
GlossarioReq
GoogleDriveCuradoriaApplyRequest
GoogleDriveCuradoriaPreviewRequest
GoogleDriveSyncRequest
GovernanceMetadataPatch
HITLRevisaoRequest
HonorariosCreate
HonorariosOut
IaDefensivaRequest
IaDefensivaStatusRequest
ImportItem
ImportResumo
ImportarJurisRequest
IndicativoEncerramento
IngerirAILogRequest
IngestRequest
IniciarWorkflowReq
InstanciarReq
IntegrationCredential
ItemIn
ItemLote
ItemOABIn
JudicialFiling
JudicialFilingAttempt
JudicialFilingTransicao
JudicialIntegrationProfile
JudicialProtocol
JudicialSyncEvent
JudicialTpuItem
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
LegalIssueCandidate
LinhaDemonstrativo
LinkIn
LiquidacaoIn
LiquidacaoOut
LoginRequest
ManusDeepRequest
MarcarItemReq
MelhorRegraOut
MemoriaCreate
MemoriaUpdate
MensagemCreate
MissingInformation
ModuleHelp
ModuleHelpCreate
ModuleHelpUpdate
MontarMatrizIn
MovimentoCreate
MovimentoUpdate
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
ParteUpdate
PartyCandidate
PartyEntity
PasswordChange
PasswordResetToken
PecaConversaoIn
PedidoExtraido
PenalCase
PenalIn
PendenciaRevisao
PendingItemCreate
PendingItemUpdate
PerfilIn
PeriodoOut
Pertinencia
PixCobrancaIn
PlanoDedup
PrazoEntrada
PrazoExtraido
PrePreencherIn
PrecificacaoCreate
Preliminar
PreliminarDocumento
PreliminarEstado
PreliminarMensagem
PrepararPacoteRequest
PrescricaoIn
Process
ProcessCreate
ProcessDataProvenance
ProcessResponse
ProcessUpdate
ProcessoConfirmadoEntrada
ProcessoPrincipalSchema
Procuracao
ProcuracaoCreate
ProcuracaoResponse
ProducaoModoPreparada
ProducaoModoRequest
ProdutividadeExportEvent
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
ProximaAcaoConfirmarRequest
PublicarArquivoReq
PurgarRequest
PushSubIn
PushSubscription
PushSubscriptionList
PushSubscriptionSafe
RaioXAcaoRequest
RaioXAnalise
RaioXConverterRequest
RaioXCreate
RaioXDocumento
RaioXIdentificacaoRevisada
RaioXUpdate
ReauthReq
ReceitaCNPJIn
ReceitaCPFIn
RecomendacaoOut
ReconcileConfirmIn
ReconciliarRateiosCasoReq
ReferenciaDocumento
RefreshRequest
RefreshToken
RegistrarRecebimentoCasoReq
RegistroCreate
RegistroTratamento
RegistroUpdate
RegraTransicaoOut
RejeitarPropostaIn
RelatorioCitacoes
RelatorioPertinencia
RescisaoIn
ResetConfirmarRequest
ResetSolicitarRequest
ResolverAlerta
RespostaCapacidadeIA
ResumirDocRequest
RevisaoRequest
RiscoExtraido
RouteUsageMetric
SaidaAlternativaRequest
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
SincronizacaoProcessoEletronico
SincronizarProcessoReq
SincronizarProcessoResp
SkillExecuteRequest
SkillExecuteResponse
SkillListItem
SmartAlertQuery
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
SourceReference
StatusSincronizacaoResp
SugerirPropostaIn
SugerirTipoRequest
SugestaoContextualizada
SugestaoIARequest
SugestaoProvaFaltante
SuggestedAction
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
TeseIn
TeseJuridica
TeseOut
TesePatch
TeseSugerida
TeseVitoriosaSimilar
TestarCredencialResp
TesteResultado
ThesisCandidate
TimeEntry
TimelineEvent
TokenResponse
TokensIA
TomadorIn
TpuImportReq
TpuMovimento
TpuSyncReq
TrabalhistaCase
TrabalhistaIn
TransicaoReq
Tribunal
TributoOut
User
UserCreate
UserKnownIP
UserResponse
UserUpdate
ValidacaoJuridicaRequest
ValidarCitacoesRequest
VarreduraIn
VerbaIn
VerbaOut
VerificarCitacoesReq
VerificarCitacoesRequest
VincularCasoRequest
VincularProcessoEntradaRequest
WikiPagina
WithdrawalCreate
WorkflowEtapa
WorkflowHistorico
WorkflowTemplate
_AreaUpdateBase
_CapacidadeRequestBase
_DespesaCampos
_ResolverClienteReq
```

> Nem toda tabela possui model ORM: ~30 tabelas do EJC existem apenas em SQL bruto
> (ver `backend/alembic/env.py`, guarda `include_name()`). Esta lista NAO e o schema completo.

## 5. Migrations

Total de arquivos: 159

Ultimas 15 por ordem de numeracao:

```
backend/alembic/versions/154_saneamento_schema.py
backend/alembic/versions/155_indices_listagem_espinha.py
backend/alembic/versions/156_case_despesas_processuais.py
backend/alembic/versions/157_ajuizamento_judicial.py
backend/alembic/versions/158_case_partes_trabalhista_pii_expand.py
backend/alembic/versions/159_user_cpf_secure.py
backend/alembic/versions/160_activity_alert_states.py
backend/alembic/versions/161_fee_estornos.py
backend/alembic/versions/162_case_financial_classification.py
backend/alembic/versions/163_process_provenance_party_identity.py
backend/alembic/versions/164_commission_rules.py
backend/alembic/versions/165_commission_operations.py
backend/alembic/versions/166_finance_governance.py
backend/alembic/versions/167_finance_fk_indexes.py
backend/alembic/versions/168_finance_ged_links.py
```

Reserva de numeracao: `backend/alembic/MIGRATION_RESERVATIONS.md`.
A trava automatica esta em `.github/workflows/governanca.yml`.

## 6. Responsabilidade por modulo — PREENCHIMENTO HUMANO

| Modulo | Responsabilidade funcional | Depende de | Nao pode ser duplicado por |
|---|---|---|---|
| | | | |

> Esta secao nao e extraivel do codigo. Define o contrato de responsabilidade
> que impede duplicacao de componentes entre agentes.
