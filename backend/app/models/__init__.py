# ── app/models/__init__.py ────────────────────────────────────────────────────
# Exporta todos os modelos para o Alembic detectar via Base.metadata
from app.models.user import User, RefreshToken, UserRole
from app.models.client import Client, ClientTipo, ClientStatus, ClientOrigem
from app.models.case import Case, CaseMovimento, CaseArea, CaseStatus, CaseFase, CasePrioridade
from app.models.process import Process
from app.models.deadline import Deadline, DeadlineTipo, DeadlineStatus, DeadlinePrioridade
from app.models.document import Document, DocConfidencialidade
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
    "Document", "DocConfidencialidade",
    "LegalDoc", "PecaTipo", "PecaStatus",
    "Fee", "FeePayment", "FeeTipo", "FeeStatus",
    "EnvironmentalCase", "OrgaoAutuador", "StatusDefesa",
    "AuditLog", "criar_audit_log",
    "AILog", "AIStatusHITL", "AITipoUso",
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
from app.models import case_parte          # noqa
from app.models import caso_area           # noqa
from app.models import centro_custo        # noqa
from app.models import checklist           # noqa
from app.models import contrato_societario # noqa
from app.models import data_room           # noqa
from app.models import diario_oficial      # noqa
from app.models import dossie_estrategico  # noqa
from app.models import jurisprudencia_interna  # noqa
from app.models import prompt_juridico     # noqa
from app.models import socio               # noqa
from app.models import sociedade_cliente   # noqa  (sociedades de CLIENTES — vertical Empresarial, migração 071)
from app.models import tese                # noqa
from app.models import prova               # noqa  (Gestão de Provas por caso — migração 073)
from app.models import wiki                # noqa
from app.models import workflow            # noqa
from app.models import redesign            # noqa  (module_help, area_modulos_mapping, document_types_master, tabela_oab_honorarios — migração 057)
from app.models.system_module_setting import SystemModuleSetting  # noqa
