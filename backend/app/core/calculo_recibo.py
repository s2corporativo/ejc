"""Recibo assinado de cálculo — prova de que um número saiu de uma calculadora.

Motivo (review do PR de correções P0, 2026-07-26): o gate de homologação em
`POST /pecas/demonstrativo` recebia do CLIENTE tanto o `ferramenta_endpoint`
quanto as linhas do resultado. Bastaria uma ferramenta ser promovida a
`homologada` para que qualquer chamador materializasse números arbitrários —
inclusive vindos de uma calculadora `bloqueada` — alegando o endpoint aprovado.
O gate afirmava um invariante que não impunha.

Aqui esse invariante passa a ser verificável: toda resposta de ferramenta de
ramos sai com um `_recibo` assinado (HMAC-SHA256 com a `SECRET_KEY`) que carrega
o endpoint e o resultado EXATO produzido pelo servidor. A geração do documento
formal só aceita o recibo — e monta a memória de cálculo a partir do resultado
assinado, nunca do que o cliente enviar.

Não é um token de autenticação: o acesso continua sendo do `AuthMiddleware`/RBAC.
É uma prova de PROVENIÊNCIA do número, com validade curta.
"""
from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Any, Optional

from app.core.config import get_settings

# Janela curta: o recibo existe para a ação imediata "calculei → gero a peça".
TTL_SEGUNDOS = 2 * 60 * 60


def _chave() -> bytes:
    return get_settings().SECRET_KEY.encode()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def normalizar_endpoint(path: str) -> str:
    """Remove o prefixo de API para casar com as chaves do registro de homologação."""
    for prefixo in ("/api/v1", "/api"):
        if path.startswith(prefixo):
            path = path[len(prefixo):]
            break
    return path.rstrip("/")


def emitir(endpoint: str, resultado: dict[str, Any]) -> str:
    """Assina `endpoint` + `resultado` e devolve o recibo (corpo.assinatura)."""
    payload = {
        "e": normalizar_endpoint(endpoint),
        "r": resultado,
        "x": int(time.time()) + TTL_SEGUNDOS,
    }
    corpo = _b64e(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    )
    assinatura = hmac.new(_chave(), corpo.encode(), sha256).hexdigest()
    return f"{corpo}.{assinatura}"


def validar(recibo: str) -> Optional[dict[str, Any]]:
    """Devolve {'endpoint', 'resultado'} se o recibo for autêntico e vigente."""
    if not recibo or "." not in recibo:
        return None
    corpo, _, assinatura = recibo.rpartition(".")
    esperado = hmac.new(_chave(), corpo.encode(), sha256).hexdigest()
    if not hmac.compare_digest(assinatura, esperado):
        return None
    try:
        payload = json.loads(_b64d(corpo))
    except Exception:
        return None
    if not isinstance(payload, dict) or int(payload.get("x", 0)) < int(time.time()):
        return None
    resultado = payload.get("r")
    if not isinstance(resultado, dict):
        return None
    return {"endpoint": payload.get("e", ""), "resultado": resultado}


# Campos que são rodapé/metadado da resposta, não itens da memória de cálculo.
_NAO_E_LINHA = {"aviso", "base", "observacao", "descricao", "_recibo"}


def linhas_do_resultado(resultado: dict[str, Any]) -> list[tuple[str, str]]:
    """Converte o resultado assinado em linhas (label, valor) da memória de cálculo.

    Mesma seleção que a UI fazia — mas executada no SERVIDOR, sobre o dado
    assinado, para que o texto do documento derive do cálculo real.
    """
    return [
        (chave.replace("_", " "), str(valor))
        for chave, valor in resultado.items()
        if chave not in _NAO_E_LINHA
        and valor is not None
        and not isinstance(valor, (dict, list))
    ]


def rodape_do_resultado(resultado: dict[str, Any]) -> str:
    partes = [str(resultado[k]) for k in ("observacao", "descricao") if resultado.get(k)]
    return "\n".join(partes)
