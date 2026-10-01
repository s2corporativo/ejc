# ── app/core/pagination_cursor.py ────────────────────────────────────────────
# Cursor de paginação keyset assinado (HMAC-SHA256) — Tarefa 2 do plano de
# performance (docs/performance/ejc-entrada-caso-hoje-baseline.md §6/§10).
#
# Contrato (fonte única, reusado por tasks/atividades/cases/clients/prazos/
# documents):
#   make_cursor(endpoint, viewer, filters, order, last_key) -> str
#   parse_cursor(token, endpoint, viewer, filters, order)   -> list  # last_key
#
# Regras de segurança (baseline §3 — contratos de visibilidade):
#   • Token opaco: payload JSON canônico + HMAC-SHA256. A chave vem de
#     PAGINATION_CURSOR_SECRET com fallback ao SECRET_KEY (ambas do
#     app.core/config.py — nenhum segredo no repo). Em dev, sem nenhuma das
#     duas, usa chave efêmera constante: cursores morrem no restart, mesma
#     postura do JWT dev (produção valida SECRET_KEY e rejeita placeholder).
#   • Mudança de usuário, filtros, ordenação ou endpoint invalida o cursor
#     (CursorInvalido → o router mapeia para 409). Reautenticação por página:
#     a query da página aplica o predicado de visibilidade corrente do
#     chamador — o cursor NUNCA concede acesso que a query não daria.
#   • Filtros canonizados (bool 0/1, None ausente, chaves ordenadas): um
#     cursor emitido para `?minhas=true` não vale para `?minhas=false`, e
#     `?status=&minhas` == `?minhas`.
#   • O payload carrega só o last_key + hash do contexto — nenhum dado de
#     negócio/PII além dos valores da chave de ordenação (id/data).
#   • Tampering: qualquer byte do body alterado quebra o HMAC; base64 mal-
#     formado ou campos ausentes caem em CursorInvalido (nunca 500).
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Mapping

from sqlalchemy import and_, or_

from app.core.config import get_settings

settings = get_settings()

__all__ = [
    "CursorInvalido",
    "canon_filters",
    "cond_keyset_2",
    "make_cursor",
    "parse_cursor",
]

_FORMATO = "json"
_SEP = "."

# Chave efêmera de DEV: produção é coberta pelo validador de SECRET_KEY do
# config (_validar_seguranca_producao); em dev um cursor que morre no restart
# é aceitável (o frontend refaz a página 1).
_DEV_FALLBACK = "ejc-dev-cursor-key-nao-usar-em-producao"


class CursorInvalido(ValueError):
    """Cursor ausente/malformado/adulterado ou emitido para outro contexto.

    ValueError por compatibilidade: routers mapeiam para HTTP 409, testes
    podem capturar como ValueError.
    """


def _chave() -> bytes:
    segredo = (
        getattr(settings, "PAGINATION_CURSOR_SECRET", "") or settings.SECRET_KEY
    )
    if not segredo:
        segredo = _DEV_FALLBACK
    return segredo.encode()


