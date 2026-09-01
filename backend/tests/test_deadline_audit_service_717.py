from __future__ import annotations

from datetime import date

import pytest

from app.models.deadline import Deadline
from app.services import deadline_audit_service as svc


def _prazo(**kw) -> Deadline:
    base = dict(
        id="dl-1",
        titulo="Prazo crítico",
        tipo="processual",
        prioridade="critica",
        data_prazo=date(2026, 9, 22),
        data_intimacao=date(2026, 9, 1),
        confirmado=False,
        calculado_por="calc-1",
        calculo_metadata={"historico_recalculo": []},
    )
    base.update(kw)
    return Deadline(**base)


def test_snapshot_nao_contem_identificador_de_caso_ou_partes():
    prova = svc.construir_prova_calculo(
        actor_id="u1",
        data_ciencia=date(2026, 9, 1),
        termo_inicial=date(2026, 9, 2),
        termo_final=date(2026, 9, 22),
        regime="civel",
        tribunal="TJMG",
        dias=15,
        dobro=False,
        excecao_recesso_penal=False,
        base_legal="CPC arts. 219 e 220",
        resultado={
            "calendario_status": "validado",
            "resultado_preliminar": False,
            "revisao_obrigatoria": False,
        },
        modo_origem="calculo_automatico",
    )
    assert prova["termo_inicial"] == "2026-09-02"
    assert prova["termo_final"] == "2026-09-22"
    assert prova["regime_calculo"] == "civel"
    assert prova["engine_version"] == svc.ENGINE_VERSION
    assert len(prova["calendario_fingerprint_sha256"]) == 64
    assert "case_id" not in prova
    assert "numero_processo" not in prova
    assert "cliente" not in prova


def test_prazo_critico_nasce_nao_confirmado_e_com_calculista():
    confirmado, calculista = svc.preparar_estado_inicial(
        prioridade="critica", actor_id="u1", confirmado_motor=True
    )
    assert confirmado is False
    assert calculista == "u1"


def test_prazo_nao_critico_preserva_estado_do_motor():
    assert svc.preparar_estado_inicial(
        prioridade="alta", actor_id="u1", confirmado_motor=True
    ) == (True, "u1")
    assert svc.preparar_estado_inicial(
        prioridade="alta", actor_id="u1", confirmado_motor=False
    ) == (False, "u1")


def test_critico_impede_autoconfirmacao():
    prazo = _prazo(calculado_por="u1")
    with pytest.raises(ValueError, match="diferente do calculista"):
        svc.registrar_conferencia(prazo, "u1")
    assert prazo.confirmado is False


def test_critico_exige_calculista_identificado():
    prazo = _prazo(calculado_por=None)
    with pytest.raises(ValueError, match="legado sem calculista"):
        svc.registrar_conferencia(prazo, "u2")


def test_segundo_usuario_confirma_e_fica_registrado():
    prazo = _prazo(calculado_por="u1")
    svc.registrar_conferencia(prazo, "u2")
    assert prazo.confirmado is True
    assert prazo.conferido_por == "u2"
    assert prazo.conferido_em is not None
    assert prazo.calculo_metadata["ultima_conferencia"]["calculado_por"] == "u1"
    assert prazo.calculo_metadata["estado_validacao"] == "conferido"


def test_mudanca_material_reabre_conferencia_e_troca_calculista():
    prazo = _prazo(
        confirmado=True,
        calculado_por="u1",
        conferido_por="u2",
        calculo_metadata={
            "historico_recalculo": [],
            "ultima_conferencia": {"por": "u2"},
        },
    )
    reabriu = svc.invalidar_conferencia(
        prazo,
        actor_id="u3",
        motivo="data_prazo_alterada",
        antes={"data_prazo": date(2026, 9, 22)},
        depois={"data_prazo": date(2026, 9, 25)},
    )
    assert reabriu is True
    assert prazo.confirmado is False
    assert prazo.calculado_por == "u3"
    assert prazo.conferido_por is None
    assert prazo.conferido_em is None
    hist = prazo.calculo_metadata["historico_recalculo"]
    assert hist[-1]["antes"]["data_prazo"] == "2026-09-22"
    assert hist[-1]["depois"]["data_prazo"] == "2026-09-25"
    assert prazo.calculo_metadata["estado_validacao"] == "aguardando_conferencia"
