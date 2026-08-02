"""Regressão: GET /analytics/roi-por-area devolvia 500 em toda chamada.

`ranking_por_area()` caía para a área do próprio caso quando o caso não tinha
linha principal em `caso_areas` — o estado comum, já que a tabela é opcional. O
fallback referenciava `Case.ramo`, atributo que NÃO existe no modelo (a coluna é
`Case.area`, ENUM `CaseArea`). SQLAlchemy levanta AttributeError já na montagem
do SELECT, o handler global converte em 500 e a auditoria de julho/2026
registrou o endpoint como quebrado.

Dois testes, dois níveis:

1. o atributo referenciado existe no modelo (trava barata, pega o erro de digitação);
2. o caminho do fallback executa de ponta a ponta e devolve a área do caso.

O segundo é o que importa: sem ele, trocar `ramo` por outro nome inexistente
passaria no primeiro.
"""
from __future__ import annotations

import pytest

from app.models.case import Case, CaseArea, CaseStatus
from app.services.rentabilidade import ranking_por_area


class _Resultado:
    """Devolve uma leva canned de linhas, no formato que o service consome."""

    def __init__(self, linhas):
        self._linhas = linhas

    def all(self):
        return self._linhas

    def scalars(self):
        return self

    def mappings(self):
        return self


class _FakeDB:
    """AsyncSession mínima: responde `execute` na ordem em que o service chama.

    A ordem é a do fluxo real de `ranking_por_area`:
      1) casos no escopo            5) áreas principais em caso_areas
      2) honorários pagos por caso  6) fallback Case.area  ← linha corrigida
      3) custo_hora por usuário
      4) time entries
    """

    def __init__(self, levas):
        self._levas = list(levas)
        self.chamadas = 0

    async def execute(self, *_a, **_kw):
        self.chamadas += 1
        return _Resultado(self._levas.pop(0) if self._levas else [])


class _UserAdmin:
    id = "u-1"
    role = "admin"


def _caso(cid: str, area: CaseArea) -> Case:
    c = Case()
    c.id = cid
    c.numero_interno = "DPT-2026-0001"
    c.titulo = "Caso de teste"
    c.area = area
    c.status = CaseStatus.triagem
    return c


def test_modelo_case_nao_tem_ramo_e_tem_area():
    """A coluna real é `area`. `ramo` nunca existiu — era a origem do 500."""
    assert hasattr(Case, "area")
    assert not hasattr(Case, "ramo"), (
        "Se `Case.ramo` passou a existir, revise o fallback de ranking_por_area()."
    )


@pytest.mark.asyncio
async def test_fallback_usa_area_do_caso_quando_nao_ha_caso_areas():
    """Sem linha principal em `caso_areas`, o caso entra agrupado pela própria área.

    Antes da correção esta chamada levantava AttributeError (→ HTTP 500).
    """
    caso = _caso("c-1", CaseArea.consumidor)
    db = _FakeDB([
        [caso],   # 1) casos no escopo
        [],       # 2) honorários pagos — nenhum
        [],       # 3) custo_hora por usuário — nenhum
        [],       # 4) time entries — nenhuma
        [],       # 5) caso_areas — VAZIO: é o que aciona o fallback
        [("c-1", CaseArea.consumidor)],  # 6) SELECT Case.id, Case.area
    ])

    resultado = await ranking_por_area(db, _UserAdmin())

    areas = {a["area"]: a for a in resultado["areas"]}
    assert "consumidor" in areas, (
        f"esperava agrupamento pela área do caso; veio {list(areas)}"
    )
    assert areas["consumidor"]["casos"] == 1
    # O enum precisa chegar agrupado como string — chave de dict com o Enum cru
    # produziria "CaseArea.consumidor" no JSON.
    assert all(isinstance(a["area"], str) for a in resultado["areas"])


@pytest.mark.asyncio
async def test_caso_areas_preenchido_tem_precedencia_sobre_a_area_do_caso():
    """Com área principal declarada, ela vence — o fallback nem é consultado."""
    caso = _caso("c-1", CaseArea.consumidor)
    db = _FakeDB([
        [caso],
        [],
        [],
        [],
        [("c-1", "civel")],  # caso_areas com principal=True
        # sem 6ª leva: se o service consultar o fallback, recebe [] e não quebra
    ])

    resultado = await ranking_por_area(db, _UserAdmin())

    assert [a["area"] for a in resultado["areas"]] == ["civel"]


@pytest.mark.asyncio
async def test_sem_casos_no_escopo_devolve_lista_vazia_sem_erro():
    db = _FakeDB([[]])
    resultado = await ranking_por_area(db, _UserAdmin())
    assert resultado["areas"] == []
