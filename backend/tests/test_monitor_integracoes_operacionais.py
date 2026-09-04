from __future__ import annotations

from datetime import date

import pytest

from app.services import diario_oficial_service as dou
from app.services.radar_poder import _parse_materias_senado


def _html_indice(itens: list[dict]) -> str:
    """HTML como o in.gov.br entrega: JSON embutido em <script id="params">.

    Este é o contrato REAL, verificado ao vivo em 04/09/2026. O contrato que
    estes testes usavam antes (`{"content": {"jsonArray": []}}`, consumido via
    `resp.json()`) nunca existiu na fonte: a resposta é HTML, e por isso o
    monitor falhava em produção todo dia enquanto os testes passavam.
    """
    import json as _json

    payload = _json.dumps({"jsonArray": itens})
    return (
        "<html><body>"
        f'<script id="params" type="application/json">{payload}</script>'
        "</body></html>"
    )


class _Resposta:
    def __init__(self, texto: str):
        self.text = texto

    def raise_for_status(self):
        return None


class _ClientOK:
    """Dublê que devolve o índice do dia — HTML, como a fonte real."""

    itens: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        return _Resposta(_html_indice(type(self).itens))


class _ClientErro(_ClientOK):
    async def get(self, *args, **kwargs):
        raise RuntimeError("falha simulada sem conteúdo sensível")


class _ClientContratoInvalido(_ClientOK):
    async def get(self, *args, **kwargs):
        # Página sem <script id="params"> — foi assim que o portal mudou.
        return _Resposta("<html><body>portal reformulado</body></html>")


@pytest.fixture(autouse=True)
def _limpar_cache_indice():
    """O índice é memoizado por execução; sem isto um teste serve o do outro."""
    dou.limpar_cache_indice()
    yield
    dou.limpar_cache_indice()


@pytest.mark.anyio
async def test_dou_zero_resultados_e_sucesso_valido(monkeypatch):
    import httpx

    _ClientOK.itens = []
    monkeypatch.setattr(httpx, "AsyncClient", _ClientOK)
    resultado = await dou.buscar_dou("termo técnico", date(2026, 8, 18))

    assert resultado == []


@pytest.mark.anyio
async def test_dou_falha_na_fonte_nao_vira_lista_vazia(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClientErro)

    with pytest.raises(dou.DOUIndisponivelError):
        await dou.buscar_dou("termo técnico", date(2026, 8, 18))


@pytest.mark.anyio
async def test_dou_quebra_de_contrato_nao_vira_zero_resultados(monkeypatch):
    """Portal sem o <script id='params'> é quebra de contrato, não 'nada hoje'.

    Regressão do defeito real: a versão anterior tratava HTML inesperado como
    exceção genérica e o job seguia reportando degradado sem ninguém entender
    por quê — e um `[]` aqui seria pior ainda, porque viraria 'ok'.
    """
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClientContratoInvalido)

    with pytest.raises(dou.DOUIndisponivelError, match="contrato do portal mudou"):
        await dou.buscar_dou("termo técnico", date(2026, 8, 18))


@pytest.mark.anyio
async def test_dou_casa_keyword_no_indice_e_normaliza(monkeypatch):
    """Casamento local: o índice traz o dia inteiro e a keyword filtra aqui."""
    import httpx

    _ClientOK.itens = [
        {
            "title": "PORTARIA SOBRE LICITAÇÃO Nº 42",
            "content": "Dispõe sobre contratação pública...",
            "urlTitle": "portaria-n-42-de-2026-123456",
            "pubName": "DO1",
            "editionNumber": "167",
        },
        {
            "title": "ATO SEM RELAÇÃO",
            "content": "Outro assunto qualquer.",
            "urlTitle": "ato-999",
            "pubName": "DO1",
            "editionNumber": "167",
        },
    ]
    monkeypatch.setattr(httpx, "AsyncClient", _ClientOK)

    r = await dou.buscar_dou("licitacao", date(2026, 8, 18))

    # 3 seções varridas com o mesmo dublê → o mesmo item casa 3 vezes.
    assert len(r) == 3
    assert r[0]["titulo"] == "PORTARIA SOBRE LICITAÇÃO Nº 42"
    # Acento e caixa não podem impedir o casamento ("licitacao" × "LICITAÇÃO").
    assert r[0]["link"] == (
        "https://www.in.gov.br/web/dou/-/portaria-n-42-de-2026-123456"
    )
    assert r[0]["edicao"] == "167"


@pytest.mark.anyio
async def test_indice_do_dia_e_baixado_uma_vez_por_secao(monkeypatch):
    """N keywords não podem custar N downloads do dia inteiro."""
    import httpx

    chamadas = {"n": 0}

    class _Contador(_ClientOK):
        async def get(self, *args, **kwargs):
            chamadas["n"] += 1
            return _Resposta(_html_indice([]))

    monkeypatch.setattr(httpx, "AsyncClient", _Contador)

    await dou.buscar_dou("primeira", date(2026, 8, 18))
    await dou.buscar_dou("segunda", date(2026, 8, 18))
    await dou.buscar_dou("terceira", date(2026, 8, 18))

    assert chamadas["n"] == 3, "3 seções, uma vez cada — não 3 por keyword"


def test_status_dou_distingue_ok_de_degradado():
    anterior = dict(dou._DOU_STATUS)
    try:
        dou._registrar_status_dou(ok=True, quantidade=0)
        ok = dou.status_dou()
        assert ok["status"] == "ok"
        assert ok["ultima_execucao_ok"] is True
        assert ok["ultima_quantidade"] == 0
        assert ok["falhas_consecutivas"] == 0

        dou._registrar_status_dou(ok=False, erro=RuntimeError("simulado"))
        ruim = dou.status_dou()
        assert ruim["status"] == "degradado"
        assert ruim["ultima_execucao_ok"] is False
        assert ruim["falhas_consecutivas"] == 1
        assert ruim["ultimo_erro_tipo"] == "RuntimeError"
        assert "simulado" not in str(ruim)
    finally:
        dou._DOU_STATUS.clear()
        dou._DOU_STATUS.update(anterior)


def test_senado_parser_aceita_shape_plano_do_endpoint_json():
    payload = {
        "PesquisaBasicaMateria": {
            "Materias": {
                "Materia": [
                    {
                        "Codigo": "12345",
                        "DescricaoIdentificacao": "PL 100/2026",
                        "Numero": "100",
                        "Ano": "2026",
                        "Ementa": "Altera norma federal para fins de teste.",
                    }
                ]
            }
        }
    }

    itens = _parse_materias_senado(payload)

    assert len(itens) == 1
    assert itens[0]["id"] == 12345
    assert itens[0]["siglaTipo"] == "PL"
    assert itens[0]["numero"] == 100
    assert itens[0]["ano"] == 2026
    assert itens[0]["casa"] == "senado"


def test_senado_parser_preserva_shape_aninhado_legado():
    payload = {
        "PesquisaBasicaMateria": {
            "Materias": {
                "Materia": {
                    "IdentificacaoMateria": {
                        "CodigoMateria": "999",
                        "SiglaTipoMateria": "PEC",
                        "NumeroMateria": "7",
                        "AnoMateria": "2026",
                    },
                    "EmentaMateria": "Ementa de teste.",
                }
            }
        }
    }

    itens = _parse_materias_senado(payload)

    assert itens == [
        {
            "id": 999,
            "siglaTipo": "PEC",
            "numero": 7,
            "ano": 2026,
            "ementa": "Ementa de teste.",
            "casa": "senado",
            "link": "https://www25.senado.leg.br/web/atividade/materias/-/materia/999",
        }
    ]
