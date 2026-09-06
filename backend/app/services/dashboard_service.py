# ── app/services/dashboard_service.py ────────────────────────────────────────
# Coleta consolidada dos KPIs gerenciais do mês (domain).
# Extraído de routers/dashboard.py para corrigir a violação de camada
# domain→api: o scheduler (job_relatorio_mensal) precisava desses dados mas
# importava do router. Agora router e scheduler consomem este serviço.
from sqlalchemy import text

from app.core.status_caso import STATUS_ABERTOS

# Literais do enum interpolados a partir da fonte canônica — valores controlados
# pelo servidor, nunca por entrada de usuário. Antes eram strings repetidas
# ('ativo','triagem') que a migration 126 tornaria inválidas em runtime.
_ABERTOS_SQL = ",".join(f"'{s.value}'" for s in STATUS_ABERTOS)
from sqlalchemy.ext.asyncio import AsyncSession


async def coletar_dados_mes(db: AsyncSession, mes: int, ano: int) -> dict:
    """Coleta consolidada — reutilizada pelo endpoint (relatorio_mensal) e
    pelo scheduler (job_relatorio_mensal)."""
    r = await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM created_at)=:m
                             AND EXTRACT(YEAR  FROM created_at)=:a) AS abertos,
          COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM data_encerramento)=:m
                             AND EXTRACT(YEAR  FROM data_encerramento)=:a) AS encerrados
        FROM cases WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    abertos, encerrados = r.one()

    r = await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE status='concluido'
                             AND EXTRACT(MONTH FROM data_conclusao)=:m
                             AND EXTRACT(YEAR  FROM data_conclusao)=:a) AS cumpridos,
          -- Mesmo defeito de `routers/dashboard.py`: o job das 07:10 troca
          -- 'pendente' por 'vencido' e o contador ia a zero. Vencido é o que
          -- passou da data sem ser cumprido nem cancelado.
          COUNT(*) FILTER (WHERE status NOT IN ('concluido','cancelado')
                             AND data_prazo < CURRENT_DATE) AS vencidos
        FROM deadlines WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    cumpridos, vencidos = r.one()

    r = await db.execute(text("""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
            AND EXTRACT(MONTH FROM data_pagamento)=:m
            AND EXTRACT(YEAR FROM data_pagamento)=:a),0),
          COALESCE(SUM(valor) FILTER (WHERE status='pendente'),0),
          COALESCE(SUM(valor) FILTER (WHERE status='atrasado'),0)
        FROM fees WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    recebido, pendente, atrasado = r.one()

    # SQL literal com bind params; a regra marca todo text(), sem olhar
    # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    r = await db.execute(text("""
        SELECT u.full_name,
          COUNT(DISTINCT c.id) FILTER (WHERE c.status IN ({abertos})) AS casos,
          COUNT(DISTINCT d.id) FILTER (WHERE EXTRACT(MONTH FROM d.data_prazo)=:m
                                         AND EXTRACT(YEAR FROM d.data_prazo)=:a) AS prazos,
          COUNT(DISTINCT d.id) FILTER (WHERE d.status='concluido'
                                         AND EXTRACT(MONTH FROM d.data_conclusao)=:m
                                         AND EXTRACT(YEAR FROM d.data_conclusao)=:a) AS cumpridos
        FROM users u
        LEFT JOIN cases c ON c.advogado_responsavel_id=u.id AND c.deleted_at IS NULL
        LEFT JOIN deadlines d ON d.responsavel_id=u.id AND d.deleted_at IS NULL
        WHERE u.role IN ('socio','advogado','advogado_auxiliar')
          AND u.is_active=true AND u.deleted_at IS NULL
        GROUP BY u.full_name ORDER BY u.full_name
    """.format(abertos=_ABERTOS_SQL)), {"m": mes, "a": ano})
    advogados = [{"nome": x[0], "casos": x[1], "prazos": x[2], "cumpridos": x[3]}
                 for x in r]

    r = await db.execute(text("""
        SELECT area, COUNT(*) FROM cases
        WHERE deleted_at IS NULL AND status NOT IN ('encerrado','arquivado')
        GROUP BY area ORDER BY COUNT(*) DESC
    """))
    por_area = [{"area": x[0], "total": x[1]} for x in r]

    r = await db.execute(text("""
        SELECT COUNT(*) FROM legal_docs
        WHERE deleted_at IS NULL AND ai_generated=true AND human_reviewed=false
    """))
    pecas_hitl = r.scalar() or 0

    return {
        "casos_abertos": abertos, "casos_encerrados": encerrados,
        "prazos_cumpridos": cumpridos, "prazos_vencidos": vencidos,
        "fin_recebido": float(recebido), "fin_pendente": float(pendente),
        "fin_atrasado": float(atrasado),
        "advogados": advogados, "por_area": por_area,
        "pecas_hitl": pecas_hitl,
    }
