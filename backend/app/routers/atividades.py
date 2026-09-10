"""Read-model canônico da Central de Atividades.

A VIEW ``vw_atividades`` unifica leitura de prazos, tarefas, suspensões, agenda e
intimações sem criar uma segunda entidade de domínio. Cada ação de escrita
continua no módulo de origem.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])

_URGENCIAS = {"vencido", "critico", "atencao", "normal"}


def _filtro_urgencia_sql(urgencia: str) -> str:
    """Traduz a mesma regra exibida no response para filtro no banco."""
    if urgencia == "vencido":
        return "v.data::date < CURRENT_DATE"
    if urgencia == "critico":
        return "v.data::date BETWEEN CURRENT_DATE AND CURRENT_DATE + 3"
    if urgencia == "atencao":
        return "v.data::date BETWEEN CURRENT_DATE + 4 AND CURRENT_DATE + 7"
    return "(v.data IS NULL OR v.data::date > CURRENT_DATE + 7)"


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    case_id: str | None = None,
    client_id: str | None = None,
    responsavel_id: str | None = None,
    urgencia: str | None = None,
    minha_fila: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista a fila operacional única, sempre sob o escopo do usuário atual.

    Os filtros são aditivos e usam parâmetros bindados. ``minha_fila`` significa
    responsabilidade direta; para perfis não-gestão o gate de carteira continua
    valendo independentemente dos filtros solicitados.
    """
    if urgencia is not None and urgencia not in _URGENCIAS:
        raise HTTPException(
            status_code=422,
            detail="Urgência inválida. Use: vencido, critico, atencao ou normal.",
        )

    condicoes = ["1=1"]
    params: dict[str, object] = {}

    if apenas_pendentes:
        condicoes.append(
            "COALESCE(v.status,'') NOT IN "
            "('concluido','concluida','tratada','cancelado')"
        )

    # Visibilidade obrigatória antes dos filtros funcionais. Um filtro nunca
    # amplia a carteira; apenas reduz o conjunto já autorizado.
    if not is_gestao(cu):
        condicoes.append(
            """(v.responsavel_id = :uid OR EXISTS (
                SELECT 1 FROM cases cc
                WHERE cc.id = v.case_id
                  AND cc.deleted_at IS NULL
                  AND (
                    cc.advogado_responsavel_id = :uid
                    OR cc.advogado_auxiliar_id = :uid
                  )
            ))"""
        )
        params["uid"] = cu.id

    if minha_fila:
        condicoes.append("v.responsavel_id = :minha_fila_uid")
        params["minha_fila_uid"] = cu.id
    elif responsavel_id:
        condicoes.append("v.responsavel_id = :responsavel_id")
        params["responsavel_id"] = responsavel_id

    if case_id:
        condicoes.append("v.case_id = :case_id")
        params["case_id"] = case_id

    if client_id:
        # Usa o Case já associado no LEFT JOIN; não cria dependência nova na
        # view e mantém a fonte de ownership no mesmo domínio.
        condicoes.append("c.client_id = :client_id")
        params["client_id"] = client_id

    if urgencia:
        condicoes.append(_filtro_urgencia_sql(urgencia))

    where = " AND ".join(condicoes)

    # SQL estrutural é composto apenas por fragmentos internos acima. Valores
    # fornecidos pelo usuário entram exclusivamente via bind params.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    rows = (
        await db.execute(
            text(
                f"""
                SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
                       v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
                       c.titulo AS caso_titulo,
                       (v.data::date - CURRENT_DATE) AS dias_restantes
                FROM vw_atividades v
                LEFT JOIN cases c
                  ON c.id = v.case_id
                 AND c.deleted_at IS NULL
                WHERE {where}
                ORDER BY v.data ASC NULLS LAST
                """
            ),
            params,
        )
    ).mappings().all()

    def _urgencia(dias: int | None) -> str:
        if dias is None:
            return "normal"
        if dias < 0:
            return "vencido"
        if dias <= 3:
            return "critico"
        if dias <= 7:
            return "atencao"
        return "normal"

    def _dias(valor):
        if valor is None:
            return None
        if hasattr(valor, "days"):
            return valor.days
        return int(valor)

    data = []
    for row in rows:
        dias = _dias(row["dias_restantes"])
        data.append(
            {
                "id": row["id"],
                "tipo": row["tipo"],
                "titulo": row["titulo"],
                "descricao": row["descricao"],
                "date": str(row["data"]) if row["data"] else None,
                "status": row["status"],
                "case_id": row["case_id"],
                "caso_titulo": row["caso_titulo"],
                "responsavel_id": row["responsavel_id"],
                "prioridade": row["prioridade"],
                "subtipo": row["subtipo"],
                "dias_restantes": dias,
                "urgencia": _urgencia(dias),
            }
        )
    return {"data": data}
