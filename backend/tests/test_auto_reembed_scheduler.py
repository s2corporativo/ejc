"""Auto-reindex do RAG (auditoria IA 2026-07-17, O-2): o job do scheduler
reembeda chunks órfãos para auto-curar a troca de embedding (migration 096) sem
passo manual. Aqui validamos o GATING e o fail-safe (sem tocar no banco)."""
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
    monkeypatch.setattr(es, "disponivel", lambda: True)
    capturado = {}
    import scripts.reembedar_chunks_orfaos as reemb

    async def _spy(**kw):
        capturado.update(kw)

    monkeypatch.setattr(reemb, "reembedar", _spy)
    await sched._reembedar_rag_orfaos()
    assert capturado.get("batch_size") == 7


async def test_erro_no_reembed_nao_propaga(monkeypatch):
    monkeypatch.setattr(sched.settings, "RAG_AUTO_REEMBED_ENABLED", True)
    monkeypatch.setattr(es, "disponivel", lambda: True)
    import scripts.reembedar_chunks_orfaos as reemb

    async def _boom(**kw):
        raise RuntimeError("falha simulada de reembed")

    monkeypatch.setattr(reemb, "reembedar", _boom)
    # não deve levantar — job é fail-safe (warning + retenta na próxima)
    await sched._reembedar_rag_orfaos()
