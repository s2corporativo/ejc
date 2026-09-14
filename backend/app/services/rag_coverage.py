"""Métricas agregadas de cobertura do RAG.

Não lê conteúdo nem dados de cliente: só agrega metadados e contagens. O mapa
MG/JEC inclui os documentos dedicados e também a jurisprudência genérica do
crawler TJMG (`categoria=jurisprudencia`, `tribunal=TJMG`) por mapeamento lógico,
sem duplicar `knowledge_docs`.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_COLECOES_MG_JEC = (
    "jurisprudencia_tjmg_acordaos",
    "jurisprudencia_tjmg_juizados",
    "sentencas_jec_tjmg",
    "fonaje_enunciados",
    "stj_juizados",
    "datajud_metadados",
)

_SQL_TRIBUNAL = "upper(COALESCE(NULLIF(kd.tribunal,''), NULLIF(kd.extra->>'tribunal',''), 'NAO_INFORMADO'))"
_SQL_AREA = "COALESCE(NULLIF(kd.extra->>'area',''), NULLIF(kd.extra->>'area_juridica',''), 'nao_informada')"
_SQL_RITO = "COALESCE(NULLIF(kd.extra->>'rito',''), 'nao_informado')"
_SQL_LEGAL_STATUS = (
    "lower(COALESCE(NULLIF(kd.extra->>'legal_status',''), "
    "NULLIF(kd.extra->>'situacao_normativa',''), "
    "NULLIF(kd.extra->>'vigencia_status',''), 'nao_informado'))"
)
_SQL_FONTE_VALIDADA = "lower(COALESCE(kd.extra->>'fonte_validada','')) = 'true'"
_SQL_COLECAO = (
    "COALESCE(NULLIF(kd.extra->>'collection',''), "
    "CASE WHEN lower(kd.categoria) = 'jurisprudencia' "
    f"AND {_SQL_TRIBUNAL} = 'TJMG' "
    "THEN 'jurisprudencia_tjmg_acordaos_auto' ELSE kd.categoria END)"
)
_SQL_ANO = (
    "CASE "
    "WHEN COALESCE(kd.extra->>'data_julgamento','') ~ '^\\d{4}-\\d{2}-\\d{2}' "
    "THEN left(kd.extra->>'data_julgamento', 4) "
    "WHEN COALESCE(kd.extra->>'data_julgamento','') ~ '^\\d{1,2}/\\d{1,2}/\\d{4}' "
    "THEN right(kd.extra->>'data_julgamento', 4) "
    "ELSE 'nao_informado' END"
)


def _filtro_mg_jec() -> str:
    cats = ",".join(f"'{c}'" for c in _COLECOES_MG_JEC)
    return (
        "(kd.categoria IN (" + cats + ") "
        "OR COALESCE(kd.extra->>'source_family','') = 'mg_jec' "
        f"OR (lower(kd.categoria) = 'jurisprudencia' AND {_SQL_TRIBUNAL} = 'TJMG'))"
    )


def _where(mg_jec_only: bool) -> str:
    """WHERE das métricas = vigente/não excluído + o MESMO gate de governança
    da recuperação (C3): cobertura nunca conta documento que a busca exclui
    (sem rag_status aprovado, vigência não verificada, súmula em quarentena,
    corpus fictício, revogado). Import tardio: ai_service é módulo pesado."""
    from app.services.ai_service import filtros_gate_rag

    base = (
        "kd.deleted_at IS NULL AND COALESCE(kd.vigente, TRUE) = TRUE "
        f"{filtros_gate_rag()}"
    )
    return f"{base} AND {_filtro_mg_jec()}" if mg_jec_only else base


async def medir_cobertura_rag(db: AsyncSession, *, mg_jec_only: bool = False) -> dict:
    """Retorna cobertura agregada e auditável, sem expor conteúdo dos chunks."""
    where = _where(mg_jec_only)

    resumo = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                SELECT
                    COUNT(DISTINCT kd.id) AS documentos,
                    COUNT(kc.id) AS chunks,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE kd.status_indexacao = 'indexado'
                    ) AS documentos_indexados,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE COALESCE(kd.extra->>'rag_status','') = 'aprovado'
                    ) AS documentos_aprovados,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE {_SQL_FONTE_VALIDADA}
                    ) AS fonte_validada_explicita,
                    MAX(COALESCE(kd.atualizado_em, kd.created_at)) AS ultima_atualizacao
                FROM knowledge_docs kd
                LEFT JOIN knowledge_chunks kc ON kc.doc_id = kd.id
                WHERE {where}
                """
            )
        )
    ).mappings().first()

    colecoes = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                SELECT
                    {_SQL_COLECAO} AS colecao,
                    COUNT(DISTINCT kd.id) AS documentos,
                    COUNT(kc.id) AS chunks,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE kd.status_indexacao = 'indexado'
                    ) AS indexados,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE COALESCE(kd.extra->>'rag_status','') = 'aprovado'
                    ) AS aprovados,
                    COUNT(DISTINCT kd.id) FILTER (
                        WHERE {_SQL_FONTE_VALIDADA}
                    ) AS fonte_validada_explicita,
                    MAX(COALESCE(kd.atualizado_em, kd.created_at)) AS ultima_atualizacao
                FROM knowledge_docs kd
                LEFT JOIN knowledge_chunks kc ON kc.doc_id = kd.id
                WHERE {where}
                GROUP BY {_SQL_COLECAO}
                ORDER BY documentos DESC, colecao
                """
            )
        )
    ).mappings().all()

    async def _dim(expr: str, nome: str, limit: int = 30) -> list[dict]:
        rows = (
            await db.execute(
                # SQL literal com bind params; a regra marca todo text(), sem olhar
                # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    f"""
                    SELECT {expr} AS valor, COUNT(*) AS documentos
                    FROM knowledge_docs kd
                    WHERE {where}
                    GROUP BY {expr}
                    ORDER BY documentos DESC, valor
                    LIMIT {int(limit)}
                    """
                )
            )
        ).mappings().all()
        return [
            {nome: r["valor"], "documentos": int(r["documentos"] or 0)} for r in rows
        ]

    por_tribunal = await _dim(_SQL_TRIBUNAL, "tribunal")
    por_area = await _dim(_SQL_AREA, "area")
    por_rito = await _dim(_SQL_RITO, "rito")
    por_ano = await _dim(_SQL_ANO, "ano")
    por_vigencia = await _dim(_SQL_LEGAL_STATUS, "legal_status")

    documentos = int((resumo or {}).get("documentos") or 0)
    validadas = int((resumo or {}).get("fonte_validada_explicita") or 0)
    return {
        "escopo": "mg_jec" if mg_jec_only else "rag_atual",
        "documentos": documentos,
        "chunks": int((resumo or {}).get("chunks") or 0),
        "documentos_indexados": int((resumo or {}).get("documentos_indexados") or 0),
        "documentos_aprovados": int((resumo or {}).get("documentos_aprovados") or 0),
        "fonte_validada_explicita": validadas,
        "pct_fonte_validada_explicita": (
            round(validadas / documentos * 100, 1) if documentos else 0.0
        ),
        "ultima_atualizacao": (resumo or {}).get("ultima_atualizacao"),
        "colecoes": [
            {
                "colecao": r["colecao"],
                "documentos": int(r["documentos"] or 0),
                "chunks": int(r["chunks"] or 0),
                "indexados": int(r["indexados"] or 0),
                "aprovados": int(r["aprovados"] or 0),
                "fonte_validada_explicita": int(r["fonte_validada_explicita"] or 0),
                "ultima_atualizacao": r["ultima_atualizacao"],
            }
            for r in colecoes
        ],
        "por_tribunal": por_tribunal,
        "por_area": por_area,
        "por_rito": por_rito,
        "por_ano": por_ano,
        "por_vigencia": por_vigencia,
        "metodologia": {
            "conta_apenas_versao_tecnica_vigente": True,
            "conteudo_exposto": False,
            "tjmg_generico_mapeado_sem_duplicacao": True,
            "tjmg_generico_colecao_logica": "jurisprudencia_tjmg_acordaos_auto",
            "fonte_validada_explicita": (
                "Conta somente extra.fonte_validada=true; ausência do metadado "
                "não é inferida como validação."
            ),
        },
    }
