"""RBAC do vínculo de documentos existentes ao caso.

Os services devem falhar antes de qualquer consulta ao banco para perfis fora da
allowlist EQUIPE_JURIDICA. Isso impede que Portal do Cliente, financeiro ou
secretaria transformem conhecimento de IDs em mutação do GED/caso.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.document_case_link_service import (
    buscar_documentos_vinculaveis,
    vincular_documento_existente,
)


class _Role:
    def __init__(self, value: str):
        self.value = value


class _User:
    def __init__(self, role: str):
        self.id = f"user-{role}"
        self.role = _Role(role)


@pytest.mark.parametrize("role", ["cliente_externo", "financeiro", "secretaria"])
async def test_busca_candidatos_rejeita_perfil_fora_da_equipe_juridica(role: str):
    with pytest.raises(HTTPException) as exc:
        await buscar_documentos_vinculaveis(
            None,  # type: ignore[arg-type] — o gate deve falhar antes de tocar no DB
            _User(role),  # type: ignore[arg-type]
            "case-inacessivel",
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail)


@pytest.mark.parametrize("role", ["cliente_externo", "financeiro", "secretaria"])
async def test_vinculo_rejeita_perfil_fora_da_equipe_juridica(role: str):
    with pytest.raises(HTTPException) as exc:
        await vincular_documento_existente(
            None,  # type: ignore[arg-type] — o gate deve falhar antes de tocar no DB
            _User(role),  # type: ignore[arg-type]
            "case-inacessivel",
            "doc-inacessivel",
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail)
