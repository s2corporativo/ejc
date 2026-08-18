"""`/ia-especializada/{perfil}` recebia `body: dict = Body(...)` cru, sem
schema Pydantic nem teto de tamanho — achado da revisão de segurança sobre a
auditoria de IA (18/08): mesma classe de payload-sem-limite que o resto da
auditoria fechou em outros endpoints (schemas/ai.py._MAX_TEXTO_IA), só que
este ficou de fora por chamar ai_gateway.chat direto sem schema nenhum.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.ia_especializada import ConsultaIaEspecializadaReq

_MUITO_GRANDE = "a" * 200_001
_NO_LIMITE = "a" * 200_000


def test_rejeita_pergunta_acima_do_teto():
    with pytest.raises(ValidationError):
        ConsultaIaEspecializadaReq(pergunta=_MUITO_GRANDE)


def test_aceita_pergunta_no_teto():
    req = ConsultaIaEspecializadaReq(pergunta=_NO_LIMITE)
    assert len(req.pergunta) == 200_000


def test_nivel_inteligencia_e_opcional():
    req = ConsultaIaEspecializadaReq(pergunta="pergunta curta")
    assert req.nivel_inteligencia is None


def test_endpoint_usa_o_schema_tipado_nao_dict_cru():
    """Trava a regressão: `dict = Body(...)` não pode voltar."""
    import inspect

    from app.routers.ia_especializada import consultar

    params = inspect.signature(consultar).parameters
    assert params["body"].annotation is ConsultaIaEspecializadaReq
