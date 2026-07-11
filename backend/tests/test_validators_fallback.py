"""Cadeias de fallback dos utilitários cadastrais (validators_service).

CNPJ: OpenCNPJ → BrasilAPI → ReceitaWS · CEP: BrasilAPI v2 → ViaCEP.
Tudo sem rede — httpx mockado na indireção _get_json.
"""
import pytest

from app.services import validators_service as vs

CNPJ = "32491468000112"   # dígitos verificadores válidos (ESCRITORIO_CNPJ)
CEP = "32600000"


def _mock_fontes(monkeypatch, respostas: dict):
    """Mocka _get_json roteando por substring da URL.
    respostas: {substring: dict | None | Exception}."""
    chamadas = []

    async def fake(url):
        chamadas.append(url)
        for chave, resp in respostas.items():
            if chave in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(vs, "_get_json", fake)
    return chamadas


def test_cnpj_valido_precondicao():
    assert vs.validar_cnpj(CNPJ)


# ── CNPJ ──────────────────────────────────────────────────────────────────────
async def test_cnpj_opencnpj_primeiro_sem_fallback(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {
        "opencnpj": {"razao_social": "ACME LTDA", "nome_fantasia": "ACME",
                     "situacao_cadastral": "Ativa", "cep": "32600-000",
                     "logradouro": "Rua A", "numero": "1", "bairro": "Centro",
                     "municipio": "Betim", "uf": "MG",
                     "telefones": [{"ddd": "31", "numero": "35311234"}]},
    })
    d = await vs.consultar_cnpj(CNPJ)
    assert d["fonte"] == "opencnpj"
    assert d["razao_social"] == "ACME LTDA"
    assert d["cidade"] == "Betim" and d["estado"] == "MG"
    assert d["telefone"] == "3135311234"
    assert len(chamadas) == 1                     # não caiu para as demais


async def test_cnpj_fallback_para_brasilapi(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {
        "opencnpj": RuntimeError("timeout"),
        "brasilapi": {"razao_social": "ACME LTDA",
                      "descricao_situacao_cadastral": "ATIVA",
                      "municipio": "BETIM", "uf": "MG",
                      "ddd_telefone_1": "3135311234"},
    })
    d = await vs.consultar_cnpj(CNPJ)
    assert d["fonte"] == "brasilapi"
    assert d["situacao"] == "ATIVA"
    assert len(chamadas) == 2


async def test_cnpj_fallback_final_receitaws(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {
        "opencnpj": None,                         # 404/estrutura inválida
        "brasilapi": RuntimeError("503"),
        "receitaws": {"status": "OK", "nome": "ACME LTDA",
                      "fantasia": "ACME", "situacao": "ATIVA",
                      "municipio": "BETIM", "uf": "MG"},
    })
    d = await vs.consultar_cnpj(CNPJ)
    assert d["fonte"] == "receitaws"
    assert d["razao_social"] == "ACME LTDA"
    assert len(chamadas) == 3


async def test_cnpj_todas_as_fontes_fora(monkeypatch):
    _mock_fontes(monkeypatch, {
        "opencnpj": RuntimeError("x"),
        "brasilapi": None,
        "receitaws": {"status": "ERROR", "message": "CNPJ inválido"},
    })
    assert await vs.consultar_cnpj(CNPJ) is None


async def test_cnpj_invalido_nem_consulta(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {})
    assert await vs.consultar_cnpj("11111111111111") is None
    assert chamadas == []                          # validação offline barra antes


# ── CEP ───────────────────────────────────────────────────────────────────────
async def test_cep_brasilapi_primeiro(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {
        "brasilapi": {"cep": "32600000", "state": "MG", "city": "Betim",
                      "neighborhood": "Centro", "street": "Rua A"},
    })
    d = await vs.consultar_cep("32.600-000")
    assert d == {"cep": "32600000", "logradouro": "Rua A", "bairro": "Centro",
                 "cidade": "Betim", "estado": "MG", "fonte": "brasilapi"}
    assert len(chamadas) == 1


async def test_cep_fallback_viacep(monkeypatch):
    chamadas = _mock_fontes(monkeypatch, {
        "brasilapi": RuntimeError("timeout"),
        "viacep": {"cep": "32600-000", "logradouro": "Rua A", "bairro": "Centro",
                   "localidade": "Betim", "uf": "MG"},
    })
    d = await vs.consultar_cep(CEP)
    assert d["fonte"] == "viacep" and d["cidade"] == "Betim"
    assert len(chamadas) == 2


async def test_cep_nao_encontrado(monkeypatch):
    _mock_fontes(monkeypatch, {"brasilapi": None, "viacep": {"erro": True}})
    assert await vs.consultar_cep(CEP) is None
    assert await vs.consultar_cep("123") is None   # tamanho inválido: offline
