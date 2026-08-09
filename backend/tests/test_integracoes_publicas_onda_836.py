"""Regressão da Onda #836 — integrações públicas oficiais.

A suíte NÃO acessa internet: todos os clientes HTTP usam MockTransport.
"""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest

from app.integrations import ckan_public_client as ckan_mod
from app.integrations import cnj_sgt_client as sgt_mod
from app.integrations import ibge_localidades_client as ibge_mod
from app.integrations import ide_sisema_client as sisema_mod
from app.integrations import pgfn_open_data_client as pgfn_mod
from app.integrations import querido_diario_client as qd_mod
from app.integrations import tcu_client as tcu_mod
from app.integrations.ckan_public_client import CkanPublicClient
from app.integrations.cnj_sgt_client import CnjSgtClient
from app.integrations.ibge_localidades_client import IbgeLocalidadesClient
from app.integrations.ide_sisema_client import IdeSisemaClient
from app.integrations.inlabs_parser import InlabsParseError, parse_xml, parse_zip
from app.integrations.pgfn_open_data_client import PgfnOpenDataClient
from app.integrations.querido_diario_client import QueridoDiarioClient
from app.integrations.tcu_client import TcuPublicClient
from app.services.juris_import import FONTES
from app.services.juris_import.tcu import normalizar_registro as normalizar_tcu


