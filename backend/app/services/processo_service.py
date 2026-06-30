"""Accessor canonico para processos do caso.
Leitores devem usar `processo_principal(case_id, db)` em vez de `cases.numero_processo`.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def processo_principal(case_id: str, db: AsyncSession) -> dict | None:
    """Retorna o processo principal do caso (is_principal=True) ou None."""
    row = (await db.execute(text("""
        SELECT id, numero_cnj, instancia, tribunal, comarca, vara,
               classe, fase, tipo, valor_causa, status
        FROM processes
        WHERE case_id = :cid AND is_principal = TRUE AND deleted_at IS NULL
        LIMIT 1
    """), {"cid": case_id})).mappings().first()
    return dict(row) if row else None


async def numero_processo_efetivo(case_id: str, db: AsyncSession, fallback: str | None = None) -> str | None:
    """Retorna numero_cnj do processo principal, ou fallback (cases.numero_processo legado)."""
    proc = await processo_principal(case_id, db)
    if proc and proc.get("numero_cnj"):
        return proc["numero_cnj"]
    return fallback
