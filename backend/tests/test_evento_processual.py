"""Fase 2 — Catálogo determinístico evento processual → termo inicial.

Garante:
  • cada evento com regra de CERTEZA produz termo (dies a quo) + base legal;
  • incertos saem como "verificar" (contagem_confirmavel=False, termo None);
  • semântica do termo: dies a quo EXCLUÍDO da contagem (CPC art. 224, caput) —
    alimentado em prazo_dias_uteis, o 1º dia contado é `inicio_contagem`;
  • evento desconhecido NUNCA presume nada.

Datas usadas (junho/2026): 01/06 segunda; 05/06 sexta; 08/06 segunda.
"""
from datetime import date

from app.services.deadline_calculator import prazo_dias_uteis
from app.services.evento_processual import (
    CATALOGO_EVENTOS,
    EVENTOS_VALIDOS,
    resolver_termo_inicial,
)


def test_catalogo_invariantes_base_legal_sempre_presente():
    for codigo, info in CATALOGO_EVENTOS.items():
        assert info.get("base_legal"), codigo
        assert info.get("nome"), codigo
    assert set(EVENTOS_VALIDOS) == set(CATALOGO_EVENTOS)


# ── Publicação no DJe (CPC art. 224, §§2º-3º) ────────────────────────────────

def test_publicacao_dje_dies_a_quo_e_inicio_contagem():
    out = resolver_termo_inicial("publicacao_dje", date(2026, 6, 8))  # segunda
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 8)          # dies a quo (excluído)
    assert out["inicio_contagem"] == date(2026, 6, 9)        # 1º dia útil seguinte
    assert "224" in out["base_legal"]
    assert out["avisos"]


def test_publicacao_dje_sexta_inicio_contagem_pula_fim_de_semana():
    out = resolver_termo_inicial("publicacao_dje", date(2026, 6, 5))  # sexta
    assert out["inicio_contagem"] == date(2026, 6, 8)  # segunda


def test_publicacao_dje_compatibilidade_com_prazo_dias_uteis():
    # Invariante crítico: o 1º dia contado por prazo_dias_uteis(termo, 1) é
    # exatamente o inicio_contagem informado (sem off-by-one) — na MESMA régua
    # do motor (aplicar_recesso=True, como motor_peca_service).
    out = resolver_termo_inicial("publicacao_dje", date(2026, 6, 5))
    assert prazo_dias_uteis(out["termo_inicial"], 1,
                            aplicar_recesso=True) == out["inicio_contagem"]


def test_publicacao_no_recesso_inicio_contagem_apos_20_de_janeiro():
    """Item 4 da auditoria: publicação em 18/12 (sexta) — o 1º dia útil contado
    respeita o recesso INTEGRAL do CPC art. 220 (20/12–20/01), igual ao motor
    (aplicar_recesso=True): inicio_contagem = 1º dia útil APÓS 20/01."""
    out = resolver_termo_inicial("publicacao_dje", date(2026, 12, 18))  # sexta
    assert out["termo_inicial"] == date(2026, 12, 18)
    # 19-20/12 fim de semana; 21/12/2026–20/01/2027 recesso art. 220 →
    # 1º dia útil contado = 21/01/2027 (quinta).
    assert out["inicio_contagem"] == date(2027, 1, 21)
    # Consistência exata com a contagem real do motor (sem off-by de 14 dias).
    assert prazo_dias_uteis(out["termo_inicial"], 1,
                            aplicar_recesso=True) == out["inicio_contagem"]


def test_disponibilizacao_dje_publicacao_no_dia_util_seguinte():
    # Disponibilizado sexta 05/06 ⇒ publicado segunda 08/06 ⇒ contagem 09/06.
    out = resolver_termo_inicial("disponibilizacao_dje", date(2026, 6, 5))
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 8)
    assert out["inicio_contagem"] == date(2026, 6, 9)
    assert "11.419" in out["base_legal"]


# ── Intimação eletrônica (Lei 11.419/2006, art. 5º) ──────────────────────────

def test_intimacao_eletronica_com_consulta_confirmavel():
    out = resolver_termo_inicial(
        "intimacao_eletronica", date(2026, 6, 10), meio="consulta")
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)
    assert "11.419" in out["base_legal"] and "231" in out["base_legal"]


def test_intimacao_eletronica_sem_consulta_vira_verificar():
    out = resolver_termo_inicial("intimacao_eletronica", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is False
    assert out["termo_inicial"] is None
    assert any("10 dias" in a for a in out["avisos"])


# ── Juntada do AR / mandado (CPC art. 231, I-II) ─────────────────────────────

def test_juntada_ar_termo_na_data_da_juntada():
    out = resolver_termo_inicial("juntada_ar", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)
    assert "231, I" in out["base_legal"]


def test_juntada_mandado_termo_na_data_da_juntada():
    out = resolver_termo_inicial("juntada_mandado", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)
    assert "231, II" in out["base_legal"]


# ── Audiência (CPC art. 1.003, §1º, por analogia) ────────────────────────────

def test_audiencia_sem_confirmacao_de_ciencia_vira_verificar():
    out = resolver_termo_inicial("audiencia", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is False
    assert out["termo_inicial"] is None
    assert out["avisos"]


def test_audiencia_com_ciencia_confirmada_termo_na_data():
    out = resolver_termo_inicial(
        "audiencia", date(2026, 6, 10), meio="ciencia_em_audiencia")
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)
    assert "1.003" in out["base_legal"]


def test_ciencia_em_audiencia_evento_direto():
    out = resolver_termo_inicial("ciencia_em_audiencia", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)


# ── Ciência expressa nos autos ───────────────────────────────────────────────

def test_ciencia_expressa_confirmavel_com_base_legal():
    out = resolver_termo_inicial("ciencia_expressa", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is True
    assert out["termo_inicial"] == date(2026, 6, 10)
    assert "239" in out["base_legal"]


# ── Evento desconhecido: nunca inventar ──────────────────────────────────────

def test_evento_desconhecido_nunca_presume():
    out = resolver_termo_inicial("evento_inventado", date(2026, 6, 10))
    assert out["contagem_confirmavel"] is False
    assert out["termo_inicial"] is None
    assert out["inicio_contagem"] is None
    assert "verificar" in out["base_legal"].lower()
    assert out["avisos"]
