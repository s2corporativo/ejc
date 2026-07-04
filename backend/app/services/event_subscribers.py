"""
event_subscribers.py — Subscribers do barramento de eventos (ativação da
arquitetura orientada a eventos do EJC).

Importado em main.py por efeito colateral: ao importar, os decorators @on
registram os handlers no event_bus. Cada subscriber é ISOLADO (o event_bus já
captura exceções e nunca derruba o request) e ADITIVO — não duplica fluxos
diretos já existentes (triagem, notificações de prazo, kanban, etc.).

Eventos hoje emitidos pelo sistema:
  caso.criado       (cases.criar)
  caso.atualizado   (cases.atualizar)
  caso.encerrado    (cases.encerrar_caso)
  movimento.criado  (cases.criar_movimento)
  documento.importado (cases.aplicar_extracao)
"""
from __future__ import annotations
import logging

from app.services.event_bus import on

logger = logging.getLogger("ejc.event_subscribers")

# Tipos de andamento que valem tradução automática em linguagem simples.
_TRADUZ_TIPOS = {"intimacao", "decisao", "peticao", "audiencia", "movimento"}

# Tipos "públicos" que o cliente pode ser avisado (sem 'peticao', que é
# estratégia/produção interna, e sem 'ia'/notas internas).
_TIPOS_PUBLICOS_CLIENTE = {"intimacao", "decisao", "audiencia", "movimento"}


@on("movimento.criado")
async def _traduzir_andamento(db, entidade_id, payload):
    """Ao registrar um andamento oficial, gera o resumo em linguagem simples (IA).
    Notas internas e itens 'ia' são ignorados (não precisam de tradução)."""
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TRADUZ_TIPOS:
        return
    from app.services.movimento_ia import traduzir_movimento
    await traduzir_movimento(db, entidade_id)


@on("movimento.criado")
async def _notificar_cliente_movimento(db, entidade_id, payload):
    """Avisa o cliente (portal) quando há um novo andamento público no caso.

    LGPD/segurança: a notificação é GENÉRICA por design. NUNCA carrega teor do
    andamento, PII, estratégia ou conteúdo interno — apenas um aviso de que houve
    atualização, com a referência mínima do número interno do caso (quando houver).
    Notas internas e itens 'ia'/'peticao' são ignorados.
    """
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TIPOS_PUBLICOS_CLIENTE:
        return

    from sqlalchemy import select
    from app.models.case import Case
    from app.models.user import User, UserRole
    from app.services.notification_service import criar_notificacao_interna

    # Carrega o caso e descobre o cliente vinculado.
    caso = await db.get(Case, entidade_id)
    if caso is None or not caso.client_id:
        return

    # Usuário-cliente = User com role cliente_externo vinculado a este client_id,
    # ativo e não removido. Pode haver mais de um acesso ao portal.
    res = await db.execute(
        select(User).where(
            User.client_id == caso.client_id,
            User.role == UserRole.cliente_externo,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    usuarios_cliente = res.scalars().all()
    if not usuarios_cliente:
        return  # cliente sem acesso ao portal: nada a notificar

    ref = f" (caso {caso.numero_interno})" if caso.numero_interno else ""
    for user in usuarios_cliente:
        await criar_notificacao_interna(
            db,
            user_id=user.id,
            titulo="Atualização no seu processo",
            mensagem=f"Há uma nova atualização no seu processo{ref}.",
            tipo="processo",
        )


@on("caso.encerrado")
async def _log_encerramento(db, entidade_id, payload):
    """Trilha leve de encerramento (o aprendizado institucional já roda em
    background no handler; aqui só registramos o evento de domínio)."""
    logger.info(
        f"[evento] caso.encerrado {entidade_id} "
        f"resultado={(payload or {}).get('resultado')}"
    )


@on("documento.importado")
async def _log_importacao(db, entidade_id, payload):
    logger.info(
        f"[evento] documento.importado → caso {entidade_id} "
        f"(partes={(payload or {}).get('partes', 0)}, areas={(payload or {}).get('areas', 0)})"
    )
