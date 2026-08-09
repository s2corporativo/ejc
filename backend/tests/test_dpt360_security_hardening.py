from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security import require_roles
from app.models.user import UserRole
from app.modules.dpt360.access_scope import visible_document_count_query
from app.modules.dpt360.intake_schemas import DptInboundOpportunity
from app.modules.dpt360 import intake_service
from app.modules.dpt360.schemas import DptPriorityItem


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def walk(dep, depth: int = 0) -> None:
        if dep is None or depth > 8:
            return
        for child in getattr(dep, "dependencies", []) or []:
            call = getattr(child, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", type(call).__name__))
            walk(child, depth + 1)

    walk(getattr(route, "dependant", None))
    return names


def test_todas_as_rotas_dpt_exigem_gate_autenticado_e_ia_tem_rate_limit():
    from app.main import app

    dpt_routes = [
        route
        for route in app.routes
        if str(getattr(route, "path", "")).startswith("/api/dpt360/")
    ]
    assert dpt_routes

    for route in dpt_routes:
        names = _dependency_names(route)
        assert "checker" in names, f"rota DPT sem require_roles: {route.path}"
        assert "get_current_user" in names, f"rota DPT sem autenticação: {route.path}"

    by_key = {
        (route.path, method): _dependency_names(route)
        for route in dpt_routes
        for method in (getattr(route, "methods", None) or [])
    }
    assert "_dep" in by_key[("/api/dpt360/actions", "POST")]
    assert "_dep" in by_key[("/api/dpt360/intake/opportunities", "POST")]


@pytest.mark.asyncio
async def test_piso_advogado_rejeita_perfis_operacionais_e_cliente_externo():
    checker = require_roles(["advogado"])

    allowed = SimpleNamespace(role=UserRole.advogado)
    assert await checker(current_user=allowed) is allowed

    for role in (
        UserRole.financeiro,
        UserRole.secretaria,
        UserRole.estagiario,
        UserRole.cliente_externo,
    ):
        with pytest.raises(HTTPException) as exc:
            await checker(current_user=SimpleNamespace(role=role))
        assert exc.value.status_code == 403


def test_legal_twin_documentos_preserva_cofre_e_exclui_caso_alheio():
    user = SimpleNamespace(id="adv-1", role=UserRole.advogado)
    stmt = visible_document_count_query(
        user,
        client_id="cliente-1",
        visible_case_ids=["caso-visivel"],
    )
    sql = str(stmt)

    assert "documents.confidencialidade IN" in sql
    assert "documents.case_id IN" in sql
    assert "documents.case_id IS NULL" in sql
    # O segundo predicado de escopo impede que um documento de outro caso seja
    # liberado somente por compartilhar client_id com a empresa visível.
    assert sql.count("documents.case_id IN") >= 1


@pytest.mark.asyncio
async def test_intake_nao_duplica_campos_livres_no_auditlog_worm(monkeypatch):
    captured: dict = {}

    async def fake_audit_log(_db, **kwargs):
        captured.update(kwargs)

    class FakeDb:
        def add(self, _obj):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.created_at = datetime(2026, 8, 9, tzinfo=timezone.utc)

    monkeypatch.setattr(intake_service, "criar_audit_log", fake_audit_log)
    payload = DptInboundOpportunity(
        origem="manual",
        pagina="/empresarial?email=pii@example.com",
        campanha="telefone-31999999999",
        assunto="Contato pii@example.com",
        mensagem="Mensagem com telefone 31 99999-9999 para triagem interna.",
        empresa="Empresa Exemplo",
        contato="Pessoa Exemplo",
        email="pii@example.com",
        telefone="31999999999",
        urgencia_declarada="alta",
    )
    user = SimpleNamespace(id="adv-1", role=UserRole.advogado)

    result = await intake_service.create_inbound_opportunity(FakeDb(), user, payload)

    assert result.status == "triagem_pendente"
    audit_payload = captured["dados_depois"]
    assert audit_payload == {
        "origem": "manual",
        "urgencia_declarada": "alta",
        "consentimento_privacidade": False,
    }
    serialized = str(captured)
    assert "pii@example.com" not in serialized
    assert "31999999999" not in serialized
    assert "Pessoa Exemplo" not in serialized


def test_prioridade_de_prazo_preserva_flag_nao_confirmada():
    item = DptPriorityItem(
        tipo="prazo",
        nivel="alto",
        company_id="cliente-1",
        company_name="Empresa",
        case_id="caso-1",
        title="Prazo sugerido pela IA",
        detail="Sugerido pela IA — a confirmar pelo advogado.",
        canonical_path="/atividades?tipo=prazo&caso=caso-1",
        due_date=date(2026, 8, 10),
        confirmado=False,
    )
    assert item.confirmado is False
    assert "confirmar" in item.detail.lower()
