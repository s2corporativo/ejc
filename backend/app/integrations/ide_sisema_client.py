"""Cliente OGC da IDE-Sisema/MG.

Fonte oficial do Sisema: WMS/WFS/WCS em host fixo. O EJC usa WFS 2.0 para
listar camadas e consultar feições vetoriais. Não aceitamos URL arbitrária nem
CQL livre para evitar SSRF/injeção no GeoServer.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import httpx


IDE_SISEMA_OWS = "https://geoserver.meioambiente.mg.gov.br/ows"
_LAYER_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")
_TRANSIENTES = {429, 500, 502, 503, 504}


class IdeSisemaError(RuntimeError):
    pass


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _parse_capabilities(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise IdeSisemaError("IDE-Sisema retornou capabilities XML inválido") from exc
    camadas: list[dict[str, str]] = []
    for feature in root.iter():
        if _local(feature.tag) != "FeatureType":
            continue
        nome = titulo = resumo = ""
        for filho in feature:
            chave = _local(filho.tag)
            valor = (filho.text or "").strip()
            if chave == "Name":
                nome = valor
            elif chave == "Title":
                titulo = valor
            elif chave == "Abstract":
                resumo = valor
        if nome:
            camadas.append({"name": nome, "title": titulo or nome, "abstract": resumo})
    return camadas


class IdeSisemaClient:
    def __init__(self, timeout_s: float = 30.0) -> None:
        self.timeout = httpx.Timeout(timeout_s)

    async def _get(self, params: dict[str, Any], *, accept: str) -> httpx.Response:
        ultimo: Exception | None = None
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Accept": accept, "User-Agent": "EJC/1.0 IDE-Sisema"},
            follow_redirects=True,
        ) as client:
            for tentativa in range(2):
                try:
                    resp = await client.get(IDE_SISEMA_OWS, params=params)
                    if resp.status_code in _TRANSIENTES:
                        raise httpx.HTTPStatusError(
                            f"HTTP {resp.status_code}", request=resp.request, response=resp
                        )
                    resp.raise_for_status()
                    return resp
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    ultimo = exc
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        break
                    if tentativa == 0:
                        await asyncio.sleep(0.6)
        status = getattr(getattr(ultimo, "response", None), "status_code", None)
        raise IdeSisemaError(
            f"IDE-Sisema indisponível{f' (HTTP {status})' if status else ''}"
        ) from ultimo

    async def listar_camadas(self) -> list[dict[str, str]]:
        resp = await self._get(
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetCapabilities",
            },
            accept="application/xml,text/xml",
        )
        return _parse_capabilities(resp.text)

    async def consultar_camadas(
        self,
        type_name: str,
        *,
        bbox: Iterable[float] | None = None,
        count: int = 50,
        srs_name: str = "EPSG:4326",
    ) -> dict[str, Any]:
        camada = (type_name or "").strip()
        if not _LAYER_RE.fullmatch(camada):
            raise ValueError("type_name de camada inválido")
        if srs_name not in {"EPSG:4326", "EPSG:4674"}:
            raise ValueError("srs_name permitido: EPSG:4326 ou EPSG:4674")
        count = max(1, min(int(count), 200))
        params: dict[str, Any] = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": camada,
            "outputFormat": "application/json",
            "count": count,
            "srsName": srs_name,
        }
        if bbox is not None:
            coords = [float(x) for x in bbox]
            if len(coords) != 4:
                raise ValueError("bbox deve conter minx,miny,maxx,maxy")
            minx, miny, maxx, maxy = coords
            if not (-180 <= minx <= 180 and -180 <= maxx <= 180):
                raise ValueError("longitude do bbox fora do intervalo")
            if not (-90 <= miny <= 90 and -90 <= maxy <= 90):
                raise ValueError("latitude do bbox fora do intervalo")
            if minx >= maxx or miny >= maxy:
                raise ValueError("bbox inválido: mínimos devem ser menores que máximos")
            params["bbox"] = f"{minx},{miny},{maxx},{maxy},{srs_name}"
        resp = await self._get(params, accept="application/json")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise IdeSisemaError("IDE-Sisema retornou GeoJSON inválido") from exc
        if not isinstance(payload, dict):
            raise IdeSisemaError("IDE-Sisema retornou formato inesperado")
        payload["proveniencia_ejc"] = {
            "fonte": "IDE-Sisema — Sisema/MG",
            "protocolo": "OGC WFS 2.0",
            "camada": camada,
        }
        return payload
