"""Relatório semanal do dono (relatorio_dono_service): coletar_numeros_semana
com FakeDB (roteia cada query pela tabela-alvo no SQL — sem Postgres) +
template determinístico do e-mail."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.relatorio_dono_service import (
    ASSINATURA_AUTOMATICA,
    coletar_numeros_semana,
    montar_email_relatorio,
)

HOJE = date(2026, 7, 13)  # uma segunda-feira


class _FakeResult:
    def __init__(self, scalar=None, first=None, rows=None):
        self._scalar, self._first, self._rows = scalar, first, rows or []

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _FakeDB:
    """Roteia cada db.execute pelo texto do SQL (tabela dominante)."""

    def __init__(self, *, prazos=0, leads=0, recebiveis=0.0,
                 custo_ia=0.0, chamadas_ia=0, top_ia=None, parados=0):
        self._prazos = prazos
        self._leads = leads
        self._recebiveis = recebiveis
        self._ia = SimpleNamespace(custo=custo_ia, chamadas=chamadas_ia)
        self._top_ia = top_ia or []
        self._parados = parados

    async def execute(self, query, params=None):
        sql = str(query)
        if "FROM deadlines" in sql:
            return _FakeResult(scalar=self._prazos)
        if "FROM clients" in sql:
            return _FakeResult(scalar=self._leads)
        if "FROM fees" in sql:
            return _FakeResult(scalar=self._recebiveis)
        if "FROM ai_logs l" in sql:  # top casos (JOIN cases)
            return _FakeResult(rows=self._top_ia)
        if "FROM ai_logs" in sql:
            return _FakeResult(first=self._ia)
        if "FROM cases c" in sql:
            return _FakeResult(scalar=self._parados)
        raise AssertionError(f"query inesperada: {sql[:80]}")


# ── coletar_numeros_semana ────────────────────────────────────────────────────

async def test_coleta_agrega_os_5_indicadores():
    top = [SimpleNamespace(numero_interno="DPT-2026-0001", titulo="Caso X",
                           custo=12.5, chamadas=7)]
    db = _FakeDB(prazos=4, leads=2, recebiveis=1500.75,
                 custo_ia=30.0, chamadas_ia=42, top_ia=top, parados=3)
    n = await coletar_numeros_semana(db, HOJE)

    assert n["prazos_vencendo_7d"] == 4
    assert n["leads_convertidos_semana"] == 2
    assert n["recebiveis_atraso_reais"] == 1500.75
    assert n["custo_ia_semana"] == 30.0
    assert n["chamadas_ia_semana"] == 42
    assert n["casos_parados_30d"] == 3
    assert n["top_casos_ia"] == [
        {"caso": "DPT-2026-0001", "custo": 12.5, "chamadas": 7}
    ]


async def test_coleta_tolera_banco_vazio():
    n = await coletar_numeros_semana(_FakeDB(), HOJE)
    assert n["prazos_vencendo_7d"] == 0
    assert n["recebiveis_atraso_reais"] == 0.0
    assert n["custo_ia_semana"] == 0.0
    assert n["top_casos_ia"] == []
    assert n["casos_parados_30d"] == 0


# ── Template ──────────────────────────────────────────────────────────────────

def _numeros(**overrides) -> dict:
    base = {
        "prazos_vencendo_7d": 4,
        "leads_convertidos_semana": 2,
        "recebiveis_atraso_reais": 1500.75,
        "custo_ia_semana": 30.0,
        "chamadas_ia_semana": 42,
        "top_casos_ia": [],
        "casos_parados_30d": 3,
    }
    base.update(overrides)
    return base


def test_email_relatorio_titulo_periodo_e_indicadores():
    assunto, corpo = montar_email_relatorio(
        _numeros(), date(2026, 7, 6), date(2026, 7, 13),
    )
    assert assunto.startswith("Relatório semanal — De Paula Teixeira Advogados")
    assert "06/07/2026 a 13/07/2026" in corpo
    # Os 5 indicadores e valores formatados em BRL.
    assert "Prazos vencendo nos próximos 7 dias" in corpo
    assert "Leads convertidos na semana" in corpo
    assert "R$ 1.500,75" in corpo
    assert "R$ 30,00" in corpo and "42 chamada(s)" in corpo
    assert "30+ dias" in corpo
    assert ASSINATURA_AUTOMATICA in corpo
    assert "whatsapp" not in corpo.lower()


def test_email_relatorio_lista_top_casos_ia_quando_houver():
    numeros = _numeros(top_casos_ia=[
        {"caso": "DPT-2026-0001", "custo": 12.5, "chamadas": 7},
    ])
    _, corpo = montar_email_relatorio(numeros, date(2026, 7, 6), date(2026, 7, 13))
    assert "DPT-2026-0001" in corpo
    assert "R$ 12,50" in corpo


def test_email_relatorio_sem_top_casos_omite_bloco():
    _, corpo = montar_email_relatorio(_numeros(), date(2026, 7, 6),
                                      date(2026, 7, 13))
    assert "maior custo de IA" not in corpo
