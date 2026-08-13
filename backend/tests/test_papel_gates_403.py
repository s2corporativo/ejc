"""Gates de PAPEL (RBAC) adicionados na blindagem de routers — testes 403.

Sem banco: exercita apenas o ramo de autorização por perfil, que dispara ANTES
de qualquer acesso ao banco. Um usuário de baixo privilégio (cliente_externo)
deve receber 403 em endpoints/depend. sensíveis; um sócio deve passar o gate.
"""
import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


# ── jurimetria_extra: métricas de êxito (sócio) e staff ────────────────────────

def test_jurimetria_consolidado_req_staff_barra_cliente():
    from app.routers.jurimetria import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_user(UserRole.cliente_externo))
    assert exc.value.status_code == 403


def test_jurimetria_consolidado_req_socio_barra_advogado():
    from app.routers.jurimetria import _req_socio
    with pytest.raises(HTTPException) as exc:
        _req_socio(_user(UserRole.advogado))
    assert exc.value.status_code == 403
    # sócio passa
    assert _req_socio(_user(UserRole.socio)).role == UserRole.socio


# ── memoria_institucional: só equipe ───────────────────────────────────────────

def test_memoria_req_staff_barra_cliente():
    from app.routers.memoria_institucional import _req_staff
    with pytest.raises(HTTPException) as exc:
        _req_staff(_user(UserRole.cliente_externo))
    assert exc.value.status_code == 403
    assert _req_staff(_user(UserRole.estagiario)).role == UserRole.estagiario


# ── despesas / relatorio_cliente: financeiro/gestão ────────────────────────────

def test_despesas_req_fin_barra_advogado_auxiliar():
    from app.routers.despesas import _req_fin
    with pytest.raises(HTTPException) as exc:
        _req_fin(_user(UserRole.advogado_auxiliar))
    assert exc.value.status_code == 403


def test_relatorio_cliente_req_fin_adv_barra_cliente():
    from app.routers.relatorio_cliente import _req_fin_adv
    with pytest.raises(HTTPException) as exc:
        _req_fin_adv(_user(UserRole.cliente_externo))
    assert exc.value.status_code == 403


# ── whatsapp /send: só equipe que fala com cliente ─────────────────────────────

async def test_whatsapp_send_barra_cliente_externo():
    # require_roles é hierárquico pelo MENOR nível da lista (secretaria=2): barra
    # cliente_externo (o buraco real: antes era qualquer autenticado), deixando a
    # equipe do escritório passar.
    from app.core.security import require_roles
    from app.routers.whatsapp import _PODE_ENVIAR
    checker = require_roles(_PODE_ENVIAR)
    with pytest.raises(HTTPException) as exc:
        await checker(_user(UserRole.cliente_externo))
    assert exc.value.status_code == 403
    # equipe (advogado, secretaria) passa
    assert (await checker(_user(UserRole.advogado))).role == UserRole.advogado
    assert (await checker(_user(UserRole.secretaria))).role == UserRole.secretaria


