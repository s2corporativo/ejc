"""Regressão AP-13: prazo materializado por Documento IA nunca nasce confirmado."""
from __future__ import annotations

import ast
import inspect
import textwrap

from app.routers import documento_ia


def test_aplicar_acoes_forca_confirmado_false_em_deadline_automatico():
    arvore = ast.parse(textwrap.dedent(inspect.getsource(documento_ia.aplicar_acoes)))
    construtores = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "Deadline"
    ]

    assert construtores, "aplicar_acoes deixou de materializar Deadline; revisar contrato"

    for chamada in construtores:
        kwargs = {kw.arg: kw.value for kw in chamada.keywords if kw.arg}
        assert "origem" in kwargs
        assert isinstance(kwargs["origem"], ast.Constant)
        assert kwargs["origem"].value == "ia_documento"
        assert "confirmado" in kwargs, "deadline automático não declarou HITL explicitamente"
        assert isinstance(kwargs["confirmado"], ast.Constant)
        assert kwargs["confirmado"].value is False
