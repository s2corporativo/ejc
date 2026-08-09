"""Cliente público do SGT/CNJ (Tabelas Processuais Unificadas - TPU).

Fonte oficial: https://www.cnj.jus.br/sgt/infWebService.php
WSDL: https://www.cnj.jus.br/sgt/sgt_ws.php?wsdl

O serviço é SOAP/RPC com corpo literal. Para não adicionar uma dependência SOAP
ao backend, este cliente monta o envelope mínimo e normaliza a resposta XML,
inclusive referências SOAP ``href``/``multiRef``. Nenhuma credencial é necessária.
"""
from __future__ import annotations

import asyncio
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx

from app.integrations.feature_flags import require_enabled


SGT_ENDPOINT = "https://www.cnj.jus.br/sgt/sgt_ws.php"
SGT_WSDL = f"{SGT_ENDPOINT}?wsdl"
SGT_NS = SGT_ENDPOINT
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XSD = "http://www.w3.org/2001/XMLSchema"

TIPOS_TABELA = frozenset({"A", "M", "C"})
TIPOS_PESQUISA = frozenset({"G", "N", "C"})
_TRANSIENTES = {429, 500, 502, 503, 504}


class CnjSgtError(RuntimeError):
    """Falha segura no WebService SGT/CNJ."""


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1].split(":", 1)[-1]


def _resolver_xml(
    root: ET.Element,
    el: ET.Element,
    visitados: frozenset[str] = frozenset(),
) -> Any:
    """Converte SOAP em Python e interrompe ciclos href/multiRef."""
    href = el.attrib.get("href")
    if href and href.startswith("#"):
        alvo_id = href[1:]
        if alvo_id in visitados:
            raise CnjSgtError("CNJ/SGT retornou referência SOAP cíclica")
        for candidato in root.iter():
            if candidato.attrib.get("id") == alvo_id:
                return _resolver_xml(root, candidato, visitados | {alvo_id})
        raise CnjSgtError("CNJ/SGT retornou referência SOAP sem destino")

    filhos = list(el)
    if not filhos:
        return (el.text or "").strip()

    pares: list[tuple[str, Any]] = [
        (_local(f.tag), _resolver_xml(root, f, visitados)) for f in filhos
    ]
    nomes = [k for k, _ in pares]
    if nomes and len(set(nomes)) == 1:
        return [v for _, v in pares]

    out: dict[str, Any] = {}
    for chave, valor in pares:
        if chave in out:
            atual = out[chave]
            if not isinstance(atual, list):
                atual = [atual]
            atual.append(valor)
            out[chave] = atual
        else:
            out[chave] = valor
    return out


def _parse_soap(xml_text: str) -> Any:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise CnjSgtError("CNJ/SGT retornou XML inválido") from exc

    for el in root.iter():
        if _local(el.tag) == "Fault":
            fault = _resolver_xml(root, el)
            codigo = fault.get("faultcode") if isinstance(fault, dict) else None
            raise CnjSgtError(
                f"CNJ/SGT retornou SOAP Fault{': ' + str(codigo) if codigo else ''}"
            )

    for el in root.iter():
        if _local(el.tag) == "return":
            return _resolver_xml(root, el)
    raise CnjSgtError("CNJ/SGT retornou resposta SOAP sem campo return")


def _envelope(method: str, params: list[tuple[str, str, str]]) -> str:
    """Envelope RPC/literal alinhado ao binding publicado no WSDL do SGT."""
    campos = "".join(
        f'<{nome} xsi:type="xsd:{tipo}">{escape(valor)}</{nome}>'
        for nome, valor, tipo in params
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:xsi="{XSI}" xmlns:xsd="{XSD}" '
        f'xmlns:soapenv="{SOAP_ENV}" xmlns:sgt="{SGT_NS}">'
        '<soapenv:Body>'
        f'<sgt:{method}>{campos}</sgt:{method}>'
        '</soapenv:Body></soapenv:Envelope>'
    )


class CnjSgtClient:
    def __init__(self, timeout_s: float = 25.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def _call(self, method: str, params: list[tuple[str, str, str]]) -> Any:
        require_enabled("cnj_sgt", "CNJ/SGT — TPU")
        body = _envelope(method, params)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{SGT_NS}#{method}"',
            "Accept": "text/xml, application/xml",
            "User-Agent": "EJC/1.0 (+https://depaulateixeira.adv.br; cnj-sgt)",
        }
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.post(
                        SGT_ENDPOINT,
                        content=body.encode("utf-8"),
                        headers=headers,
                    )
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    return _parse_soap(resp.text)
                except CnjSgtError:
                    raise
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    ultimo = exc
                    status = getattr(
                        getattr(exc, "response", None), "status_code", None
                    )
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.5)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise CnjSgtError(
            f"CNJ/SGT indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo

    async def pesquisar(
        self,
        tipo_tabela: str,
        valor: str,
        *,
        tipo_pesquisa: str = "N",
    ) -> Any:
        tabela = (tipo_tabela or "").upper().strip()
        pesquisa = (tipo_pesquisa or "").upper().strip()
        valor = (valor or "").strip()
        if tabela not in TIPOS_TABELA:
            raise ValueError(
                "tipo_tabela deve ser A (assunto), M (movimento) ou C (classe)"
            )
        if pesquisa not in TIPOS_PESQUISA:
            raise ValueError(
                "tipo_pesquisa deve ser G (glossário), N (nome) ou C (código)"
            )
        if not valor or len(valor) > 200:
            raise ValueError("valor de pesquisa obrigatório (máximo 200 caracteres)")
        return await self._call(
            "pesquisarItemPublicoWS",
            [
                ("tipoTabela", tabela, "string"),
                ("tipoPesquisa", pesquisa, "string"),
                ("valorPesquisa", valor, "string"),
            ],
        )

    async def detalhes(self, seq_item: int | str, tipo_item: str) -> Any:
        tipo = (tipo_item or "").upper().strip()
        if tipo not in TIPOS_TABELA:
            raise ValueError("tipo_item deve ser A, M ou C")
        seq = str(seq_item).strip()
        if not seq.isdigit():
            raise ValueError("seq_item deve ser numérico")
        return await self._call(
            "getArrayDetalhesItemPublicoWS",
            [("seqItem", seq, "string"), ("tipoItem", tipo, "string")],
        )

    async def filhos(self, seq_item: int | str, tipo_item: str) -> Any:
        tipo = (tipo_item or "").upper().strip()
        if tipo not in TIPOS_TABELA:
            raise ValueError("tipo_item deve ser A, M ou C")
        seq = str(seq_item).strip()
        if not seq.isdigit():
            raise ValueError("seq_item deve ser numérico")
        return await self._call(
            "getArrayFilhosItemPublicoWS",
            [("seqItem", seq, "int"), ("tipoItem", tipo, "string")],
        )

    async def ultima_versao(self) -> str:
        resultado = await self._call("getDataUltimaVersao", [])
        return str(resultado or "").strip()
