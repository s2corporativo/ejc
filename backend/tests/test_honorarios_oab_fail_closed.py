"""Barreiras fail-closed do estimador baseado na tabela OAB/MG.

Nenhuma estimativa pode ser produzida por IA quando fonte oficial ou vigência
não forem verificáveis. Os valores usados aqui são apenas fixtures sintéticas.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.models.redesign import TabelaOABHonorario
from app.routers import honorarios_oab


def _item(
    *,
    item_id: str = "item-1",
    fonte: str = "https://www.oabmg.org.br/arquivo/tabela-teste.pdf",
    vigencia_inicio: date | None = date(2026, 1, 1),
) -> TabelaOABHonorario:
    return TabelaOABHonorario(
        id=item_id,
        item_codigo="8.1",
        descricao="Procedimento de teste",
        area_juridica="civel",
        valor_minimo=1000.0,
        percentual=10.0,
        unidade="R$",
        vigencia_inicio=vigencia_inicio,
        vigencia_fim=None,
        fonte=fonte,
        observacoes="Fixture sintética",
        ativo=True,
    )


@pytest.mark.parametrize(
    "fonte",
    [
        None,
        "",
        "Tabela OAB/MG sem URL",
        "http://www.oabmg.org.br/tabela.pdf",
        "https://oabmg.org.br.evil.example/tabela.pdf",
        "https://example.org/oabmg.org.br/tabela.pdf",
    ],
)
def test_fonte_nao_oficial_e_rejeitada(fonte):
    assert honorarios_oab._fonte_oabmg_oficial(fonte) is False


def test_fonte_https_no_dominio_oficial_e_aceita():
    assert honorarios_oab._fonte_oabmg_oficial(
        "Tabela oficial: https://documentos.oabmg.org.br/tabela.pdf"
    ) is True


async def test_contexto_exclui_seed_legado_e_item_sem_vigencia(monkeypatch):
    itens = [
        _item(item_id="oficial"),
        _item(item_id="legado", fonte="PDF institucional do escritório"),
        _item(item_id="sem-vigencia", vigencia_inicio=None),
    ]

    async def _vigentes(*args, **kwargs):
        return itens

    monkeypatch.setattr(honorarios_oab, "_itens_oab_vigentes", _vigentes)
    contexto, verificados = await honorarios_oab._contexto_oab(
        object(), "civel", "procedimento"
    )

    assert [item.id for item in verificados] == ["oficial"]
    assert "tabela-teste.pdf" in contexto
    assert "PDF institucional do escritório" not in contexto


async def test_estimar_falha_fechado_sem_chamar_ia(monkeypatch):
    async def _vazios(*args, **kwargs):
        return []

    async def _ia_nao_pode_ser_chamada(*args, **kwargs):
        raise AssertionError("IA não pode ser chamada sem tabela oficial vigente")

    monkeypatch.setattr(honorarios_oab, "_itens_oab_vigentes", _vazios)
    monkeypatch.setattr(honorarios_oab.ai_gateway, "chat", _ia_nao_pode_ser_chamada)

    with pytest.raises(HTTPException) as exc:
        await honorarios_oab.estimar(
            body=honorarios_oab.EstimativaIn(
                area="civel",
                tipo_acao="procedimento de teste",
            ),
            db=object(),
            cu=object(),
        )

    assert exc.value.status_code == 503
    assert "fonte HTTPS no domínio oabmg.org.br" in exc.value.detail


async def test_tabela_expoe_somente_itens_verificados(monkeypatch):
    itens = [
        _item(item_id="oficial"),
        _item(item_id="legado", fonte="Tabela OAB/MG sem URL"),
    ]

    async def _vigentes(*args, **kwargs):
        return itens

    monkeypatch.setattr(honorarios_oab, "_itens_oab_vigentes", _vigentes)
    out = await honorarios_oab.itens_tabela(
        area="civel",
        tipo="procedimento",
        db=object(),
        cu=object(),
    )

    assert out["disponivel"] is True
    assert len(out["itens"]) == 1
    assert out["itens"][0]["item_codigo"] == "8.1"
    assert out["criterio_fonte"].startswith("HTTPS")


async def test_seed_legado_esta_desativado():
    from app.seeds.oab_honorarios_seed import run

    with pytest.raises(RuntimeError, match="Seed legado OAB/MG desativado"):
        await run()
