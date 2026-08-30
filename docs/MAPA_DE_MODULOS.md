# MAPA DE MODULOS — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-08-30, commit `9fe3642d`.
> Regenerar apos alteracao estrutural. Nao editar as secoes automaticas a mao.

## 1. Estrutura de primeiro e segundo nivel

```
.claude
.claude/agents
.claude/hooks
.claude/skills
backend
backend/alembic
backend/app
backend/graphify-out
backend/scripts
backend/seeds
backend/tests
config
docs
docs/ai
docs/analises
docs/arquivo
docs/audit
docs/auditoria
docs/auditorias
docs/biblioteca_juridica
docs/consolidacao
docs/decisoes
docs/engineering
docs/estrategia
docs/operacao
frontend
frontend/public
frontend/src
frontend/tests
infra
infra/woodpecker
nginx
qa
qa/e2e
qa/evidencias
qa/homologacao
scripts
scripts/audit_2026-07-01
scripts/backup
scripts/governanca
scripts/inventory
scripts/rag
scripts/tests
vps-tools
```

## 2. Backend — modulos Python

| Caminho | Arquivos .py | Linhas |
|---|---|---|
| `backend` | 1 | 124 |
| `backend/alembic` | 1 | 194 |
| `backend/alembic/versions` | 144 | 10659 |
| `backend/app` | 2 | 604 |
| `backend/app/core` | 29 | 4643 |
| `backend/app/eval` | 6 | 1868 |
| `backend/app/integrations` | 14 | 1964 |
| `backend/app/models` | 68 | 5546 |
| `backend/app/modules` | 1 | 0 |
| `backend/app/modules/auditoria` | 2 | 60 |
| `backend/app/modules/dpt360` | 13 | 2561 |
| `backend/app/repositories` | 2 | 98 |
| `backend/app/routers` | 160 | 50087 |
| `backend/app/schemas` | 31 | 2812 |
| `backend/app/seeds` | 10 | 3918 |
| `backend/app/services` | 179 | 54545 |
| `backend/app/services/ai` | 13 | 2875 |
| `backend/app/services/ai/agent` | 4 | 772 |
| `backend/app/services/ai/agent/tools` | 6 | 893 |
| `backend/app/services/ai/core` | 12 | 2553 |
| `backend/app/services/ambiental` | 2 | 338 |
| `backend/app/services/calc` | 8 | 1722 |
| `backend/app/services/conhecimento_ingest` | 4 | 666 |
| `backend/app/services/fiscal` | 3 | 605 |
| `backend/app/services/ingestors` | 8 | 1818 |
| `backend/app/services/juris_import` | 7 | 1017 |
| `backend/app/services/nfse` | 3 | 617 |
| `backend/app/services/observability` | 2 | 270 |
| `backend/app/services/providers` | 5 | 868 |
| `backend/app/services/system_prompts` | 40 | 2498 |
| `backend/app/tasks` | 7 | 1061 |
| `backend/app/utils` | 4 | 272 |
| `backend/scripts` | 22 | 3926 |
| `backend/seeds` | 3 | 679 |
| `backend/tests` | 550 | 101944 |

## 3. Frontend — estrutura de src

| Caminho | Arquivos .ts/.tsx | Linhas |
|---|---|---|
| `frontend/src` | 5 | 288 |
| `frontend/src/components` | 90 | 35129 |
| `frontend/src/components/__tests__` | 4 | 579 |
| `frontend/src/components/base` | 1 | 97 |
| `frontend/src/components/visual` | 4 | 1640 |
| `frontend/src/components/visual/__tests__` | 1 | 96 |
| `frontend/src/config` | 8 | 2059 |
| `frontend/src/config/__tests__` | 1 | 21 |
| `frontend/src/content` | 1 | 820 |
| `frontend/src/contexts` | 2 | 157 |
| `frontend/src/lib` | 34 | 2910 |
| `frontend/src/pages` | 99 | 39437 |
| `frontend/src/pages/CasoDetalhe` | 19 | 5101 |
| `frontend/src/pages/CentralAtividades` | 2 | 528 |
| `frontend/src/pages/EntradaUnica` | 4 | 1208 |
| `frontend/src/pages/__tests__` | 6 | 381 |
| `frontend/src/pages/dpt360` | 26 | 3824 |
| `frontend/src/pages/portal` | 7 | 1740 |
| `frontend/src/pages/ramos` | 22 | 7118 |
| `frontend/src/stores` | 8 | 1314 |
| `frontend/src/types` | 4 | 530 |
| `frontend/src/utils` | 5 | 315 |

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
ConsultaIaEspecializadaReq
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
Deadline
DeadlineCreate
DeadlineResponse
DeadlineUpdate
DeepResearchRequest
DemonstrativoRequest
DespesaCreate
DiarioOficialAlerta
DiarioOficialKeyword
DistribuicaoIn
DistribuicaoLucro
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
DptPriorityItem
DptTwinDimension
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
GerarDocsClienteIn
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
ModeloDocumentoCreate
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
PasswordChange
PasswordResetToken
PecaConversaoIn
PedidoExtraido
PenalCase
PenalIn
PendenciaRevisao
PendingItemCreate
PendingItemUpdate
PeriodoOut
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
ProcessResponse
ProcessUpdate
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
StatusSincronizacaoResp
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
TeseIn
TeseJuridica
TeseOut
TesePatch
TeseRenomada
TeseSugerida
TeseVitoriosaCreate
TeseVitoriosaSimilar
TestarCredencialResp
TesteResultado
ThesisCandidate
TimeEntry
TokenResponse
TomadorIn
TrabalhistaCase
TrabalhistaIn
TransicaoReq
Tribunal
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

Total de arquivos: 144

Ultimas 15 por ordem de numeracao:

```
backend/alembic/versions/138_consolida_fontes_ingestao.py
backend/alembic/versions/139_dpt360_ciclo_vida_lgpd.py
backend/alembic/versions/140_preliminares_fundacao_schema.py
backend/alembic/versions/141_dpt360_diagnostico.py
backend/alembic/versions/142_document_hash_rescan.py
backend/alembic/versions/143_signature_documento_visualizado.py
backend/alembic/versions/144_alembic_version_varchar128.py
backend/alembic/versions/145_drop_orphan_db_only_columns.py
backend/alembic/versions/146_case_sigilo_reforcado.py
backend/alembic/versions/147_pendencia_impacto_providencia.py
backend/alembic/versions/149_documents_sha256_integridade.py
backend/alembic/versions/150_indices_fk_espinha_dominio.py
backend/alembic/versions/151_case_status_anterior.py
backend/alembic/versions/152_thesis_candidate_tese_banco.py
backend/alembic/versions/153_legal_doc_client_id.py
```

Reserva de numeracao: `backend/alembic/MIGRATION_RESERVATIONS.md`.
A trava automatica esta em `.github/workflows/governanca.yml`.

## 6. Responsabilidade por modulo — PREENCHIMENTO HUMANO

| Modulo | Responsabilidade funcional | Depende de | Nao pode ser duplicado por |
|---|---|---|---|
| | | | |

> Esta secao nao e extraivel do codigo. Define o contrato de responsabilidade
> que impede duplicacao de componentes entre agentes.
