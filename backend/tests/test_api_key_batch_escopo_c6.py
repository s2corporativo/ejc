"""C6 (análise E2E de IA 2026-09-03) — rag_public cross-tenant.

`POST /rag/knowledge-base/batch`:
  • chave IRRESTRITA: item com client_id/case_id → 422 claro, nada gravado;
  • chave restrita: client_id igual ao da chave → aceito; diferente → 422;
    case_id do próprio cliente → aceito (doc nasce com case_id); de outro
    cliente/inexistente → 422.
Reusa o fake de AsyncSession de tests/test_api_key_batch.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.api_key import ApiKey
from app.models.case import Case, CaseArea
from app.models.rag import KnowledgeDoc
from tests.test_api_key_batch import BATCH, _item, _nova_chave, ctx  # noqa: F401


def _post(ctx, chave, itens):
    return ctx["client"].post(BATCH, json={"itens": itens}, headers={"X-API-Key": chave})


def _docs(ctx, chave_origem):
    return [d for d in ctx["db"].store[KnowledgeDoc] if d.chave_origem == chave_origem]


def _caso(id_, client_id):
    return Case(id=id_, titulo="Caso", area=CaseArea.civil, client_id=client_id,
                created_at=datetime.now(timezone.utc))


# ── chave irrestrita ──────────────────────────────────────────────────────────

def test_chave_irrestrita_recusa_client_id_no_payload(ctx):
    r = _post(ctx, ctx["chave"], [_item("k:1"), _item("k:2", client_id="cli-x")])
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "item 1" in detail and "irrestrita" in detail
    # Lote inteiro recusado: nem o item válido foi gravado.
    assert not _docs(ctx, "k:1") and not _docs(ctx, "k:2")


def test_chave_irrestrita_recusa_case_id_no_payload(ctx):
    r = _post(ctx, ctx["chave"], [_item("k:3", case_id="caso-x")])
    assert r.status_code == 422
    assert "irrestrita" in r.json()["detail"]
    assert not _docs(ctx, "k:3")


def test_chave_irrestrita_segue_aceitando_item_publico(ctx):
    r = _post(ctx, ctx["chave"], [_item("k:4")])
    assert r.status_code == 201
    assert _docs(ctx, "k:4")[0].client_id is None


# ── chave restrita a cliente ──────────────────────────────────────────────────

def test_chave_restrita_aceita_client_id_igual(ctx):
    chave, ak = _nova_chave(client_id="cli-1")
    ctx["db"].store[ApiKey].append(ak)
    r = _post(ctx, chave, [_item("k:5", client_id="cli-1")])
    assert r.status_code == 201
    assert _docs(ctx, "k:5")[0].client_id == "cli-1"


def test_chave_restrita_recusa_client_id_diferente(ctx):
    chave, ak = _nova_chave(client_id="cli-1")
    ctx["db"].store[ApiKey].append(ak)
    r = _post(ctx, chave, [_item("k:6", client_id="cli-2")])
    assert r.status_code == 422
    assert "difere" in r.json()["detail"]
    assert not _docs(ctx, "k:6")


def test_chave_restrita_aceita_case_id_do_proprio_cliente(ctx):
    chave, ak = _nova_chave(client_id="cli-1")
    ctx["db"].store[ApiKey].append(ak)
    ctx["db"].store[Case] = [_caso("caso-1", "cli-1")]
    r = _post(ctx, chave, [_item("k:7", case_id="caso-1")])
    assert r.status_code == 201, r.json()
    doc = _docs(ctx, "k:7")[0]
    assert doc.client_id == "cli-1" and doc.case_id == "caso-1"


def test_chave_restrita_recusa_case_id_inexistente_ou_de_outro_cliente(ctx):
    chave, ak = _nova_chave(client_id="cli-1")
    ctx["db"].store[ApiKey].append(ak)
    ctx["db"].store[Case] = []   # o fake não devolve caso → não pertence/não existe
    r = _post(ctx, chave, [_item("k:8", case_id="caso-de-outro")])
    assert r.status_code == 422
    assert "case_id" in r.json()["detail"]
    assert not _docs(ctx, "k:8")


def test_mensagem_nao_ecoa_ids_do_payload(ctx):
    r = _post(ctx, ctx["chave"], [_item("k:9", client_id="segredo-cliente-999")])
    assert r.status_code == 422
    assert "segredo-cliente-999" not in r.json()["detail"]
