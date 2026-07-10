"""Precificação (services/precificacao_service.py): matemática pura de
`calcular_honorario` para cada fee_type / modo de cálculo, clamping por
min/max, extremos de percentual (0 e 100) e guardas de None/zero.

A função usa `db.execute(...).fetchone()`, mas toda a lógica de negócio é
pura sobre a linha retornada — então a DB é substituída por um fake em
memória (mesmo estilo do FakeDB em test_deep_research_service.py), o que
mantém estes testes rodando no sandbox sem Postgres.
"""
from __future__ import annotations

import pytest

from app.services.precificacao_service import calcular_honorario

COLUNAS = (
    "id", "area", "case_type", "complexity", "fee_type", "base_amount",
    "percentage_of_value", "min_amount", "max_amount", "exit_percentage",
    "oab_reference", "notes",
)


def _regra(**overrides) -> dict:
    """Linha completa de pricing_rules com defaults None sobrescrevíveis."""
    base = {c: None for c in COLUNAS}
    base.update(
        id="rule-1", area="civel", case_type="acao_indenizatoria",
        complexity="media", fee_type="fixo",
    )
    base.update(overrides)
    return base


class _FakeRow:
    def __init__(self, mapping: dict):
        self._mapping = mapping


class _FakeResult:
    def __init__(self, row: dict | None):
        self._row = _FakeRow(row) if row is not None else None

    def fetchone(self):
        return self._row


class _FakeDB:
    """Retorna sempre a mesma linha (ou None) independentemente do SQL."""

    def __init__(self, row: dict | None):
        self._row = row

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._row)


async def _calc(row: dict | None, causa_valor=None) -> dict:
    return await calcular_honorario(_FakeDB(row), "rule-1", causa_valor)


# ── Modos de cálculo por fee_type ───────────────────────────────────────────

async def test_percentual_aplica_percentual_sobre_valor_da_causa():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=10), causa_valor=100_000
    )
    assert out["componente_percentual"] == 10_000.0
    assert out["estimado_honorarios"] == 10_000.0
    assert out["honorario_exito"] is None


async def test_misto_soma_base_com_componente_percentual():
    out = await _calc(
        _regra(fee_type="misto", base_amount=1_000, percentage_of_value=10),
        causa_valor=100_000,
    )
    assert out["componente_percentual"] == 10_000.0
    assert out["estimado_honorarios"] == 11_000.0  # base 1.000 + 10% de 100.000


async def test_fixo_ignora_percentual_mesmo_com_pct_preenchido():
    out = await _calc(
        _regra(fee_type="fixo", base_amount=5_000, percentage_of_value=10),
        causa_valor=100_000,
    )
    # componente é informado, mas o estimado permanece o valor fixo.
    assert out["componente_percentual"] == 10_000.0
    assert out["estimado_honorarios"] == 5_000.0


async def test_exit_percentage_calcula_honorario_de_exito():
    out = await _calc(
        _regra(fee_type="exito", base_amount=2_000, exit_percentage=20),
        causa_valor=50_000,
    )
    assert out["honorario_exito"] == 10_000.0
    assert out["estimado_honorarios"] == 2_000.0  # entrada fixa
    assert out["componente_percentual"] == 0.0


# ── Clamping por min_amount / max_amount ────────────────────────────────────

async def test_clamp_eleva_estimado_ate_min_amount():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=1, min_amount=500),
        causa_valor=10_000,  # 1% => 100, abaixo do mínimo
    )
    assert out["estimado_honorarios"] == 500.0
    assert out["min_amount"] == 500.0


async def test_clamp_limita_estimado_ao_max_amount():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=50, max_amount=20_000),
        causa_valor=100_000,  # 50% => 50.000, acima do teto
    )
    assert out["estimado_honorarios"] == 20_000.0
    assert out["max_amount"] == 20_000.0


# ── Extremos de percentual (0 e 100) ────────────────────────────────────────

async def test_percentual_zero_cai_para_valor_base():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=0, base_amount=800),
        causa_valor=1_000,
    )
    # pct 0 é falsy: não calcula componente e mantém a base.
    assert out["componente_percentual"] == 0.0
    assert out["estimado_honorarios"] == 800.0


async def test_percentual_cem_por_cento_repassa_valor_integral():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=100),
        causa_valor=1_000,
    )
    assert out["componente_percentual"] == 1_000.0
    assert out["estimado_honorarios"] == 1_000.0


# ── Guardas de None / zero (sem divisão por zero / sem crash) ────────────────

async def test_causa_valor_none_nao_quebra_e_usa_base():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=10, base_amount=3_000),
        causa_valor=None,
    )
    assert out["componente_percentual"] == 0.0
    assert out["estimado_honorarios"] == 3_000.0
    assert out["causa_valor_informado"] is None


async def test_exito_sem_causa_retorna_honorario_exito_none():
    out = await _calc(
        _regra(fee_type="exito", exit_percentage=20), causa_valor=None
    )
    # (0) * pct => 0.0, tratado como ausência (None), não como R$ 0,00.
    assert out["honorario_exito"] is None


async def test_todos_os_valores_none_retorna_zero_sem_crash():
    out = await _calc(_regra(fee_type="fixo"), causa_valor=None)
    assert out["estimado_honorarios"] == 0.0
    assert out["componente_percentual"] == 0.0
    assert out["honorario_exito"] is None


async def test_regra_inexistente_ou_inativa_retorna_erro():
    out = await _calc(None, causa_valor=1_000)
    assert out == {"erro": "Regra não encontrada ou inativa"}


async def test_retorno_ecoa_metadados_da_regra():
    out = await _calc(
        _regra(fee_type="percentual", percentage_of_value=10,
               oab_reference="Tab. OAB/MG item 3"),
        causa_valor=10_000,
    )
    assert out["rule_id"] == "rule-1"
    assert out["area"] == "civel"
    assert out["fee_type"] == "percentual"
    assert out["oab_reference"] == "Tab. OAB/MG item 3"