def _mock_async_client(monkeypatch, modulo, handler):
    real = httpx.AsyncClient

    def factory(**kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(modulo.httpx, "AsyncClient", factory)


def test_ckan_rejeita_host_fora_da_allowlist():
    with pytest.raises(ValueError):
        CkanPublicClient("qualquer-host")


async def test_ckan_descobre_recurso_oficial_sem_baixar_arquivo(monkeypatch):
    chamadas = []

    def handler(req: httpx.Request) -> httpx.Response:
        chamadas.append(str(req.url))
        return httpx.Response(200, json={
            "success": True,
            "result": {
                "count": 1,
                "results": [{
                    "id": "ds-1",
                    "title": "Autos de Infração",
                    "resources": [
                        {
                            "id": "r1", "name": "2026.csv", "format": "CSV",
                            "url": "https://dadosabertos.ibama.gov.br/dataset/2026.csv",
                            "last_modified": "2026-08-01T10:00:00",
                        },
                        {
                            "id": "r2", "name": "legado", "format": "CSV",
                            "url": "http://inseguro.exemplo/legado.csv",
                        },
                    ],
                }],
            },
        })

    _mock_async_client(monkeypatch, ckan_mod, handler)
    cli = CkanPublicClient("ibama")
    recursos = await cli.recursos_por_busca("auto de infração", formatos=["CSV"])
    assert len(recursos) == 1
    assert recursos[0].resource_id == "r1"
    assert recursos[0].source == "ibama"
    assert len(chamadas) == 1  # somente package_search; recurso não foi baixado


async def test_cnj_sgt_monta_soap_e_normaliza_return(monkeypatch):
    visto = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto["body"] = req.content.decode()
        xml = """<?xml version='1.0'?>
        <soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/'>
          <soapenv:Body>
            <pesquisarItemPublicoWSResponse>
              <return><codigo>123</codigo><descricao>Procedimento Comum</descricao></return>
            </pesquisarItemPublicoWSResponse>
          </soapenv:Body>
        </soapenv:Envelope>"""
        return httpx.Response(200, text=xml, headers={"content-type": "text/xml"})

    _mock_async_client(monkeypatch, sgt_mod, handler)
    out = await CnjSgtClient().pesquisar("C", "procedimento", tipo_pesquisa="N")
    assert out["codigo"] == "123"
    assert out["descricao"] == "Procedimento Comum"
    assert "pesquisarItemPublicoWS" in visto["body"]
    assert "<tipoTabela" in visto["body"] and ">C</tipoTabela>" in visto["body"]


async def test_tcu_limita_quantidade_e_normaliza(monkeypatch):
    visto = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto.update(dict(req.url.params))
        return httpx.Response(200, json=[{
            "key": "AC-123-2026-P",
            "tipo": "Acórdão",
            "anoAcordao": 2026,
            "numeroAcordao": 123,
            "titulo": "Licitação — qualificação técnica",
            "colegiado": "Plenário",
            "dataSessao": "2026-07-01",
            "relator": "Ministro X",
            "sumario": "Representação sobre exigência de habilitação.",
            "urlAcordao": "https://pesquisa.apps.tcu.gov.br/documento/acordao-completo/123",
        }])

    _mock_async_client(monkeypatch, tcu_mod, handler)
    out = await TcuPublicClient().listar_acordaos(quantidade=999)
    assert visto["quantidade"] == "100"
    assert out[0]["numero"] == 123
    assert out[0]["fonte"] == "TCU — Dados Abertos"


def test_tcu_esta_registrado_no_importador_rag():
    assert "tcu" in FONTES
    assert FONTES["tcu"]["enabled"] is True
    assert callable(FONTES["tcu"]["buscar"])
    j = normalizar_tcu({
        "chave": "AC-1-2026-P",
        "numero": 1,
        "titulo": "Licitação",
        "sumario": "Pregão eletrônico e habilitação",
        "url": "https://tcu.gov.br/acordao/1",
        "data_sessao": "01/08/2026",
        "colegiado": "Plenário",
    })
    assert j is not None
    assert j.tribunal == "TCU"
    assert j.area_juridica == "Administrativo"
    assert j.data == "2026-08-01"


async def test_ibge_canonicaliza_nome_sem_acento(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/estados/MG/municipios")
        return httpx.Response(200, json=[{
            "id": 3106705,
            "nome": "Betim",
            "regiao-imediata": {
                "regiao-intermediaria": {
                    "UF": {
                        "id": 31, "sigla": "MG", "nome": "Minas Gerais",
                        "regiao": {"id": 3, "sigla": "SE", "nome": "Sudeste"},
                    }
                }
            },
        }, {
            "id": 3144805,
            "nome": "Nova Lima",
            "regiao-imediata": {
                "regiao-intermediaria": {
                    "UF": {
                        "id": 31, "sigla": "MG", "nome": "Minas Gerais",
                        "regiao": {"id": 3, "sigla": "SE", "nome": "Sudeste"},
                    }
                }
            },
        }])

    _mock_async_client(monkeypatch, ibge_mod, handler)
    cli = IbgeLocalidadesClient()
    item = await cli.canonicalizar("Nóva Lima", "mg")
    assert item and item["id"] == 3144805
    assert item["uf_sigla"] == "MG"


async def test_querido_diario_envia_parametros_e_marca_agregador(monkeypatch):
    visto = {}

    def handler(req: httpx.Request) -> httpx.Response:
        visto.update(dict(req.url.params))
        return httpx.Response(200, json={"total_gazettes": 0, "gazettes": []})

    _mock_async_client(monkeypatch, qd_mod, handler)
    out = await QueridoDiarioClient().buscar(
        codigo_ibge="3106705", termo="licenciamento ambiental", tamanho=7
    )
    assert visto["territory_ids"] == "3106705"
    assert visto["size"] == "7"
    assert out["proveniencia_ejc"]["natureza"] == "agregador_secundario"
    assert out["proveniencia_ejc"]["conferencia_original_obrigatoria"] is True


async def test_ide_sisema_lista_camadas_wfs(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        xml = """<WFS_Capabilities xmlns='http://www.opengis.net/wfs/2.0'>
          <FeatureTypeList><FeatureType>
            <Name>sisema:areas_embargadas</Name>
            <Title>Áreas Embargadas</Title>
            <Abstract>Camada ambiental de teste</Abstract>
          </FeatureType></FeatureTypeList>
        </WFS_Capabilities>"""
        return httpx.Response(200, text=xml)

    _mock_async_client(monkeypatch, sisema_mod, handler)
    itens = await IdeSisemaClient().listar_camadas()
    assert itens == [{
        "name": "sisema:areas_embargadas",
        "title": "Áreas Embargadas",
        "abstract": "Camada ambiental de teste",
    }]


async def test_ide_sisema_bloqueia_bbox_invalido_sem_rede():
    cli = IdeSisemaClient()
    with pytest.raises(ValueError):
        await cli.consultar_camadas("sisema:camada", bbox=[-44, -20, -45, -19])


async def test_pgfn_filtra_links_nao_oficiais(monkeypatch):
    html = """
      <html><body>
        <a href='https://arquivos.pgfn.gov.br/dados-abertos/2026/base.zip'>Base 2026 ZIP</a>
        <a href='https://evil.example/base.csv'>Base falsa</a>
        <a href='/pgfn/pt-br/assuntos/pagina-sem-download'>Ajuda</a>
      </body></html>
    """

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, request=req)

    _mock_async_client(monkeypatch, pgfn_mod, handler)
    itens = await PgfnOpenDataClient().listar_recursos(ano=2026)
    assert len(itens) == 1
    assert itens[0]["url"].startswith("https://arquivos.pgfn.gov.br/")


def test_inlabs_parse_xml_mantem_proveniencia_e_conferencia():
    xml = b"""<root><article id='42' artType='DO1' pubDate='2026-08-08'>
      <title>Portaria de teste</title>
      <body>Texto oficial suficientemente longo para ser processado pelo EJC.</body>
    </article></root>"""
    itens = parse_xml(xml)
    assert len(itens) == 1
    assert itens[0].titulo == "Portaria de teste"
    assert itens[0].identificador == "42"
    assert itens[0].requer_conferencia_certificada is True


def test_inlabs_zip_rejeita_path_traversal():
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("../escape.xml", "<root><article><body>conteudo longo o bastante para teste</body></article></root>")
    with pytest.raises(InlabsParseError):
        parse_zip(buf.getvalue())


def test_paths_historicos_brasilapi_foram_preservados_e_novas_rotas_existem():
    from app.integrations import routers

    paths = {r.path for r in routers.brasilapi_router.routes}
    assert "/brasilapi/cnpj/{cnpj}" in paths
    assert "/brasilapi/cep/{cep}" in paths
    assert "/cnj/tpu/pesquisar" in paths
    assert "/tcu/acordaos" in paths
    assert "/ibge/canonicalizar" in paths
    assert "/dados-publicos/{fonte}/recursos" in paths
    assert "/pgfn/divida-ativa/recursos" in paths
    assert "/querido-diario/{codigo_ibge}" in paths
    assert "/ide-sisema/feicoes" in paths
    assert routers.brasilapi_router.prefix == "/integracoes"
