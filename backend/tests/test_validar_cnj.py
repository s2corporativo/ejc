"""CNJ na entrada de casos — validar_cnj (validators_service) + field_validator
em CaseCreate/CaseUpdate (schemas/case.py).

Números CNJ pré-calculados (DV pelo módulo 97 — Res. CNJ 65/2008), reaproveitados
de test_verificador_jurisprudencia.py para não divergir da fonte da regra:
"""
import pytest
from pydantic import ValidationError

from app.schemas.case import CaseCreate, CaseUpdate
from app.services.validators_service import normalizar_cnj, validar_cnj

CNJ_VALIDO_TJMG = "0001234-10.2020.8.13.0024"       # DV correto (com máscara)
CNJ_VALIDO_TJMG_SEM_MASCARA = "00012341020208130024"  # mesmos 20 dígitos, sem máscara
CNJ_VALIDO_STJ = "0004567-56.2019.3.00.0000"        # DV correto, STJ
CNJ_DV_ERRADO = "0001234-11.2020.8.13.0024"         # DV trocado (11 no lugar de 10)


# ── validar_cnj (função pura) ─────────────────────────────────────────────────

def test_cnj_valido_com_mascara_passa():
    assert validar_cnj(CNJ_VALIDO_TJMG)
    assert validar_cnj(CNJ_VALIDO_STJ)


def test_cnj_valido_sem_mascara_passa():
    assert validar_cnj(CNJ_VALIDO_TJMG_SEM_MASCARA)
    # com e sem máscara referem-se ao MESMO número:
    assert normalizar_cnj(CNJ_VALIDO_TJMG) == CNJ_VALIDO_TJMG_SEM_MASCARA


def test_cnj_dv_trocado_falha():
    assert not validar_cnj(CNJ_DV_ERRADO)


def test_cnj_vazio_ou_none_nao_valida():
    # A função pura considera vazio inválido; a decisão de "aceitar ausência"
    # é do chamador (o schema, abaixo).
    assert not validar_cnj("")
    assert not validar_cnj(None)  # type: ignore[arg-type]


def test_cnj_tamanho_e_pontuacao_invalidos_falham():
    assert not validar_cnj("123")                     # curto demais
    assert not validar_cnj("0001234/10.2020.8.13.0024")  # pontuação fora do padrão


# ── field_validator no schema (entrada de create/update) ──────────────────────

def _case_create(numero):
    return CaseCreate(titulo="Ação de teste", area="civil",
                      client_id="cli-1", numero_processo=numero)


def test_schema_create_aceita_cnj_valido_com_e_sem_mascara():
    assert _case_create(CNJ_VALIDO_TJMG).numero_processo == CNJ_VALIDO_TJMG
    assert (_case_create(CNJ_VALIDO_TJMG_SEM_MASCARA).numero_processo
            == CNJ_VALIDO_TJMG_SEM_MASCARA)


def test_schema_create_vazio_ou_none_passa():
    # Caso pode ainda não ter número: None e "" são aceitos (viram None).
    assert _case_create(None).numero_processo is None
    assert _case_create("").numero_processo is None
    assert _case_create("   ").numero_processo is None
    # Omitir o campo também passa (default None).
    assert CaseCreate(titulo="X", area="civil",
                      client_id="cli-1").numero_processo is None


def test_schema_create_dv_trocado_rejeita():
    with pytest.raises(ValidationError) as exc:
        _case_create(CNJ_DV_ERRADO)
    assert "CNJ inválido" in str(exc.value)


def test_schema_update_valida_igual_ao_create():
    # Update com número válido passa; DV trocado rejeita; ausência do campo passa.
    assert CaseUpdate(numero_processo=CNJ_VALIDO_STJ).numero_processo == CNJ_VALIDO_STJ
    with pytest.raises(ValidationError):
        CaseUpdate(numero_processo=CNJ_DV_ERRADO)
    assert CaseUpdate(titulo="só muda o título").numero_processo is None
