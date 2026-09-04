# ── tests/test_users_oab_djen_validacao.py ───────────────────────────────────
# `PATCH /users/{id}` gravava `djen_oab_numero`/`djen_oab_uf` por `setattr`
# direto, sem validação nenhuma. Três consequências reais:
#
#   • número com lixo ("252.599", "abc") ia para o banco e a consulta ao CNJ
#     nunca casava — captura zero, sem erro;
#   • UF inexistente ("XX") ou com 3 letras estourava o String(2) em 500;
#   • metade do par (número sem UF) fazia o job SELECIONAR o advogado
#     (`djen_oab_numero IS NOT NULL`) e descartá-lo em seguida — o modo de
#     falha mais caro num sistema de prazos, porque parece configurado.
#
# A validação de formato vive no schema (vale para qualquer chamador) e a
# coerência do par no router (que enxerga o valor já gravado).
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.users import _validar_par_oab_djen
from app.schemas.auth import UserUpdate


# ── formato (schema) ─────────────────────────────────────────────────────────

def test_numero_e_uf_normalizados():
    u = UserUpdate(djen_oab_numero=" 252599 ", djen_oab_uf=" mg ")
    assert (u.djen_oab_numero, u.djen_oab_uf) == ("252599", "MG")


@pytest.mark.parametrize("numero", ["252.599", "abc", "252599/MG", "25 2599"])
def test_numero_com_lixo_e_recusado(numero):
    with pytest.raises(ValidationError):
        UserUpdate(djen_oab_numero=numero)


def test_numero_maior_que_a_coluna_e_recusado():
    # users.djen_oab_numero é String(10): sem isto, o erro só apareceria no
    # banco, como 500.
    with pytest.raises(ValidationError):
        UserUpdate(djen_oab_numero="12345678901")


@pytest.mark.parametrize("uf", ["XX", "MGG", "M", "BR"])
def test_uf_inexistente_e_recusada(uf):
    with pytest.raises(ValidationError):
        UserUpdate(djen_oab_uf=uf)


def test_todas_as_27_ufs_sao_aceitas():
    from app.core.ufs import UFS_BRASIL

    for uf in UFS_BRASIL:
        assert UserUpdate(djen_oab_uf=uf).djen_oab_uf == uf


def test_string_vazia_vira_none_para_desligar_o_monitoramento():
    u = UserUpdate(djen_oab_numero="", djen_oab_uf="")
    assert u.djen_oab_numero is None and u.djen_oab_uf is None
    # `exclude_unset` preserva a intenção de limpar (campo foi enviado).
    assert set(u.model_dump(exclude_unset=True)) == {
        "djen_oab_numero",
        "djen_oab_uf",
    }


# ── coerência do par (router) ────────────────────────────────────────────────

def _user(numero=None, uf=None):
    return SimpleNamespace(djen_oab_numero=numero, djen_oab_uf=uf)


def test_par_completo_passa():
    _validar_par_oab_djen(_user(), {"djen_oab_numero": "252599", "djen_oab_uf": "MG"})


def test_limpar_os_dois_passa():
    _validar_par_oab_djen(
        _user("252599", "MG"), {"djen_oab_numero": None, "djen_oab_uf": None}
    )


def test_numero_sem_uf_e_recusado():
    with pytest.raises(HTTPException) as exc:
        _validar_par_oab_djen(_user(), {"djen_oab_numero": "252599"})
    assert exc.value.status_code == 400
    assert "indivisível" in exc.value.detail


def test_uf_sem_numero_e_recusada():
    with pytest.raises(HTTPException) as exc:
        _validar_par_oab_djen(_user(), {"djen_oab_uf": "MG"})
    assert exc.value.status_code == 400


def test_patch_parcial_completa_o_par_ja_gravado():
    """Trocar só a UF de quem já tem número é legítimo — o par continua
    completo depois da mudança."""
    _validar_par_oab_djen(_user("252599", "MG"), {"djen_oab_uf": "SP"})


def test_patch_parcial_que_quebraria_o_par_e_recusado():
    with pytest.raises(HTTPException):
        _validar_par_oab_djen(_user("252599", "MG"), {"djen_oab_uf": None})


def test_patch_que_nao_toca_oab_nao_e_afetado():
    _validar_par_oab_djen(_user("252599", "MG"), {"phone": "31999999999"})
    _validar_par_oab_djen(_user(), {"full_name": "Fulano"})
