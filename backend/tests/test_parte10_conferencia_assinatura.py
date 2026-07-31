"""Contratos estruturais da Parte 10 — inteligência, minuta e HITL enxuto.

Estes testes são deliberadamente independentes de banco/provedor: travam a
arquitetura e a linguagem normativa que não podem regredir silenciosamente.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _texto(relativo: str) -> str:
    return (REPO / relativo).read_text(encoding="utf-8")


def test_python_alterado_na_parte10_tem_sintaxe_valida() -> None:
    arquivos = [
        "backend/app/routers/validador_juridico.py",
        "backend/app/routers/ai_tools.py",
        "backend/app/routers/ia_saude.py",
        "backend/app/routers/legal_docs.py",
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
    fonte_legada = _texto("backend/app/routers/legal_docs_legacy.py")

    assert "minuta_ia=bool(doc.ai_generated and not doc.human_reviewed)" in fonte_nova
    assert "_gates_exportacao_protocolo" in fonte_legada
    assert "await _gates_exportacao_protocolo(db, d)" in fonte_legada


def test_fachada_legal_docs_substitui_so_as_rotas_conflitantes() -> None:
    fachada = _texto("backend/app/routers/legal_docs.py")

    assert "legal_docs_legacy" in fachada
    assert '"/legal-docs/{doc_id}", "PATCH"' in fachada
    assert '"/legal-docs/{doc_id}/aprovar", "PATCH"' in fachada
    assert "aprovar_compativel" in fachada
    assert "ConferenciaAssinaturaRequest" in fachada
    assert "Provimento OAB 205/2021" in fachada  # somente detector para remoção
    assert "replace" in fachada


def test_status_ia_espelha_o_resolver_real_do_gateway() -> None:
    fonte = _texto("backend/app/routers/ai_tools.py")

    assert "settings = get_settings()" in fonte
    assert "settings.ANTHROPIC_MODEL_COMPLEXO" in fonte
    assert '"modelos_por_tarefa": _modelos_por_tarefa(settings)' in fonte
    assert '"modelo_resolvido_pelo_gateway"' in fonte
    assert '"habilitado": bool(settings.OLLAMA_ENABLED)' in fonte
    assert '"disponivel": disponivel' in fonte
    assert '"mensagem": None if disponivel else MSG_IA_NAO_ATIVADA' in fonte
    assert "ia_disponivel" in fonte
    assert 'os.getenv("ANTHROPIC_MODEL_RAPIDO"' not in fonte
    assert 'os.getenv("ANTHROPIC_MODEL_COMPLEXO"' not in fonte


def test_nao_ha_duas_rotas_get_ia_status() -> None:
    detalhado = _texto("backend/app/routers/ai_tools.py")
    leigo = _texto("backend/app/routers/ia_saude.py")

    assert '@router.get("/status")' in detalhado
    assert "async def ia_status" in leigo  # compatibilidade de import/teste
    assert "@router_status.get" not in leigo


def test_prompts_corrigem_o_fundamento_normativo() -> None:
    base = _texto("backend/app/services/system_prompts/base.py")
    executivo = _texto("backend/app/services/system_prompts/modo_executivo.py")
    conjunto = base + executivo

    assert "Provimento OAB 205/2021" not in conjunto
    assert "Lei 8.906/1994" in conjunto
    assert "art. 32" in conjunto
    assert "MINUTA GERADA POR IA" in conjunto


def test_frontend_adota_fluxo_unico_sem_perder_ferramentas_anteriores() -> None:
    novo = _texto("frontend/src/pages/Pecas.tsx")
    legado = REPO / "frontend/src/pages/PecasLegacy.tsx"

    assert legado.exists()
    assert 'import PecasLegacy from "./PecasLegacy"' in novo
    assert "/conferir-assinar" in novo
    assert "/pdf-minuta" in novo
    assert "Confirmo a conferência e assino" in novo
    assert "Ferramentas avançadas preservadas" in novo
    assert "normalizarLinguagemLegada" in novo
    assert '{" ""}' not in novo
    assert "Provimento OAB 205/2021" not in novo


def test_frontend_bloqueia_as_acoes_hitl_redundantes_da_tela_legada() -> None:
    novo = _texto("frontend/src/pages/Pecas.tsx")

    for rotulo in (
        'rotulo === "Revisar"',
        'rotulo === "Revisar e Aprovar"',
        'rotulo === "Aprovar peça"',
        'rotulo === "Aprovar revisão"',
    ):
        assert rotulo in novo
    assert 'Use a ação única "Conferir e assinar"' in novo
