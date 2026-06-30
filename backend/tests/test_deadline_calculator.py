# Testes do calculador de prazos — núcleo crítico do EJC.
from datetime import date, timedelta
from app.services import deadline_calculator as dc


def setup_function(_):
    # Isola o estado global (feriados/suspensões em memória) entre testes.
    dc.set_feriados_db(set())
    dc.set_suspensoes_tribunal({})


# ── Fins de semana e feriados ─────────────────────────────────────────────────
def test_fim_de_semana_nao_e_dia_util():
    assert dc.eh_dia_util(date(2026, 6, 13)) is False   # sábado
    assert dc.eh_dia_util(date(2026, 6, 14)) is False   # domingo


def test_feriado_nacional_fixo():
    assert dc.eh_feriado(date(2026, 9, 7)) is True       # Independência
    assert dc.eh_dia_util(date(2026, 9, 7)) is False


def test_feriado_movel_sexta_santa():
    pascoa = dc.calcular_pascoa(2026)
    sexta_santa = pascoa - timedelta(days=2)
    assert dc.eh_feriado(sexta_santa) is True


# ── Feriados municipais (vêm do banco; aqui injetados) ────────────────────────
def test_feriado_municipal_altera_dia_util():
    aniversario_betim = date(2026, 12, 17)              # quinta-feira útil
    assert dc.eh_dia_util(aniversario_betim) is True
    dc.set_feriados_db({aniversario_betim})
    assert dc.eh_dia_util(aniversario_betim) is False


# ── Contagem de prazos ────────────────────────────────────────────────────────
def test_prazo_dias_uteis_janela_limpa():
    # 15/06/2026 (seg) + 5 úteis, sem feriados na janela => 22/06/2026 (seg)
    assert dc.prazo_dias_uteis(date(2026, 6, 15), 5) == date(2026, 6, 22)


def test_prazo_dias_uteis_conta_apenas_uteis():
    venc = dc.prazo_dias_uteis(date(2026, 6, 15), 10)
    assert dc.eh_dia_util(venc)
    assert venc > date(2026, 6, 15)


def test_prazo_corridos_prorroga_para_dia_util():
    # 28/05/2026 + 10 corridos = 07/06 (domingo) => prorroga p/ 08/06 (seg)
    venc = dc.prazo_dias_corridos(date(2026, 5, 28), 10, prorrogar_fim=True)
    assert venc == date(2026, 6, 8)
    assert dc.eh_dia_util(venc, forense=False)


# ── Suspensão por tribunal (escopada) ─────────────────────────────────────────
def test_suspensao_tribunal_empurra_prazo_do_tribunal():
    ini = date(2026, 5, 29)                              # sexta
    base = dc.prazo_dias_uteis(ini, 5)
    dc.set_suspensoes_tribunal({"TJMG": {date(2026, 6, d) for d in range(1, 6)}})
    assert dc.prazo_dias_uteis(ini, 5, tribunal="TJMG") > base


def test_suspensao_nao_afeta_outro_tribunal():
    ini = date(2026, 5, 29)
    base = dc.prazo_dias_uteis(ini, 5)
    dc.set_suspensoes_tribunal({"TJMG": {date(2026, 6, d) for d in range(1, 6)}})
    assert dc.prazo_dias_uteis(ini, 5, tribunal="TRT3") == base   # outro tribunal
    assert dc.prazo_dias_uteis(ini, 5) == base                    # sem tribunal


# ── Defesa ambiental (IBAMA) ──────────────────────────────────────────────────
def test_defesa_ambiental_estrutura_e_base_legal():
    r = dc.prazo_defesa_ambiental(date(2026, 6, 1))
    assert {"data_legal", "data_interna", "dias_restantes", "base_legal"} <= set(r)
    assert r["data_interna"] <= r["data_legal"]            # margem antes do legal
    assert "6.514" in r["base_legal"]
