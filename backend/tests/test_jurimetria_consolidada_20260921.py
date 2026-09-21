from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.jurimetria import (
    _bucket,
    _resumo,
    classificar_resultado,
    intervalo_wilson,
)
from app.services.jurimetria_tribunais import agregacao
from app.services.tese_vinculo_service import (
    atualizar_resultado_vinculo,
    normalizar_resultado_tese,
    reconciliar_metricas_tese,
)
from app.services.jurimetria_tribunais.snapshots import preparar_snapshot
from scripts.avaliar_jurimetria_gold import avaliar, validar_item


def test_taxonomia_case_reconhece_write_path_e_aliases_historicos() -> None:
    assert _bucket("exito") == "exito_total"
    assert _bucket("exito_total") == "exito_total"
    assert _bucket("exito_parcial") == "exito_parcial"
    assert _bucket("derrota") == "improcedente"
    assert _bucket("improcedente") == "improcedente"
    assert _bucket("acordo") == "acordo"
    assert _bucket("desistencia") == "outro"
    assert _bucket("arquivado") == "outro"

    assert classificar_resultado("exito") == "favoravel"
    assert classificar_resultado("derrota") == "desfavoravel"
    assert classificar_resultado("acordo") == "acordo"
    assert classificar_resultado("desistencia") == "nao_decidido"


def test_taxa_judicial_exclui_acordo_e_sem_merito_do_denominador() -> None:
    resumo = _resumo(
        [
            _bucket("exito"),
            _bucket("derrota"),
            _bucket("acordo"),
            _bucket("desistencia"),
        ]
    )

    assert resumo["n"] == 4
    assert resumo["n_decididos"] == 2
    assert resumo["taxa_exito"] == 50.0
    assert resumo["taxa_improcedencia"] == 50.0
    assert resumo["distribuicao"]["acordo"] == 1
    assert resumo["n_nao_decididos"] == 1
    assert resumo["intervalo_confianca_95"]["metodo"] == "wilson"


def test_intervalo_wilson_evitar_falsa_precisao() -> None:
    ic = intervalo_wilson(6, 10)
    assert ic is not None
    assert ic["inferior"] == pytest.approx(31.3, abs=0.1)
    assert ic["superior"] == pytest.approx(83.2, abs=0.1)
    assert intervalo_wilson(0, 0) is None


def test_resultado_tese_novo_e_validado() -> None:
    assert normalizar_resultado_tese(None) == "pendente"
    assert normalizar_resultado_tese("procedente") == "procedente"
    with pytest.raises(ValueError):
        normalizar_resultado_tese("vitoria")


def test_jurimetria_externa_expoe_ic95() -> None:
    g = agregacao._grupo_vazio()
    g["n"] = 10
    g["n_com_desfecho"] = 10
    g[agregacao.tpu.PROCEDENCIA] = 6
    g[agregacao.tpu.IMPROCEDENCIA] = 4

    fechado = agregacao._fechar_grupo(g)
    assert fechado["taxa_procedencia"] == 0.6
    assert fechado["intervalo_confianca_95_procedencia"]["inferior"] == pytest.approx(
        31.3, abs=0.1
    )
    assert fechado["intervalo_confianca_95_procedencia"]["superior"] == pytest.approx(
        83.2, abs=0.1
    )


@pytest.mark.asyncio
async def test_por_magistrado_fica_fail_closed_sem_dado_confiavel() -> None:
    from app.routers.jurimetria import por_magistrado

    user = SimpleNamespace(role=SimpleNamespace(value="advogado"))
    with pytest.raises(HTTPException) as exc:
        await por_magistrado(area=None, limit=20, db=None, cu=user)

    assert exc.value.status_code == 409
    assert "desabilitada" in str(exc.value.detail).lower()


class _ResultMetricas:
    def __init__(self, *, row=None, tese=None):
        self._row = row
        self._tese = tese

    def one(self):
        return self._row

    def scalar_one_or_none(self):
        return self._tese


class _FakeDBMetricas:
    def __init__(self, row, tese):
        self.row = row
        self.tese = tese
        self.calls = 0
        self.flushes = 0

    async def flush(self):
        self.flushes += 1

    async def execute(self, _query):
        self.calls += 1
        if self.calls % 2 == 1:
            return _ResultMetricas(row=self.row)
        return _ResultMetricas(tese=self.tese)


