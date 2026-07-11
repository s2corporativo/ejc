"""Solicitação de documentos ao cliente (solicitacao_documento_service +
routers): status agregado (função pura), template determinístico do e-mail e
contrato dos routers montados no app (paths do frontend). Sem Postgres."""
from __future__ import annotations

from app.services.solicitacao_documento_service import (
    ASSINATURA_AUTOMATICA,
    MAX_ITENS,
    MIN_ITENS,
    montar_email_solicitacao,
    recalcular_status,
)


# ── recalcular_status (upload marca item → status agregado) ────────────────────

def test_status_pendente_sem_nenhum_envio():
    assert recalcular_status(["pendente", "pendente"]) == "pendente"


def test_status_parcial_com_envio_incompleto():
    assert recalcular_status(["enviado", "pendente"]) == "parcial"


def test_status_atendida_com_todos_enviados():
    assert recalcular_status(["enviado", "enviado"]) == "atendida"


def test_status_item_unico():
    assert recalcular_status(["pendente"]) == "pendente"
    assert recalcular_status(["enviado"]) == "atendida"


def test_status_lista_vazia_degrada_para_pendente():
    assert recalcular_status([]) == "pendente"


def test_fluxo_upload_recalcula_progressivamente():
    """Simula o fluxo do POST /portal/.../upload: cada upload marca UM item e
    o agregado transita pendente → parcial → atendida."""
    status = ["pendente", "pendente", "pendente"]
    assert recalcular_status(status) == "pendente"
    status[0] = "enviado"
    assert recalcular_status(status) == "parcial"
    status[1] = "enviado"
    assert recalcular_status(status) == "parcial"
    status[2] = "enviado"
    assert recalcular_status(status) == "atendida"


# ── Template do e-mail de solicitação ──────────────────────────────────────────

def test_email_solicitacao_lista_documentos_e_instrucao_portal():
    assunto, corpo = montar_email_solicitacao(
        "Maria Silva",
        [{"nome": "RG e CPF", "descricao": "frente e verso"},
         {"nome": "Comprovante de residência", "descricao": None}],
        mensagem="Precisamos até sexta-feira.",
    )
    assert assunto == "[De Paula Teixeira Advogados] Solicitação de documentos"
    assert "Maria Silva" in corpo
    assert "RG e CPF" in corpo and "frente e verso" in corpo
    assert "Comprovante de residência" in corpo
    assert "Precisamos até sexta-feira." in corpo
    assert "Portal do Cliente" in corpo
    assert ASSINATURA_AUTOMATICA in corpo
    assert "whatsapp" not in corpo.lower()


def test_email_solicitacao_sem_mensagem_omite_bloco():
    _, corpo = montar_email_solicitacao("Cliente", [{"nome": "Doc"}], None)
    assert "Doc" in corpo
    # Sem parágrafo vazio da mensagem livre.
    assert "<p></p>" not in corpo


def test_limites_do_contrato():
    assert MIN_ITENS == 1
    assert MAX_ITENS == 30


# ── Contrato: rotas montadas no app (paths chamados pelo frontend) ─────────────

def test_rotas_do_contrato_existem_no_app():
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/casos/{case_id}/solicitacoes-documentos" in paths
    assert "/api/portal/solicitacoes-documentos" in paths
    assert ("/api/portal/solicitacoes-documentos/itens/{item_id}/upload"
            in paths)

    # Middleware do Portal: o prefixo /api/portal/ segue liberado ao
    # cliente_externo (guarda central de auth_middleware).
    metodos = {
        (r.path, m)
        for r in app.routes if hasattr(r, "methods")
        for m in (r.methods or [])
    }
    assert ("/api/casos/{case_id}/solicitacoes-documentos", "POST") in metodos
    assert ("/api/casos/{case_id}/solicitacoes-documentos", "GET") in metodos
    assert ("/api/portal/solicitacoes-documentos", "GET") in metodos
    assert (
        "/api/portal/solicitacoes-documentos/itens/{item_id}/upload", "POST"
    ) in metodos
