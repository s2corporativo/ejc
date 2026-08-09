"""Regressões rápidas do controle de publicação externa no Portal (#861).

Os testes DB-level em test_portal_idor_matrix_dblevel.py cobrem o isolamento por
linha. Aqui travamos a defesa em profundidade que precisa funcionar ANTES de
qualquer query: cliente_externo nunca administra publicação, apesar de
AuthMiddleware permitir a subárvore /api/portal/*.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


class _DBNoop:
    async def execute(self, *args, **kwargs):  # pragma: no cover - não deve rodar
        raise AssertionError("query executada antes do gate de papel")


@pytest.fixture
def cliente_portal() -> User:
    return User(
        id="portal-user",
        role=UserRole.cliente_externo,
        client_id="cliente-1",
        email="portal@example.invalid",
        full_name="Cliente Portal",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_cliente_nao_lista_documentos_administrativos(cliente_portal):
    from app.routers.portal_documentos import listar_documentos_admin

    with pytest.raises(HTTPException) as exc:
        await listar_documentos_admin(
            page=1,
            page_size=20,
            db=_DBNoop(),
            cu=cliente_portal,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "nome_funcao",
    ["publicar_documento_portal", "revogar_documento_portal"],
)
async def test_cliente_nao_publica_nem_revoga_documento(
    cliente_portal, nome_funcao: str
):
    from app.routers import portal_documentos

    funcao = getattr(portal_documentos, nome_funcao)
    with pytest.raises(HTTPException) as exc:
        await funcao(document_id="doc-alheio", db=_DBNoop(), cu=cliente_portal)
    assert exc.value.status_code == 403


def test_leitura_portal_exige_publicacao_e_confidencialidade_normal():
    """Guarda estrutural adicional ao teste DB-level positivo/negativo."""
    from app.routers.portal import documentos

    source = inspect.getsource(documentos)
    assert "Document.publicado_portal.is_(True)" in source
    assert "Document.confidencialidade == DocConfidencialidade.normal" in source
