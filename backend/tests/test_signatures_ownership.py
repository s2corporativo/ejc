"""Fix (allowlist /api/signatures p/ cliente_externo) — o portal só usa
POST /signatures/{id}/assinar, mas o middleware libera todo /api/signatures ao
cliente_externo. É SEGURO porque o próprio router de signatures aplica
ownership por client_id em toda leitura/escrita acessível ao portal. Estes
testes travam esse invariante (source-inspection, sem DB/rede)."""
from __future__ import annotations

import inspect

from app.routers import signatures as sig


def test_listar_filtra_por_client_id_do_cliente_externo():
    src = inspect.getsource(sig.listar)
    assert "cliente_externo" in src
    assert "SignatureRequest.client_id == cu.client_id" in src


def test_assinar_exige_cliente_externo_e_filtra_ownership():
    src = inspect.getsource(sig.assinar)
    assert "cliente_externo" in src
    # a solicitação é buscada já filtrada pelo client_id do próprio cliente
    assert "SignatureRequest.client_id == cu.client_id" in src


def test_criar_solicitacao_exige_staff_nao_cliente_externo():
    src = inspect.getsource(sig.criar_solicitacao)
    # criação restrita a staff via require_roles — cliente_externo não consta
    # do CONJUNTO DE ROLES autorizados (a menção no corpo é só p/ notificar o
    # portal). Isola a linha do require_roles para checar o allowlist de roles.
    linha_roles = next(l for l in src.splitlines() if "require_roles" in l)
    assert "advogado" in linha_roles and "socio" in linha_roles
    assert "cliente_externo" not in linha_roles
