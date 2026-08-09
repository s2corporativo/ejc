"""Regressões de governança societária introduzidas pela auditoria #861."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _DBScalar:
    def __init__(self, value):
        self.value = value

    async def scalar(self, _stmt):
        return self.value


@pytest.mark.asyncio
async def test_criador_nao_aprova_a_propria_distribuicao():
    from app.routers.gestao_societaria import aprovar_distribuicao

    dist = SimpleNamespace(
        id="dist-1",
        status="calculado",
        created_by="admin-1",
        aprovado_por=None,
        aprovado_em=None,
    )
    cu = SimpleNamespace(id="admin-1", role=SimpleNamespace(value="admin"))

    with pytest.raises(HTTPException) as exc:
        await aprovar_distribuicao(
            dist_id="dist-1",
            db=_DBScalar(dist),
            cu=cu,
        )
    assert exc.value.status_code == 403
    assert "segregação de funções" in str(exc.value.detail)
    assert dist.status == "calculado"


@pytest.mark.asyncio
async def test_mutacao_societaria_sensivel_exige_motivo():
    from app.routers.gestao_societaria import SocioPatch, atualizar_socio

    socio = SimpleNamespace(
        id="socio-1",
        user_id="user-1",
        participacao_percentual=0.5,
        regime="misto",
        pro_labore=1000,
        oab_numero=None,
        oab_uf=None,
        data_entrada=None,
        data_saida=None,
        meta_produtividade=None,
        ativo=True,
        observacoes=None,
    )
    cu = SimpleNamespace(id="admin-2", role=SimpleNamespace(value="admin"))

    with pytest.raises(HTTPException) as exc:
        await atualizar_socio(
            socio_id="socio-1",
            req=SocioPatch(pro_labore=2000),
            db=_DBScalar(socio),
            cu=cu,
        )
    assert exc.value.status_code == 422
    assert "motivo_alteracao" in str(exc.value.detail)
