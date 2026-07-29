"""Diagnóstico de integridade referencial — SOMENTE LEITURA.

O relatório identifica dependentes de pais soft-deletados, referências físicas
inválidas e divergências de contadores sem alterar dados nem expor PII.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Teto de IDs retornados por achado. O total permanece exato, mas a transferência
# e a memória do worker ficam limitadas no próprio banco.
LIMITE_IDS = 100


async def _achado(
    db: AsyncSession,
    *,
    tipo: str,
    sql: str,
    entidade: str,
    entidade_pai: str | None,
    estado_pai: str | None,
    severidade: str,
    acao_recomendada: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Conta o conjunto completo e materializa no máximo ``LIMITE_IDS`` IDs.

    ``sql`` deve projetar exatamente uma coluna ``id`` e não conter ponto e
    vírgula final. A primeira consulta obtém apenas ``COUNT(*)``; a segunda
    aplica ``LIMIT`` no PostgreSQL. Assim o limite não é apenas cosmético no
    payload e o diagnóstico continua seguro mesmo em banco muito degradado.
    """
    consulta = sql.strip().rstrip(";")
    parametros = dict(params or {})

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM ( {consulta} ) AS diagnostico"),
            parametros,
        )
    ).scalar_one()
    total = int(total or 0)

    parametros_ids = {**parametros, "_limite_ids": LIMITE_IDS}
    ids = [
        str(valor)
        for valor in (
            await db.execute(
                text(f"{consulta}\nLIMIT :_limite_ids"),
                parametros_ids,
            )
        ).scalars().all()
    ]

    return {
        "tipo": tipo,
        "entidade": entidade,
        "entidade_pai": entidade_pai,
        "estado_pai": estado_pai,
        "severidade": severidade,
        "total": total,
        "ids": ids,
        "truncado": total > len(ids),
        "acao_recomendada": acao_recomendada,
    }


def _sql_dependente_de_caso_excluido(tabela: str) -> str:
    return f"""
        SELECT f.id FROM {tabela} f
        JOIN cases c ON c.id = f.case_id
        WHERE f.deleted_at IS NULL AND c.deleted_at IS NOT NULL
        ORDER BY f.id
    """


def _sql_dependente_de_caso_inexistente(tabela: str) -> str:
    return f"""
        SELECT f.id FROM {tabela} f
        LEFT JOIN cases c ON c.id = f.case_id
        WHERE f.deleted_at IS NULL AND f.case_id IS NOT NULL AND c.id IS NULL
        ORDER BY f.id
    """


