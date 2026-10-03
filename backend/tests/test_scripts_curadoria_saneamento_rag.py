"""Scripts operacionais do pente fino do RAG (03/10/2026).

* `curadoria_vigencia_lote` (C-1): aplica em lote decisões de vigência já
  tomadas por curador, com fonte oficial HTTPS, data, notas e trilha.
* `saneamento_destilacao_ia_legado` (A-2): devolve à curadoria o estoque
  global e aprovado criado pela rota antiga `/rag/ingerir-ai-log`.

Unitários sempre; ponta a ponta só com RUN_DB_TESTS=1 (Postgres + pgvector).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from scripts import curadoria_vigencia_lote as cvl
from scripts import saneamento_destilacao_ia_legado as sdl

HOJE = date(2026, 10, 3)
_OK = {"doc_id": "d1", "legal_status": "vigente",
       "link_oficial": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
       "conferido_em": "2026-10-01", "notas": "Conferido texto compilado"}


# ── curadoria em lote: validação ─────────────────────────────────────────────

def test_linha_valida_e_normalizada():
    linha, erro = cvl.validar_linha(2, {**_OK, "legal_status": " Vigente "}, HOJE)
    assert erro is None and linha.legal_status == "vigente"
    assert linha.conferido_em == "2026-10-01"


@pytest.mark.parametrize("campo,valor,trecho", [
    ("legal_status", "vigencia_nao_verificada", "legal_status inválido"),
    ("link_oficial", "http://www.planalto.gov.br/x", "HTTPS"),
    ("link_oficial", "https://www.jusbrasil.com.br/x", "domínio oficial"),
    ("conferido_em", "03/10/2026", "data ISO"),
    ("conferido_em", "2026-12-31", "futuro"),
    ("notas", "ok", "notas obrigatórias"),
    ("doc_id", "", "doc_id vazio"),
])
def test_linha_invalida_e_recusada(campo, valor, trecho):
    linha, erro = cvl.validar_linha(2, {**_OK, campo: valor}, HOJE)
    assert linha is None and trecho in erro


def test_planilha_com_erro_ou_repetida_nao_passa(tmp_path: Path):
    arq = tmp_path / "lote.csv"
    arq.write_text(
        "doc_id,legal_status,link_oficial,conferido_em,notas\n"
        f"d1,vigente,{_OK['link_oficial']},2026-10-01,Conferido texto\n"
        f"d1,vigente,{_OK['link_oficial']},2026-10-01,Conferido texto\n"
        "d2,vigente,https://site.com/x,2026-10-01,Conferido texto\n",
        encoding="utf-8",
    )
    validas, erros, digest = cvl.ler_planilha(arq, HOJE)
    assert [l.doc_id for l in validas] == ["d1"]
    assert any("repetido" in e for e in erros) and any("domínio oficial" in e for e in erros)
    assert len(digest) == 64


def test_planilha_sem_colunas_obrigatorias(tmp_path: Path):
    arq = tmp_path / "lote.csv"
    arq.write_text("doc_id,legal_status\nd1,vigente\n", encoding="utf-8")
    validas, erros, _ = cvl.ler_planilha(arq, HOJE)
    assert not validas and "cabeçalho" in erros[0]


def test_extra_com_curadoria_atende_ao_gate_de_vigencia():
    linha, _ = cvl.validar_linha(7, _OK, HOJE)
    extra = cvl.extra_com_curadoria(
        {"legal_status": "vigencia_nao_verificada",
         "legal_status_inferido_em": "2026-09-01", "rag_status": "aprovado"},
        linha, "u-socio", "abc123",
    )
    assert extra["legal_status"] == "vigente"
    assert extra["legal_status_origem"] == "curadoria:u-socio"
    assert extra["legal_status_verificado_em"] == "2026-10-01"
    assert "legal_status_inferido_em" not in extra
    assert extra["rag_status"] == "aprovado"          # aprovação não é tocada
    assert extra["legal_status_lote"]["linha"] == 7


# ── saneamento A-2: transformação ────────────────────────────────────────────

def test_log_id_da_chave():
    assert sdl.log_id_da_chave("ai_log_abc") == "abc"
    assert sdl.log_id_da_chave("caso:1") is None
    assert sdl.log_id_da_chave("ai_log_") is None


def test_extra_saneado_volta_a_fila_e_guarda_o_antes():
    extra = sdl.extra_saneado(
        {"rag_status": "aprovado", "human_reviewed": True, "aprovado_por": "u1",
         "origem": "ai_log_hitl"},
        escopo="caso:c1", responsavel="u-adm",
    )
    assert extra["rag_status"] == "pendente" and extra["requires_human_review"] is True
    assert "human_reviewed" not in extra
    assert extra["saneamento_a2"]["antes"]["rag_status"] == "aprovado"
    assert extra["origem"] == "ai_log_hitl"


async def test_saneamento_aplicar_exige_responsavel():
    assert await sdl.executar(aplicar=True, responsavel=None) == 2


# ── ponta a ponta (Postgres real) ────────────────────────────────────────────

_db = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture
async def _engine(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import AsyncSessionLocal, engine
    async with AsyncSessionLocal() as db:
        # Não deixa resíduo para outros testes db-level.
        await db.execute(text(
            "DELETE FROM knowledge_docs WHERE chave_origem LIKE 'planalto:zzcvl%' "
            "OR (chave_origem LIKE 'ai\\_log\\_%' AND extra ? 'saneamento_a2')"))
        await db.commit()
    await engine.dispose()


async def _doc(db, *, categoria, chave, conteudo, extra):
    doc_id = str(uuid.uuid4())
    await db.execute(text(
        "INSERT INTO knowledge_docs (id, titulo, categoria, chave_origem, vigente, "
        "status_indexacao, extra) VALUES (:id,:t,:c,:k,true,'indexado',CAST(:e AS jsonb))"
    ), {"id": doc_id, "t": f"T {chave}", "c": categoria, "k": chave, "e": json.dumps(extra)})
    await db.execute(text(
        "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) VALUES (:i,:d,0,:c)"
    ), {"i": str(uuid.uuid4()), "d": doc_id, "c": conteudo})
    return doc_id


@_db
async def test_curadoria_em_lote_torna_a_legislacao_recuperavel(_engine, monkeypatch, tmp_path):
    from app.core.database import AsyncSessionLocal
    from app.models.user import User, UserRole
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzcvl{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        socio = User(id=uuid.uuid4().hex, full_name="Curador", hashed_password="x",
                     email=f"cvl-{uuid.uuid4().hex[:8]}@ejc.local", role=UserRole.socio)
        db.add(socio)
        doc_id = await _doc(db, categoria="legislacao", chave=f"planalto:{termo}",
                            conteudo=f"Art. 1º norma {termo}",
                            extra={"rag_status": "aprovado",
                                   "legal_status": "vigencia_nao_verificada",
                                   "legal_status_inferido_em": "2026-09-01"})
        await db.commit()
        assert await buscar_contexto_rag(db, termo, limite=5) == []   # gate exclui

    arq = tmp_path / "lote.csv"
    arq.write_text("doc_id,legal_status,link_oficial,conferido_em,notas\n"
                   f"{doc_id},vigente,{_OK['link_oficial']},2026-10-01,Conferido no Planalto\n",
                   encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda *_: cvl.PALAVRA_CONFIRMACAO)
    assert await cvl.executar(arq, socio.id, aplicar=True) == 0

    async with AsyncSessionLocal() as db:
        res = await buscar_contexto_rag(db, termo, limite=5)
        assert [r["doc_id"] for r in res] == [doc_id]
        trilha = (await db.execute(text(
            "SELECT count(*) FROM audit_logs WHERE registro_id = :d "
            "AND acao = 'CURADORIA_VIGENCIA_LOTE'"), {"d": doc_id})).scalar()
        assert trilha == 1


@_db
async def test_curadoria_em_lote_recusa_curador_sem_papel(_engine, tmp_path):
    from app.core.database import AsyncSessionLocal
    from app.models.user import User, UserRole

    async with AsyncSessionLocal() as db:
        estagiario = User(id=uuid.uuid4().hex, full_name="Est", hashed_password="x",
                          email=f"cvl-{uuid.uuid4().hex[:8]}@ejc.local", role=UserRole.estagiario)
        db.add(estagiario)
        await db.commit()
    arq = tmp_path / "lote.csv"
    arq.write_text("doc_id,legal_status,link_oficial,conferido_em,notas\n"
                   f"x,vigente,{_OK['link_oficial']},2026-10-01,Conferido no Planalto\n",
                   encoding="utf-8")
    assert await cvl.executar(arq, estagiario.id, aplicar=False) == 1


@_db
async def test_saneamento_tira_o_legado_global_da_recuperacao(_engine, monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzsdl{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        doc_id = await _doc(db, categoria="conhecimento_ia",
                            chave=f"ai_log_{uuid.uuid4()}",
                            conteudo=f"Output de IA sobre o caso {termo}",
                            extra={"rag_status": "aprovado", "origem": "ai_log_hitl"})
        await db.commit()
        assert [r["doc_id"] for r in await buscar_contexto_rag(db, termo, limite=5)] == [doc_id]

    from app.models.user import User, UserRole
    async with AsyncSessionLocal() as db:
        adm = User(id=uuid.uuid4().hex, full_name="Adm", hashed_password="x",
                   email=f"sdl-{uuid.uuid4().hex[:8]}@ejc.local", role=UserRole.admin)
        db.add(adm)
        await db.commit()

    monkeypatch.setattr("builtins.input", lambda *_: sdl.PALAVRA_CONFIRMACAO)
    assert await sdl.executar(aplicar=True, responsavel="inexistente") == 2
    assert await sdl.executar(aplicar=True, responsavel=adm.id) == 0

    async with AsyncSessionLocal() as db:
        assert await buscar_contexto_rag(db, termo, limite=5) == []
        extra = (await db.execute(text("SELECT extra FROM knowledge_docs WHERE id = :d"),
                                  {"d": doc_id})).scalar()
        assert extra["rag_status"] == "pendente"
        assert extra["saneamento_a2"]["antes"]["rag_status"] == "aprovado"
