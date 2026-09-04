# ── app/models/__init__.py ────────────────────────────────────────────────────
# Exporta todos os modelos para o Alembic detectar via Base.metadata
from app.models.user import User, RefreshToken, UserRole
from app.models.client import Client, ClientTipo, ClientStatus, ClientOrigem
from app.models.case import Case, CaseMovimento, CaseArea, CaseStatus, CaseFase, CasePrioridade
from app.models.process import Process
from app.models.deadline import Deadline, DeadlineTipo, DeadlineStatus, DeadlinePrioridade
from app.models.document import Document, DocConfidencialidade
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.document_rescan import DocumentHashRescanBatch, DocumentHashRescanItem
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.models.legal_doc import LegalDoc, PecaTipo, PecaStatus
from app.models.fee import Fee, FeePayment, FeeTipo, FeeStatus
from app.models.environmental import EnvironmentalCase, OrgaoAutuador, StatusDefesa
from app.models.especializado import (
    EmpresarialCase, EmpresarialTipo, EmpresarialStatus,
    CivelCase, CivelTipo, CivelStatus,
    PenalCase, PenalTipo, PenalFase,
    TrabalhistaCase, TrabalhistaTipo, TrabalhistaFase,
    AdminCase, AdminTipo, AdminStatus,
    BancarioCase, BancarioTipo, BancarioStatus,
)
from app.models.audit_log import AuditLog, criar_audit_log
from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
from app.models.ai_provider_metric import AIProviderMetric
from app.models.notification import Notification
from app.models.feriado import Feriado
from app.models.procuracao import Procuracao
from app.models.rag import KnowledgeDoc, KnowledgeChunk
from app.models.api_key import ApiKey

__all__ = [
    "User", "RefreshToken", "UserRole",
    "Client", "ClientTipo", "ClientStatus", "ClientOrigem",
    "Case", "CaseMovimento", "CaseArea", "CaseStatus", "CaseFase", "CasePrioridade",
    "Process",
    "Deadline", "DeadlineTipo", "DeadlineStatus", "DeadlinePrioridade",
    "Document", "DocConfidencialidade", "DocumentIntakeBatch", "DocumentIntakeItem", "DocumentHashRescanBatch", "DocumentHashRescanItem",
    "RaioXAnalise", "RaioXDocumento",
    "LegalDoc", "PecaTipo", "PecaStatus",
    "Fee", "FeePayment", "FeeTipo", "FeeStatus",
    "EnvironmentalCase", "OrgaoAutuador", "StatusDefesa",
    "AuditLog", "criar_audit_log",
    "AILog", "AIStatusHITL", "AITipoUso", "AIProviderMetric",
    "Notification", "Feriado", "Procuracao",
    "KnowledgeDoc", "KnowledgeChunk",
    "ApiKey",
]
from app.models.template import DocTemplate  # noqa
from app.models.task import Task, TaskStatus  # noqa
from app.models.time_entry import TimeEntry  # noqa
from app.models.signature import SignatureRequest, SignatureStatus  # noqa
from app.models.push import PushSubscription  # noqa
from app.models.djen import DjenComunicacao  # noqa
from app.models.password_reset import PasswordResetToken, UserKnownIP  # noqa
from app.models.suspensao import SuspensaoTribunal  # noqa

# ── P0/P1-6: registrar TODOS os models p/ o Alembic autogenerate enxergar a
# metadata completa (causa-raiz do drift de schema). Import de módulo basta —
# executa as definições de classe e as anexa a Base.metadata.
from app.models import ai_skill            # noqa
from app.models import atendimento         # noqa
from app.models import bank_analysis       # noqa
from app.models import case_intelligence   # noqa  (snapshot versionado da inteligência do caso — migração 101)
from app.models import matriz_teses        # noqa  (Matriz de Teses estruturada — FASE 3, migração 102)
from app.models import fee_proposal        # noqa  (Proposta de honorários versionada — FASE 4, migração 103)
from app.models import case_parte          # noqa
from app.models import caso_area           # noqa
from app.models import centro_custo        # noqa
from app.models import checklist           # noqa
from app.models import contrato_societario # noqa
from app.models import data_room           # noqa
from app.models import dataroom_teses_v4_compat  # noqa  # models ORM arquivados com os routers _dead_code (PR #1115) — registro em Base.metadata mantido p/ Alembic/gate schema
from app.models import diario_oficial      # noqa
from app.models import dossie_estrategico  # noqa
from app.models import jurisprudencia_interna  # noqa
from app.models import legal_chat            # noqa
from app.models import preliminar             # noqa  (fusão aditiva Sala Jurídica + Raio-X — migração 139)
from app.models import dpt_diagnostico       # noqa  (persistência DPT360 — migração 141)
from app.models import prompt_juridico     # noqa
from app.models import socio               # noqa
from app.models import sociedade_cliente   # noqa
from app.models import tese                # noqa
from app.models import prova               # noqa
from app.models import ficha_triagem       # noqa
from app.models import solicitacao_documento  # noqa
from app.models import wiki                # noqa
from app.models import workflow            # noqa
from app.models import redesign            # noqa
from app.models import calendar_feed_credential  # noqa  (feed ICS revogável — migração 113)
from app.models.system_module_setting import SystemModuleSetting  # noqa
from app.models.nfse import NotaFiscalServico, NFSeStatus  # noqa
from app.models.route_usage_metric import RouteUsageMetric  # noqa
from app.models.scheduler_heartbeat import SchedulerHeartbeat  # noqa
from app.models.integration_credential import IntegrationCredential  # noqa  (Cofre de Credenciais — migração 108)
from app.models.processo_eletronico import (  # noqa  (MNI 2.2.2 leitura — migração 132)
    Tribunal, CredencialProcessoEletronico, SincronizacaoProcessoEletronico,
    DocumentoProcessoEletronicoDedup,
)
from app.models.saneamento import (  # noqa  (schema saneamento — migração 154)
    TpuMovimento, DatajudSnapshot, ExcecaoNumero, PlanoDedup,
    IndicativoEncerramento, Divergencia, Execucao,
)

# Registra normalização defensiva da Sala Jurídica depois que os modelos estão
# carregados: área sugerida canônica e citações legadas saneadas em memória.
from app.models import legal_chat_normalization as _legal_chat_normalization  # noqa: F401,E402

# Registra a política runtime que suprime temporariamente a exigência de TOTP sem
# alterar os valores persistidos. A importação é deliberadamente tardia para
# evitar ciclo durante a definição de User.
from app.core import two_factor_policy as _two_factor_policy  # noqa: F401,E402
