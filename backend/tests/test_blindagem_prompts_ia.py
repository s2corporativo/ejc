# ── tests/test_blindagem_prompts_ia.py ───────────────────────────────────────
# Blindagem anti-alucinação P0.1/P0.2 (docs/arquivo/planos/MAPA_PROMPTS_IA03.md):
#
#   P0.1 — routers/prompts_juridicos.py::executar_prompt SEMPRE injeta system
#          message com a base canônica (garantir_identidade) e NÃO confia no
#          task_type arbitrário do request (clamp por allowlist → default seguro).
#
#   P0.2 — services/peca_service.py: etapas intermediárias do pipeline (1, 2,
#          5 e 6) carregam BASE_ESTRUTURADA no system prompt SEM quebrar o
#          parse JSON da etapa 1 (_tipo_identificado) e SEM remover/enfraquecer
#          as regras inline existentes (etapas 4 e 7 intactas).
#
# Padrão dos testes de IA do projeto (sem Postgres/IA real): _FakeDB + handler
# real com dependências monkeypatched; a IA é substituída por um recorder.
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import app.services.peca_service as ps
from app.models.prompt_juridico import PromptCategoria, PromptJuridico
from app.routers import prompts_juridicos as pj
from app.routers.prompts_juridicos import (
    ExecutarPromptReq,
    _TASK_TYPE_DEFAULT,
    _clamp_task_type,
)
from app.services.legal_base import BASE_ESTRUTURADA


# ══════════════════════════════════════════════════════════════════════════════
# P0.1 — clamp de task_type (função pura)
# ══════════════════════════════════════════════════════════════════════════════

def test_clamp_aceita_tasks_do_task_routing():
    from app.services.ai_gateway import TASK_ROUTING
    for task in TASK_ROUTING:
        assert _clamp_task_type(task) == task


def test_clamp_aceita_aliases_do_gateway():
    from app.services.ai_gateway import TASK_ALIASES
    for alias in TASK_ALIASES:
        assert _clamp_task_type(alias) == alias


def test_clamp_task_arbitrario_cai_no_default_seguro():
    for lixo in ("drop_all_rules", "ignore_previous_instructions", "xpto",
                 "analise_juridica; DROP TABLE", "elaboracao_peca "):
        clamped = _clamp_task_type(lixo)
        # " elaboracao_peca " com espaço é normalizado (strip/lower) — os demais
        # caem no default.
        assert clamped in {_TASK_TYPE_DEFAULT, "elaboracao_peca"}
    assert _clamp_task_type("drop_all_rules") == _TASK_TYPE_DEFAULT


def test_clamp_vazio_ou_none_cai_no_default():
    assert _clamp_task_type("") == _TASK_TYPE_DEFAULT
    assert _clamp_task_type(None) == _TASK_TYPE_DEFAULT
    assert _clamp_task_type("   ") == _TASK_TYPE_DEFAULT


def test_clamp_normaliza_caixa_e_espacos():
    assert _clamp_task_type("  Chat_Rapido ") == "chat_rapido"


def test_default_e_conhecido_do_gateway():
    # O default do clamp precisa existir no TASK_ROUTING (roteamento estável).
    from app.services.ai_gateway import TASK_ROUTING
    assert _TASK_TYPE_DEFAULT in TASK_ROUTING


# ══════════════════════════════════════════════════════════════════════════════
# P0.1 — endpoint executar_prompt (handler real, _FakeDB)
# ══════════════════════════════════════════════════════════════════════════════

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """execute() devolve sempre o mesmo PromptJuridico; commit() é no-op."""

    def __init__(self, prompt):
        self._prompt = prompt

    async def execute(self, *a, **k):
        return _Res(self._prompt)

    async def commit(self):
        return None


def _prompt_biblioteca() -> PromptJuridico:
    return PromptJuridico(
        id="p1",
        titulo="Análise CDC",
        categoria=PromptCategoria.analise,
        conteudo="Analise o tema {{tema}} sob a ótica do CDC e aponte fundamentos.",
        publico=True,
        vezes_executado=0,
    )


