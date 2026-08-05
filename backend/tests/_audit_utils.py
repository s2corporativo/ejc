from sqlalchemy import text
from typing import Any, Mapping


async def expurgar_audit_por_registro(db_conn, where_sql: str, params: Mapping[str, Any] | None = None) -> None:
    """Expurga linhas de audit_logs usando a via privilegiada.

    Executa SET LOCAL ejc.audit_logs_permitir_expurgo = 'on' NA MESMA transação
    e em seguida um DELETE com a cláusula WHERE fornecida.

    Uso típico:
        await expurgar_audit_por_registro(db, "registro_id = :id", {"id": uuid})

    `db_conn` pode ser uma AsyncSession ou Connection com método execute().
    """
    params = dict(params or {})
    await db_conn.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
    await db_conn.execute(text(f"DELETE FROM audit_logs WHERE {where_sql}"), params)
