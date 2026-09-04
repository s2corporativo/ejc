"""O prazo ADMINISTRATIVO também avisa quando o calendário está degradado.

Terceira ocorrência da mesma classe de defeito neste PR. `routers/deadlines.py`
fixava `resultado_preliminar: False`, `revisao_obrigatoria: False` e
`aviso: None` no ramo administrativo — mas esse ramo usa as MESMAS funções de
dia útil e os MESMOS feriados do banco que o processual. Com a carga de
feriados falha, o prazo saía carimbado como DEFINITIVO sem os feriados
municipais, e ninguém era avisado.

Risco jurídico direto: prazo administrativo perdido por feriado municipal que
o sistema não conhecia, apresentado ao advogado como resultado final.

O que se trava aqui: os dois ramos (processual e administrativo) leem a MESMA
fonte de degradação. Duas cópias da regra viram duas verdades.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import deadline_calculator as dc


@pytest.fixture(autouse=True)
def _calendario_limpo():
    """Preserva e restaura o estado global de runtime do calendário."""
    original = dict(dc._CALENDARIO_RUNTIME)
    yield
    dc._CALENDARIO_RUNTIME.clear()
    dc._CALENDARIO_RUNTIME.update(original)


def _marcar(feriados_ok, suspensoes_ok):
    dc._CALENDARIO_RUNTIME["feriados_ok"] = feriados_ok
    dc._CALENDARIO_RUNTIME["suspensoes_ok"] = suspensoes_ok


# ── A fonte única ───────────────────────────────────────────────────────────

def test_falha_de_feriados_degrada_mesmo_sem_tribunal():
    """`_FERIADOS_DB` é global: entra no cálculo sem tribunal informado.

    Enquanto a condição exigia `tribunal`, um cálculo sem tribunal saía como
    definitivo mesmo com os feriados municipais ausentes.
    """
    _marcar(feriados_ok=False, suspensoes_ok=True)
    degradado, aviso = dc.estado_degradacao(tribunal=None)
    assert degradado is True
    assert aviso and "preliminar" in aviso.lower()


def test_falha_de_suspensoes_so_degrada_com_tribunal():
    """Suspensão é POR tribunal — sem tribunal na conta, não afeta o cálculo."""
    _marcar(feriados_ok=True, suspensoes_ok=False)
    assert dc.estado_degradacao(tribunal=None) == (False, None)
    degradado, aviso = dc.estado_degradacao(tribunal="TJMG")
    assert degradado is True and aviso


def test_calendario_integro_nao_degrada():
    _marcar(feriados_ok=True, suspensoes_ok=True)
    assert dc.estado_degradacao(tribunal="TJMG") == (False, None)


def test_estado_nao_inicializado_nao_degrada():
    """`None` é 'ainda não carregou', não 'falhou' — não pode virar aviso falso.

    Aviso de degradação que aparece sempre deixa de ser lido; é o mecanismo do
    'painel verde que mente', invertido.
    """
    _marcar(feriados_ok=None, suspensoes_ok=None)
    assert dc.estado_degradacao(tribunal="TJMG") == (False, None)


# ── Os dois ramos concordam ─────────────────────────────────────────────────

def test_processual_e_administrativo_leem_a_mesma_fonte():
    """Guarda contra a regra voltar a ser copiada em dois lugares."""
    import inspect

    from app.routers import deadlines as router_prazos

    fonte_router = inspect.getsource(router_prazos)
    assert "estado_degradacao" in fonte_router, (
        "o ramo administrativo voltou a decidir degradação por conta própria"
    )
    assert '"resultado_preliminar": False' not in fonte_router, (
        "resultado_preliminar fixo em False reintroduz o defeito: prazo "
        "administrativo carimbado como definitivo com calendário degradado"
    )

    fonte_calc = inspect.getsource(dc.calcular_prazo_processual)
    assert "estado_degradacao" in fonte_calc, (
        "o ramo processual deixou de usar a fonte única"
    )


def test_prazo_processual_propaga_a_degradacao():
    """Ponta a ponta no ramo processual, com o calendário marcado como falho."""
    _marcar(feriados_ok=False, suspensoes_ok=True)
    resultado = dc.calcular_prazo_processual(
        data_inicio=date(2026, 3, 2), dias=15, regime="civel", tribunal="TJMG",
    )
    assert resultado["resultado_preliminar"] is True
    assert resultado["revisao_obrigatoria"] is True
    assert resultado["aviso"] == dc.AVISO_CALENDARIO_DEGRADADO

    _marcar(feriados_ok=True, suspensoes_ok=True)
    ok = dc.calcular_prazo_processual(
        data_inicio=date(2026, 3, 2), dias=15, regime="civel", tribunal="TJMG",
    )
    assert ok["resultado_preliminar"] is False
    assert ok["aviso"] is None