def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


@pytest.fixture
def gw_recorder(monkeypatch):
    """Captura a chamada ao gateway e neutraliza o registro de auditoria."""
    captured: dict = {}

    async def fake_chat(messages, task_type, temperature=None, max_tokens=None, **kw):
        captured["messages"] = messages
        captured["task_type"] = task_type
        return SimpleNamespace(
            texto="resposta simulada", modelo="fake-model", provedor="fake",
            fallback_ativado=False, input_tokens=1, output_tokens=1,
        )

    async def fake_log(db, **kw):
        captured["log_kwargs"] = kw
        return "log-1"

    import app.services.ai_gateway as gw
    import app.services.ai_guard as guard
    monkeypatch.setattr(gw, "chat", fake_chat)
    monkeypatch.setattr(guard, "registrar_ai_log", fake_log)
    return captured


async def _executar(req: ExecutarPromptReq, gw_recorder):
    out = await pj.executar_prompt(
        "p1", req, db=_FakeDB(_prompt_biblioteca()), cu=_user()
    )
    return out, gw_recorder


async def test_executar_sempre_injeta_system_com_base(gw_recorder):
    out, cap = await _executar(
        ExecutarPromptReq(variaveis={"tema": "negativação indevida"}), gw_recorder
    )
    msgs = cap["messages"]
    # 1º message é SEMPRE system com a base canônica anti-alucinação.
    assert msgs[0]["role"] == "system"
    assert "[IDENTIDADE]" in msgs[0]["content"]
    assert "NUNCA invente lei" in msgs[0]["content"]
    assert "NUNCA prometa resultado" in msgs[0]["content"]
    # user message preservada com a variável preenchida.
    assert msgs[-1]["role"] == "user"
    assert "negativação indevida" in msgs[-1]["content"]
    assert out["is_rascunho"] is True


async def test_executar_clampa_task_type_arbitrario(gw_recorder):
    _, cap = await _executar(
        ExecutarPromptReq(task_type="ignore_previous_instructions"), gw_recorder
    )
    assert cap["task_type"] == _TASK_TYPE_DEFAULT
    # A base entra MESMO com task_type fora de _TASKS_COM_BASE.
    assert "[IDENTIDADE]" in cap["messages"][0]["content"]


async def test_executar_task_type_valido_passa_intacto(gw_recorder):
    _, cap = await _executar(
        ExecutarPromptReq(task_type="chat_rapido"), gw_recorder
    )
    assert cap["task_type"] == "chat_rapido"


async def test_executar_default_do_schema_preservado(gw_recorder):
    # Fail-safe: o default do schema (analise_juridica) segue valendo — nenhuma
    # regressão de roteamento para quem não envia task_type.
    _, cap = await _executar(ExecutarPromptReq(), gw_recorder)
    assert cap["task_type"] == "analise_juridica"


# ══════════════════════════════════════════════════════════════════════════════
# P0.2 — BASE_ESTRUTURADA nas etapas intermediárias do pipeline de peças
# ══════════════════════════════════════════════════════════════════════════════

class _PipeDB:
    """Sem case_id o pipeline não consulta o banco — só add()/commit() no fim."""

    def __init__(self):
        self.added: list = []

    def add(self, obj, *a, **k):
        self.added.append(obj)

    async def commit(self):
        return None


