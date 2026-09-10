"""Invariantes P0 de confirmação de prazo no próprio modelo."""
from app.models.deadline import Deadline, DeadlinePrioridade


def test_datajud_nunca_nasce_confirmado_mesmo_se_caller_pedir_true():
    prazo = Deadline(origem="datajud", confirmado=True)
    assert prazo.confirmado is False


def test_importacao_ia_nunca_nasce_confirmada():
    prazo = Deadline(origem="importacao_ia")
    assert prazo.confirmado is False


def test_origem_ia_prefixada_nunca_nasce_confirmada():
    prazo = Deadline(origem="ia_djen", confirmado=True)
    assert prazo.confirmado is False


def test_prazo_critico_nunca_nasce_confirmado():
    prazo = Deadline(prioridade=DeadlinePrioridade.critica, confirmado=True)
    assert prazo.confirmado is False


def test_prazo_manual_nao_tem_confirmacao_reescrita_pelo_construtor():
    prazo = Deadline(origem="manual", confirmado=True)
    assert prazo.confirmado is True
