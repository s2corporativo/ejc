"""Reconciliação dos dois campos de OAB do usuário (AUD27-P3-9).

O `User` tem `oab_number` (perfil) e `djen_oab_numero`/`djen_oab_uf` (captura),
sem ligação entre eles. O advogado que preenchia só o do perfil era pulado em
SILÊNCIO pelo job das 06h30 — o sistema tinha o dado e não capturava intimação
nenhuma. Num sistema de prazos, é a falha mais cara possível.

O que estes testes travam, além da resolução: que a UF NUNCA seja adivinhada.
Número de OAB sem UF é ambíguo no país inteiro; supor o estado do escritório
monitoraria a inscrição de OUTRO advogado — pior que não monitorar, porque
pareceria funcionar.
"""
from __future__ import annotations

import pytest

from app.services.djen_service import oab_para_captura


class _Adv:
    def __init__(self, *, djen_num=None, djen_uf=None, perfil=None):
        self.djen_oab_numero = djen_num
        self.djen_oab_uf = djen_uf
        self.oab_number = perfil


# ── campo explícito da captura vence sempre ──────────────────────────────────

def test_campo_explicito_da_captura_tem_precedencia():
    adv = _Adv(djen_num="252599", djen_uf="MG", perfil="111111/SP")
    assert oab_para_captura(adv) == ("252599", "MG")


def test_mascara_no_numero_e_normalizada():
    adv = _Adv(djen_num="252.599", djen_uf="mg")
    assert oab_para_captura(adv) == ("252599", "MG")


# ── fallback do perfil, quando traz a UF ─────────────────────────────────────

@pytest.mark.parametrize("perfil,esperado", [
    ("252599/MG", ("252599", "MG")),
    ("OAB/MG 252599", ("252599", "MG")),
    ("252599 MG", ("252599", "MG")),
    ("251174/mg", ("251174", "MG")),
])
def test_perfil_com_uf_alimenta_a_captura(perfil, esperado):
    """Era este o caso que fazia o job pular o advogado em silêncio."""
    assert oab_para_captura(_Adv(perfil=perfil)) == esperado


# ── a UF nunca é adivinhada ──────────────────────────────────────────────────

@pytest.mark.parametrize("perfil", ["252599", "OAB 252599", "nº 252599", ""])
def test_perfil_sem_uf_nao_vira_captura(perfil):
    """Sem UF determinável, devolve vazio — e o chamador registra
    `oab_nao_configurada`, que aparece no diagnóstico. Chutar a UF do
    escritório monitoraria a inscrição de outro advogado."""
    assert oab_para_captura(_Adv(perfil=perfil)) == ("", "")


def test_rotulo_oab_nao_e_confundido_com_uf():
    """Sem a lista de exceções, "OAB 252599" resolveria uf="OA"."""
    numero, uf = oab_para_captura(_Adv(perfil="OAB 252599"))
    assert (numero, uf) == ("", "")


def test_sem_nenhum_campo_preenchido():
    assert oab_para_captura(_Adv()) == ("", "")


def test_captura_parcial_no_campo_dedicado_cai_para_o_perfil():
    """`djen_oab_numero` sem UF é configuração incompleta; se o perfil tiver a
    informação completa, ela vale."""
    adv = _Adv(djen_num="252599", djen_uf=None, perfil="251174/MG")
    assert oab_para_captura(adv) == ("251174", "MG")
