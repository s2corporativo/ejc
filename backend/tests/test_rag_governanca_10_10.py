"""Gates de regressão para a alimentação governada da IA jurídica."""
from __future__ import annotations

import inspect


def test_defaults_sao_estritos_e_modelos_suportados():
    from app.core.config import get_settings
    from app.services.embedding_service import validar_modelo_local
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    assert settings.RAG_EXIGIR_APROVADO is True
    assert settings.RAG_RERANK_ENABLED is False
    ok, detalhe = validar_modelo_local()
    assert ok, detalhe
    rerank = {m["model"] for m in TextCrossEncoder.list_supported_models()}
    assert settings.RAG_RERANK_MODEL in rerank


def test_migration_preserva_vetores_legados_para_rollback():
    # Teste de contrato: migration publicada não pode voltar a DROP destrutivo.
    from pathlib import Path

    path = Path(__file__).parents[1] / "alembic/versions/096_rag_embedding_1024.py"
    fonte = path.read_text(encoding="utf-8")
    assert "RENAME COLUMN embedding TO embedding_legacy_768" in fonte
    assert "RENAME COLUMN embedding_legacy_768 TO embedding" in fonte


def test_reindex_usa_paginacao_estavel_sem_offset():
    import scripts.reembedar_chunks_orfaos as reemb

    sql = str(reemb._SQL_DOCS_COM_ORFAO).upper()
    assert "OFFSET" not in sql
    assert "KD.ID > :AFTER" in sql


def test_sumulas_problematicas_ficam_fora_do_rag():
    from app.services.sumulas_ingestion import SUMULAS_SEED

    por_chave = {(s["tribunal"], str(s.get("numero"))): s for s in SUMULAS_SEED}
    assert por_chave[("TST", "277")]["situacao"] == "superada"
    assert por_chave[("TST", "331")]["situacao"] == "revisao"


def test_citation_check_reutiliza_gate_central():
    from app.services import citation_check

    assert "_filtros_gate_rag" in inspect.getsource(citation_check._existe_sumula)
    assert "_filtros_gate_rag" in inspect.getsource(citation_check._existe_artigo)


def test_trilha_rag_registra_ids_ordem_score_e_versao_sem_conteudo():
    from app.services.ai.core.audit_logger import _fontes_str

    trilha = _fontes_str([{
        "chunk_id": "chunk-1", "doc_id": "doc-1", "versao": 3,
        "score": 0.91, "titulo": "Lei X", "categoria": "legislacao",
        "conteudo": "PII QUE NAO PODE IR PARA O LOG",
    }])
    assert "rank=1" in trilha
    assert "chunk=chunk-1" in trilha and "doc=doc-1" in trilha
    assert "versao=3" in trilha and "score=0.91" in trilha
    assert "PII QUE NAO PODE" not in trilha


def test_calculadora_alimentos_nao_inventa_percentual_do_stj():
    from pathlib import Path

    fonte = (Path(__file__).parents[1] / "app/routers/ramos.py").read_text(
        encoding="utf-8"
    )
    assert "Padrão STJ: 1/3" not in fonte
    assert "Súmula 277/STJ trata apenas" in fonte


def test_fluxos_internos_e_externos_declaram_estado_de_curadoria():
    from pathlib import Path

    app = Path(__file__).parents[1] / "app"
    encerramento = (app / "routers/cases.py").read_text(encoding="utf-8")
    drive = (app / "services/google_drive_service.py").read_text(encoding="utf-8")
    peca = (app / "services/case_intel.py").read_text(encoding="utf-8")
    assert '"rag_status": "aprovado"' in encerramento
    assert 'extra["rag_status"] = "pendente"' in drive
    assert '"aprovado" if meta["human_reviewed"] else "pendente"' in peca
