from __future__ import annotations

from datetime import date

import pytest

from app.services import diario_oficial_service as dou
from app.services.radar_poder import _parse_materias_senado


class _Resposta:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _ClientOK:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        return _Resposta({"content": {"jsonArray": []}})


class _ClientErro(_ClientOK):
    async def get(self, *args, **kwargs):
        raise RuntimeError("falha simulada sem conteúdo sensível")


@pytest.mark.anyio
async def test_dou_zero_resultados_e_sucesso_valido(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClientOK)
    resultado = await dou.buscar_dou("termo técnico", date(2026, 8, 18))

    assert resultado == []


@pytest.mark.anyio
async def test_dou_falha_na_fonte_nao_vira_lista_vazia(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _ClientErro)

    with pytest.raises(dou.DOUIndisponivelError):
        await dou.buscar_dou("termo técnico", date(2026, 8, 18))


def test_status_dou_distingue_ok_de_degradado():
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