@pytest.mark.asyncio
async def test_reconciliacao_tese_usa_apenas_decididos_no_denominador() -> None:
    tese = SimpleNamespace(
        vezes_usada=0,
        vezes_venceu=0,
        vezes_perdeu=0,
        taxa_sucesso=None,
    )
    db = _FakeDBMetricas(
        SimpleNamespace(total=17, venceu=2, perdeu=1),
        tese,
    )

    reconciliada = await reconciliar_metricas_tese(db, "tese-1")

    assert reconciliada is tese
    assert tese.vezes_usada == 17
    assert tese.vezes_venceu == 2
    assert tese.vezes_perdeu == 1
    assert tese.taxa_sucesso == pytest.approx(2 / 3, abs=0.0001)


@pytest.mark.asyncio
async def test_atualizar_resultado_vinculo_reconcilia_na_mesma_transacao() -> None:
    tese = SimpleNamespace(
        vezes_usada=0,
        vezes_venceu=0,
        vezes_perdeu=0,
        taxa_sucesso=None,
    )
    db = _FakeDBMetricas(
        SimpleNamespace(total=4, venceu=3, perdeu=1),
        tese,
    )
    link = SimpleNamespace(tese_id="tese-1", resultado="pendente")

    await atualizar_resultado_vinculo(db, link=link, resultado="procedente")

    assert link.resultado == "procedente"
    assert tese.taxa_sucesso == pytest.approx(0.75)


def _resposta_snapshot_minima() -> dict:
    return {
        "fonte": "DataJud/CNJ — API Pública (api_publica_tjmg)",
        "escopo": {
            "tribunal": "TJMG",
            "municipios": ["Betim"],
            "classe": 436,
            "assunto": 10433,
            "desde": "2026-01-01",
            "ate": "2026-08-31",
        },
        "coleta": {
            "coletado_em": "2026-09-21T12:00:00Z",
            "n_documentos": 187,
            "truncado": False,
        },
        "tpu": {"versao": "26/05/2026"},
        "total": {
            "n": 187,
            "decididos_merito": 120,
            "taxa_procedencia": 0.63,
            "intervalo_confianca_95_procedencia": {
                "inferior": 54.1,
                "superior": 70.9,
                "nivel": 0.95,
                "metodo": "wilson",
            },
        },
        "por_municipio": [],
        "por_assunto": [],
        "por_municipio_assunto": [],
        "reforma_2grau": {"taxa_reforma": None},
        "fontes_complementares": {},
    }


def test_snapshot_guarda_apenas_agregado_minimizado() -> None:
    dados = preparar_snapshot(_resposta_snapshot_minima())
    assert dados["tribunal"] == "TJMG"
    assert dados["n_documentos"] == 187
    assert "total" in dados["agregado"]
    serializado = str(dados).lower()
    assert "numeroprocesso" not in serializado
    assert "partes" not in serializado


def test_snapshot_rejeita_identificador_processual_mesmo_em_objeto_aninhado() -> None:
    resposta = _resposta_snapshot_minima()
    resposta["total"]["numeroProcesso"] = "0000000-00.2026.8.13.0000"
    with pytest.raises(ValueError, match="chave sensível"):
        preparar_snapshot(resposta)


def test_snapshot_rejeita_numero_cnj_oculto_em_valor_textual() -> None:
    resposta = _resposta_snapshot_minima()
    resposta["total"]["observacao"] = "processo 0000000-00.2026.8.13.0000"
    with pytest.raises(ValueError, match="identificador sensível"):
        preparar_snapshot(resposta)


def test_gold_evaluator_calcula_matriz_sem_identificador() -> None:
    itens = [
        {
            "id": "g001",
            "esperado": "procedencia",
            "movimentos": [{"codigo": 219, "dataHora": "2026-01-10T10:00:00Z"}],
        },
        {
            "id": "g002",
            "esperado": "improcedencia",
            "movimentos": [{"codigo": 220, "dataHora": "2026-01-11T10:00:00Z"}],
        },
    ]
    resultado = avaliar(itens)
    assert resultado["n"] == 2
    assert resultado["acuracia"] == 1.0
    assert resultado["taxa_indeterminacao"] == 0.0


def test_gold_evaluator_recusa_pii_ou_numero_de_processo() -> None:
    with pytest.raises(ValueError):
        validar_item(
            {
                "id": "g001",
                "esperado": "procedencia",
                "movimentos": [],
                "numeroProcesso": "0000000-00.2026.8.13.0000",
            }
        )
