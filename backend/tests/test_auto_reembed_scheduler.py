"""Auto-reindex do RAG (auditoria IA 2026-07-17, O-2): o job do scheduler
reembeda chunks órfãos para auto-curar a troca de embedding (migration 096) sem
passo manual. Aqui validamos o GATING e o fail-safe (sem tocar no banco)."""
from types import SimpleNamespace

import app.services.scheduler as sched
import app.services.embedding_service as es


async def test_desligado_por_flag_nao_reembeda(monkeypatch):
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_ENABLED", False)
    chamado = {"n": 0}
    import scripts.reembedar_chunks_orfaos as reemb

    async def _spy(**kw):
        chamado["n"] += 1

    monkeypatch.setattr(reemb, "reembedar", _spy)
    await sched._reembedar_rag_orfaos()
    assert chamado["n"] == 0


async def test_pula_quando_embeddings_indisponiveis(monkeypatch):
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_ENABLED", True)
    monkeypatch.setattr(es, "disponivel", lambda: False)
    chamado = {"n": 0}
    import scripts.reembedar_chunks_orfaos as reemb

    async def _spy(**kw):
        chamado["n"] += 1

    monkeypatch.setattr(reemb, "reembedar", _spy)
    await sched._reembedar_rag_orfaos()
    assert chamado["n"] == 0


async def test_reembeda_com_batch_quando_disponivel(monkeypatch):
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_ENABLED", True)
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_BATCH", 7)
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_MAX_DOCS_PER_RUN", 11)
    monkeypatch.setattr(es, "disponivel", lambda: True)
    capturado = {}
    import scripts.reembedar_chunks_orfaos as reemb

    async def _spy(**kw):
        capturado.update(kw)

    monkeypatch.setattr(reemb, "reembedar", _spy)
    await sched._reembedar_rag_orfaos()
    assert capturado.get("batch_size") == 7
    assert capturado.get("max_docs") == 11


async def test_erro_no_reembed_nao_propaga(monkeypatch):
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_ENABLED", True)
    monkeypatch.setattr(es, "disponivel", lambda: True)
    import scripts.reembedar_chunks_orfaos as reemb

    async def _boom(**kw):
        raise RuntimeError("falha simulada de reembed")

    monkeypatch.setattr(reemb, "reembedar", _boom)
    # não deve levantar — job é fail-safe (warning + retenta na próxima)
    await sched._reembedar_rag_orfaos()



def test_sql_reembed_prioriza_nao_tentados_antes_de_falhas():
    import scripts.reembedar_chunks_orfaos as reemb

    sql = str(reemb._SQL_DOCS_COM_ORFAO)

    assert "CASE WHEN kd.status_indexacao = 'erro' THEN 1 ELSE 0 END AS bucket" in sql
    assert "ORDER BY bucket, kd.id" in sql
    assert ":after_bucket" in sql


async def test_falha_de_embedding_move_documento_para_bucket_de_retentativa(monkeypatch):
    import scripts.reembedar_chunks_orfaos as reemb

    class _Rows:
        def all(self):
            return [SimpleNamespace(id="chunk-1", conteudo="conteúdo para teste")]

    class _DB:
        def __init__(self):
            self.execucoes = []

        async def execute(self, stmt, params=None):
            sql = str(stmt)
            self.execucoes.append((sql, dict(params or {})))
            return _Rows()

    async def _sem_vetores(textos):
        return None

    monkeypatch.setattr(reemb, "gerar_embeddings", _sem_vetores)
    db = _DB()

    resultado = await reemb._reembedar_doc(db, "doc-falha", False)

    assert resultado == "erro"
    assert any(
        "UPDATE knowledge_docs SET status_indexacao='erro'" in sql
        for sql, _ in db.execucoes
    )
