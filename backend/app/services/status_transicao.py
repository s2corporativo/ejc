# ── app/services/status_transicao.py ─────────────────────────────────────────
# Transições automáticas de estado do caso (Bloco 3, seção 6 do desenho —
# decisão do titular 2026-08-02: mover SOZINHO, sempre para frente, nunca
# regredir; o advogado pode corrigir manualmente).
#
#   documento_vinculado : aberto → em_instrucao
#   peca_criada         : aberto|em_instrucao → em_producao
#   peca_protocolada    : aberto|em_instrucao|em_producao → protocolado
#
# Invariantes:
#   • NUNCA regride (o destino só é aplicado se o estado atual for uma origem
#     permitida — estados já à frente ficam como estão);
#   • NUNCA toca encerrado/arquivado (terminais);
#   • cada avanço registra CaseMovimento tipo "nota" NA MESMA transação do
#     evento — chamador comita (ou dá rollback) junto com a operação principal.
from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento, CaseStatus

logger = logging.getLogger("ejc.status_transicao")

#: evento → (estados de origem que avançam, estado de destino)
TRANSICOES_POR_EVENTO: dict[str, tuple[frozenset[CaseStatus], CaseStatus]] = {
    "documento_vinculado": (
        frozenset({CaseStatus.aberto}),
        CaseStatus.em_instrucao,
    ),
    "peca_criada": (
        frozenset({CaseStatus.aberto, CaseStatus.em_instrucao}),
        CaseStatus.em_producao,
    ),
    "peca_protocolada": (
        frozenset({CaseStatus.aberto, CaseStatus.em_instrucao, CaseStatus.em_producao}),
        CaseStatus.protocolado,
    ),
}

#: Estados terminais — a transição automática jamais os toca.
STATUS_TERMINAIS: frozenset[CaseStatus] = frozenset(
    {CaseStatus.encerrado, CaseStatus.arquivado}
)


def _status_atual(case: Case) -> CaseStatus | None:
    """Status como enum, tolerante a valor string (fakes/dados antigos)."""
    valor = case.status
    if isinstance(valor, CaseStatus):
        return valor
    try:
        return CaseStatus(valor) if valor is not None else None
    except ValueError:
        return None


async def avancar_status_por_evento(
    db: AsyncSession, case: Case | None, evento: str, *, user_id: str | None = None,
) -> bool:
    """Avança o estado do caso em função do evento, NA transação corrente.

    Retorna True quando houve avanço (status alterado + CaseMovimento "nota"
    adicionado à sessão, sem commit — o commit é do chamador, junto com a
    operação principal). False quando não há nada a fazer: evento desconhecido,
    caso ausente/excluído, estado terminal, ou estado já igual/à frente do
    destino (nunca regride).
    """
    if case is None or getattr(case, "deleted_at", None) is not None:
        return False
    regra = TRANSICOES_POR_EVENTO.get(evento)
    if regra is None:
        logger.warning("Evento de transição de estado desconhecido: %r", evento)
        return False
    origens, destino = regra
    atual = _status_atual(case)
    if atual is None or atual in STATUS_TERMINAIS or atual not in origens:
        return False
    case.status = destino
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case.id, tipo="nota",
        descricao=(
            f"Estado avançado automaticamente para {destino.value} "
            f"(evento: {evento}) — ajuste manual disponível."
        ),
        created_by=user_id,
    ))
    logger.info(
        "Caso %s: %s → %s (evento %s)", case.id,
        atual.value, destino.value, evento,
    )
    return True


async def avancar_status_pos_commit(
    db: AsyncSession, case_id: str | None, evento: str, *, user_id: str | None = None,
) -> bool:
    """Variante FAIL-SAFE para chamadas APÓS o commit da operação principal
    (upload de documento, criação de peça, registro de protocolo): a operação
    já está persistida, então falha na transição vira warning e segue — nunca
    propaga. Faz commit próprio quando avança; rollback próprio quando falha.

    Não usar dentro da transação principal — lá o ponto certo é
    `avancar_status_por_evento` (falha deve abortar junto, sem engolir
    IntegrityError).
    """
    if not case_id:
        return False
    try:
        case = await db.get(Case, case_id)
        if await avancar_status_por_evento(db, case, evento, user_id=user_id):
            await db.commit()
            return True
        return False
    except Exception as e:
        try:
            await db.rollback()
        except Exception:  # sessão já invalidada — nada mais a desfazer
            pass
        logger.warning(
            "Transição automática de estado falhou (case=%s, evento=%s): %s",
            case_id, evento, e,
        )
        return False
