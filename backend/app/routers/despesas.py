import csv
import io
import calendar
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
from app.core.sql_safe import construir_update
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services.finance_governance import (
    competencia_de_data,
    exigir_competencia_aberta,
    limite_dupla_aprovacao,
    solicitar_ou_consumir_aprovacao,
)

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


class GerarRecorrentesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    competencia: str

    @field_validator("competencia")
    @classmethod
    def _validar_competencia(cls, valor: str) -> str:
        if len(valor) != 7 or valor[4] != "-":
            raise ValueError("competencia inválida: use AAAA-MM")
        ano, mes = (int(p) for p in valor.split("-"))
        if ano < 1900 or mes < 1 or mes > 12:
            raise ValueError("competencia inválida: use AAAA-MM")
        return valor


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
    if competencia:
        params = {"competencia": competencia}
        resumo_stmt = text("""
            SELECT
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='fixo' AND status!='cancelado'
                      AND competencia = :competencia
                ), 0) AS total_fixo,
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='variavel' AND status!='cancelado'
                      AND competencia = :competencia
                ), 0) AS total_variavel,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pago' AND competencia = :competencia
                ), 0) AS total_pago_mes,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pendente' AND competencia = :competencia
                ), 0) AS total_pendente_mes
            FROM office_expenses
            WHERE deleted_at IS NULL
        """)
        categoria_stmt = text("""
            SELECT categoria, SUM(valor) AS total, COUNT(*) AS qtd
            FROM office_expenses
            WHERE deleted_at IS NULL AND status!='cancelado'
              AND competencia = :competencia
            GROUP BY categoria
            ORDER BY total DESC
        """)
    else:
        params = {}
        resumo_stmt = text("""
            SELECT
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='fixo' AND status!='cancelado'
                ), 0) AS total_fixo,
                COALESCE(SUM(valor) FILTER (
                    WHERE tipo='variavel' AND status!='cancelado'
                ), 0) AS total_variavel,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pago'
                ), 0) AS total_pago_mes,
                COALESCE(SUM(valor) FILTER (
                    WHERE status='pendente'
                ), 0) AS total_pendente_mes
            FROM office_expenses
            WHERE deleted_at IS NULL
        """)
        categoria_stmt = text("""
            SELECT categoria, SUM(valor) AS total, COUNT(*) AS qtd
            FROM office_expenses
            WHERE deleted_at IS NULL AND status!='cancelado'
            GROUP BY categoria
            ORDER BY total DESC
        """)

    result = await db.execute(resumo_stmt, params)
    row = result.mappings().first()
    por_cat = await db.execute(categoria_stmt, params)
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
    params = {
        "categoria": categoria,
        "tipo": tipo,
        "status": status,
        "competencia": competencia,
        "recorrente": recorrente,
    }
    result = await db.execute(
        text("""
            SELECT id, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status,
                   competencia, created_by, created_at, updated_at
            FROM office_expenses
            WHERE deleted_at IS NULL
              AND (CAST(:categoria AS text) IS NULL OR categoria = :categoria)
              AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
              AND (CAST(:status AS text) IS NULL OR status = :status)
              AND (CAST(:competencia AS text) IS NULL OR competencia = :competencia)
              AND (CAST(:recorrente AS boolean) IS NULL OR recorrente = :recorrente)
            ORDER BY categoria, descricao
        """),
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
    params: dict = {
        "competencia": competencia,
        "categoria": categoria,
        "tipo": tipo,
        "status": status,
    }
    result = await db.execute(
        text("""
            SELECT competencia, categoria, subcategoria, tipo, descricao, valor,
                   vencimento, pago_em, recorrente, recorrencia, status
            FROM office_expenses
            WHERE deleted_at IS NULL
              AND (CAST(:competencia AS text) IS NULL OR competencia = :competencia)
              AND (CAST(:categoria AS text) IS NULL OR categoria = :categoria)
              AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
              AND (CAST(:status AS text) IS NULL OR status = :status)
            ORDER BY competencia DESC, categoria, descricao
        """),
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


@router.post("/recorrentes/gerar", status_code=201)
async def gerar_recorrentes(
    body: GerarRecorrentesIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await exigir_competencia_aberta(
        db, body.competencia, "Gerar despesas recorrentes"
    )
    ano_alvo, mes_alvo = (int(p) for p in body.competencia.split("-"))
    templates = (
        await db.execute(text("""
            SELECT DISTINCT ON (categoria, COALESCE(subcategoria,''), tipo, descricao)
                id, categoria, subcategoria, tipo, descricao, valor,
                vencimento, recorrencia, competencia
            FROM office_expenses
            WHERE deleted_at IS NULL AND recorrente=TRUE AND status!='cancelado'
            ORDER BY categoria, COALESCE(subcategoria,''), tipo, descricao,
                     updated_at DESC NULLS LAST, created_at DESC
        """))
    ).mappings().all()
    gerados, ignorados = [], []
    for t in templates:
        recorrencia=(t["recorrencia"] or "mensal").lower()
        devido=True
        if t["competencia"]:
            ano_base, mes_base=(int(p) for p in t["competencia"].split("-"))
            delta=(ano_alvo-ano_base)*12+(mes_alvo-mes_base)
            devido = delta >= 0 and (
                recorrencia == "mensal"
                or (recorrencia == "trimestral" and delta % 3 == 0)
                or (recorrencia == "anual" and delta % 12 == 0)
            )
        if not devido:
            continue
        vencimento=None
        if t["vencimento"]:
            dia=min(t["vencimento"].day, calendar.monthrange(ano_alvo, mes_alvo)[1])
            vencimento=date(ano_alvo, mes_alvo, dia)
        existente=(await db.execute(text("""
            SELECT id FROM office_expenses
            WHERE deleted_at IS NULL AND status!='cancelado'
              AND competencia=:competencia AND categoria=:categoria
              AND COALESCE(subcategoria,'')=COALESCE(:subcategoria,'')
              AND tipo=:tipo AND descricao=:descricao AND valor=:valor
            LIMIT 1
        """), {
            "competencia":body.competencia,"categoria":t["categoria"],
            "subcategoria":t["subcategoria"],"tipo":t["tipo"],
            "descricao":t["descricao"],"valor":t["valor"],
        })).scalar_one_or_none()
        if existente:
            ignorados.append(existente); continue
        novo=(await db.execute(text("""
            INSERT INTO office_expenses
              (categoria,subcategoria,tipo,descricao,valor,vencimento,recorrente,
               recorrencia,status,competencia,created_by)
            VALUES
              (:categoria,:subcategoria,:tipo,:descricao,:valor,:vencimento,
               FALSE,NULL,'pendente',:competencia,:created_by)
            RETURNING id
        """), {
            "categoria":t["categoria"],"subcategoria":t["subcategoria"],
            "tipo":t["tipo"],"descricao":t["descricao"],"valor":t["valor"],
            "vencimento":vencimento,"competencia":body.competencia,
            "created_by":current_user.id,
        })).scalar_one()
        gerados.append(novo)
        await criar_audit_log(
            db,current_user.id,current_user.role.value,"CREATE","office_expenses",novo,
            detalhes=f"Despesa recorrente gerada para {body.competencia}; template={t['id']}",
        )
    await db.commit()
    return {"competencia":body.competencia,"gerados":len(gerados),"ignorados":len(ignorados),"ids":gerados}


@router.post("", status_code=201)
async def create_despesa(
    body: DespesaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dados = _normalizar_baixa(body.model_dump())
    competencia_mutacao = (
        dados.get("competencia")
        or competencia_de_data(dados.get("pago_em") or dados.get("vencimento"))
    )
    await exigir_competencia_aberta(
        db, competencia_mutacao, "Criar despesa"
    )
    approval_required = None
    if dados.get("status") == "pago":
        limite = await limite_dupla_aprovacao(db)
        if Decimal(str(dados["valor"])) >= limite:
            dados["status"] = "pendente"
            dados["pago_em"] = None
            approval_required = True
    duplicado = (
        await db.execute(
            text(
                """
                SELECT id FROM office_expenses
                WHERE deleted_at IS NULL AND status != 'cancelado'
                  AND categoria=:categoria AND tipo=:tipo AND descricao=:descricao
                  AND valor=:valor
                  AND vencimento IS NOT DISTINCT FROM :vencimento
                  AND competencia IS NOT DISTINCT FROM :competencia
                  AND created_at >= NOW() - INTERVAL '10 minutes'
                LIMIT 1
                """
            ),
            {
                "categoria": dados["categoria"], "tipo": dados["tipo"],
                "descricao": dados["descricao"], "valor": dados["valor"],
                "vencimento": dados.get("vencimento"),
                "competencia": dados.get("competencia"),
            },
        )
    ).scalar_one_or_none()
    if duplicado:
        raise HTTPException(status_code=409, detail="Possível despesa duplicada: lançamento idêntico criado nos últimos 10 minutos.")
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
    approval_info = None
    if approval_required:
        approval_info = await solicitar_ou_consumir_aprovacao(
            db,
            entity_type="office_expense",
            entity_id=row["id"],
            amount=row["valor"],
            user=current_user,
            reason="Pagamento de despesa acima da alçada configurada.",
        )
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
    if approval_info and approval_info.get("required"):
        row["approval_required"] = True
        row["approval_id"] = approval_info.get("approval_id")
        row["approval_threshold"] = approval_info.get("threshold")
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
    competencia_atual = (
        antes["competencia"]
        or competencia_de_data(antes["pago_em"] or antes["vencimento"])
    )
    await exigir_competencia_aberta(
        db, competencia_atual, "Alterar despesa"
    )
    updates = _normalizar_baixa(updates, status_atual=antes["status"])
    competencia_nova = (
        updates.get("competencia")
        or antes["competencia"]
        or competencia_de_data(
            updates.get("pago_em")
            or antes["pago_em"]
            or updates.get("vencimento")
            or antes["vencimento"]
        )
    )
    await exigir_competencia_aberta(
        db, competencia_nova, "Alterar despesa"
    )
    if updates.get("status") == "pago" and antes["status"] != "pago":
        approval = await solicitar_ou_consumir_aprovacao(
            db,
            entity_type="office_expense",
            entity_id=despesa_id,
            amount=antes["valor"],
            user=current_user,
            reason="Pagamento de despesa acima da alçada configurada.",
        )
        if approval.get("required"):
            await criar_audit_log(
                db,
                current_user.id,
                current_user.role.value,
                "REQUEST_APPROVAL",
                "office_expenses",
                despesa_id,
                detalhes="Baixa aguardando segunda aprovação financeira.",
                dados_depois={
                    "approval_id": approval.get("approval_id"),
                    "valor": str(antes["valor"]),
                },
            )
            await db.commit()
            return {
                **dict(antes),
                "approval_required": True,
                "approval_id": approval.get("approval_id"),
                "approval_threshold": approval.get("threshold"),
            }

    stmt, params = construir_update(
        updates,
        tabela="office_expenses",
        exigir_nao_excluido=True,
    )
    params["where_id"] = despesa_id
    result = await db.execute(stmt, params)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")

    atualizado = await db.execute(
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
    depois_row = atualizado.mappings().first()
    if not depois_row:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    depois = dict(depois_row)
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
    competencia_atual = (
        antes["competencia"]
        or competencia_de_data(antes["pago_em"] or antes["vencimento"])
    )
    await exigir_competencia_aberta(
        db, competencia_atual, "Excluir despesa"
    )

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