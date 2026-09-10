"""Contratos de segurança da expansão da busca global (#717 / EJC 4.0)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.models.deadline import Deadline
from app.models.document import Document
from app.models.fee import Fee
from app.models.task import Task
from app.routers import search as search_router


def _user(role: str, uid: str = "u-adv"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def test_tarefa_e_prazo_so_usam_ownership_direto_quando_avulsos():
    user = _user("advogado")

    tarefa_sql = str(search_router._escopo_tarefas(select(Task), user))
    prazo_sql = str(search_router._escopo_prazos(select(Deadline), user))

    # Com caso, a carteira é soberana; atribuição direta não concede acesso.
    assert "tasks.case_id IN" in tarefa_sql
    assert "deadlines.case_id IN" in prazo_sql
    assert "cases.advogado_responsavel_id" in tarefa_sql
    assert "cases.advogado_auxiliar_id" in tarefa_sql
    assert "cases.advogado_responsavel_id" in prazo_sql
    assert "cases.advogado_auxiliar_id" in prazo_sql

    # Sem caso, responsabilidade/autoria direta continuam válidas.
    assert "tasks.case_id IS NULL" in tarefa_sql
    assert "tasks.responsavel_id" in tarefa_sql
    assert "tasks.criado_por" in tarefa_sql
    assert "deadlines.case_id IS NULL" in prazo_sql
    assert "deadlines.responsavel_id" in prazo_sql


def test_documento_busca_respeita_cofre_e_ownership():
    user = _user("advogado")
    sql = str(search_router._escopo_documentos(select(Document), user))

    assert "documents.confidencialidade" in sql
    assert "documents.uploaded_by" in sql
    assert "documents.client_id" in sql
    assert "documents.case_id" in sql


def test_financeiro_advogado_fica_restrito_a_casos_proprios():
    user = _user("advogado")
    sql = str(search_router._escopo_fees(select(Fee), user))

    assert "fees.case_id" in sql
    assert "cases.advogado_responsavel_id" in sql
    assert "cases.advogado_auxiliar_id" in sql


def test_financeiro_perfil_fiduciario_preserva_escopo_total():
    user = _user("financeiro")
    sql = str(search_router._escopo_fees(select(Fee), user))

    assert "fees.case_id IN" not in sql


def test_busca_global_nao_pesquisa_conteudo_ou_expoe_valores():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routers"
        / "search.py"
    ).read_text(encoding="utf-8")

    assert "Document.ocr_text" not in source
    assert "Task.descricao.ilike" not in source
    assert "Deadline.descricao.ilike" not in source
    assert '"valor": fee.valor' not in source
    assert '"percentual_exito"' not in source
    assert '"observacoes"' not in source


def test_deep_links_novos_usam_superficies_canonicas():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routers"
        / "search.py"
    ).read_text(encoding="utf-8")

    assert '"/atividades?tipo=tarefa"' in source
    assert '"/atividades?tipo=prazo"' in source
    assert '?tab=documentos' in source
    assert '?tab=financeiro' in source


def test_cliente_identificavel_usa_gate_canonico_de_carteira():
    user = _user("advogado")
    sql = str(search_router._escopo_clientes(select(search_router.Client), user))
    assert "clients.id IN" in sql
    assert "clients.responsavel_id" in sql
    assert "cases.advogado_responsavel_id" in sql
    assert "cases.advogado_auxiliar_id" in sql


def test_secretaria_preserva_visao_total_do_crm():
    user = _user("secretaria")
    sql = str(search_router._escopo_clientes(select(search_router.Client), user))
    assert "clients.id IN" not in sql
