"""Contratos estruturais da Parte 10 — inteligência, minuta e HITL enxuto.

Estes testes são deliberadamente independentes de banco/provedor: travam a
arquitetura e a linguagem normativa que não podem regredir silenciosamente.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
REPO = BACKEND.parent


def _texto(relativo: str) -> str:
    return (REPO / relativo).read_text(encoding="utf-8")


def test_python_alterado_na_parte10_tem_sintaxe_valida() -> None:
    arquivos = [
        "backend/app/routers/validador_juridico.py",
        "backend/app/routers/ai_tools.py",
        "backend/app/services/system_prompts/base.py",
        "backend/app/services/system_prompts/modo_executivo.py",
    ]
    for arquivo in arquivos:
        ast.parse(_texto(arquivo), filename=arquivo)


def test_router_expoe_ato_unico_e_pdf_imediato() -> None:
    fonte = _texto("backend/app/routers/validador_juridico.py")

    assert '@router.patch("/legal-docs/{doc_id}/conferir-assinar")' in fonte
    assert '@router.get("/legal-docs/{doc_id}/pdf-minuta")' in fonte
    assert "confirmado: bool" in fonte
    assert "payload.confirmado is not True" in fonte


def test_ato_unico_preserva_gates_e_trilha_de_auditoria() -> None:
    fonte = _texto("backend/app/routers/validador_juridico.py")

    assert "_VALIDACAO_SCORE_MINIMO = 75" in fonte
    assert "_auditar_jurisprudencia_peca" in fonte
    assert "AIStatusHITL.aplicado" in fonte
    assert '"CONFERENCIA_ASSINATURA_HITL"' in fonte
    assert "legal_doc_validation_current.is_(True)" in fonte
    assert "_gerar_validacao_corrente" in fonte


def test_pdf_minuta_nao_remove_o_gate_do_pdf_de_protocolo() -> None:
    fonte_nova = _texto("backend/app/routers/validador_juridico.py")
    fonte_principal = _texto("backend/app/routers/legal_docs.py")

    assert "minuta_ia=bool(doc.ai_generated and not doc.human_reviewed)" in fonte_nova
    assert "_gates_exportacao_protocolo" in fonte_principal
    assert "await _gates_exportacao_protocolo(db, d)" in fonte_principal


def test_status_ia_usa_settings_tipadas_e_expoe_modelos_por_tarefa() -> None:
    fonte = _texto("backend/app/routers/ai_tools.py")

    assert "settings = get_settings()" in fonte
    assert "settings.ANTHROPIC_MODEL_COMPLEXO" in fonte
    assert '"modelos_por_tarefa": _modelos_por_tarefa(settings)' in fonte
    assert 'os.getenv("ANTHROPIC_MODEL_RAPIDO"' not in fonte
    assert 'os.getenv("ANTHROPIC_MODEL_COMPLEXO"' not in fonte


def test_prompts_corrigem_o_fundamento_normativo() -> None:
    base = _texto("backend/app/services/system_prompts/base.py")
    executivo = _texto("backend/app/services/system_prompts/modo_executivo.py")
    conjunto = base + executivo

    assert "Provimento OAB 205/2021" not in conjunto
    assert "Lei 8.906/1994" in conjunto
    assert "art. 32" in conjunto
    assert "MINUTA GERADA POR IA" in conjunto
