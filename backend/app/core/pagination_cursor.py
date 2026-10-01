# ── app/core/pagination_cursor.py ────────────────────────────────────────────
# Cursor de paginação comum (Tarefa 2) — assinado, vinculado a
# usuário/papel/filtros/ordem/endpoint, com expiração.
#
# Design (contrato do plano de performance):
#   make_cursor(endpoint, viewer, filters, order, last_key) -> str
#   parse_cursor(token, endpoint, viewer, filters, order)  -> list
#
# Garantias:
#   - Token = base64url(payload JSON) + "." + HMAC-SHA256(payload)
#     A chave HMAC é DERIVADA de Settings.SECRET_KEY (app/core/config.py) —
#     o segredo NUNCA vai para o repo; trocar o SECRET_KEY invalida cursores
#     (efeito aceitável: o cliente refaz a página 1).
#   - parse_cursor rejeita: assinatura/payload violados, endpoint/viewer
#     (id+role)/filtros/ordem diferentes, token expirado (TTL padrão 30 min).
#     → invalidação automática quando o contexto muda; autorização é
#       REAPLICADA em toda página (o cursor nunca carrega autorização).
#   - last_key pode conter None (colunas anuláveis; ordenação NULLS LAST).
#   - Semântica live: o cursor NÃO promete snapshot — linha editada entre
#     páginas segue a ordem corrente; documentado no contrato das rotas.
#
# O predicado keyset (condicao_lexicografica) implementa
# (c1..cn) > (v1..vn) sob ASC NULLS LAST com valores None — via recursão:
#   maior que nulo-não-existe no último nível; antes disso:
#     val None → col IS NULL E resolve o restante
#     val ok   → col IS NULL (nulls last: qualquer NULL vem depois)
#                OU col > val OU (col == val E restante)
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import and_, false as _false, or_
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings

# TTL padrão dos cursores (s): uma sessão de navegação não deve receber
# páginas de um estado muito velho; editores concorrentes invalidam naturalmente.
CURSOR_TTL_PADRAO = 1800

_VERSAO = "v1"


def _chave_hmac() -> bytes:
    """Deriva chave exclusiva do cursor do SECRET_KEY (nunca persistida)."""
    return hmac.new(
        get_settings().SECRET_KEY.encode("utf-8"),
        b"ejc:pagination-cursor:" + _VERSAO.encode(),
        hashlib.sha256,
    ).digest()


# ── normalização de filtros (determinística) ─────────────────────────────────

def normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Forma canônica dos filtros para binding do cursor.

    - chaves ordenadas na serialização (sort_keys)
    - string vazia → None (filtro ausente)
    - bool/None preservados; números e strings intactos
    """
    limpo: dict[str, Any] = {}
    for k in sorted(filters):
        v = filters[k]
        if isinstance(v, str):
            v = v.strip()
            v = v if v != "" else None
        limpo[k] = v
    return limpo


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


# ── serialização de chaves (datas/datetimes → ISO; None preservado) ─────────

def serializar_key(last_key: Sequence[Any]) -> list[Any]:
    out = []
    for v in last_key:
        if v is None:
            out.append(None)
        elif isinstance(v, datetime):
            out.append(v.isoformat())
        elif hasattr(v, "isoformat"):  # date
            out.append(v.isoformat())
        else:
            out.append(v)
    return out


# ── make/parse ───────────────────────────────────────────────────────────────

def make_cursor(endpoint: str, viewer, filters: dict, order: str,
                last_key: Sequence[Any]) -> str:
    """Emite token assinado para continuar a listagem a partir de `last_key`."""
    payload = {
        "v": _VERSAO,
        "e": endpoint,
        "u": viewer.id,
        "r": getattr(viewer.role, "value", str(viewer.role)),
        "f": normalize_filters(filters),
        "o": order,
        "k": serializar_key(last_key),
        "exp": int(time.time()) + CURSOR_TTL_PADRAO,
    }
    corpo = base64.urlsafe_b64encode(_canon(payload).encode("utf-8")).decode("ascii")
    sig = hmac.new(_chave_hmac(), corpo.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{corpo}.{sig}"


def parse_cursor(token: str, endpoint: str, viewer, filters: dict,
                 order: str) -> list[Any]:
    """Valida e devolve a last_key. Qualquer divergência → HTTPException 400."""
    try:
        corpo, sig = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="cursor inválido")
    esperada = hmac.new(_chave_hmac(), corpo.encode("ascii"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperada, sig):
        raise HTTPException(status_code=400, detail="cursor inválido")
    try:
        pad = "=" * (-len(corpo) % 4)
        payload = json.loads(base64.urlsafe_b64decode(corpo + pad).decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="cursor inválido")
    if not isinstance(payload, dict) or payload.get("v") != _VERSAO:
        raise HTTPException(status_code=400, detail="cursor inválido")
    if payload.get("e") != endpoint:
        raise HTTPException(status_code=400, detail="cursor inválido")
    if payload.get("u") != viewer.id:
        raise HTTPException(status_code=400, detail="cursor inválido")
    if payload.get("r") != getattr(viewer.role, "value", str(viewer.role)):
        raise HTTPException(status_code=400, detail="cursor inválido")
    if payload.get("f") != normalize_filters(filters):
        raise HTTPException(status_code=400, detail="cursor inválido")
    if payload.get("o") != order:
        raise HTTPException(status_code=400, detail="cursor inválido")
    try:
        if int(payload.get("exp", 0)) < int(time.time()):
            raise HTTPException(status_code=400, detail="cursor expirado")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="cursor inválido")
    k = payload.get("k")
    if not isinstance(k, list):
        raise HTTPException(status_code=400, detail="cursor inválido")
    return k


# ── predicado keyset (ORDER BY total com NULLS LAST) ─────────────────────────

def condicao_lexicografica(
    colunas: Sequence[ColumnElement],
    ultimo: Sequence[Any],
    direcoes: Optional[Sequence[str]] = None,
) -> ColumnElement:
    """(c1..cn) > (v1..vn) na semântica default do PostgreSQL:
    ASC NULLS LAST (NULL = +∞) e DESC NULLS FIRST (NULL = −∞).

    `ultimo` recebe os valores DESSERIALIZADOS (date/datetime/str/None) —
    a desserialização é responsabilidade da rota (conhece os tipos).
    `direcoes`: sequência de "asc"/"desc" (padrão: todas "asc"); o par
    (direção, NULLS) segue o default do PG para que o predicado case com o
    ORDER BY da query.
    """
    if len(colunas) != len(ultimo):
        raise HTTPException(status_code=400, detail="cursor inválido")
    if not colunas:
        return _false()
    dirs = list(direcoes) if direcoes else ["asc"] * len(colunas)
    if len(dirs) != len(colunas):
        raise HTTPException(status_code=400, detail="cursor inválido")
    return _depois(list(colunas), list(ultimo), dirs)


def _depois(cols: list, vals: list, dirs: list) -> ColumnElement:
    col, val, d = cols[0], vals[0], dirs[0]
    resto = _depois(cols[1:], vals[1:], dirs[1:]) if len(cols) > 1 else None

    def _resto() -> ColumnElement:
        return resto if resto is not None else _false()

    if len(cols) == 1:
        if val is None:
            # nível final com valor NULL: ordem ASC (NULLS LAST) não tem nada
            # depois; DESC (NULLS FIRST) tem todos os não-nulos depois.
            return _false() if d == "asc" else col.is_not(None)
        return col > val if d == "asc" else col < val
    if val is None:
        if d == "asc":
            # NULL = +∞: só outra linha NULL pode vir depois (resolve no resto)
            return and_(col.is_(None), _resto())
        # NULL = −∞ (primeiro): depois dele vêm os outros NULLs (resto)
        # e TODOS os não-nulos
        return or_(and_(col.is_(None), _resto()), col.is_not(None))
    if d == "asc":
        return or_(
            col.is_(None),                        # NULLS LAST: NULL vem depois
            and_(col > val, col.is_not(None)),    # estritamente maior
            and_(col == val, _resto()),           # empate: resolve no restante
        )
    return or_(
        and_(col < val, col.is_not(None)),        # estritamente menor
        and_(col == val, _resto()),               # empate: resolve no restante
    )


# ── desserialização de chaves por rota ───────────────────────────────────────

def deserializar_key(k: Sequence[Any], *tipos: type) -> list[Any]:
    """Converte strings ISO de volta para os tipos informados (None preservado).

    `tipos` alinha posição a posição com a chave; `None` em tipos[x] pula a
    conversão (ex.: id string).
    """
    out: list[Any] = []
    for i, v in enumerate(k):
        alvo = tipos[i] if i < len(tipos) else None
        if v is None or alvo is None:
            out.append(v)
            continue
        try:
            out.append(alvo(v))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="cursor inválido")
    return out


def order_str(*partes: tuple[ColumnElement, str]) -> str:
    """String canônica de ordem p/ binding do cursor.

    Ex.: order_str((Task.data_limite, "asc_nulls_last"), (Task.created_at, "asc"),
                   (Task.id, "asc")) → "data_limite:asc_nulls_last,..."
    """
    return ",".join(f"{getattr(c, 'key', str(c))}:{d}" for c, d in partes)
