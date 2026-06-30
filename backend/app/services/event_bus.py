"""
event_bus.py — Barramento de eventos de domínio (outbox pattern), ADITIVO.

Roda AO LADO dos fluxos existentes (BackgroundTasks + APScheduler) — não
substitui nem remove nada. Cada ação de negócio relevante pode emitir um evento
que é (1) persistido na tabela `domain_events` (trilha de auditoria / outbox) e
(2) entregue a subscribers registrados.

Princípio de segurança: emitir() é FAIL-SAFE — qualquer erro é engolido e logado,
NUNCA propaga para o request do usuário. Subscribers isolados em try/except.

Como estender (sem risco): registre um subscriber com @on("caso.criado").
"""
import json
import logging
import uuid

from sqlalchemy import text

logger = logging.getLogger("ejc.event_bus")

# tipo de evento -> lista de corrotinas async(db, entidade_id, payload)
_SUBSCRIBERS: dict[str, list] = {}


def on(tipo: str):
    """Decorator para registrar um subscriber de um tipo de evento."""
    def deco(fn):
        _SUBSCRIBERS.setdefault(tipo, []).append(fn)
        return fn
    return deco


async def emitir(tipo: str, entidade: str, entidade_id, payload: dict | None = None,
                 usuario_id: str | None = None) -> None:
    """
    Persiste o evento na outbox e dispara subscribers. Idempotente do ponto de
    vista de segurança: nunca lança exceção para quem chama (BackgroundTask).
    """
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO domain_events (id, tipo, entidade, entidade_id, payload, usuario_id)
                    VALUES (:id, :tipo, :ent, :eid, CAST(:payload AS jsonb), :uid)
                """),
                {"id": str(uuid.uuid4()), "tipo": tipo, "ent": entidade,
                 "eid": str(entidade_id), "payload": json.dumps(payload or {}),
                 "uid": str(usuario_id) if usuario_id else None},
            )
            await db.commit()

            for fn in _SUBSCRIBERS.get(tipo, []):
                try:
                    await fn(db, entidade_id, payload or {})
                except Exception as e:  # subscriber isolado — não derruba os outros
                    logger.warning(f"[event_bus] subscriber de '{tipo}' falhou: {e}")
        logger.info(f"[event_bus] emitido: {tipo} ({entidade}:{entidade_id})")
    except Exception as e:
        # Outbox indisponível NÃO pode quebrar a operação de negócio.
        logger.warning(f"[event_bus] emitir('{tipo}') ignorado por erro: {e}")


# ── Helper síncrono p/ uso em BackgroundTasks do FastAPI ──────────────────────
async def emitir_caso_criado(case_id: str, usuario_id: str | None = None) -> None:
    await emitir("caso.criado", "case", case_id, {"origem": "intake"}, usuario_id)
