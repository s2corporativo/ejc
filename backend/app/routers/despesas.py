import csv
import io
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.csv_safe import sanitize_csv_row
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User

_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _req_fin(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _FIN:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro")
    return cu


router = APIRouter(prefix="/despesas", tags=["despesas"], dependencies=[Depends(_req_fin)])


class _DespesaCampos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria: Optional[str] = Field(None, min_length=1, max_length=100)
    subcategoria: Optional[str] = Field(None, max_length=100)
    tipo: Optional[Literal["fixo", "variavel"]] = None
    descricao: Optional[str] = Field(None, min_length=1, max_length=500)
    valor: Optional[Decimal] = Field(None, gt=0)
    vencimento: Optional[date] = None
    pago_em: Optional[date] = None
    recorrente: Optional[bool] = None
    recorrencia: Optional[str] = Field(None, max_length=100)
    status: Optional[Literal["pendente", "pago", "cancelado"]] = None
    competencia: Optional[str] = None

    @field_validator("categoria", "descricao")
    @classmethod
    def _nao_vazio(cls, valor: Optional[str]) -> Optional[str]:
        if valor is not None and not valor.strip():
            raise ValueError("campo não pode ser vazio")
        return valor.strip() if valor is not None else valor

    @field_validator("competencia")
    @classmethod
    def _competencia(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if len(valor) != 7 or valor[4] != "-":
            raise ValueError("competencia inválida: use AAAA-MM")
        try:
            ano, mes = (int(p) for p in valor.split("-"))
        except ValueError as exc:
            raise ValueError("competencia inválida: use AAAA-MM") from exc
        if ano < 1900 or mes < 1 or mes > 12:
            raise ValueError("competencia inválida: use AAAA-MM")
        return valor


class DespesaCreate(_DespesaCampos):
    categoria: str = Field(..., min_length=1, max_length=100)
    tipo: Literal["fixo", "variavel"] = "fixo"
    descricao: str = Field(..., min_length=1, max_length=500)
    valor: Decimal = Field(..., gt=0)
    recorrente: bool = False
    status: Literal["pendente", "pago", "cancelado"] = "pendente"


class DespesaUpdate(_DespesaCampos):
    pass


def _normalizar_baixa(dados: dict, *, status_atual: Optional[str] = None) -> dict:
    """Mantém a invariável financeira ``status=pago`` ↔ ``pago_em``.

    A data de caixa é histórica e não pode ser reescrita por uma edição comum.
    Só sintetizamos ``date.today()`` quando há transição real para ``pago``.
    Ao sair de ``pago`` limpamos a data se o chamador não informar outra coisa;
    uma tentativa explícita de manter ``pago_em`` em estado não pago é rejeitada.
    """
    normalizados = dict(dados)
    status_informado = "status" in normalizados
    status_novo = normalizados.get("status", status_atual)
    pago_em_informado = "pago_em" in normalizados

    if status_novo == "pago":
        if status_informado and status_atual != "pago":
            # create(status=pago) ou transição pendente/cancelado -> pago.
            if normalizados.get("pago_em") is None:
                normalizados["pago_em"] = date.today()
        elif status_atual == "pago" and pago_em_informado and normalizados.get("pago_em") is None:
            raise HTTPException(
                status_code=422,
                detail="despesa paga deve manter uma data de pagamento válida",
            )
        # Edição de descrição/categoria/etc. em despesa já paga: não tocar pago_em.
    else:
        if pago_em_informado and normalizados.get("pago_em") is not None:
            raise HTTPException(
                status_code=422,
                detail="pago_em só pode ser informado quando o status da despesa for 'pago'",
            )
        if status_informado and status_atual == "pago" and not pago_em_informado:
            normalizados["pago_em"] = None

    return normalizados


@router.get("/resumo")
async def get_resumo(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comp_filter = "AND competencia = :competencia" if competencia else ""
    params = {"competencia": competencia} if competencia else {}
    result = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            SELECT
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='fixo' AND status!='cancelado' {comp_filter}
                ), 0) AS total_fixo,
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='variavel' AND status!='cancelado' {comp_filter}
                ), 0) AS total_variavel,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pago' {comp_filter}
                ), 0) AS total_pago_mes,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pendente' {comp_filter}
                ), 0) AS total_pendente_mes
            FROM office_expenses
            WHERE deleted_at IS NULL
            """
        ),
        params,
    )
    row = result.mappings().first()

    por_cat = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            SELECT categoria, SUM(valor) AS total, COUNT(*) AS qtd
            FROM office_expenses
            WHERE deleted_at IS NULL AND status!='cancelado' {comp_filter}
            GROUP BY categoria
            ORDER BY total DESC
            """
        ),
        params,
    )
    categorias = [dict(r) for r in por_cat.mappings().all()]

    def _dec(v):
        return Decimal(str(v)) if v is not None else Decimal("0")

    return {
        "total_fixo": _dec(row["total_fixo"]),
        "total_variavel": _dec(row["total_variavel"]),
        "total_pago_mes": _dec(row["total_pago_mes"]),
        "total_pendente_mes": _dec(row["total_pendente_mes"]),
        "por_categoria": categorias,
    }


