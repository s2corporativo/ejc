"""Bloco 6 — Testes de PERMISSÃO por perfil (advogado/estagiário/financeiro...).

A auditoria funcional não exercitou perfis diferentes de Superadmin. Estes testes
travam o comportamento REAL do gate RBAC central (`require_roles`), que é
HIERÁRQUICO pelo MENOR nível da lista permitida: um perfil não listado ainda passa
se seu nível ≥ o menor nível permitido. Sem banco — exercita a dependency direto
(mesmo estilo de test_papel_gates_403.py).
"""
import pytest

from app.models.user import User, UserRole
from app.core.security import (
    require_roles,
    require_admin,
    has_permission,
    ROLE_LEVEL,
)


def _u(role: UserRole) -> User:
    return User(id="u1", role=role)


async def _passa(allowed, role: UserRole) -> bool:
    checker = require_roles(allowed)
    try:
        await checker(current_user=_u(role))
        return True
    except Exception as e:  # HTTPException(403)
        assert getattr(e, "status_code", None) == 403
        return False


# ── Gate financeiro: [superadmin, admin, socio, financeiro] (nível mínimo = 4) ──
FIN_GATE = ["superadmin", "admin", "socio", "financeiro"]


@pytest.mark.parametrize("role", [
    UserRole.superadmin, UserRole.admin, UserRole.socio,
    UserRole.advogado, UserRole.advogado_auxiliar, UserRole.financeiro,
])
async def test_fin_gate_passa_nivel_suficiente(role):
    # advogado/advogado_auxiliar NÃO estão na lista, mas passam por HIERARQUIA
    # (nível ≥ financeiro=4). Comportamento real e não-óbvio — travado aqui.
    assert await _passa(FIN_GATE, role) is True


@pytest.mark.parametrize("role", [
    UserRole.estagiario, UserRole.secretaria, UserRole.cliente_externo,
])
async def test_fin_gate_barra_nivel_insuficiente(role):
    assert await _passa(FIN_GATE, role) is False


# ── Gate sensível: [superadmin, admin, socio] (nível mínimo = 7) ──
# Auditoria, Lixeira, Conhecimento, Curadoria RAG usam este gate.
SOCIO_GATE = ["superadmin", "admin", "socio"]


@pytest.mark.parametrize("role", [
    UserRole.superadmin, UserRole.admin, UserRole.socio,
])
async def test_socio_gate_passa(role):
    assert await _passa(SOCIO_GATE, role) is True


@pytest.mark.parametrize("role", [
    UserRole.advogado, UserRole.advogado_auxiliar, UserRole.financeiro,
    UserRole.estagiario, UserRole.secretaria, UserRole.cliente_externo,
])
async def test_socio_gate_barra_abaixo_de_socio(role):
    # advogado (nível 6) < socio (7) → 403. Confirma que advogado NÃO vê Auditoria/Lixeira.
    assert await _passa(SOCIO_GATE, role) is False


# ── require_admin: exige admin (8) ou superior (dependency SÍNCRONA) ──
def test_require_admin_passa_admin_superadmin():
    assert require_admin(_u(UserRole.admin)).role == UserRole.admin
    assert require_admin(_u(UserRole.superadmin)).role == UserRole.superadmin


@pytest.mark.parametrize("role", [
    UserRole.socio, UserRole.advogado, UserRole.financeiro,
    UserRole.estagiario, UserRole.cliente_externo,
])
def test_require_admin_barra_abaixo_de_admin(role):
    with pytest.raises(Exception) as exc:
        require_admin(_u(role))
    assert exc.value.status_code == 403


# ── has_permission: matriz de permissões explícitas por perfil ──
def test_has_permission_matriz_por_perfil():
    # advogado: tem 'casos', NÃO tem 'honorarios'
    assert has_permission("advogado", "casos") is True
    assert has_permission("advogado", "honorarios") is False
    # financeiro: tem 'honorarios', NÃO tem 'casos'
    assert has_permission("financeiro", "honorarios") is True
    assert has_permission("financeiro", "casos") is False
    # estagiario: tem 'tarefas'/'documentos', NÃO tem 'honorarios'
    assert has_permission("estagiario", "tarefas") is True
    assert has_permission("estagiario", "honorarios") is False
    # superadmin: curinga
    assert has_permission("superadmin", "qualquer_coisa") is True
    # cliente_externo: escopo mínimo
    assert has_permission("cliente_externo", "meu_caso") is True
    assert has_permission("cliente_externo", "casos") is False


def test_hierarquia_de_niveis_monotonica_e_sem_duplicidade():
    # Regressão do bug v2 (chave 'socio' duplicada com ['*']): garante ordem estrita.
    ordem = ["cliente_externo", "secretaria", "estagiario", "financeiro",
             "advogado_auxiliar", "advogado", "socio", "admin", "superadmin"]
    niveis = [ROLE_LEVEL[r] for r in ordem]
    assert niveis == sorted(niveis)
    assert len(set(niveis)) == len(niveis)  # sem empates
