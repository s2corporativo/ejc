"""Invariantes de governança endurecidos pela auditoria de IA (#1150).

Cobre os achados P1-4, P1-5, P1-6 e P1-8: quem pode revisar, o que o agente
default precisa comprovar, o que o kill-switch faz sem provider elegível e o que
o modelo enxerga de cada fonte.
"""
import inspect

import pytest


# ── P1-6: kill-switch fail-closed no próprio gateway ────────────────────────

def test_resolver_cadeia_nao_sintetiza_provider_externo():
    """Cadeia vazia permanece vazia — nada de 'último recurso' no Groq.

    O fail-closed vinha de um patch instalado no boot da API; o worker Celery
    não o carregava e podia chamar provider externo com o kill-switch ligado.
    """
    from app.services import ai_gateway

    # Lê o ARQUIVO, não o objeto: o hardening de runtime embrulha _resolver_cadeia,
    # e inspecionar a função devolveria o wrapper conforme a ordem dos testes. O
    # invariante é do código-fonte — o gateway não pode sintetizar provider.
    fonte = inspect.getsource(inspect.getmodule(ai_gateway))
    assert 'cadeia = [("groq"' not in fonte
    assert "FAIL-CLOSED" in fonte


def test_worker_celery_carrega_registro_e_telemetria_de_providers():
    from app.core.celery_app import celery_app

    assert "app.services.event_subscribers" in celery_app.conf.include


# ── P1-4: agentes de mérito exigem fonte ────────────────────────────────────

@pytest.mark.parametrize(
    "agente", ["CaseAgent", "EJCCoordinatorAgent", "FinanceAgent"]
)
def test_agentes_de_merito_exigem_fonte(agente):
    """CaseAgent é o default do intent_classifier: sem exige_fonte, o caminho
    mais comum do chat responde tese jurídica sem verificação de citação."""
    from app.services.ai.core.agent_registry import AGENT_REGISTRY

    a = AGENT_REGISTRY[agente]
    assert a.exige_fonte is True
    assert any("validate_citations" in str(s) for s in a.skills)


# ── P1-8: metadados de fonte chegam ao modelo ───────────────────────────────

def test_fontes_levam_tribunal_vigencia_versao_e_url_ao_prompt():
    from app.services.ai_service import _formatar_fontes

    saida = _formatar_fontes([{
        "titulo": "Súmula 331 do TST",
        "categoria": "jurisprudencia",
        "conteudo": "Contrato de prestação de serviços. Legalidade.",
        "fonte": "https://www.tst.jus.br/sumulas",
        "versao": 3,
        "tribunal": "TST",
        "atualizado_em": "2026-07-18",
        "situacao_juridica": {"code": "vigente", "label": "vigente", "warning": False},
    }])
    for esperado in ("TST", "versão 3", "2026-07-18", "vigente",
                     "https://www.tst.jus.br/sumulas"):
        assert esperado in saida


def test_fonte_com_vigencia_duvidosa_vai_marcada():
    from app.services.ai_service import _formatar_fontes

    saida = _formatar_fontes([{
        "titulo": "Lei revogada",
        "categoria": "legislacao",
        "conteudo": "texto",
        "situacao_juridica": {
            "code": "vigencia_nao_verificada",
            "label": "vigência não verificada",
            "warning": True,
        },
    }])
    assert "⚠ vigência não verificada" in saida


def test_formatar_fontes_tolera_metadados_ausentes():
    """O reranker é opt-in; sem ele não há tribunal nem situação jurídica."""
    from app.services.ai_service import _formatar_fontes

    saida = _formatar_fontes([
        {"titulo": "Doc", "categoria": "legislacao", "conteudo": "texto"}
    ])
    assert "[Fonte 1] Doc" in saida and "texto" in saida


# ── P1-5: revisão e aprovação são atos de advogado ──────────────────────────

@pytest.mark.parametrize(
    "funcao", ["revisar", "aprovar", "conferir_e_assinar"]
)
def test_revisao_e_aprovacao_de_peca_exigem_advogado(funcao):
    """A revisão humana da peça é ato privativo do advogado (D5, 2026-09-05:
    citação normativa incorreta removida — Provimento 205/2021 trata de
    publicidade, não de HITL)."""
    from app.routers import legal_docs

    fonte = inspect.getsource(getattr(legal_docs, funcao))
    assert "requer_advogado" in fonte


def test_hitl_do_ailog_exige_advogado_para_revisar():
    from app.routers import ai as router_ai

    fonte = inspect.getsource(router_ai.atualizar_hitl)
    assert "requer_advogado" in fonte
    assert '("revisado", "aplicado")' in fonte