@router.get("")
async def list_despesas(
    categoria: Optional[str] = Query(None),
    tipo: Optional[Literal["fixo", "variavel"]] = Query(None),
    status: Optional[Literal["pendente", "pago", "cancelado"]] = Query(None),
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    recorrente: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = ["deleted_at IS NULL"]
    params = {}
    if categoria:
        conditions.append("categoria = :categoria")
        params["categoria"] = categoria
    if tipo:
        conditions.append("tipo = :tipo")
        params["tipo"] = tipo
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if competencia:
        conditions.append("competencia = :competencia")
        params["competencia"] = competencia
    if recorrente is not None:
        conditions.append("recorrente = :recorrente")
        params["recorrente"] = recorrente

    where = " AND ".join(conditions)
    result = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            SELECT id, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   competencia, created_by, created_at, updated_at
            FROM office_expenses
            WHERE {where}
            ORDER BY categoria, descricao
            """
        ),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


@router.get("/export/csv")
async def export_despesas_csv(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    categoria: Optional[str] = Query(None),
    tipo: Optional[Literal["fixo", "variavel"]] = Query(None),
    status: Optional[Literal["pendente", "pago", "cancelado"]] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = ["deleted_at IS NULL"]
    params: dict = {}
    if competencia:
        conditions.append("competencia = :competencia")
        params["competencia"] = competencia
    if categoria:
        conditions.append("categoria = :categoria")
        params["categoria"] = categoria
    if tipo:
        conditions.append("tipo = :tipo")
        params["tipo"] = tipo
    if status:
        conditions.append("status = :status")
        params["status"] = status
    where = " AND ".join(conditions)
    result = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            SELECT competencia, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status
            FROM office_expenses
            WHERE {where}
            ORDER BY competencia DESC, categoria, descricao
            """
        ),
        params,
    )
    rows = result.mappings().all()

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(sanitize_csv_row([
        "Competência", "Categoria", "Subcategoria", "Tipo", "Descrição",
        "Valor", "Vencimento", "Pago em", "Recorrente", "Recorrência", "Status",
    ]))
    for r in rows:
        valor = Decimal(str(r["valor"] or 0)).quantize(Decimal("0.01"))
        w.writerow(sanitize_csv_row([
            r["competencia"] or "", r["categoria"] or "", r["subcategoria"] or "",
            r["tipo"] or "", r["descricao"] or "",
            format(valor, ".2f").replace(".", ","),
            r["vencimento"] or "", r["pago_em"] or "",
            "Sim" if r["recorrente"] else "Não", r["recorrencia"] or "",
            r["status"] or "",
        ]))
    nome = f"despesas_{competencia or 'todas'}.csv"
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("", status_code=201)
async def create_despesa(
    body: DespesaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dados = _normalizar_baixa(body.model_dump())
    result = await db.execute(
        text(
            """
            INSERT INTO office_expenses
                (categoria, subcategoria, tipo, descricao, valor, vencimento, pago_em,
                 recorrente, recorrencia, status, competencia, created_by)
            VALUES
                (:categoria, :subcategoria, :tipo, :descricao, :valor,
                 :vencimento, :pago_em, :recorrente, :recorrencia, :status,
                 :competencia, :created_by)
            RETURNING id, categoria, subcategoria, tipo, descricao, valor,
                      vencimento, pago_em, recorrente, recorrencia, status,
                      competencia, created_at
            """
        ),
        {**dados, "created_by": current_user.id},
    )
    row = dict(result.mappings().first())
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "CREATE",
        "office_expenses",
        row["id"],
        detalhes="Despesa do escritório criada",
        dados_depois=jsonable_encoder(row),
    )
    await db.commit()
    return row


@router.patch("/{despesa_id}")
async def update_despesa(
    despesa_id: str,
    body: DespesaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    atual = await db.execute(
        text(
            """
            SELECT id, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   competencia, created_at, updated_at
            FROM office_expenses
            WHERE id=:id AND deleted_at IS NULL
            """
        ),
        {"id": despesa_id},
    )
    antes = atual.mappings().first()
    if not antes:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo informado para atualizar")
    updates = _normalizar_baixa(updates, status_atual=antes["status"])

    set_clause = ", ".join(f"{k}=:{k}" for k in updates)
    result = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            UPDATE office_expenses
            SET {set_clause}, updated_at=NOW()
            WHERE id=:id AND deleted_at IS NULL
            RETURNING id, categoria, subcategoria, tipo, descricao, valor,
                      vencimento, pago_em, recorrente, recorrencia, status,
                      competencia, created_at, updated_at
            """
        ),
        {**updates, "id": despesa_id},
    )
    depois = dict(result.mappings().first())
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "UPDATE",
        "office_expenses",
        despesa_id,
        detalhes=f"campos alterados: {sorted(updates)}",
        dados_antes=jsonable_encoder(dict(antes)),
        dados_depois=jsonable_encoder(depois),
    )
    await db.commit()
    return depois


@router.delete("/{despesa_id}")
async def delete_despesa(
    despesa_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    atual = await db.execute(
        text(
            """
            SELECT id, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   competencia, created_at, updated_at
            FROM office_expenses
            WHERE id=:id AND deleted_at IS NULL
            """
        ),
        {"id": despesa_id},
    )
    antes = atual.mappings().first()
    if not antes:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    await db.execute(
        text("UPDATE office_expenses SET deleted_at=NOW(), updated_at=NOW() WHERE id=:id"),
        {"id": despesa_id},
    )
    await criar_audit_log(
        db,
        current_user.id,
        current_user.role.value,
        "DELETE",
        "office_expenses",
        despesa_id,
        detalhes="Despesa do escritório removida por soft delete",
        dados_antes=jsonable_encoder(dict(antes)),
    )
    await db.commit()
    return {"ok": True, "id": despesa_id}