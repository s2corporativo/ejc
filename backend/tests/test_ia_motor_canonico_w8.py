"""W8 (BE-14 — plano de limpeza §10): motor canônico nas portas legadas.

`/ai/analisar-caso` e `/ai/resumir-documento` passam a rodar no Núcleo único
(capacidades.analisar / capacidades.resumir → orchestrator) quando
IA_MOTOR_CANONICO=True (default de produção), mantendo sobre o envelope
canônico os APELIDOS que os consumidores da porta legada já leem:
`resposta`/`analise` (IA.tsx e TabResumo.tsx), `ai_log_id`, `aviso` e
`fontes_usadas`. Flag de porta: IA_MOTOR_CANONICO=false volta ao motor legado
`ai_service` SEM deploy (mesmo padrão do menu 9 e do G1). O gate de ownership
(case_id) roda ANTES do motor nos dois modos.

Padrão do repo para IDOR sem Postgres (test_ai_idor_case_id_gates.py): handler
REAL chamado direto, dependências monkeypatched na origem. Sem rede, sem banco.
Dados fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.schemas.ai import AnalisarCasoRequest, ResumirDocRequest

pytestmark = pytest.mark.anyio


def _settings():
    from app.core.config import get_settings

    return get_settings()


FATOS = "Fatos ficticios com mais de trinta caracteres para o teste do motor."
TEXTO = "Texto ficticio de intimacao com mais de cinquenta caracteres para teste."


def _user() -> User:
    return User(id="u-adv-1", role=UserRole.advogado)


class _FakeDB:
    pass


def _permitir_acesso(monkeypatch):
    import app.core.ownership as ownership_mod

    async def fake(db, cu, case_id):
        return SimpleNamespace(id=case_id)

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", fake)


def _bloquear_acesso(monkeypatch):
    import app.core.ownership as ownership_mod

    async def fake(db, cu, case_id):
        raise HTTPException(status_code=403, detail="Sem permissão")

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", fake)


# ── /ai/analisar-caso — modo canônico (default) ──────────────────────────────


async def test_analisar_caso_usa_nucleo_e_mantem_apelidos(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    _permitir_acesso(monkeypatch)
    legado = {"sim": False}

    async def legado_nunca(*a, **kw):
        legado["sim"] = True
        return {}

    monkeypatch.setattr(ai_router, "analisar_caso", legado_nunca)

    recebido = {}

    async def fake_analisar(db, user, *, case_id=None, texto=None, area=None,
                            perfil=None, opcoes=None):
        recebido.update(
            case_id=case_id, texto=texto, area=area, opcoes=opcoes, user=user
        )
        return {
            "conteudo": "ANALISE_DO_NUCLEO",
            "capacidade": "analisar",
            "log_id": "log-1",
            "fontes_rag": ["chunk-a", "chunk-b"],
            "status_hitl": "gerado",
            "aviso_hitl": "Revisão obrigatória por advogado.",
        }

    monkeypatch.setattr(capacidades, "analisar", fake_analisar)

    req = AnalisarCasoRequest(
        descricao_fatos=FATOS,
        area="civel",
        nomes_proteger=["Parte Contraria"],
    )
    r = await ai_router.analisar(req, _FakeDB(), _user())

    # Motor legado NÃO roda no modo canônico.
    assert legado["sim"] is False
    # O núcleo recebe os mesmos insumos que o motor legado recebia.
    assert recebido["texto"] == FATOS
    assert recebido["area"] == "civel"
    assert recebido["case_id"] is None
    assert recebido["opcoes"] == {"nomes_proteger": ["Parte Contraria"]}
    assert recebido["user"].id == "u-adv-1"
    # Envelope canônico preservado…
    assert r["conteudo"] == "ANALISE_DO_NUCLEO"
    assert r["capacidade"] == "analisar"
    assert r["log_id"] == "log-1"
    # …com os apelidos que os consumidores já leem.
    assert r["resposta"] == "ANALISE_DO_NUCLEO"  # IA.tsx (Markdown)
    assert r["analise"] == "ANALISE_DO_NUCLEO"  # TabResumo.tsx (modal)
    assert r["ai_log_id"] == "log-1"  # trilha legada
    assert r["fontes_usadas"] == 2  # IA.tsx
    assert r["aviso"] == "Revisão obrigatória por advogado."  # IA.tsx


async def test_gate_de_ownership_roda_antes_do_nucleo_analisar(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    _bloquear_acesso(monkeypatch)
    nucleo = {"sim": False}

    async def nucleo_nunca(*a, **kw):
        nucleo["sim"] = True
        return {}

    monkeypatch.setattr(capacidades, "analisar", nucleo_nunca)

    req = AnalisarCasoRequest(
        descricao_fatos=FATOS, area="civel", case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.analisar(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    # O dossiê/escopo RAG é aberto DENTRO do motor — se ele rodar antes do
    # gate, o 403 chega tarde demais. A ordem é parte do contrato de segurança.
    assert nucleo["sim"] is False


async def test_rollback_flag_false_usa_motor_legado_analisar(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    monkeypatch.setattr(_settings(), "IA_MOTOR_CANONICO", False)
    _permitir_acesso(monkeypatch)

    async def fake_legado(db, user_id, fatos, area, nomes_proteger=None,
                          case_id=None):
        return {"resposta": "OK_LEGADO", "ai_log_id": "log-2", "fontes_usadas": 3}

    monkeypatch.setattr(ai_router, "analisar_caso", fake_legado)

    nucleo = {"sim": False}

    async def nucleo_nunca(*a, **kw):
        nucleo["sim"] = True
        return {}

    monkeypatch.setattr(capacidades, "analisar", nucleo_nunca)

    req = AnalisarCasoRequest(descricao_fatos=FATOS, area="civel")
    r = await ai_router.analisar(req, _FakeDB(), _user())
    assert nucleo["sim"] is False
    assert r["resposta"] == "OK_LEGADO"
    # A saída canônica da porta legada é preservada (canonizar mapeia
    # resposta→conteudo) — contrato idêntico ao de antes do W8.
    assert r["conteudo"] == "OK_LEGADO"
    assert r["ai_log_id"] == "log-2"
    assert r["fontes_usadas"] == 3


# ── /ai/resumir-documento — modo canônico (default) ──────────────────────────


async def test_resumir_documento_usa_nucleo_e_mantem_apelidos(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    _permitir_acesso(monkeypatch)
    legado = {"sim": False}

    async def legado_nunca(*a, **kw):
        legado["sim"] = True
        return {}

    monkeypatch.setattr(ai_router, "resumir_documento", legado_nunca)

    recebido = {}

    async def fake_resumir(db, user, *, case_id=None, texto=None, area=None,
                           perfil=None, opcoes=None):
        recebido.update(case_id=case_id, texto=texto, user=user)
        return {
            "conteudo": "RESUMO_DO_NUCLEO",
            "capacidade": "resumir",
            "log_id": "log-3",
            "fontes_rag": [],
            "status_hitl": "gerado",
            "aviso_hitl": "Revisão obrigatória por advogado.",
        }

    monkeypatch.setattr(capacidades, "resumir", fake_resumir)

    req = ResumirDocRequest(texto=TEXTO, case_id="caso-do-proprio-advogado")
    r = await ai_router.resumir(req, _FakeDB(), _user())

    assert legado["sim"] is False
    assert recebido["texto"] == TEXTO
    assert recebido["case_id"] == "caso-do-proprio-advogado"
    assert recebido["user"].id == "u-adv-1"
    assert r["conteudo"] == "RESUMO_DO_NUCLEO"
    assert r["resposta"] == "RESUMO_DO_NUCLEO"  # IA.tsx
    assert r["ai_log_id"] == "log-3"
    assert r["fontes_usadas"] == 0
    assert r["aviso"] == "Revisão obrigatória por advogado."


async def test_gate_de_ownership_roda_antes_do_nucleo_resumir(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    _bloquear_acesso(monkeypatch)
    nucleo = {"sim": False}

    async def nucleo_nunca(*a, **kw):
        nucleo["sim"] = True
        return {}

    monkeypatch.setattr(capacidades, "resumir", nucleo_nunca)

    req = ResumirDocRequest(texto=TEXTO, case_id="caso-de-outro-advogado")
    with pytest.raises(HTTPException) as exc:
        await ai_router.resumir(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    assert nucleo["sim"] is False


async def test_rollback_flag_false_usa_motor_legado_resumir(monkeypatch):
    from app.routers import ai as ai_router
    from app.services.ai.core import capacidades

    monkeypatch.setattr(_settings(), "IA_MOTOR_CANONICO", False)
    _permitir_acesso(monkeypatch)

    async def fake_legado(db, user_id, texto_documento, case_id=None):
        return {"resposta": "OK_LEGADO_RESUMO", "ai_log_id": "log-4"}

    monkeypatch.setattr(ai_router, "resumir_documento", fake_legado)

    nucleo = {"sim": False}

    async def nucleo_nunca(*a, **kw):
        nucleo["sim"] = True
        return {}

    monkeypatch.setattr(capacidades, "resumir", nucleo_nunca)

    req = ResumirDocRequest(texto=TEXTO)
    r = await ai_router.resumir(req, _FakeDB(), _user())
    assert nucleo["sim"] is False
    assert r["resposta"] == "OK_LEGADO_RESUMO"
    assert r["conteudo"] == "OK_LEGADO_RESUMO"
    assert r["ai_log_id"] == "log-4"


# ── Default da flag (rollback documentado sem deploy) ────────────────────────


def test_flag_motor_canonico_default_ligado():
    """O default LIGADO é o propósito do W8 (porta legada deixa de ser o motor
    em produção). Rollback continua possível por env sem deploy — mesmo
    padrão do menu 9 (Onda 1) e do G1 (cache de IA, W9)."""
    assert _settings().IA_MOTOR_CANONICO is True
