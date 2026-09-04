"""C3 (análise E2E de IA 2026-09-03) — métricas pelo MESMO filtro do gate.

`rag_coverage` e `knowledge_governance.health_snapshot` contam documentos com
o fragmento `ai_service.filtros_gate_rag()` — o que a recuperação exclui
(vigência não verificada, quarentena de súmula, corpus fictício, sem
rag_status aprovado) não entra no painel.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.core.config import get_settings
from app.models.rag import KnowledgeDoc
from app.services import ai_service, knowledge_governance as kg, rag_coverage


def test_fragmento_publico_e_alias_privado_sao_o_mesmo():
    assert ai_service._filtros_gate_rag is ai_service.filtros_gate_rag


def test_where_da_cobertura_usa_exatamente_o_fragmento_do_gate(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RAG_EXIGIR_VIGENCIA_VERIFICADA", True)
    monkeypatch.setattr(s, "RAG_EXIGIR_APROVADO", True)
    monkeypatch.setattr(s, "RAG_SUMULAS_QUARENTENA", True)
    where = rag_coverage._where(mg_jec_only=False)
    assert ai_service.filtros_gate_rag() in where
    # As quatro exclusões do gate estão presentes, literalmente.
    assert "legal_status_verificado_em" in where       # vigência verificada
    assert "= 'aprovado'" in where                     # rag_status aprovado
    assert "'ficticio'" in where                       # corpus fictício
    assert "'conferido'" in where                      # quarentena de súmulas
    assert "NOT IN ('revogada','revogado')" in where   # revogada nunca entra


def test_where_acompanha_a_flag_de_vigencia(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RAG_EXIGIR_VIGENCIA_VERIFICADA", False)
    assert "legal_status_verificado_em" not in rag_coverage._where(False)
    monkeypatch.setattr(s, "RAG_EXIGIR_VIGENCIA_VERIFICADA", True)
    assert "legal_status_verificado_em" in rag_coverage._where(False)


# ── health_snapshot: usable_docs = passa no gate SQL ─────────────────────────

class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Responde: select(KnowledgeDoc) → docs; select de métricas de chunk →
    tuplas; text() do gate → ids recuperáveis (simula o Postgres aplicando o
    fragmento — o ORM não avalia SQL cru)."""

    def __init__(self, docs, metrics, recuperaveis):
        self.docs = docs
        self.metrics = metrics
        self.recuperaveis = recuperaveis
        self.sql_gate: str | None = None

    async def execute(self, stmt, params=None):
        if isinstance(stmt, type(text(""))):
            self.sql_gate = str(stmt)
            return _Scalars([(i,) for i in self.recuperaveis])
        desc = stmt.column_descriptions
        if desc and desc[0].get("entity") is KnowledgeDoc and desc[0].get("name") == "KnowledgeDoc":
            return _Scalars(self.docs)
        return _Scalars(self.metrics)


def _doc(id_, **extra):
    return KnowledgeDoc(
        id=id_, titulo=f"Doc {id_}", categoria="legislacao_geral", vigente=True,
        status_indexacao="indexado", hash_conteudo=id_, extra=extra,
        created_at=datetime.now(timezone.utc), atualizado_em=datetime.now(timezone.utc),
        fonte="https://www.planalto.gov.br/x",
    )


async def test_usable_docs_conta_so_o_que_passa_no_gate(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "RAG_EXIGIR_VIGENCIA_VERIFICADA", True)
    monkeypatch.setattr(s, "RAG_EXIGIR_APROVADO", True)

    docs = [
        # aprovado + vigência verificada → passa no gate
        _doc("ok", rag_status="aprovado", legal_status="vigente",
             legal_status_origem="curadoria", legal_status_verificado_em="2026-09-01"),
        # aprovado SEM vigência verificada → o gate exclui → não conta
        _doc("sem-vigencia", rag_status="aprovado"),
        # fictício (Bíblia EJC) aprovado → o gate exclui → não conta
        _doc("ficticio", rag_status="aprovado", ficticio="true"),
    ]
    metrics = [(d.id, 3, 1200, 3) for d in docs]
    # O "Postgres" (simulado) devolve só o doc que satisfaz o fragmento.
    db = _FakeDB(docs, metrics, recuperaveis={"ok"})

    snap = await kg.health_snapshot(db)

    assert db.sql_gate is not None
    assert ai_service.filtros_gate_rag() in db.sql_gate
    resumo = snap["summary"]
    assert resumo["approved_docs"] == 3      # rag_status=aprovado nos três
    assert resumo["retrievable_docs"] == 1   # mas só UM passa no gate
    assert resumo["usable_docs"] == 1        # utilizável = recuperável + íntegro
    assert resumo["usable_percent"] == round(1 / 3 * 100, 1)
