"""Hardening adicional da Onda #836 após revisão do PR #887.

Sem rede real: HTTP é simulado e os testes focam em proveniência/parse seguro.
"""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest

from app.integrations import cnj_sgt_client as sgt_mod
from app.integrations import feature_flags
from app.integrations import ide_sisema_client as sisema_mod
from app.integrations import inlabs_parser as inlabs_mod
from app.integrations import pgfn_open_data_client as pgfn_mod
from app.integrations.cnj_sgt_client import CnjSgtClient, CnjSgtError
from app.integrations.ide_sisema_client import IdeSisemaClient
from app.integrations.inlabs_parser import InlabsParseError, parse_xml, parse_zip
from app.integrations.pgfn_open_data_client import PgfnOpenDataClient
from app.services.juris_import.tcu import normalizar_registro as normalizar_tcu


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    for env_name in feature_flags.FLAGS.values():
        monkeypatch.setenv(env_name, "true")


def _mock_httpx(monkeypatch, modulo, handler):
    real = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real(**kwargs)

    monkeypatch.setattr(modulo.httpx, "AsyncClient", factory)


def test_tcu_rejeita_url_https_fora_do_dominio_oficial():
    julgado = normalizar_tcu({
        "chave": "AC-99-2026-P",
        "numero": 99,
        "ano": 2026,
        "titulo": "Licitação",
        "sumario": "Texto de teste",
        "url": "https://evil.example/acordao/99",
        "data_sessao": "2026-08-01",
        "colegiado": "Plenário",
    })
    assert julgado is None


def test_inlabs_rejeita_doctype_e_entity():
    xml = b"""<?xml version='1.0'?>
    <!DOCTYPE root [<!ENTITY x 'conteudo'>]>
    <root><article><body>&x;&x;&x;&x;&x;</body></article></root>"""
    with pytest.raises(InlabsParseError, match="DTD/ENTITY"):
        parse_xml(xml)


def test_inlabs_converte_falha_de_leitura_zip_em_erro_controlado(monkeypatch):
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("dou.xml", "<root><article><body>texto suficientemente longo</body></article></root>")

    real_zip = inlabs_mod.ZipFile

    class ZipComFalha:
        def __init__(self, *args, **kwargs):
            self._zip = real_zip(*args, **kwargs)

        def infolist(self):
            return self._zip.infolist()

        def read(self, info):
            raise RuntimeError("membro criptografado ou ilegível")

    monkeypatch.setattr(inlabs_mod, "ZipFile", ZipComFalha)
    with pytest.raises(InlabsParseError, match="membro XML"):
        parse_zip(buf.getvalue())


def test_cnj_sgt_rejeita_referencia_soap_ciclica():
    xml = """<Envelope><Body><return href='#id1'/><multiRef id='id1' href='#id1'/></Body></Envelope>"""
    with pytest.raises(CnjSgtError, match="cíclica"):
        sgt_mod._parse_soap(xml)


async def test_cnj_sgt_detalhes_envia_seqitem_string(monkeypatch):
    visto = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto["body"] = req.content.decode("utf-8")
        return httpx.Response(
            200,
            text="<Envelope><Body><return><ok>1</ok></return></Body></Envelope>",
        )

    _mock_httpx(monkeypatch, sgt_mod, handler)
    await CnjSgtClient().detalhes("123", "C")
    assert '<seqItem xsi:type="xsd:string">123</seqItem>' in visto["body"]


async def test_pgfn_nao_confunde_pagina_sem_download_com_recurso(monkeypatch):
    html = """
    <html><body>
      <a href='https://arquivos.pgfn.gov.br/dados-abertos/2026/base.zip'>Base ZIP</a>
      <a href='/pgfn/pt-br/assuntos/pagina-sem-download'>Ajuda</a>
    </body></html>
    """

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, request=req)

    _mock_httpx(monkeypatch, pgfn_mod, handler)
    itens = await PgfnOpenDataClient().listar_recursos(ano=None)
    assert len(itens) == 1
    assert itens[0]["url"].endswith("/base.zip")


async def test_sisema_preserva_featurecollection_em_envelope(monkeypatch):
    geojson = {
        "type": "FeatureCollection",
        "features": [],
        "proveniencia_ejc": "valor-original-do-servidor",
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=geojson)

    _mock_httpx(monkeypatch, sisema_mod, handler)
    out = await IdeSisemaClient().consultar_camadas("sisema:camada", count=1)
    assert out["geojson"] == geojson
    assert out["geojson"]["proveniencia_ejc"] == "valor-original-do-servidor"
    assert out["proveniencia_ejc"]["fonte"] == "IDE-Sisema — Sisema/MG"
