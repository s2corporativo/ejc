"""C1 (análise E2E de IA 2026-09-03) — o seed nasce VETORIZADO.

`seeds.seed_all.vetorizar_orfaos_pos_seed` roda o reindexador idempotente de
chunks órfãos ao final do seed quando o provider de embeddings está
disponível. Testes com monkeypatch: nunca baixam modelo nem tocam banco.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seeds.seed_all as seed_all  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services import embedding_service  # noqa: E402
from scripts import reembedar_chunks_orfaos as reembed_mod  # noqa: E402


@pytest.fixture
def _fora_do_pytest(monkeypatch):
    """O guard de pytest é desligado para exercitar o caminho real."""
    monkeypatch.setattr(seed_all, "_em_pytest", lambda: False)


async def test_seed_reembeda_orfaos_quando_embeddings_disponiveis(monkeypatch, _fora_do_pytest):
    chamadas: list[dict] = []

    async def fake_reembedar(batch_size=20, dry_run=False):
        chamadas.append({"batch_size": batch_size, "dry_run": dry_run})
        return {"ok": 24, "erros": 0, "dry_run": 0, "disponivel": True}

    monkeypatch.setattr(get_settings(), "SEED_EMBED_ORFAOS", True)
    monkeypatch.setattr(get_settings(), "RAG_AUTO_REEMBED_BATCH", 7)
    monkeypatch.setattr(embedding_service, "disponivel", lambda: True)
    monkeypatch.setattr(reembed_mod, "reembedar", fake_reembedar)

    resumo = await seed_all.vetorizar_orfaos_pos_seed()

    assert resumo["executado"] is True
    assert resumo["ok"] == 24
    assert chamadas == [{"batch_size": 7, "dry_run": False}]


async def test_seed_nao_reembeda_sem_embeddings(monkeypatch, _fora_do_pytest):
    async def explode(*a, **k):
        raise AssertionError("reembedar não deve ser chamado sem embeddings")

    monkeypatch.setattr(get_settings(), "SEED_EMBED_ORFAOS", True)
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    monkeypatch.setattr(reembed_mod, "reembedar", explode)

    resumo = await seed_all.vetorizar_orfaos_pos_seed()
    assert resumo == {"executado": False, "motivo": "embeddings_indisponiveis"}


async def test_seed_respeita_flag_desligada(monkeypatch, _fora_do_pytest):
    async def explode(*a, **k):
        raise AssertionError("reembedar não deve ser chamado com a flag desligada")

    monkeypatch.setattr(get_settings(), "SEED_EMBED_ORFAOS", False)
    monkeypatch.setattr(embedding_service, "disponivel", lambda: True)
    monkeypatch.setattr(reembed_mod, "reembedar", explode)

    resumo = await seed_all.vetorizar_orfaos_pos_seed()
    assert resumo == {"executado": False, "motivo": "desligado"}


async def test_seed_em_pytest_nunca_baixa_modelo(monkeypatch):
    """Sem o fixture: PYTEST_CURRENT_TEST está definido → curto-circuito antes
    de consultar o provider (que poderia tentar baixar o modelo)."""
    def explode():
        raise AssertionError("disponivel() não deve ser consultado em pytest")

    monkeypatch.setattr(get_settings(), "SEED_EMBED_ORFAOS", True)
    monkeypatch.setattr(embedding_service, "disponivel", explode)

    resumo = await seed_all.vetorizar_orfaos_pos_seed()
    assert resumo == {"executado": False, "motivo": "pytest"}


async def test_seed_all_encadeia_reembed_ao_final():
    """A wiring em main() é best-effort (_rodar_seed_async) e vem DEPOIS da
    base jurídica — o reembed só faz sentido após o seed gravar os docs."""
    src = Path(seed_all.__file__).read_text(encoding="utf-8")
    i_base = src.index('_rodar_seed_async("base_juridica_real"')
    i_reembed = src.index('_rodar_seed_async("reembed_orfaos_pos_seed"')
    assert i_base < i_reembed


async def test_reembedar_devolve_contagens_quando_indisponivel(monkeypatch):
    monkeypatch.setattr(reembed_mod, "emb_disponivel", lambda: False)
    out = await reembed_mod.reembedar(batch_size=5)
    assert out == {"ok": 0, "erros": 0, "dry_run": 0, "disponivel": False}
