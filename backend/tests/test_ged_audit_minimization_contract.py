"""Contratos LGPD de minimização dos audits de upload/download documental.

A resposta HTTP pode identificar o arquivo para orientar o usuário, mas a trilha
imutável não deve replicar filename livre ou mensagens técnicas de exceção.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def _trecho(source: str, inicio: str, fim: str) -> str:
    start = source.index(inicio)
    end = source.index(fim, start)
    return source[start:end]


def test_raio_x_upload_preserva_feedback_http_sem_filename_no_worm():
    source = (ROOT / "raio_x.py").read_text(encoding="utf-8")
    bloco = _trecho(
        source,
        "async def analisar_documentos(",
        '@router.post("/{analise_id}/reanalisar")',
    )

    assert '"duplicados": duplicados' in bloco
    assert '"erros": erros' in bloco
    assert '"duplicados_count": len(duplicados)' in bloco
    assert '"erros_count": len(erros)' in bloco
    audit = bloco[: bloco.index("await db.commit()")]
    audit_payload = audit[audit.rindex("dados_depois={") :]
    assert '"duplicados": duplicados' not in audit_payload
    assert '"erros": erros' not in audit_payload


def test_raio_x_download_nao_replica_nome_original_no_audit():
    source = (ROOT / "raio_x.py").read_text(encoding="utf-8")
    bloco = _trecho(
        source,
        "async def download(",
        '@router.get("/{analise_id}/exportar")',
    )
    audit = bloco[bloco.index("await criar_audit_log(") : bloco.index("await db.commit()")]
    assert "doc.nome_original" not in audit


def test_sala_upload_preserva_feedback_http_sem_filename_no_worm():
    source = (ROOT / "legal_chat.py").read_text(encoding="utf-8")
    bloco = _trecho(
        source,
        "async def anexar_documentos(",
        '@router.get(\n    "/{session_id}/conversao/preview"',
    )

    assert '"duplicados": duplicados' in bloco
    assert '"erros": erros' in bloco
    assert '"duplicados_count": len(duplicados)' in bloco
    assert '"erros_count": len(erros)' in bloco
    audit = bloco[: bloco.index("await db.commit()")]
    audit_payload = audit[audit.rindex("dados_depois={") :]
    assert '"duplicados": duplicados' not in audit_payload
    assert '"erros": erros' not in audit_payload


def test_sala_nao_persiste_exception_bruta_em_resultado_analise():
    source = (ROOT / "legal_chat.py").read_text(encoding="utf-8")
    bloco = _trecho(
        source,
        "async def anexar_documentos(",
        '@router.get(\n    "/{session_id}/conversao/preview"',
    )

    assert "str(exc)" not in bloco
    assert '"erro_codigo": "extracao_indisponivel"' in bloco
