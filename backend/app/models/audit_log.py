# ── app/models/audit_log.py ──────────────────────────────────────────────────
# Log de auditoria IMUTÁVEL — nunca editar/deletar registros (LGPD art. 37)
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    user_role = Column(String(30), nullable=True)
    ip = Column(String(45), nullable=True)

    acao = Column(String(30), nullable=False, index=True)
    entidade = Column(String(50), nullable=False, index=True)
    registro_id = Column(String(36), nullable=True, index=True)

    dados_antes = Column(JSONB, nullable=True)
    dados_depois = Column(JSONB, nullable=True)
    detalhes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="audit_logs")


def _minimizar_payload_upload(payload: dict | None) -> dict | None:
    """Remove nomes/erros por arquivo antes de persistir evento UPLOAD em WORM.

    Nomes de arquivo podem conter CPF, número de processo ou nome de cliente.
    Para rastreabilidade do ato bastam os IDs das entidades criadas e as
    contagens de duplicidade/erro; a resposta funcional ao usuário continua
    contendo os detalhes necessários para correção imediata do lote.
    """
    if payload is None:
        return None
    saida = dict(payload)
    for chave in ("duplicados", "erros"):
        if chave not in saida:
            continue
        valor = saida.pop(chave)
        if isinstance(valor, (list, tuple, set)):
            saida[f"{chave}_count"] = len(valor)
        elif valor is None:
            saida[f"{chave}_count"] = 0
        else:
            # Formato inesperado: não serializar valor potencialmente sensível.
            saida[f"{chave}_count"] = 1
    return saida


async def criar_audit_log(
    db,
    user_id: str | None,
    user_role: str | None,
    acao: str,
    entidade: str,
    registro_id: str | None = None,
    detalhes: str | None = None,
    ip: str | None = None,
    dados_antes: dict | None = None,
    dados_depois: dict | None = None,
):
    """Grava auditoria na mesma transação da operação principal.

    Quando o chamador não passa ``ip``, usa o endereço capturado pelo
    ``ClientIPMiddleware``. Eventos ``UPLOAD`` sofrem minimização adicional
    antes do WORM para não tornar nomes de arquivo/erros por arquivo um dado
    pessoal permanentemente retido.
    """
    if ip is None:
        from app.core.request_context import get_client_ip

        ip = get_client_ip()
    if acao.upper() == "UPLOAD":
        dados_antes = _minimizar_payload_upload(dados_antes)
        dados_depois = _minimizar_payload_upload(dados_depois)
    log = AuditLog(
        id=str(uuid4()),
        user_id=user_id,
        user_role=user_role,
        acao=acao,
        entidade=entidade,
        registro_id=registro_id,
        detalhes=detalhes,
        ip=ip,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
    )
    db.add(log)
    # Commit pelo chamador (mesma transação da operação principal)
