from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func

from app.core.database import Base


class RouteUsageMetric(Base):
    """Uso AGREGADO das rotas candidatas à remoção (Onda 3 §4.5 · decisão da Onda 5).

    Uma linha por (rota, método, papel, hora): o caminho quente apenas incrementa
    um contador em memória e um job periódico faz o UPSERT somando a contagem
    aqui — não há INSERT por request.

    Privacidade (LGPD): grava só o TEMPLATE da rota (``/api/casos/{case_id}``),
    o método, o PAPEL do usuário e a hora truncada. Nunca user_id, IP,
    querystring, corpo ou qualquer identificador pessoal. Por isso NÃO substitui
    a trilha de auditoria (``audit_logs``), que tem finalidade probatória.
    """

    __tablename__ = "route_usage_metrics"
    __table_args__ = (
        UniqueConstraint("rota", "metodo", "papel", "hora", name="uq_route_usage_bucket"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    rota = Column(String(200), nullable=False, index=True)   # template, sem ids concretos
    metodo = Column(String(10), nullable=False)
    papel = Column(String(40), nullable=False)               # papel RBAC, não usuário
    hora = Column(DateTime(timezone=True), nullable=False, index=True)   # bucket horário UTC

    contagem = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
