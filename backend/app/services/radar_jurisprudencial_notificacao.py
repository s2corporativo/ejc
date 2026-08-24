# ── app/services/radar_jurisprudencial_notificacao.py ────────────────────────
# Radar Jurisprudencial — notificação (PR 4, Commit 8).
#
# Só alertas "critica"/"alta" notificam ativamente — "media"/"baixa" ficam
# visíveis só via GET /teses/alertas (evita fadiga de alerta; parametrizável
# depois se a experiência de uso pedir).
#
# Destinatários: `Tese.validada_por` de cada tese afetada (quem por último
# validou aquela tese é quem mais precisa saber que algo novo pode ameaçá-la)
# — OU, se nenhuma tese afetada tiver `validada_por` preenchido, TODOS os
# usuários ativos advogado+ (mesmo piso de `routers.teses._pode_editar`),
# mesmo padrão de `_notificar_equipe` do radar legislativo. Sem serviço
# central de "quem recebe alerta jurídico" no repo — esta é a primeira
# decisão de design nesse sentido, documentada aqui em vez de em um módulo
# genérico novo (evita generalizar prematuramente a partir de 1 caso de uso).
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.tese import Tese
from app.models.user import User
from app.services.notification_service import notificar

logger = logging.getLogger("ejc.radar_jurisprudencial")

SEVERIDADES_QUE_NOTIFICAM = frozenset({"critica", "alta"})

_ROLES_ADVOGADO_MAIS = frozenset(
    r for r, nivel in ROLE_LEVEL.items() if nivel >= ROLE_LEVEL["advogado"]
)


async def _destinatarios(db: AsyncSession, teses_afetadas: list[dict]) -> list[str]:
    tese_ids = [t["tese_id"] for t in teses_afetadas if t.get("tese_id")]
    validadores: set[str] = set()
    if tese_ids:
        linhas = (await db.execute(
            select(Tese.validada_por).where(
                Tese.id.in_(tese_ids), Tese.validada_por.is_not(None),
            )
        )).scalars().all()
        validadores = {v for v in linhas if v}
    if validadores:
        return sorted(validadores)

    linhas = (await db.execute(
        select(User.id).where(
            User.is_active.is_(True), User.deleted_at.is_(None),
            User.role.in_(_ROLES_ADVOGADO_MAIS),
        )
    )).scalars().all()
    return sorted(linhas)


async def notificar_alerta(db: AsyncSession, alerta, teses_afetadas: list[dict]) -> int:
    """Notifica os destinatários de um alerta recém-criado, se a severidade
    justificar. Retorna quantos usuários foram notificados (0 se a
    severidade não notifica ou não há destinatário). Nunca levanta —
    notificação é enriquecimento, não deve derrubar o radar."""
    if alerta.severidade not in SEVERIDADES_QUE_NOTIFICAM:
        return 0
    try:
        destinatarios = await _destinatarios(db, teses_afetadas)
        titulo = f"Radar Jurisprudencial: possível impacto ({alerta.severidade})"
        mensagem = (
            f"{alerta.titulo or 'Decisão nova'} ({alerta.tribunal or 'tribunal não informado'}) "
            f"pode afetar {len(teses_afetadas)} tese(s) do banco. Revisar em "
            f"/teses/alertas."
        )
        for user_id in destinatarios:
            await notificar(
                db, user_id, titulo, mensagem,
                tipo="alerta_juridico", link=f"/teses/alertas/{alerta.id}",
            )
        return len(destinatarios)
    except Exception as e:
        logger.warning("Falha ao notificar alerta %s do radar: %s", alerta.id, e)
        return 0
