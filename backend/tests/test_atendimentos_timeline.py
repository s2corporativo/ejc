from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.atendimento import Atendimento, AtendimentoTipo
from app.routers.atendimentos import (
    _aplicar_status_solicitacao,
    _is_staff,
    _out,
    _validar_contato_status,
    _validar_prioridade,
    _pode_editar_atendimento,
    _titulo_tarefa,
)


def _user(role: str, user_id: str = "user-1"):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value=role))


def _atendimento(**overrides):
    values = {
        "id": "atendimento-1",
        "client_id": "cliente-1",
        "case_id": None,
        "tipo": AtendimentoTipo.whatsapp,
        "data_atendimento": None,
        "duracao_min": None,
        "duracao_horas": None,
        "resumo": "Cliente pediu retorno sobre o caso.",
        "proximo_passo": None,
        "solicitacao": "Enviar uma atualização do processo.",
        "solicitacao_atendida": False,
        "atendida_em": None,
        "atendida_por_id": None,
        "solicitacao_prazo": None,
        "solicitacao_prioridade": "normal",
        "solicitacao_responsavel_id": "user-1",
        "solicitacao_alerta_nivel": None,
        "task_id": None,
        "contato_status": "confirmado",
        "observacoes_privadas": "Nota interna protegida.",
        "advogado_responsavel_id": "user-1",
        "satisfacao_cliente": None,
        "created_by": "user-1",
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return Atendimento(**values)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("superadmin", True),
        ("admin", True),
        ("socio", True),
        ("advogado", True),
        ("secretaria", True),
        ("financeiro", False),
        ("estagiario", False),
        ("advogado_auxiliar", False),
        ("cliente_externo", False),
    ],
)
def test_atendimento_rbac_e_explicito(role, expected):
    assert _is_staff(_user(role)) is expected


def test_gestao_edita_qualquer_registro_e_equipe_apenas_o_proprio():
    atendimento = _atendimento(
        created_by="criador",
        advogado_responsavel_id="responsavel",
    )

    assert _pode_editar_atendimento(atendimento, _user("socio", "gestor"))
    assert _pode_editar_atendimento(
        atendimento,
        _user("advogado", "responsavel"),
    )
    assert _pode_editar_atendimento(
        atendimento,
        _user("secretaria", "criador"),
    )
    assert _pode_editar_atendimento(
        atendimento,
        _user("advogado", "user-1"),
    )
    assert not _pode_editar_atendimento(
        atendimento,
        _user("advogado", "outro"),
    )


def test_status_atendido_registra_e_limpa_a_rastreabilidade():
    atendimento = _atendimento()

    _aplicar_status_solicitacao(atendimento, True, "user-2")
    assert atendimento.solicitacao_atendida is True
    assert atendimento.atendida_em is not None
    assert atendimento.atendida_por_id == "user-2"

    _aplicar_status_solicitacao(atendimento, False, "user-2")
    assert atendimento.solicitacao_atendida is False
    assert atendimento.atendida_em is None
    assert atendimento.atendida_por_id is None


def test_nao_permite_atender_sem_descrever_a_solicitacao():
    atendimento = _atendimento(solicitacao="   ")

    with pytest.raises(HTTPException) as exc:
        _aplicar_status_solicitacao(atendimento, True, "user-2")

    assert exc.value.status_code == 422


def test_saida_da_timeline_oculta_nota_privada_e_informa_permissao():
    atendimento = _atendimento()

    payload = _out(
        atendimento,
        _user("secretaria", "user-1"),
        com_privado=False,
    )

    assert payload["resumo"] == atendimento.resumo
    assert payload["solicitacao"] == atendimento.solicitacao
    assert payload["solicitacao_atendida"] is False
    assert payload["observacoes_privadas"] is None
    assert payload["pode_editar"] is True


@pytest.mark.parametrize("prioridade", ["baixa", "normal", "alta", "urgente"])
def test_prioridades_validas_sao_normalizadas(prioridade):
    assert _validar_prioridade(prioridade.upper()) == prioridade


@pytest.mark.parametrize(
    "status",
    ["iniciado", "confirmado", "nao_concluido"],
)
def test_status_de_contato_validos(status):
    assert _validar_contato_status(status) == status


def test_rejeita_prioridade_e_status_de_contato_invalidos():
    with pytest.raises(HTTPException):
        _validar_prioridade("critica")
    with pytest.raises(HTTPException):
        _validar_contato_status("enviado")


def test_saida_identifica_solicitacao_atrasada_e_vinculos():
    atendimento = _atendimento(
        solicitacao_prazo=datetime.now(timezone.utc) - timedelta(hours=1),
        solicitacao_prioridade="urgente",
        task_id="task-1",
        contato_status="iniciado",
    )

    payload = _out(atendimento, _user("advogado", "user-1"))

    assert payload["solicitacao_atrasada"] is True
    assert payload["solicitacao_prioridade"] == "urgente"
    assert payload["task_id"] == "task-1"
    assert payload["contato_status"] == "iniciado"


def test_conclusao_e_reabertura_controlam_marcador_de_alerta():
    atendimento = _atendimento(solicitacao_alerta_nivel="proximo")

    _aplicar_status_solicitacao(atendimento, True, "user-2")
    assert atendimento.solicitacao_alerta_nivel == "concluido"

    _aplicar_status_solicitacao(atendimento, False, "user-2")
    assert atendimento.solicitacao_alerta_nivel is None


def test_tarefa_vinculada_nao_replica_conteudo_sensivel():
    conteudo = "Pedido sigiloso do cliente com dados pessoais"

    titulo = _titulo_tarefa(conteudo)

    assert titulo == "Solicitação de cliente"
    assert conteudo not in titulo
