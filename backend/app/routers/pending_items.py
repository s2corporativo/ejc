"""Client pending items CRUD"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import cliente_id_visivel
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User

router = APIRouter(prefix="/clients", tags=["pending-items"])

# Vocabulário fechado — espelha as opções do formulário (DossieCliente.tsx:
# PENDING_STATUS_LABEL e o <select> de tipo). Payload fora disso vira 422 em
# vez de gravar valor arbitrário que o front não sabe rotular/colorir.
#
# `procuracao`, `certidao` e `outro` foram ACRESCENTADOS: o <select> do
# formulário já oferecia os três, mas o backend os rejeitava com 422 — quem
# escolhesse "Procuração", "Certidão" ou "Outro" não conseguia salvar a
# pendência. O vocabulário do backend é que estava atrasado em relação à
# interface, e são tipos jurídicos legítimos (a certidão, em particular, é o
# caso típico de `providencia="emitir_certidao"`).
_TIPOS_VALIDOS = {"documento", "informacao", "assinatura", "pagamento",
                  "procuracao", "certidao", "outro"}
_STATUS_VALIDOS = {"pendente", "solicitado", "recebido", "em_analise", "concluido"}

# Frente 12 do plano de evolução: o que transforma a lista de ausências em
# plano de ação. Ambos são OPCIONAIS (coluna nullable, migration 147) — a
# pendência continua válida sem classificação, e `None` significa "ainda não
# avaliado", não "sem impacto".
_IMPACTOS_VALIDOS = {"alto", "medio", "baixo"}
_PROVIDENCIAS_VALIDAS = {"solicitar_cliente", "obter_processo",
                         "emitir_certidao", "diligencia_externa", "outro"}


def _valida_vocabulario(valor, validos, campo):
    """Valida contra vocabulário fechado aceitando None (campo não informado).

    Usado só por `impacto`/`providencia`, que são nullable no banco — ao
    contrário de type/status, aqui `null` explícito é um valor legítimo
    (limpar a classificação num PATCH)."""
    if valor is None:
        return None
    if valor not in validos:
        raise ValueError(f"{campo} inválido; use um de: {sorted(validos)}")
    return valor


class PendingItemCreate(BaseModel):
    case_id: Optional[str] = None
    type: str = "documento"
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "pendente"
    due_date: Optional[date] = None
    impacto: Optional[str] = None
    providencia: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _valida_type(cls, v: str) -> str:
        if v not in _TIPOS_VALIDOS:
            raise ValueError(f"type inválido; use um de: {sorted(_TIPOS_VALIDOS)}")
        return v

    @field_validator("impacto")
    @classmethod
    def _valida_impacto(cls, v: Optional[str]) -> Optional[str]:
        return _valida_vocabulario(v, _IMPACTOS_VALIDOS, "impacto")

    @field_validator("providencia")
    @classmethod
    def _valida_providencia(cls, v: Optional[str]) -> Optional[str]:
        return _valida_vocabulario(v, _PROVIDENCIAS_VALIDAS, "providencia")

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: str) -> str:
        if v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v


class PendingItemUpdate(BaseModel):
    # case_id aceita null explícito (desvincular do caso) — só quando NÃO-null
    # precisa apontar para caso do mesmo cliente (checado no handler, mesma
    # validação de PendingItemCreate).
    case_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    impacto: Optional[str] = None
    providencia: Optional[str] = None

    # title/type/status são NOT NULL na tabela (client_pending_items). Como
    # são Optional aqui só para permitir OMITIR o campo num PATCH parcial,
    # `null` explícito precisa ser rejeitado — sem isto, {"status": null}
    # passava a validação e virava UPDATE ... SET status=NULL, estourando a
    # constraint em 500 sem tratamento (achado do code-reviewer).
    @field_validator("title")
    @classmethod
    def _valida_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("title não pode ser nulo")
        return v

    @field_validator("type")
    @classmethod
    def _valida_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("type não pode ser nulo")
        if v not in _TIPOS_VALIDOS:
            raise ValueError(f"type inválido; use um de: {sorted(_TIPOS_VALIDOS)}")
        return v

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("status não pode ser nulo")
        if v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v

    # impacto/providencia são nullable no banco: `null` explícito é permitido
    # e significa "limpar a classificação".
    @field_validator("impacto")
    @classmethod
    def _valida_impacto(cls, v: Optional[str]) -> Optional[str]:
        return _valida_vocabulario(v, _IMPACTOS_VALIDOS, "impacto")

    @field_validator("providencia")
    @classmethod
    def _valida_providencia(cls, v: Optional[str]) -> Optional[str]:
        return _valida_vocabulario(v, _PROVIDENCIAS_VALIDAS, "providencia")


async def _exigir_cliente_visivel(db: AsyncSession, cu: User, client_id: str) -> None:
    """Gate de titularidade (client_ownership canônico — antes esta era uma
    cópia local em SQL cru que só dava passe livre à gestão, deixando a
    secretaria sem ver pendências do próprio funil que opera; achado da
    auditoria). 404 (não 403) para não confirmar a existência de cliente
    alheio. Sem isso, qualquer usuário listava/alterava pendências de
    qualquer cliente (IDOR)."""
    if not await cliente_id_visivel(db, cu, client_id):
        raise HTTPException(404, "Cliente não encontrado")


async def _validar_case_do_cliente(db: AsyncSession, client_id: str, case_id: str) -> None:
    """Impede vincular a pendência a um caso de OUTRO cliente (achado da
    auditoria: case_id não era conferido contra o cliente da URL)."""
    row = (await db.execute(text("""
        SELECT 1 FROM cases WHERE id = :case_id AND client_id = :cid
          AND deleted_at IS NULL
    """), {"case_id": case_id, "cid": client_id})).first()
    if row is None:
        raise HTTPException(422, "case_id não pertence a este cliente")


@router.get("/{client_id}/pending-items")
async def list_pending_items(
    client_id: str,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
    q = "SELECT * FROM client_pending_items WHERE client_id=:cid AND deleted_at IS NULL"
    params = {"cid": client_id}
    if status:
        q += " AND status=:status"
        params["status"] = status
    q += " ORDER BY created_at DESC"
    result = await db.execute(text(q), params)
    return [dict(r) for r in result.mappings().all()]


@router.post("/{client_id}/pending-items", status_code=201)
async def create_pending_item(
    client_id: str,
    body: PendingItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
    # `is not None` (não truthy) — "" também precisa validar: client_pending_
    # items.case_id não tem FK, então "" passava direto pro INSERT como
    # referência inválida (nem NULL nem caso real). Achado do CodeRabbit.
    if body.case_id is not None:
        await _validar_case_do_cliente(db, client_id, body.case_id)
    result = await db.execute(
        text("""INSERT INTO client_pending_items
            (client_id, case_id, type, title, description, status, due_date,
             impacto, providencia, created_by)
            VALUES (:cid,:case_id,:type,:title,:desc,:status,:due,
                    :impacto,:providencia,:created_by)
            RETURNING *"""),
        {
            "cid": client_id,
            "case_id": body.case_id,
            "type": body.type,
            "title": body.title,
            "desc": body.description,
            "status": body.status,
            "due": body.due_date,
            "impacto": body.impacto,
            "providencia": body.providencia,
            "created_by": str(current_user.id),
        }
    )
    row = dict(result.mappings().first())
    # Sem PII/conteúdo no audit log (imutável — migration 131 WORM): título é
    # texto livre do usuário e pode conter dado sensível do caso/cliente.
    # Achado do Codex no PR #1063.
    await criar_audit_log(db, current_user.id, current_user.role.value,
                          "CREATE", "client_pending_items", row["id"],
                          detalhes=f"cliente {client_id}, type={body.type}")
    await db.commit()
    return row


@router.patch("/{client_id}/pending-items/{item_id}")
async def update_pending_item(
    client_id: str,
    item_id: str,
    body: PendingItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
    result = await db.execute(text("SELECT id FROM client_pending_items WHERE id=:id AND client_id=:cid AND deleted_at IS NULL"), {"id": item_id, "cid": client_id})
    if not result.fetchone():
        raise HTTPException(404, "Item not found")

    mudancas = body.model_dump(exclude_unset=True)
    if not mudancas:
        return {"ok": True}
    if "case_id" in mudancas and mudancas["case_id"] is not None:
        await _validar_case_do_cliente(db, client_id, mudancas["case_id"])

    sets = []
    params = {"id": item_id}
    for field, value in mudancas.items():
        sets.append(f"{field}=:{field}")
        params[field] = value
    if mudancas.get("status") == "concluido":
        sets.append("completed_at=NOW()")
    sets.append("updated_at=NOW()")

    await db.execute(text(f"UPDATE client_pending_items SET {','.join(sets)} WHERE id=:id"), params)
    await criar_audit_log(db, current_user.id, current_user.role.value,
                          "UPDATE", "client_pending_items", item_id,
                          detalhes=f"cliente {client_id}: {', '.join(mudancas)}")
    await db.commit()
    return {"ok": True}


@router.delete("/{client_id}/pending-items/{item_id}")
async def delete_pending_item(
    client_id: str,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _exigir_cliente_visivel(db, current_user, client_id)
    # Só grava o audit log (imutável) se uma linha foi de fato afetada — sem
    # isto, id inexistente/já excluído/de outro cliente gravava um "DELETE"
    # no WORM sem nenhuma exclusão real ter ocorrido (achado do Codex).
    result = await db.execute(
        text("UPDATE client_pending_items SET deleted_at=NOW() "
             "WHERE id=:id AND client_id=:cid AND deleted_at IS NULL"),
        {"id": item_id, "cid": client_id}
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Item not found")
    await criar_audit_log(db, current_user.id, current_user.role.value,
                          "DELETE", "client_pending_items", item_id,
                          detalhes=f"cliente {client_id}")
    await db.commit()
    return {"ok": True}
