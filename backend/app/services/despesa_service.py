from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.despesa import DespesaCreate, DespesaUpdate


_COLUNAS_RETORNO = """
    id, categoria, subcategoria, tipo, descricao, valor,
    vencimento, pago_em, recorrente, recorrencia, status,
    competencia, recorrencia_origem_id, created_by,
    created_at, updated_at
"""


def _dict(row) -> dict:
    return dict(row) if row is not None else {}


def _vencimento_na_competencia(
    vencimento_modelo: date | None, competencia: str
) -> date | None:
    if vencimento_modelo is None:
        return None
    ano, mes = (int(parte) for parte in competencia.split("-", 1))
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(vencimento_modelo.day, ultimo_dia))


async def obter_despesa(
    db: AsyncSession, despesa_id: str, *, incluir_excluida: bool = False
) -> dict | None:
    deleted = "" if incluir_excluida else "AND deleted_at IS NULL"
    result = await db.execute(
        text(
            f"""
            SELECT {_COLUNAS_RETORNO}
            FROM office_expenses
            WHERE id = :id {deleted}
            """
        ),
        {"id": despesa_id},
    )
    row = result.mappings().first()
    return _dict(row) if row else None


async def criar_despesa(
    db: AsyncSession, payload: DespesaCreate, *, user_id: str
) -> dict:
    dados = payload.model_dump(mode="python")
    result = await db.execute(
        text(
            f"""
            INSERT INTO office_expenses
                (categoria, subcategoria, tipo, descricao, valor, vencimento,
                 pago_em, recorrente, recorrencia, status, competencia,
                 created_by)
            VALUES
                (:categoria, :subcategoria, :tipo, :descricao, :valor,
                 :vencimento, :pago_em, :recorrente, :recorrencia, :status,
                 :competencia, :created_by)
            RETURNING {_COLUNAS_RETORNO}
            """
        ),
        {**dados, "created_by": user_id},
    )
    return _dict(result.mappings().first())


async def atualizar_despesa(
    db: AsyncSession, despesa_id: str, payload: DespesaUpdate
) -> tuple[dict, dict]:
    antes = await obter_despesa(db, despesa_id)
    if antes is None:
        raise LookupError("Despesa não encontrada")
    if antes.get("recorrencia_origem_id") and payload.recorrente is True:
        raise ValueError(
            "Lançamento gerado por recorrência não pode se tornar um novo modelo recorrente"
        )

    updates = payload.model_dump(exclude_unset=True, mode="python")
    if not updates:
        raise ValueError("Nenhum campo válido para atualizar")

    if "recorrente" in updates:
        if updates["recorrente"]:
            updates["recorrencia"] = updates.get("recorrencia") or antes.get(
                "recorrencia"
            ) or "mensal"
        else:
            updates["recorrencia"] = None
    elif "recorrencia" in updates and not antes.get("recorrente"):
        raise ValueError("Recorrência só pode ser definida em um modelo recorrente")

    set_clause = ", ".join(f"{campo} = :{campo}" for campo in updates)
    result = await db.execute(
        text(
            f"""
            UPDATE office_expenses
            SET {set_clause}, updated_at = NOW()
            WHERE id = :id AND deleted_at IS NULL
            RETURNING {_COLUNAS_RETORNO}
            """
        ),
        {**updates, "id": despesa_id},
    )
    depois = _dict(result.mappings().first())
    return antes, depois


async def excluir_despesa(db: AsyncSession, despesa_id: str) -> dict:
    antes = await obter_despesa(db, despesa_id)
    if antes is None:
        raise LookupError("Despesa não encontrada")
    await db.execute(
        text(
            """
            UPDATE office_expenses
            SET deleted_at = NOW(), updated_at = NOW()
            WHERE id = :id AND deleted_at IS NULL
            """
        ),
        {"id": despesa_id},
    )
    return antes


async def gerar_recorrentes(
    db: AsyncSession, competencia: str, *, user_id: str
) -> dict:
    """Gera uma competência a partir dos modelos recorrentes, sem duplicação.

    Cada par modelo+competência recebe advisory lock transacional no PostgreSQL.
    Assim retries e duas requisições concorrentes são serializados sem exigir
    criação de UNIQUE em tabela já populada durante o rolling deploy.
    """
    templates = (
        await db.execute(
            text(
                """
                SELECT id, categoria, subcategoria, tipo, descricao, valor,
                       vencimento, recorrencia
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND recorrente = TRUE
                  AND recorrencia_origem_id IS NULL
                ORDER BY categoria, descricao
                """
            )
        )
    ).mappings().all()

    gerados = 0
    existentes = 0
    ids: list[str] = []
    for modelo in templates:
        lock_key = f"despesa-recorrente:{modelo['id']}:{competencia}"
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:chave, 0))"),
            {"chave": lock_key},
        )
        existente = (
            await db.execute(
                text(
                    """
                    SELECT id
                    FROM office_expenses
                    WHERE deleted_at IS NULL
                      AND recorrencia_origem_id = :origem_id
                      AND competencia = :competencia
                    LIMIT 1
                    """
                ),
                {"origem_id": modelo["id"], "competencia": competencia},
            )
        ).scalar_one_or_none()
        if existente:
            existentes += 1
            continue

        vencimento = _vencimento_na_competencia(modelo["vencimento"], competencia)
        criado = (
            await db.execute(
                text(
                    """
                    INSERT INTO office_expenses
                        (categoria, subcategoria, tipo, descricao, valor,
                         vencimento, recorrente, recorrencia, status, competencia,
                         recorrencia_origem_id, created_by)
                    VALUES
                        (:categoria, :subcategoria, :tipo, :descricao, :valor,
                         :vencimento, FALSE, :recorrencia, 'pendente', :competencia,
                         :origem_id, :created_by)
                    RETURNING id
                    """
                ),
                {
                    "categoria": modelo["categoria"],
                    "subcategoria": modelo["subcategoria"],
                    "tipo": modelo["tipo"],
                    "descricao": modelo["descricao"],
                    "valor": Decimal(str(modelo["valor"] or 0)),
                    "vencimento": vencimento,
                    "recorrencia": modelo["recorrencia"] or "mensal",
                    "competencia": competencia,
                    "origem_id": modelo["id"],
                    "created_by": user_id,
                },
            )
        ).scalar_one()
        gerados += 1
        ids.append(str(criado))

    return {
        "competencia": competencia,
        "modelos": len(templates),
        "gerados": gerados,
        "ja_existentes": existentes,
        "ids_gerados": ids,
    }