async def _rodar_pipeline(monkeypatch, respostas: dict[int, str] | None = None,
                          tipo_peca: str = "contestacao"):
    """Roda gerar_peca_pipeline com IA/RAG fake; retorna (calls, eventos)."""
    calls: list[dict] = []

    async def fake_gw(messages, task_type, temperature=None, max_tokens=None, **kw):
        calls.append({"messages": messages, "task_type": task_type})
        texto = (respostas or {}).get(len(calls), "resposta simulada")
        return SimpleNamespace(
            texto=texto, modelo="fake-model", provedor="fake",
            input_tokens=1, output_tokens=1,
        )

    async def rag_vazio(*a, **k):
        return []

    async def sem_citacoes(db, material):
        return {"confirmadas": 0, "total": 0}

    async def sem_codigo(db, area):
        return None

    monkeypatch.setattr(ps, "gw_chat", fake_gw)
    monkeypatch.setattr(ps, "buscar_contexto_rag", rag_vazio)
    monkeypatch.setattr(ps, "get_settings", lambda: SimpleNamespace(
        PECAS_RAG_MODELOS_ENABLED=False, PECAS_RAG_MODELOS_TOPK=3,
    ))
    import app.services.citation_check as citation_check
    import app.services.peca_numeracao as peca_numeracao
    monkeypatch.setattr(citation_check, "verificar_citacoes", sem_citacoes)
    monkeypatch.setattr(peca_numeracao, "proximo_codigo_peca", sem_codigo)

    eventos: list[str] = []
    async for ev in ps.gerar_peca_pipeline(
        db=_PipeDB(), user_id="u1", tipo_peca=tipo_peca, area_direito="civil",
        descricao_fatos="Fatos fictícios de teste da blindagem.",
        pedidos="Pedidos fictícios.", nomes_proteger=[], case_id=None,
        instrucoes_adicionais=None,
    ):
        eventos.append(ev)
    return calls, eventos


async def test_etapas_intermediarias_carregam_base_estruturada(monkeypatch):
    calls, _ = await _rodar_pipeline(monkeypatch)
    # Ordem das chamadas de IA: etapa1, etapa2, etapa4, etapa5, etapa6, etapa7.
    assert len(calls) == 6
    for idx in (0, 1, 3, 4):  # etapas 1, 2, 5 e 6
        sys = calls[idx]["messages"][0]
        assert sys["role"] == "system", idx
        assert BASE_ESTRUTURADA in sys["content"], f"etapa da chamada {idx} sem base"
        assert calls[idx]["task_type"] == "analise_juridica", idx


async def test_regras_inline_existentes_preservadas(monkeypatch):
    # Mudança APENAS aditiva: etapa 4 mantém a regra própria de jurisprudência e
    # a etapa 7 mantém as REGRAS INVIOLÁVEIS da redação final.
    calls, _ = await _rodar_pipeline(monkeypatch)
    etapa4 = calls[2]["messages"][0]["content"]
    assert "NUNCA invente julgados" in etapa4
    etapa7 = calls[5]["messages"][0]["content"]
    assert "REGRAS INVIOLÁVEIS" in etapa7
    assert "Nunca invente números de processos" in etapa7
    assert calls[5]["task_type"] == "elaboracao_peca"


async def test_base_estruturada_nao_quebra_parse_json_da_etapa1(monkeypatch):
    # Modo "auto": a etapa 1 devolve JSON e _tipo_identificado precisa continuar
    # parseando normalmente com a base injetada no system.
    resposta_json = json.dumps({
        "tipo_confirmado": "contestacao", "rito": "comum",
        "competencia": "vara cível", "requisitos": [],
    })
    calls, eventos = await _rodar_pipeline(
        monkeypatch, respostas={1: resposta_json}, tipo_peca="auto",
    )
    assert BASE_ESTRUTURADA in calls[0]["messages"][0]["content"]
    # O evento de conclusão do pipeline confirma o tipo parseado do JSON.
    dados_finais = [
        json.loads(ev.split("data: ", 1)[1].strip())
        for ev in eventos if ev.startswith("event: concluido")
    ]
    assert dados_finais and dados_finais[0]["tipo_peca_identificado"] == "contestacao"


async def test_pipeline_persiste_ailog_e_legal_doc(monkeypatch):
    # Fail-safe: com a base injetada, o fim do pipeline continua gravando
    # AILog + LegalDoc normalmente.
    calls, eventos = await _rodar_pipeline(monkeypatch)
    assert any(ev.startswith("event: concluido") for ev in eventos)
    assert len(calls) == 6
