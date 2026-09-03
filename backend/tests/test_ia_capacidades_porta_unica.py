"""I1 — UMA PORTA DE IA POR CAPACIDADE (análise E2E de 03/09/2026).

O que este arquivo trava:

1. as cinco portas existem, são POST e nascem PROTEGIDAS (nenhuma pública);
2. `cliente_externo` é barrado comparando o VALOR do enum — `str(UserRole.x)`
   devolve "UserRole.cliente_externo" e o gate escrito assim nunca dispara;
3. `analisar`/`redigir` exigem equipe jurídica (secretaria/financeiro não passam);
4. a porta delega ao Núcleo Único com `nivel_inteligencia=None` — quem decide o
   nível é o PISO por tarefa do gateway, não um "alto" fixo em toda chamada;
5. `case_id` passa por ownership ANTES de qualquer montagem de contexto;
6. o envelope canônico é o mesmo saindo do orquestrador ou de uma porta legada.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.routers import ia_capacidades
from app.schemas.ai import AnalisarRequest, ConversarRequest, RedigirRequest

pytestmark = pytest.mark.anyio


class _FakeDB:
    async def execute(self, *a, **kw):  # pragma: no cover - não deve ser usado
        raise AssertionError("a porta não deve consultar o banco diretamente")


_RESPOSTA_NUCLEO = {
    "conteudo": "Rascunho de análise.",
    "tarefa": "analise_caso",
    "modelo": "anthropic/claude",
    "provider": "anthropic",
    "log_id": "log-1",
    "fontes": [{"titulo": "CDC", "categoria": "legislacao"}],
    "citacoes": [],
    "alertas": ["conferir citação"],
    "custo_estimado_brl": 0.12,
    "tokens_input": 100,
    "tokens_output": 40,
    "is_rascunho": True,
    "requer_revisao": True,
    "status_hitl": "gerado",
    "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def nucleo(monkeypatch):
    """Substitui o orquestrador e devolve o que a porta pediu a ele."""
    capturado: dict = {}

    async def fake_run(**kwargs):
        capturado.update(kwargs)
        return dict(_RESPOSTA_NUCLEO)

    from app.services.ai.core import capacidades as mod

    monkeypatch.setattr(mod.orchestrator, "run", fake_run)
    monkeypatch.setattr(
        ia_capacidades, "get_settings", lambda: SimpleNamespace(AI_ENABLED=True),
    )
    return capturado


def _adv() -> User:
    return User(id="u-adv", role=UserRole.advogado)


# ── 1. Superfície: cinco portas, todas protegidas ────────────────────────────

def test_as_cinco_portas_existem_e_nenhuma_e_publica():
    from app.main import app

    esperadas = {
        "/api/ia/analisar", "/api/ia/redigir", "/api/ia/resumir",
        "/api/ia/conversar", "/api/ia/extrair",
    }
    encontradas = {}
    for r in app.routes:
        path = getattr(r, "path", "")
        if path in esperadas:
            encontradas[path] = r

    assert set(encontradas) == esperadas, f"faltam portas: {esperadas - set(encontradas)}"
    for path, rota in encontradas.items():
        assert "POST" in (getattr(rota, "methods", None) or set()), path
        nomes = {
            getattr(d.call, "__name__", "")
            for d in (getattr(rota, "dependant", None).dependencies or [])
        }
        # get_current_user entra como dependência do handler; o rate_limit vem
        # como dependência da rota. Ambos precisam estar lá.
        fonte = nomes | {
            getattr(sub.call, "__name__", "")
            for d in (getattr(rota, "dependant", None).dependencies or [])
            for sub in (d.dependencies or [])
        }
        assert "get_current_user" in fonte or any(
            "current_user" in n for n in fonte
        ), f"{path} sem gate de autenticação"


def test_capacidades_declaradas_sao_exatamente_cinco():
    from app.services.ai.core import capacidades

    assert set(capacidades.CAPACIDADES) == {
        "analisar", "redigir", "resumir", "conversar", "extrair",
    }
    assert set(capacidades.PORTAS) == set(capacidades.CAPACIDADES)


# ── 2. cliente_externo: comparação por VALOR do enum ─────────────────────────

async def test_cliente_externo_nao_entra_em_nenhuma_capacidade(nucleo):
    cu = User(id="u-cli", role=UserRole.cliente_externo)
    body = ConversarRequest(mensagem="Como está meu processo?")
    with pytest.raises(HTTPException) as exc:
        await ia_capacidades.conversar(body, _FakeDB(), cu)
    assert exc.value.status_code == 403
    assert not nucleo, "o Núcleo não pode ser acionado para cliente_externo"


async def test_gate_de_cliente_externo_usa_o_valor_e_nao_str_do_enum():
    """`str(UserRole.cliente_externo)` == 'UserRole.cliente_externo'."""
    from app.services.ai.core import capacidades

    assert str(UserRole.cliente_externo) != "cliente_externo"
    with pytest.raises(HTTPException):
        capacidades._bloquear_cliente_externo(
            SimpleNamespace(role=UserRole.cliente_externo)
        )
    # Também funciona quando o papel chega como string pura.
    with pytest.raises(HTTPException):
        capacidades._bloquear_cliente_externo(SimpleNamespace(role="cliente_externo"))


# ── 3. Equipe jurídica em analisar/redigir ───────────────────────────────────

async def test_analisar_e_redigir_exigem_equipe_juridica(nucleo):
    cu = User(id="u-sec", role=UserRole.secretaria)
    with pytest.raises(HTTPException) as exc:
        await ia_capacidades.analisar(
            AnalisarRequest(texto="Fatos fictícios com mais de trinta caracteres."),
            _FakeDB(), cu,
        )
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await ia_capacidades.redigir(
            RedigirRequest(texto="Minuta de contestação"), _FakeDB(), cu,
        )
    assert not nucleo


async def test_resumir_nao_exige_equipe_juridica(nucleo, monkeypatch):
    from app.schemas.ai import ResumirRequest

    cu = User(id="u-sec", role=UserRole.secretaria)
    r = await ia_capacidades.resumir(
        ResumirRequest(texto="Texto longo o suficiente para resumo."), _FakeDB(), cu,
    )
    assert r["capacidade"] == "resumir"
    assert nucleo["task_type"] == "resumo"


# ── 4. Delegação ao Núcleo (sem forçar nível) ────────────────────────────────

async def test_porta_delega_ao_nucleo_sem_forcar_nivel(nucleo):
    r = await ia_capacidades.analisar(
        AnalisarRequest(
            texto="Fatos fictícios com mais de trinta caracteres para análise.",
            area="consumidor",
        ),
        _FakeDB(), _adv(),
    )
    assert nucleo["task_type"] == "analise_caso"
    assert nucleo["domain"] == "consumidor"
    # O PISO por tarefa decide — nada de "alto" fixo em toda chamada.
    assert nucleo["nivel_inteligencia"] is None
    assert r["conteudo"] == "Rascunho de análise."
    assert r["is_rascunho"] is True and r["requer_revisao"] is True
    assert r["aviso_hitl"]
    assert r["fontes_rag"] == [{"titulo": "CDC", "categoria": "legislacao"}]
    assert r["tokens"] == {"input": 100, "output": 40, "total": 140}
    assert r["custo_estimado_brl"] == 0.12


async def test_cada_capacidade_tem_task_type_proprio(nucleo):
    from app.schemas.ai import ExtrairRequest, ResumirRequest

    await ia_capacidades.redigir(
        RedigirRequest(texto="Rascunho de petição inicial"), _FakeDB(), _adv())
    assert nucleo["task_type"] == "legal_draft"
    await ia_capacidades.conversar(
        ConversarRequest(texto="Qual o prazo?"), _FakeDB(), _adv())
    assert nucleo["task_type"] == "chat"
    await ia_capacidades.extrair(
        ExtrairRequest(texto="Documento com prazos e partes."), _FakeDB(), _adv())
    assert nucleo["task_type"] == "document_extraction"
    await ia_capacidades.resumir(
        ResumirRequest(texto="Decisão longa para resumo."), _FakeDB(), _adv())
    assert nucleo["task_type"] == "resumo"


async def test_perfil_da_ia_especializada_vira_dominio_e_parametro(nucleo):
    await ia_capacidades.analisar(
        AnalisarRequest(
            texto="Fatos fictícios com mais de trinta caracteres para análise.",
            perfil="financeira",
        ),
        _FakeDB(), _adv(),
    )
    assert nucleo["domain"] == "financeiro"
    assert nucleo["params"]["perfil"] == "financeira"


# ── 5. Ownership do caso antes de qualquer contexto ──────────────────────────

async def test_case_id_passa_por_ownership_antes_do_nucleo(nucleo, monkeypatch):
    import app.core.ownership as ownership_mod

    async def nega(db, cu, case_id):
        raise HTTPException(403, "Sem acesso ao caso")

    monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", nega)
    with pytest.raises(HTTPException) as exc:
        await ia_capacidades.analisar(
            AnalisarRequest(
                texto="Fatos fictícios com mais de trinta caracteres para análise.",
                case_id="caso-de-outro",
            ),
            _FakeDB(), _adv(),
        )
    assert exc.value.status_code == 403
    assert not nucleo, "o contexto do caso alheio não pode ter sido montado"


# ── 6. Envelope canônico também para porta legada ────────────────────────────

def test_canonizar_traduz_o_shape_antigo():
    from app.services.ai.core import capacidades

    legado = {
        "ai_log_id": "log-9", "resposta": "texto antigo",
        "fontes": [{"titulo": "STJ"}], "provedor": "groq", "modelo": "llama",
        "tokens_input": 10, "tokens_output": 5,
    }
    env = capacidades.canonizar("resumir", legado)
    assert env["conteudo"] == "texto antigo"
    assert env["capacidade"] == "resumir"
    assert env["log_id"] == "log-9"
    assert env["provider"] == "groq"
    assert env["fontes_rag"] == [{"titulo": "STJ"}]
    assert env["tokens"] == {"input": 10, "output": 5, "total": 15}
    assert env["is_rascunho"] is True
    assert env["status_hitl"] == "gerado"
    assert env["aviso_hitl"]
    # Chaves do contrato novo, todas presentes.
    assert set(env) >= {
        "conteudo", "capacidade", "tarefa", "modelo", "provider", "log_id",
        "is_rascunho", "requer_revisao", "status_hitl", "aviso_hitl",
        "fontes_rag", "citacoes", "custo_estimado_brl", "tokens",
    }


def test_tarefa_ia_mapeia_para_capacidade():
    from app.services.ai.core import capacidades
    from app.services.system_prompts import TarefaIA

    assert capacidades.capacidade_da_tarefa(TarefaIA.MINUTAS) == "redigir"
    assert capacidades.capacidade_da_tarefa(TarefaIA.RESUMO) == "resumir"
    assert capacidades.capacidade_da_tarefa(TarefaIA.PRAZOS) == "extrair"
    assert capacidades.capacidade_da_tarefa(TarefaIA.ANALISE_CASO) == "analisar"
    assert capacidades.capacidade_da_tarefa(TarefaIA.RAG_QUERY) == "conversar"
    # Toda TarefaIA cai em UMA das cinco portas — nenhuma fica órfã.
    for tarefa in TarefaIA:
        assert capacidades.capacidade_da_tarefa(tarefa) in capacidades.CAPACIDADES
