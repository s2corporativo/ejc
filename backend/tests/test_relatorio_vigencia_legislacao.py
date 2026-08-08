"""scripts/relatorio_vigencia_legislacao.py — relatório de triagem de vigência.

Achado da auditoria: 1.479 documentos de legislação com
`legal_status_unverified`, e nenhum bloqueio para citar norma não vigente
como se fosse atual. Este script entrega a metade segura (relatório
somente-leitura); a metade que exige tocar o gate anti-alucinação
(citation_gate.py) ficou fora desta sessão por depender de Postgres real
para validar sem risco de enfraquecer o gate (ver docstring do script).

Sem banco: `_active_docs`/`_chunk_metrics` são monkeypatchados — o teste cobre
só a lógica de classificação/ordenação de `_levantar`, que já é exercitada
(via `inferir_situacao_juridica`) por test_knowledge_governance.py.
"""
from __future__ import annotations

from datetime import datetime, timezone


from app.models.rag import KnowledgeDoc
from scripts import relatorio_vigencia_legislacao as script


def _doc(**kwargs) -> KnowledgeDoc:
    defaults = {
        "id": "doc-1",
        "titulo": "Lei de teste",
        "categoria": "legislacao",
        "fonte": "https://www.planalto.gov.br/ccivil_03/leis/teste.htm",
        "extra": {"rag_status": "aprovado"},
        "vigente": True,
        "versao": 1,
        "status_indexacao": "indexado",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return KnowledgeDoc(**defaults)


class _FakeDB:
    """Nunca é tocado diretamente — só repassado aos monkeypatches."""


async def _levantar_com(monkeypatch, docs: list[KnowledgeDoc], metrics: dict) -> dict:
    async def fake_active_docs(db, *, include_history=False):
        return docs

    async def fake_chunk_metrics(db):
        return metrics

    monkeypatch.setattr(script, "_active_docs", fake_active_docs)
    monkeypatch.setattr(script, "_chunk_metrics", fake_chunk_metrics)
    return await script._levantar(_FakeDB())


async def test_documento_sem_legal_status_entra_como_nao_verificado(monkeypatch):
    doc = _doc(id="lei-1", extra={"rag_status": "aprovado"})  # sem legal_status
    relatorio = await _levantar_com(monkeypatch, [doc], {})

    assert relatorio["vigencia_nao_verificada"]["total"] == 1
    assert relatorio["vigencia_nao_verificada"]["documentos"][0]["id"] == "lei-1"
    assert relatorio["contradicao_vigente_mas_status_nao_atual"]["total"] == 0


async def test_documento_vigente_true_com_status_revogada_e_contradicao(monkeypatch):
    """O par mais perigoso: versão atual no EJC, mas a governança já sabe que
    está revogada — hoje nada impede que a IA cite isto como direito em vigor."""
    doc = _doc(
        id="lei-2",
        vigente=True,
        extra={"rag_status": "aprovado", "legal_status": "revogada"},
    )
    relatorio = await _levantar_com(monkeypatch, [doc], {})

    ct = relatorio["contradicao_vigente_mas_status_nao_atual"]
    assert ct["total"] == 1
    assert ct["documentos"][0]["id"] == "lei-2"
    assert ct["documentos"][0]["legal_status"] == "revogada"
    assert relatorio["vigencia_nao_verificada"]["total"] == 0


async def test_documento_vigente_explicito_nao_aparece_em_nenhuma_lista(monkeypatch):
    doc = _doc(extra={"rag_status": "aprovado", "legal_status": "vigente"})
    relatorio = await _levantar_com(monkeypatch, [doc], {})

    assert relatorio["vigencia_nao_verificada"]["total"] == 0
    assert relatorio["contradicao_vigente_mas_status_nao_atual"]["total"] == 0
    assert relatorio["total_docs_ativos"] == 1


async def test_documento_categoria_nao_legislativa_sem_status_nao_alarma(monkeypatch):
    """Só legislação sem legal_status vira 'não verificada' por padrão
    (mesma regra de knowledge_governance.inferir_situacao_juridica) — doutrina
    sem o campo não é candidata a bloqueio de vigência."""
    doc = _doc(categoria="doutrina", extra={"rag_status": "aprovado"})
    relatorio = await _levantar_com(monkeypatch, [doc], {})

    assert relatorio["vigencia_nao_verificada"]["total"] == 0


async def test_ordenacao_prioriza_maior_superficie_de_citacao(monkeypatch):
    pouco_citado = _doc(id="lei-baixo", titulo="Lei pouco vetorizada")
    muito_citado = _doc(id="lei-alto", titulo="Lei muito vetorizada")
    metrics = {
        "lei-baixo": {"chunks": 2, "embedded": 1},
        "lei-alto": {"chunks": 50, "embedded": 50},
    }
    relatorio = await _levantar_com(monkeypatch, [pouco_citado, muito_citado], metrics)

    docs = relatorio["vigencia_nao_verificada"]["documentos"]
    assert [d["id"] for d in docs] == ["lei-alto", "lei-baixo"]


async def test_relatorio_nunca_escreve_no_banco(monkeypatch):
    """O relatório é somente-leitura: garante que _levantar não chama
    métodos de mutação (add/commit/execute de UPDATE) — só leitura via
    _active_docs/_chunk_metrics monkeypatchados."""
    class _DBQueTravaEmMutacao:
        def __getattr__(self, nome):
            if nome in {"add", "commit", "delete"}:
                raise AssertionError(f"relatório de vigência não pode chamar db.{nome}()")
            raise AttributeError(nome)

    async def fake_active_docs(db, *, include_history=False):
        return []

    async def fake_chunk_metrics(db):
        return {}

    monkeypatch.setattr(script, "_active_docs", fake_active_docs)
    monkeypatch.setattr(script, "_chunk_metrics", fake_chunk_metrics)
    relatorio = await script._levantar(_DBQueTravaEmMutacao())
    assert relatorio["total_docs_ativos"] == 0
