"""Regressão do Módulo 5/8: validação de argumentos de tool contra input_schema.

O input_schema era enviado ao provedor mas nunca conferido na execução: o LLM
podia devolver campo faltando ou tipo errado direto para uma tool de escrita
com efeito colateral. A validação falha antes do handler, sem tocar o banco.
"""
import pytest

from app.services.ai.agent.tools.registry import ToolSpec, _ToolArgError, _validar_args


def _spec(name="t", props=None, required=()):
    return ToolSpec(
        name=name,
        description="d",
        input_schema={"type": "object", "properties": props or {}, "required": list(required)},
        handler=lambda args, ctx: args,
        requer_confirmacao=False,
        roles=None,
    )


def test_aceita_args_validos():
    spec = _spec(props={"descricao": {"type": "string"}}, required=["descricao"])
    _validar_args(spec, {"descricao": "nota"})


def test_rejeita_campo_obrigatorio_ausente():
    spec = _spec(props={"descricao": {"type": "string"}}, required=["descricao"])
    with pytest.raises(_ToolArgError, match="obrigat"):
        _validar_args(spec, {})


def test_rejeita_campo_obrigatorio_vazio():
    spec = _spec(props={"descricao": {"type": "string"}}, required=["descricao"])
    with pytest.raises(_ToolArgError):
        _validar_args(spec, {"descricao": ""})


def test_rejeita_tipo_errado():
    spec = _spec(props={"n": {"type": "string"}}, required=["n"])
    with pytest.raises(_ToolArgError, match="deve ser string"):
        _validar_args(spec, {"n": 123})


def test_aceita_boolean_false_como_valido():
    spec = _spec(props={"ativo": {"type": "boolean"}}, required=["ativo"])
    _validar_args(spec, {"ativo": False})


def test_rejeita_enum_fora_das_opcoes():
    spec = _spec(props={"tipo": {"type": "string", "enum": ["a", "b"]}}, required=["tipo"])
    with pytest.raises(_ToolArgError, match="permitidas"):
        _validar_args(spec, {"tipo": "z"})


def test_ignora_campos_nao_declarados_e_nulos():
    spec = _spec(props={"descricao": {"type": "string"}}, required=["descricao"])
    _validar_args(spec, {"descricao": "ok", "extra": 1, "nulo": None})


def test_schema_sem_required_nao_exige_nada():
    spec = _spec(props={})
    _validar_args(spec, {})


def test_registrar_nota_caso_exige_descricao_string():
    """Regressão do achado: a tool de escrita mais perigosa."""
    spec = ToolSpec(
        name="registrar_nota_caso",
        description="d",
        input_schema={
            "type": "object",
            "properties": {"descricao": {"type": "string"}},
            "required": ["descricao"],
        },
        handler=lambda a, c: a,
        requer_confirmacao=True,
        roles=None,
    )
    with pytest.raises(_ToolArgError, match="deve ser string"):
        _validar_args(spec, {"descricao": 42})
