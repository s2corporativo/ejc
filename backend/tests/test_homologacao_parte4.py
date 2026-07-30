"""Regressões da Homologação Técnica do EJC — Parte 4."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import checklists, prompts_juridicos
from app.routers.prompts_juridicos import PromptIn
from app.services.ai_skill_service import _system_prompt_skill


def _user(user_id: str = "u1", role: str = "advogado"):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value=role))


def _prompt(*, created_by: str = "u1", publico: bool = False):
    return SimpleNamespace(
        id="p1",
        titulo="Prompt de teste",
        categoria="analise",
        conteudo="Conteúdo jurídico fictício com tamanho suficiente.",
        descricao=None,
        tags=None,
        favorito=False,
        publico=publico,
        vezes_executado=0,
        versao=1,
        avaliacao_media=None,
        created_by=created_by,
        created_at=None,
        updated_at=None,
    )


@pytest.mark.parametrize(
    "skill_name",
    ["simulador-defesa-adversarial", "prescricao-decadencia"],
)
def test_skills_criticas_recebem_regra_processual_correta(skill_name):
    skill = SimpleNamespace(name=skill_name, system_prompt="Prompt original.")
    prompt = _system_prompt_skill(skill)

    assert "art. 487, II, do CPC" in prompt
    assert "resolve o mérito" in prompt
    assert "Nunca o descreva como extinção sem resolução" in prompt
    assert "art. 26 do CDC" in prompt
    assert "art. 27" in prompt
    assert "pretensão autônoma" in prompt
    assert prompt.startswith("Prompt original.")


def test_guardrail_nao_altera_skill_fora_do_escopo():
    skill = SimpleNamespace(name="auditor-pedidos", system_prompt="Prompt original.")
    assert _system_prompt_skill(skill) == "Prompt original."


def test_novo_prompt_e_privado_por_padrao():
    assert PromptIn.model_fields["publico"].default is False


def test_visibilidade_de_prompt_privado_respeita_autoria_e_gestao():
    prompt = _prompt(created_by="autor", publico=False)

    assert prompts_juridicos._pode_visualizar_prompt(_user("autor"), prompt)
    assert not prompts_juridicos._pode_visualizar_prompt(_user("terceiro"), prompt)
    assert prompts_juridicos._pode_visualizar_prompt(
        _user("socio", "socio"), prompt
    )


def test_prompt_publico_e_visivel_sem_transferir_gestao():
    prompt = _prompt(created_by="autor", publico=True)
    terceiro = _user("terceiro")

    assert prompts_juridicos._pode_visualizar_prompt(terceiro, prompt)
    assert not prompts_juridicos._pode_gerir_prompt(terceiro, prompt)


def test_gestao_de_prompt_e_do_autor_ou_socio():
    prompt = _prompt(created_by="autor")

    assert prompts_juridicos._pode_gerir_prompt(_user("autor"), prompt)
    assert not prompts_juridicos._pode_gerir_prompt(_user("terceiro"), prompt)
    assert prompts_juridicos._pode_gerir_prompt(
        _user("gestor", "socio"), prompt
    )


def test_saida_expoe_capacidade_sem_vazar_conteudo_privado():
    prompt = _prompt(created_by="autor")
    saida_autor = prompts_juridicos._out(prompt, _user("autor"))
    saida_terceiro = prompts_juridicos._out(prompt, _user("terceiro"))

    assert saida_autor["pode_editar"] is True
    assert saida_autor["pode_excluir"] is True
    assert saida_terceiro["pode_editar"] is False
    assert saida_terceiro["pode_excluir"] is False


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, value):
        self.value = value
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return _ScalarResult(self.value)

    async def commit(self):
        self.commits += 1


async def test_autor_remove_proprio_prompt():
    prompt = _prompt(created_by="autor")
    db = _FakeDB(prompt)

    await prompts_juridicos.remover_prompt("p1", db=db, cu=_user("autor"))

    assert prompt.deleted_at is not None
    assert db.commits == 1


async def test_advogado_nao_remove_prompt_de_terceiro():
    prompt = _prompt(created_by="autor")

    with pytest.raises(HTTPException) as exc:
        await prompts_juridicos.remover_prompt(
            "p1", db=_FakeDB(prompt), cu=_user("terceiro")
        )

    assert exc.value.status_code == 403
    assert "autor ou sócio" in exc.value.detail


def test_autor_advogado_remove_proprio_template():
    template = SimpleNamespace(created_by="autor")

    assert checklists._pode_remover_template(_user("autor"), template)
    assert not checklists._pode_remover_template(_user("terceiro"), template)
    assert checklists._pode_remover_template(
        _user("gestor", "socio"), template
    )
