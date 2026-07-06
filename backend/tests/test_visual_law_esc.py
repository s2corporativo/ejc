# ── tests/test_visual_law_esc.py ─────────────────────────────────────────────
# #34: o esc() dos geradores de PDF Visual Law é a barreira anti-injeção de HTML
# (o payload dos verticais vem do frontend/usuário e é interpolado no HTML→PDF).
# Sem teste, uma regressão em esc reabriria injeção de markup nos relatórios.
from app.services.visual_law_theme import esc


def test_esc_neutraliza_script_e_tags():
    saida = esc("<script>alert('x')</script>")
    assert "<script>" not in saida
    assert "&lt;script&gt;" in saida


def test_esc_escapa_aspas_e_ampersand():
    saida = esc('a & b "c" \'d\'')
    assert "&amp;" in saida
    assert "&quot;" in saida or "&#x27;" in saida  # aspas escapadas
    assert "<" not in saida and ">" not in saida


def test_esc_none_vira_string_vazia():
    assert esc(None) == ""
