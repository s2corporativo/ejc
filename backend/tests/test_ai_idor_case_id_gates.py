"""IDOR real em endpoints de IA que aceitam `case_id` opcional (auditoria de
segurança 18/08, achados #1/#outros — "AI APIs" audit).

`/analisar-caso` era o caso GRAVE: o case_id chegava a `analisar_caso()` sem
nenhuma checagem de ownership, e dentro do serviço ele abre o ESCOPO RAG
restrito do cliente do caso (peça_interna/precedente_interno/comunicacao_
processual) e monta o DOSSIÊ inteiro (fatos, prazos, honorários, peças,
histórico) dentro do prompt — qualquer usuário autenticado lia caso de
carteira alheia só informando o id. Os endpoints irmãos (`/dossie`,
`/teses-ocultas`, `/auditar-peca`) já tinham o gate; este não tinha.

`/resumir-documento`, `/preparar-audiencia` e `/analisar-contrato` não vazam
dado do caso (o conteúdo vem no corpo da requisição), mas sem ownership o
AILog é gravado como se pertencesse a um caso alheio — poluição da trilha de
auditoria daquele caso.

Padrão do repo para IDOR sem Postgres (test_ai_detectar_prazos.py): handler
REAL chamado direto, `verificar_acesso_caso` monkeypatched no módulo de
origem (é import LOCAL dentro do handler, então soh o patch em
app.core.ownership tem efeito). Sem rede, sem banco. Dados fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.schemas.ai import (
    AnalisarCasoRequest,
    ResumirDocRequest,
)

pytestmark = pytest.mark.anyio


def _user() -> User:
    return User(id="u-adv-1", role=UserRole.advogado)


class _FakeDB:
    pass


def _bloquear_acesso(monkeypatch, motivo="Sem permissão"):
    """Simula caso de OUTRO advogado: verificar_acesso_caso nega (403)."""
    import app.core.ownership as ownership_mod

    async def fake(db, cu, case_id):
        raise HTTPException(status_code=403, detail=motivo)

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", fake)


def _permitir_acesso(monkeypatch):
    """Simula caso do PRÓPRIO advogado: verificar_acesso_caso libera."""
    import app.core.ownership as ownership_mod

    async def fake(db, cu, case_id):
        return SimpleNamespace(id=case_id)

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", fake)


def _servico_nunca_deveria_rodar(monkeypatch, alvo_modulo, nome_func):
    """Se o gate falhar em barrar, o teste denuncia QUE o serviço rodou —
    não deixa a asserção depender só do HTTPException borbulhar."""
    chamado = {"sim": False}

    async def fake(*a, **kw):
        chamado["sim"] = True
        return {"resposta": "NAO_DEVERIA_CHEGAR_AQUI"}

    monkeypatch.setattr(alvo_modulo, nome_func, fake)
    return chamado


# ── /analisar-caso — o achado GRAVE (leitura de dado de outro caso) ─────────

async def test_analisar_caso_barra_case_id_de_outro_advogado(monkeypatch):
    from app.routers import ai as ai_router

    _bloquear_acesso(monkeypatch)
    chamado = _servico_nunca_deveria_rodar(monkeypatch, ai_router, "analisar_caso")

    req = AnalisarCasoRequest(
        descricao_fatos="Fatos ficticios com mais de trinta caracteres para teste.",
        area="civel",
        case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.analisar(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    # A barreira tem que impedir o SERVIÇO de rodar — senão o dossiê/escopo
    # RAG do caso alheio já foi montado antes da exceção "salvar" nada.
    assert chamado["sim"] is False


async def test_analisar_caso_libera_case_id_do_proprio_advogado(monkeypatch):
    from app.routers import ai as ai_router

    _permitir_acesso(monkeypatch)

    async def fake_analisar(db, user_id, fatos, area, nomes_proteger=None, case_id=None):
        return {"resposta": "ok", "case_id_recebido": case_id}

    monkeypatch.setattr(ai_router, "analisar_caso", fake_analisar)

    req = AnalisarCasoRequest(
        descricao_fatos="Fatos ficticios com mais de trinta caracteres para teste.",
        area="civel",
        case_id="caso-do-proprio-advogado",
    )
    r = await ai_router.analisar(req, _FakeDB(), _user())
    assert r["case_id_recebido"] == "caso-do-proprio-advogado"


async def test_analisar_caso_sem_case_id_nao_aciona_ownership(monkeypatch):
    """Uso comum (sem vincular a um caso) não pode quebrar nem exigir gate."""
    import app.core.ownership as ownership_mod
    from app.routers import ai as ai_router

    async def nunca_deveria_ser_chamado(db, cu, case_id):
        raise AssertionError("verificar_acesso_caso não deveria ser chamado sem case_id")

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", nunca_deveria_ser_chamado)

    async def fake_analisar(db, user_id, fatos, area, nomes_proteger=None, case_id=None):
        return {"resposta": "ok"}

    monkeypatch.setattr(ai_router, "analisar_caso", fake_analisar)

    req = AnalisarCasoRequest(
        descricao_fatos="Fatos ficticios com mais de trinta caracteres para teste.",
        area="civel",
    )
    r = await ai_router.analisar(req, _FakeDB(), _user())
    assert r["resposta"] == "ok"


# ── Trilha de auditoria: resumir-documento / preparar-audiencia / analisar-contrato ─

async def test_resumir_documento_barra_case_id_de_outro_advogado(monkeypatch):
    from app.routers import ai as ai_router

    _bloquear_acesso(monkeypatch)
    chamado = _servico_nunca_deveria_rodar(monkeypatch, ai_router, "resumir_documento")

    req = ResumirDocRequest(
        texto="Texto ficticio de intimacao com mais de cinquenta caracteres para teste.",
        case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.resumir(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    assert chamado["sim"] is False


async def test_preparar_audiencia_barra_case_id_de_outro_advogado(monkeypatch):
    from app.routers import ai as ai_router
    from app.routers.ai import AudienciaReq

    _bloquear_acesso(monkeypatch)
    chamado = _servico_nunca_deveria_rodar(monkeypatch, ai_router, "preparar_audiencia")

    req = AudienciaReq(
        resumo_caso="Resumo ficticio do caso com mais de cinquenta caracteres para teste.",
        tipo_audiencia="conciliacao",
        case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.audiencia(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    assert chamado["sim"] is False


async def test_analisar_contrato_barra_case_id_de_outro_advogado(monkeypatch):
    from app.routers import ai as ai_router
    from app.routers.ai import AnaliseContratoReq

    _bloquear_acesso(monkeypatch)
    chamado = _servico_nunca_deveria_rodar(monkeypatch, ai_router, "analisar_contrato")

    req = AnaliseContratoReq(
        texto_contrato="Cláusula ficticia de contrato com mais de cem caracteres " * 3,
        case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.analisar_contrato_endpoint(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    assert chamado["sim"] is False


async def test_auditar_peca_com_conteudo_direto_barra_case_id_de_outro_advogado(monkeypatch):
    """O gate de /auditar-peca só rodava no caminho `peca_id` (via
    doc.case_id) — com `conteudo` direto, req.case_id passava sem checagem."""
    from app.routers import ai as ai_router
    from app.routers.ai import AuditarPecaReq

    _bloquear_acesso(monkeypatch)
    chamado = _servico_nunca_deveria_rodar(monkeypatch, ai_router, "auditar_peca")

    req = AuditarPecaReq(
        conteudo="Conteúdo fictício de petição com mais de cem caracteres " * 3,
        tipo_peca="contestacao",
        case_id="caso-de-outro-advogado",
    )
    with pytest.raises(HTTPException) as exc:
        await ai_router.auditar(req, _FakeDB(), _user())
    assert exc.value.status_code == 403
    assert chamado["sim"] is False


# ── Gate hierárquico onde cabia allowlist exata (auditoria 18/08) ───────────
# ROLE_LEVEL["financeiro"]=4 fica ACIMA de ROLE_LEVEL["estagiario"]=3 — um gate
# escrito como `ROLE_LEVEL.get(...) < ROLE_LEVEL["estagiario"]` deixa o papel
# financeiro passar pela porta de entrada de superfície jurídica (mesmo
# defeito que EQUIPE_JURIDICA/requer_equipe_juridica, Issue #694, existe para
# fechar). O ownership do caso já barrava o acesso de fato; aqui a checagem é
# da FORMA do gate — role errado é rejeitado ANTES de qualquer consulta ao caso.

def _financeiro() -> User:
    return User(id="u-financeiro-1", role=UserRole.financeiro)


async def test_assistente_estrategico_rejeita_financeiro_antes_do_ownership():
    from app.routers import ai as ai_router
    from app.routers.ai import AssistenteCasoReq

    req = AssistenteCasoReq(pergunta="Pergunta ficticia com mais de cinco caracteres.")
    with pytest.raises(HTTPException) as exc:
        await ai_router.assistente_estrategico(
            "caso-qualquer", req, _FakeDB(), _financeiro(),
        )
    assert exc.value.status_code == 403


async def test_visual_law_rejeita_financeiro(monkeypatch):
    from app.routers import ai as ai_router
    from app.routers.ai import VisualLawReq

    req = VisualLawReq(tipo="timeline")
    with pytest.raises(HTTPException) as exc:
        await ai_router.visual_law("caso-qualquer", req, _FakeDB(), _financeiro())
    assert exc.value.status_code == 403


async def test_assistente_estrategico_ainda_libera_estagiario_no_gate_de_papel(monkeypatch):
    """O gate de PAPEL não pode ficar mais restritivo que antes para quem já
    tinha acesso — só fecha o vazamento do financeiro."""
    from app.routers import ai as ai_router
    from app.routers.ai import AssistenteCasoReq

    async def fake_execute(*a, **k):
        class _R:
            def scalar_one_or_none(self):
                return None
        return _R()

    db = _FakeDB()
    db.execute = fake_execute

    req = AssistenteCasoReq(pergunta="Pergunta ficticia com mais de cinco caracteres.")
    with pytest.raises(HTTPException) as exc:
        await ai_router.assistente_estrategico(
            "caso-inexistente", req, db, User(id="u-estag-1", role=UserRole.estagiario),
        )
    # Passa do gate de PAPEL (não é 403 de papel) — 404 é o caso não existir.
    assert exc.value.status_code == 404