def _b64(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode().rstrip("=")


def _b64d(texto: str) -> bytes:
    pad = "=" * (-len(texto) % 4)
    try:
        return base64.urlsafe_b64decode(texto + pad)
    except Exception as exc:
        raise CursorInvalido("cursor malformado") from exc


def _compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hmac(body: str) -> str:
    return _b64(hmac.new(_chave(), body.encode(), hashlib.sha256).digest())


def canon_filters(filters: Mapping[str, Any] | None) -> str:
    """Forma canônica dos filtros para invalidação determinística.

    Regras: chaves ordenadas; None é AUSENTE (não "None"); bool vira 0/1
    (senão "True" != "true" criaria dois cursores para a mesma consulta);
    demais valores via str(). `status` vazio é ausente (convenção do
    /deadlines/: status="" significa todos).
    """
    canon: dict[str, str] = {}
    for chave in sorted(filters or {}):
        valor = filters[chave]
        if valor is None:
            continue
        if isinstance(valor, str) and valor == "":
            continue
        if isinstance(valor, bool):
            valor = "1" if valor else "0"
        canon[chave] = str(valor)
    return _compact(canon)


def _contexto(endpoint: str, viewer_id: str, filters: Mapping[str, Any] | None,
              order: str) -> str:
    return _compact({
        "e": endpoint,
        "u": str(viewer_id),
        "f": hashlib.sha256(canon_filters(filters).encode()).hexdigest(),
        "o": order,
    })


def make_cursor(
    endpoint: str,
    viewer: Any,
    filters: Mapping[str, Any] | None,
    order: str,
    last_key: Sequence[Any],
) -> str:
    """Emiti um cursor opaco para continuar DEPOIS de `last_key`.

    `last_key` é a tupla de valores da chave de ordenação da ÚLTIMA linha da
    página (mesma cardinalidade/semântica do `order` informado).
    """
    payload = {
        "v": 1,
        "c": _contexto(endpoint, str(getattr(viewer, "id", viewer)), filters, order),
        "k": list(last_key),
    }
    body = _b64(_compact(payload).encode())
    return body + _SEP + _hmac(body)


def parse_cursor(
    token: str,
    endpoint: str,
    viewer: Any,
    filters: Mapping[str, Any] | None,
    order: str,
) -> list:
    """Valida assinatura E contexto; devolve o last_key (lista de valores).

    Levanta CursorInvalido quando: formato/HMAC inválidos, versão
    desconhecida, ou o cursor foi emitido para outro usuário/filtros/
    ordenação/endpoint (invalidação determinística — baseline §6.4).
    """
    if not token or _SEP not in token:
        raise CursorInvalido("cursor ausente ou malformado")
    body, _, sig = token.rpartition(_SEP)
    if not body or not sig:
        raise CursorInvalido("cursor ausente ou malformado")
    if not hmac.compare_digest(sig, _hmac(body)):
        raise CursorInvalido("cursor inválido (assinatura)")
    payload_raw = _b64d(body)
    try:
        payload = json.loads(payload_raw.decode())
    except Exception as exc:
        raise CursorInvalido("cursor malformado") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise CursorInvalido("cursor de versão desconhecida")
    esperado = _contexto(endpoint, str(getattr(viewer, "id", viewer)), filters, order)
    if not hmac.compare_digest(str(payload.get("c")), esperado):
        raise CursorInvalido(
            "cursor não corresponde a esta consulta: emita um novo "
            "(filtros, ordenação, endpoint ou usuário mudaram)"
        )
    chave = payload.get("k")
    if not isinstance(chave, list):
        raise CursorInvalido("cursor sem chave de continuação")
    return chave


def cond_keyset_2(col_a, col_b, last, *, direction: str, nulls_tail: bool):
    """Condição 'linha vem DEPOIS de last' para ordenação de 2 colunas.

    Regras (baseline §6.4 — páginas do cursor são uma partição determinística
    da MESMA ordem do caminho legacy):
      • col_b é o desempate absoluto (id) — presumido NOT NULL;
      • direction="desc" replica `col_a DESC` do Postgres, cujo default é
        NULLS FIRST ⇒ nulls_tail=False (NULL ≡ cabeça);
      • para ordenações NULLS LAST (forçadas ou ASC default) use
        nulls_tail=True ⇒ NULL ≡ cauda, e as linhas NULL vêm DEPOIS de
        qualquer valor.
    `last` é a dupla (valor_a, valor_b) do cursor — valores Python nativos
    (coerção ISO→date/datetime é responsabilidade do router, como em tasks.py).
    """
    if len(last) != 2:
        raise CursorInvalido("cursor incompatível com a ordenação atual")
    last_a, last_b = last
    compara = (col_a < last_a) if direction == "desc" else (col_a > last_a)
    if last_a is None:
        # last está na cauda (ou cabeça) dos NULL: restam só NULLs, por (col_b)
        return and_(col_a.is_(None), col_b > last_b)
    ramos = []
    if nulls_tail:
        ramos.append(col_a.is_(None))  # NULLs vêm depois de qualquer valor
    ramos.extend([compara, and_(col_a == last_a, col_b > last_b)])
    return or_(*ramos)
