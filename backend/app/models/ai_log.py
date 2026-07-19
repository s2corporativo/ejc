# ── app/models/ai_log.py ─────────────────────────────────────────────────────
from __future__ import annotations

import enum
import re
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Boolean, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship, validates

from app.core.database import Base

_TRIBUNAL_REF = re.compile(
    r"\b(STF|STJ|TST|TSE|STM|CNJ|TJ[A-Z]{2}|TRF[1-6]|TRT\d{1,2}|TRE[-/]?[A-Z]{2})\b",
    re.I,
)
_DATA_REF = re.compile(r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{2}-\d{2})\b")
_TERMO_REF = re.compile(
    r"\b(ac[oó]rd[aã]o|julgad[oa]|precedente|REsp|AREsp|AgInt|AgRg|RHC|HC|MS|ADI|ADPF|tema)\b",
    re.I,
)


def normalizar_modelo_ia(modelo: str | None) -> str | None:
    if not modelo:
        return modelo
    m = modelo.strip()
    if not m:
        return m
    if "/" in m:
        return m
    if m.lower().startswith("llama"):
        return f"groq/{m}"
    if m.lower().startswith("claude"):
        return f"anthropic/{m}"
    return m


def _proteger_cnj_jurisprudencial(texto: str) -> tuple[str, dict[str, str]]:
    """Protege temporariamente apenas CNJ com contexto inequívoco de citação.

    O AILog alimenta o gate de citações no momento da aprovação HITL. Mascarar
    todo número CNJ tornaria esse gate inoperante. Por outro lado, preservar o
    número do processo do próprio cliente seria exposição desnecessária.

    Um CNJ só é preservado quando a janela próxima contém tribunal reconhecível
    E marcador jurídico de precedente ou data. Demais números de processo seguem
    pseudonimizados normalmente.
    """
    from app.services.sanitizer import _PATTERNS

    processo_re = next(pattern for pattern, placeholder in _PATTERNS if placeholder == "[PROCESSO]")
    refs: dict[str, str] = {}

    def repl(match: re.Match) -> str:
        ini = max(0, match.start() - 220)
        fim = min(len(texto), match.end() + 220)
        janela = texto[ini:fim]
        if _TRIBUNAL_REF.search(janela) and (_TERMO_REF.search(janela) or _DATA_REF.search(janela)):
            token = f"[[REF_JULGADO_{len(refs) + 1:03d}]]"
            refs[token] = match.group(0)
            return token
        return match.group(0)

    return processo_re.sub(repl, texto), refs


def pseudonimizar_texto_auditoria(valor: str | None) -> str | None:
    """Pseudonimiza PII persistida sem destruir referências para citation gate."""
    if valor is None:
        return None
    texto = str(valor)
    if not texto:
        return texto
    protegido, refs = _proteger_cnj_jurisprudencial(texto)
    try:
        from app.services.ai.pseudonymizer import pseudonimizar
        limpo, _ = pseudonimizar(protegido)
    except Exception:
        from app.services.sanitizer import sanitizar_pii
        limpo, _ = sanitizar_pii(protegido)
    for token, cnj in refs.items():
        limpo = limpo.replace(token, cnj)
    return limpo


class AIStatusHITL(str, enum.Enum):
    gerado = "gerado"
    revisado = "revisado"
    aplicado = "aplicado"
    descartado = "descartado"


class AITipoUso(str, enum.Enum):
    analise_caso = "analise_caso"
    redacao_peca = "redacao_peca"
    consulta_rag = "consulta_rag"
    resumo_documento = "resumo_documento"
    outro = "outro"


class AILog(Base):
    __tablename__ = "ai_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)

    tipo_uso = Column(SAEnum(AITipoUso), nullable=False)
    modelo = Column(String(50), nullable=False, default="nao_informado")

    prompt_sanitizado = Column(Text, nullable=False)
    pii_removida = Column(Boolean, default=False)
    resposta = Column(Text, nullable=True)
    critica_adversarial = Column(Text, nullable=True)
    fontes_rag = Column(Text, nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    custo_estimado = Column(Numeric(12, 6), nullable=True)

    status_hitl = Column(SAEnum(AIStatusHITL), nullable=False, default=AIStatusHITL.gerado, index=True)
    revisado_por = Column(String(36), nullable=True)
    revisado_em = Column(DateTime(timezone=True), nullable=True)

    feedback = Column(String(20), nullable=True)
    feedback_em = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="ai_logs")

    @validates("modelo")
    def _normalizar_modelo(self, key, value):
        return normalizar_modelo_ia(value)

    @validates("resposta", "critica_adversarial")
    def _pseudonimizar_saida(self, key, value):
        return pseudonimizar_texto_auditoria(value)