async def diagnosticar_integridade(db: AsyncSession) -> dict[str, Any]:
    """Gera relatório completo de integridade sem escrita ou correção automática."""
    achados: list[dict[str, Any]] = []

    for tabela, tipo, entidade, severidade, acao in (
        (
            "legal_docs",
            "peca_de_caso_excluido",
            "legal_docs",
            "alta",
            "Nenhuma exclusão. A peça deve herdar a invisibilidade do caso nas "
            "superfícies operacionais; restaurar o caso a traz de volta.",
        ),
        (
            "documents",
            "documento_de_caso_excluido",
            "documents",
            "alta",
            "Nenhuma exclusão. Avaliar se o documento deve ser reclassificado "
            "para o GED geral ou seguir a visibilidade do caso.",
        ),
        (
            "deadlines",
            "prazo_de_caso_excluido",
            "deadlines",
            "critica",
            "Nenhuma exclusão. Prazo vivo de caso excluído pode gerar alerta "
            "fantasma ou esconder prazo real — exige conferência humana.",
        ),
        (
            "tasks",
            "tarefa_de_caso_excluido",
            "tasks",
            "media",
            "Nenhuma exclusão. Reatribuir ou encerrar a tarefa conforme decisão "
            "do responsável.",
        ),
    ):
        achados.append(
            await _achado(
                db,
                tipo=tipo,
                sql=_sql_dependente_de_caso_excluido(tabela),
                entidade=entidade,
                entidade_pai="cases",
                estado_pai="excluido",
                severidade=severidade,
                acao_recomendada=acao,
            )
        )

    for tabela, tipo in (
        ("legal_docs", "peca_com_caso_inexistente"),
        ("documents", "documento_com_case_id_invalido"),
        ("deadlines", "prazo_com_case_id_invalido"),
        ("tasks", "tarefa_com_referencia_invalida"),
    ):
        achados.append(
            await _achado(
                db,
                tipo=tipo,
                sql=_sql_dependente_de_caso_inexistente(tabela),
                entidade=tabela,
                entidade_pai="cases",
                estado_pai="inexistente",
                severidade="critica",
                acao_recomendada=(
                    "Esperado zero: há FK real para cases.id. Valor diferente "
                    "de zero indica FK ausente ou carga fora do ORM — investigar "
                    "a migration mais recente antes de corrigir dados."
                ),
            )
        )

    achados.append(
        await _achado(
            db,
            tipo="caso_com_cliente_excluido",
            sql="""
                SELECT c.id FROM cases c
                JOIN clients cl ON cl.id = c.client_id
                WHERE c.deleted_at IS NULL AND cl.deleted_at IS NOT NULL
                ORDER BY c.id
            """,
            entidade="cases",
            entidade_pai="clients",
            estado_pai="excluido",
            severidade="alta",
            acao_recomendada=(
                "Nenhuma exclusão. Restaurar o cliente ou reatribuir a "
                "titularidade após conferência humana."
            ),
        )
    )

    achados.append(
        await _achado(
            db,
            tipo="caso_com_cliente_inexistente",
            sql="""
                SELECT c.id FROM cases c
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE c.deleted_at IS NULL AND cl.id IS NULL
                ORDER BY c.id
            """,
            entidade="cases",
            entidade_pai="clients",
            estado_pai="inexistente",
            severidade="critica",
            acao_recomendada=(
                "Esperado zero: cases.client_id é NOT NULL com FK para clients.id."
            ),
        )
    )

    achados.append(
        await _achado(
            db,
            tipo="documento_orfao_invalido",
            sql="""
                SELECT d.id FROM documents d
                WHERE d.deleted_at IS NULL
                  AND d.case_id IS NULL
                  AND d.client_id IS NULL
                  AND (d.uploaded_by IS NULL OR d.uploaded_by = '')
                ORDER BY d.id
            """,
            entidade="documents",
            entidade_pai=None,
            estado_pai=None,
            severidade="media",
            acao_recomendada=(
                "Nenhuma exclusão. Classificar manualmente ou mover para o GED "
                "institucional. Documento sem caso, mas com cliente ou autor, é "
                "triagem legítima e não aparece neste achado."
            ),
        )
    )

    contadores = await _conferir_contadores(db)
    if contadores["divergente"]:
        achados.append(
            {
                "tipo": "divergencia_contador_agregado_vs_listagem",
                "entidade": "cases",
                "entidade_pai": None,
                "estado_pai": None,
                "severidade": "alta",
                "total": 1,
                "ids": [],
                "truncado": False,
                "acao_recomendada": (
                    "Dashboard e listagem devem derivar de core/status_caso.py. "
                    "A divergência indica uma definição paralela de caso ativo."
                ),
                "detalhe": contadores,
            }
        )

    total_achados = sum(achado["total"] for achado in achados)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "somente_leitura": True,
        "achados": achados,
        "contadores": contadores,
        "resumo": {
            "tipos_com_achado": [
                achado["tipo"] for achado in achados if achado["total"]
            ],
            "total_registros_afetados": total_achados,
            "integro": total_achados == 0,
        },
    }


async def _conferir_contadores(db: AsyncSession) -> dict[str, Any]:
    """Compara a definição canônica de ativos com a antiga por subtração."""
    from app.core.status_caso import STATUS_ABERTOS, STATUS_FECHADOS

    abertos = [status.value for status in STATUS_ABERTOS]
    fechados = [status.value for status in STATUS_FECHADOS]

    linha = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = ANY(:abertos)) AS ativos,
                  COUNT(*) FILTER (WHERE status = ANY(:fechados)) AS fechados,
                  COUNT(*) FILTER (WHERE status = 'arquivado') AS arquivados
                FROM cases WHERE deleted_at IS NULL
                """
            ),
            {"abertos": abertos, "fechados": fechados},
        )
    ).one()

    excluidos = (
        await db.execute(
            text("SELECT COUNT(*) FROM cases WHERE deleted_at IS NOT NULL")
        )
    ).scalar() or 0
    listagem_padrao = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM cases WHERE deleted_at IS NULL "
                "AND status <> 'arquivado'"
            )
        )
    ).scalar() or 0

    total, ativos, fechados_n, arquivados = linha
    por_subtracao = total - fechados_n
    return {
        "total_geral": total,
        "total_ativo": ativos,
        "total_arquivado": arquivados,
        "total_excluido": excluidos,
        "total_listagem_padrao": listagem_padrao,
        "ativos_agregado": ativos,
        "ativos_por_subtracao": por_subtracao,
        "divergente": ativos != por_subtracao,
    }
