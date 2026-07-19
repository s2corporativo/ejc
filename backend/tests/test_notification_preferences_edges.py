"""Bordas de notification_preferences não cobertas por test_notification_preferences:

- is_quiet_hours: limites exatos (início inclusivo, fim exclusivo) na janela
  normal e na virada de meia-noite; guardas start==end e start/end None -> False.
- category_enabled: pref=None -> True, atributo mapeado ausente -> True, tipo
  não mapeado -> True.
"""
from __future__ import annotations

from datetime import datetime, time
from types import SimpleNamespace

from app.services.notification_preferences import category_enabled, is_quiet_hours


def _em(hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 7, 10, hh, mm)


# ── is_quiet_hours: janela normal 08:00–18:00 ───────────────────────────────

def test_janela_normal_inicio_inclusivo_e_fim_exclusivo():
    ini, fim = time(8), time(18)
    assert is_quiet_hours(_em(8, 0), ini, fim) is True     # início: inclusivo
    assert is_quiet_hours(_em(12, 0), ini, fim) is True    # dentro
    assert is_quiet_hours(_em(17, 59), ini, fim) is True   # antes do fim
    assert is_quiet_hours(_em(18, 0), ini, fim) is False   # fim: exclusivo
    assert is_quiet_hours(_em(7, 59), ini, fim) is False   # antes do início
    assert is_quiet_hours(_em(23, 0), ini, fim) is False   # fora


# ── is_quiet_hours: virada de meia-noite 22:00–07:00 ────────────────────────

def test_virada_meia_noite_cobre_faixa_noturna():
    ini, fim = time(22), time(7)
    assert is_quiet_hours(_em(22, 0), ini, fim) is True    # início inclusivo
    assert is_quiet_hours(_em(23, 0), ini, fim) is True    # noite
    assert is_quiet_hours(_em(3, 0), ini, fim) is True     # madrugada
    assert is_quiet_hours(_em(6, 59), ini, fim) is True    # antes do fim
    assert is_quiet_hours(_em(7, 0), ini, fim) is False    # fim exclusivo
    assert is_quiet_hours(_em(8, 0), ini, fim) is False    # manhã, fora
    assert is_quiet_hours(_em(12, 0), ini, fim) is False   # meio-dia, fora


# ── is_quiet_hours: guardas ─────────────────────────────────────────────────

def test_start_igual_end_nunca_e_silencioso():
    assert is_quiet_hours(_em(9, 0), time(9), time(9)) is False


def test_start_ou_end_none_desliga_silencio():
    assert is_quiet_hours(_em(23, 0), None, time(7)) is False
    assert is_quiet_hours(_em(23, 0), time(22), None) is False
    assert is_quiet_hours(_em(23, 0), None, None) is False


# ── category_enabled ────────────────────────────────────────────────────────

def test_sem_preferencia_libera_todas_as_categorias():
    assert category_enabled(None, "honorario") is True
    assert category_enabled(None, "prazo") is True


def test_tipo_mapeado_respeita_flag_ligada_e_desligada():
    pref = SimpleNamespace(prazos_enabled=True, financeiro_enabled=False)
    assert category_enabled(pref, "prazo") is True
    assert category_enabled(pref, "honorario") is False   # -> financeiro_enabled
    assert category_enabled(pref, "financeiro") is False


def test_tipo_nao_mapeado_sempre_liberado():
    pref = SimpleNamespace(financeiro_enabled=False)
    assert category_enabled(pref, "sistema") is True
    assert category_enabled(pref, "auditoria") is True


def test_atributo_mapeado_ausente_assume_liberado():
    # 'documento' -> documentos_enabled, que não existe neste objeto -> default True.
    pref = SimpleNamespace(prazos_enabled=True)
    assert category_enabled(pref, "documento") is True
