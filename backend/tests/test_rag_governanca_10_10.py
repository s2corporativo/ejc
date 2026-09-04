"""Gates de regressão para a alimentação governada da IA jurídica."""
from __future__ import annotations

import inspect


def test_defaults_sao_estritos_e_modelos_suportados():
    from app.core.config import get_settings
    from app.services.embedding_service import validar_modelo_local
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    assert settings.RAG_EXIGIR_APROVADO is True
    assert settings.RAG_EXIGIR_VIGENCIA_VERIFICADA is True   # Issue #636
    assert settings.RAG_RERANK_ENABLED is False
    ok, detalhe = validar_modelo_local()
    assert ok, detalhe
    rerank = {m["model"] for m in TextCrossEncoder.list_supported_models()}
    assert settings.RAG_RERANK_MODEL in rerank


def test_migration_preserva_vetores_legados_para_rollback():
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
    assert "begin_nested" in inspect.getsource(reemb.reembedar)


def test_sumulas_problematicas_ficam_fora_do_rag():
    from app.services.sumulas_ingestion import SUMULAS_SEED

    por_chave = {(s["tribunal"], str(s.get("numero"))): s for s in SUMULAS_SEED}
    assert por_chave[("TST", "277")]["situacao"] == "superada"
    assert por_chave[("TST", "331")]["situacao"] == "revisao"


def test_citation_check_reutiliza_gate_central():
    from app.services import citation_check

    assert "_filtros_gate_rag" in inspect.getsource(citation_check._existe_sumula)
    assert "_filtros_gate_rag" in inspect.getsource(citation_check._fonte_artigo)
    assert "_fonte_artigo" in inspect.getsource(citation_check._existe_artigo)
    assert "_fonte_artigo" in inspect.getsource(citation_check._artigo_superado)


def test_trilha_rag_registra_ids_ordem_score_e_versao_sem_conteudo():
    from app.services.ai.core.audit_logger import _fontes_str

    trilha = _fontes_str(
        [
            {
                "chunk_id": "chunk-1",
                "doc_id": "doc-1",
                "versao": 3,
                "score": 0.91,
                "titulo": "Lei X",
                "categoria": "legislacao",
                "conteudo": "PII QUE NAO PODE IR PARA O LOG",
            }
        ]
    )
    assert "rank=1" in trilha
    assert "chunk=chunk-1" in trilha and "doc=doc-1" in trilha
    assert "versao=3" in trilha and "score=0.91" in trilha
    assert "PII QUE NAO PODE" not in trilha


def test_calculadora_alimentos_nao_inventa_percentual_do_stj():
    from pathlib import Path

    routers = Path(__file__).parents[1] / "app/routers"
    fonte = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(routers.glob("ramos*.py"))
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
    # O critério ficou MAIS estrito: além da revisão humana, a peça precisa
    # estar em status apto ao RAG — rascunho apenas revisado não vira
    # fundamentação. O que continua invariante: sem revisão humana, `pendente`.
    assert '"aprovado" if human_reviewed and status_apto_rag else "pendente"' in peca


# ── Revisão automatizada do PR (03/09/2026) ─────────────────────────────────
# `notas` chegava no corpo vindo da tela, mas o schema não a declarava: o
# Pydantic a descartava e o registro de auditoria de uma decisão jurídica ficava
# sem a única parte que explica o PORQUÊ. E a confiança vinha por um PATCH
# separado — falhar o segundo passo deixava o documento aprovado sem nível.
def test_revisao_exige_notas():
    import pytest as _pytest
    from pydantic import ValidationError

    from app.routers.rag_governance import RevisaoRequest

    with _pytest.raises(ValidationError):
        RevisaoRequest(aprovado=True)
    with _pytest.raises(ValidationError):
        RevisaoRequest(aprovado=True, notas="")

    r = RevisaoRequest(aprovado=True, notas="ementa conferida no TJMG em 01/09")
    assert r.confidence_level is None


def test_revisao_recusa_confianca_fora_do_vocabulario():
    import pytest as _pytest
    from pydantic import ValidationError

    from app.routers.rag_governance import RevisaoRequest

    with _pytest.raises(ValidationError):
        RevisaoRequest(aprovado=True, notas="ok", confidence_level="altissima")
    assert RevisaoRequest(
        aprovado=True, notas="ok", confidence_level="alta").confidence_level == "alta"


def test_decisao_grava_notas_e_confianca_no_mesmo_extra():
    from app.routers.rag_governance import _registrar_decisao_revisao

    extra = _registrar_decisao_revisao(
        {"origem": "manual"}, aprovado=True, user_id="u1",
        agora="2026-09-03T12:00:00+00:00",
        notas="ementa conferida na fonte oficial; vigente",
        confidence_level="alta",
    )
    assert extra["rag_status"] == "aprovado"
    assert extra["human_review_notes"] == "ementa conferida na fonte oficial; vigente"
    assert extra["confidence_level"] == "alta"
    # Mesmo contrato JSONB que o PATCH de curadoria escrevia.
    assert extra["curadoria"]["reviewed_by"] == "u1"
    assert extra["curadoria"]["reviewed_at"] == "2026-09-03T12:00:00+00:00"
    assert extra["origem"] == "manual"   # não destrói o que já existia


def test_sem_confianca_o_extra_nao_ganha_curadoria():
    from app.routers.rag_governance import _registrar_decisao_revisao

    extra = _registrar_decisao_revisao(
        None, aprovado=False, user_id="u1", notas="superado por súmula posterior")
    assert extra["rag_status"] == "recusado"
    assert extra["human_review_notes"] == "superado por súmula posterior"
    assert "confidence_level" not in extra
    assert "curadoria" not in extra


def test_notas_longas_sao_truncadas_sem_estourar_o_campo():
    from app.routers.rag_governance import _registrar_decisao_revisao

    extra = _registrar_decisao_revisao(
        None, aprovado=True, user_id="u1", notas="x" * 5000)
    assert len(extra["human_review_notes"]) == 2000


# ── Prévia do texto indexado (revisão automatizada do PR, 03/09/2026) ────────
# O conteúdo do documento vive em KnowledgeChunk.conteudo, não em `extra`: sem
# devolvê-lo, o revisor aprovava legislação/jurisprudência para a IA vendo só
# título e metadados.
def test_previa_curta_volta_inteira():
    from app.services.knowledge_governance import _PREVIA_MAX_CHARS, _recortar_previa

    assert _recortar_previa("Art. 42. Texto curto.") == "Art. 42. Texto curto."
    assert _recortar_previa("") == ""
    assert _recortar_previa(None) == ""
    assert len(_recortar_previa("x" * (_PREVIA_MAX_CHARS + 500))) <= _PREVIA_MAX_CHARS


def test_previa_corta_em_fronteira_de_paragrafo_quando_compensa():
    from app.services.knowledge_governance import _PREVIA_MAX_CHARS, _recortar_previa

    # Fronteira depois da metade do teto: o corte a respeita.
    corpo = "a" * (_PREVIA_MAX_CHARS - 100) + "\n\n" + "b" * 500
    assert _recortar_previa(corpo).endswith("a")
    assert "b" not in _recortar_previa(corpo)

    # Fronteira cedo demais: cortar ali jogaria fora metade da prévia útil.
    corpo2 = "a" * 10 + "\n\n" + "b" * (_PREVIA_MAX_CHARS * 2)
    assert len(_recortar_previa(corpo2)) == _PREVIA_MAX_CHARS
