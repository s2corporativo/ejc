# ── tests/test_migracao_gateway_fase1b.py ────────────────────────────────────
# FASE 1b — Orquestrador Jurídico (docs/arquivo/planos/MAPA_PROMPTS_IA03.md §5
# Passo 2): a camada
# legada de IA (ai_service 6 funções vivas + ia_extra 5 fluxos + case_intel)
# passa INTEIRAMENTE pelo gateway central com task_type coberto pela barreira
# anti-alucinação (legal_base):
#
#   - PROSA jurídica → task ∈ legal_base._TASKS_COM_BASE (aplicar_base injeta
#     BASE_IDENTIDADE no gateway);
#   - saída JSON estruturada (sugestao_honorarios) → mantém o task do fluxo e
#     PREPENDE BASE_ESTRUTURADA no system (padrão do peca_service);
#   - regras inline dos prompts PRESERVADAS (mudança aditiva);
#   - AILog registra provedor/modelo e tokens REAIS devolvidos pelo gateway
#     (ia_extra não grava mais settings.GROQ_MODEL hardcoded);
#   - get_groq() não existe mais em nenhum módulo (bypass eliminado).
#
# Padrão dos testes de IA do projeto (sem Postgres/IA real): handler/serviço
# chamado direto com _FakeDB; gateway substituído por um recorder que captura
# messages + task_type. Dados 100% fictícios.
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.ai_log import AILog
from app.services import legal_base
from app.services.legal_base import BASE_ESTRUTURADA, _TASKS_COM_BASE


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self):
        self.added: list = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _gw_recorder(calls: list):
    """Recorder do gateway central: captura messages/task_type e devolve
    GatewayResponse-like com provedor/modelo/tokens fake."""
    async def fake_chat(messages, task_type="analise_juridica", **kw):
        calls.append({"messages": messages, "task_type": task_type})
        return SimpleNamespace(
            texto="resposta simulada", modelo="fake-model", provedor="fake",
            task_type=task_type, fallback_ativado=False, usage=None,
            input_tokens=11, output_tokens=22,
        )
    return fake_chat


async def _rag_vazio(*a, **k):
    return []


def _log_unico(db: _FakeDB) -> AILog:
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    return logs[0]


FATOS = (
    "Fatos fictícios de teste: consumidor relata cobrança indevida em fatura "
    "de serviço de telefonia e negativação posterior. Sem dados reais."
)


# ══════════════════════════════════════════════════════════════════════════════
# ai_service — 6 funções vivas
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def svc(monkeypatch):
    import app.services.ai_service as svc
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)
    monkeypatch.setattr(svc, "buscar_contexto_rag", _rag_vazio)
    return svc


async def test_analisar_caso_legada_task_coberto_pela_base(svc, monkeypatch):
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.analisar_caso(db, "u1", FATOS, area="consumidor")
    assert out["resposta"] == "resposta simulada"
    assert len(calls) == 1
    assert calls[0]["task_type"] == "estrategia"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    # Regras inline do prompt mestre preservadas (proteção mais específica).
    sys = calls[0]["messages"][0]
    assert sys["role"] == "system"
    assert "NUNCA invente súmulas" in sys["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_resumir_documento_migrado_para_task_de_prosa(svc, monkeypatch):
    # MAPA (Passo 2, cautela de task_type): resumir_documento vai para task de
    # PROSA coberto — NÃO "resumo" (que fica fora de _TASKS_COM_BASE).
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.resumir_documento(db, "u1", FATOS)
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "chat_rapido"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "Não invente informações" in calls[0]["messages"][0]["content"]
    log = _log_unico(db)
    assert log.modelo == "fake/fake-model"
    assert log.tokens_input == 11 and log.tokens_output == 22


async def test_detectar_teses_ocultas_task_coberto(svc, monkeypatch):
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.detectar_teses_ocultas(db, "u1", FATOS, area="consumidor")
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "estrategia"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "NUNCA invente jurisprudência" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_auditar_peca_task_coberto(svc, monkeypatch):
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.auditar_peca(db, "u1", "Peça fictícia de teste.", "contestacao")
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "auditoria_peca"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "NUNCA invente lei ou jurisprudência" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_preparar_audiencia_task_coberto(svc, monkeypatch):
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.preparar_audiencia(db, "u1", FATOS, "instrução")
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "estrategia"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "nunca invente fatos" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_analisar_contrato_migrado_para_task_de_prosa_coberto(svc, monkeypatch):
    # "analise_contrato" está FORA de _TASKS_COM_BASE (e é usado pelo
    # BankForensicsAgent com saída estruturada) → a análise de contrato, que é
    # PROSA (relatório), migra para "auditoria_peca" (coberto pela base).
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.analisar_contrato(
        db, "u1", "Contrato fictício de prestação de serviços para teste.",
    )
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "auditoria_peca"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "REGRAS INVIOLÁVEIS" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_extrair_prazos_json_prepende_base_estruturada(svc, monkeypatch):
    # MAPA Passo 3 (lacuna Fase 1b): fluxo JSON com task "resumo" (fora de
    # _TASKS_COM_BASE por design) PREPENDE BASE_ESTRUTURADA no system — padrão
    # do peca_service/ia_extra sugestao-honorarios. Parse fail-safe intacto.
    calls: list = []
    monkeypatch.setattr(svc, "gw_chat", _gw_recorder(calls))
    db = _FakeDB()
    out = await svc.extrair_prazos_ia(db, "u1", FATOS)
    assert calls[0]["task_type"] == "resumo"
    sys = calls[0]["messages"][0]
    assert sys["role"] == "system"
    assert BASE_ESTRUTURADA in sys["content"]
    # Regras inline específicas do prompt preservadas (mudança aditiva).
    assert "NUNCA invente prazo" in sys["content"]
    assert "APENAS com JSON" in sys["content"]
    # Resposta não-JSON → nenhum prazo materializado (fail-safe intacto).
    assert out["prazos"] == [] and out["total"] == 0
    assert _log_unico(db).modelo == "fake/fake-model"


# ══════════════════════════════════════════════════════════════════════════════
# ia_extra — 5 fluxos (handler direto, sem HTTP)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def ia_extra_consolidado(monkeypatch):
    import app.routers.ai as mod
    import app.core.config as cfg
    import app.core.config as _cfg_fix
    _st = _cfg_fix.Settings()
    _st.AI_ENABLED = True
    _st.AI_PROVIDER = "groq"
    monkeypatch.setattr(cfg, "get_settings", lambda: _st)
    monkeypatch.setattr(mod, "_buscar_contexto_rag_consolidacao", _rag_vazio)
    return mod


def _cu():
    return SimpleNamespace(id="u1")


async def test_traduzir_andamento_task_de_prosa_coberto(ia_extra_consolidado, monkeypatch):
    calls: list = []
    monkeypatch.setattr(ia_extra_consolidado, "_gw_chat_consolidacao", _gw_recorder(calls))
    db = _FakeDB()
    out = await ia_extra_consolidado.traduzir_andamento(
        ia_extra_consolidado.TraduzirIn(texto=FATOS), db=db, cu=_cu(),
    )
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "chat_rapido"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "Não invente fatos" in calls[0]["messages"][0]["content"]
    log = _log_unico(db)
    # AILog agora registra o provedor/modelo e tokens REAIS do gateway.
    assert log.modelo == "fake/fake-model"
    assert log.tokens_input == 11 and log.tokens_output == 22


async def test_resumir_texto_task_de_prosa_coberto(ia_extra_consolidado, monkeypatch):
    calls: list = []
    monkeypatch.setattr(ia_extra_consolidado, "_gw_chat_consolidacao", _gw_recorder(calls))
    db = _FakeDB()
    out = await ia_extra_consolidado.resumir_texto(
        ia_extra_consolidado.ResumirIn(texto=FATOS), db=db, cu=_cu(),
    )
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "chat_rapido"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "Não invente nada" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


# ── /ai/gerar-minuta: consolidada na porta canônica (Legal Drafting 2.0 §3) ──
# Esta rota tinha PIPELINE PRÓPRIO e era a menos protegida das quatro que
# geravam peça (sem response_validator, sem reforço de sigilo pelo caso real,
# sem scope_case_id), COM consumidor ativo em produção. O invariante que
# importa deixou de ser "qual system prompt ela manda ao gateway" e passou a
# ser "ela delega ao Núcleo Único, herdando todos os gates".
async def test_gerar_minuta_delega_a_porta_canonica(ia_extra_consolidado, monkeypatch):
    from app.services.ai.core import capacidades

    chamadas: list = []
    gw: list = []

    async def _redigir_recorder(db, user, **kw):
        chamadas.append(kw)
        return {
            "conteudo": "minuta simulada", "capacidade": "redigir",
            "tarefa": "minutas", "modelo": "anthropic/claude", "provider": "anthropic",
            "log_id": "log-canonico", "fontes_rag": [{"titulo": "CDC", "categoria": "legislacao"}],
            "citacoes": [], "alertas": ["conferir citação"], "custo_estimado_brl": 0.1,
            "tokens": {"input": 11, "output": 22, "total": 33},
            "is_rascunho": True, "requer_revisao": True, "status_hitl": "gerado",
            "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
        }

    monkeypatch.setattr(capacidades, "redigir", _redigir_recorder)
    # Prova negativa: o gateway NÃO deve mais ser chamado direto por esta rota.
    monkeypatch.setattr(ia_extra_consolidado, "_gw_chat_consolidacao", _gw_recorder(gw))

    db = _FakeDB()
    out = await ia_extra_consolidado.gerar_minuta(
        ia_extra_consolidado.MinutaIn(
            tema="cobrança indevida fictícia", fatos=FATOS, tipo_peca="contestação",
            area="consumidor",
        ),
        db=db, cu=_cu(),
    )

    # 1. Passou pelo Núcleo Único, não pelo gateway direto.
    assert len(chamadas) == 1, "a rota deve delegar a capacidades.redigir"
    assert gw == [], "não pode mais chamar o gateway direto (perderia os gates)"

    # 2. O contrato antigo do request chegou íntegro à porta canônica.
    kw = chamadas[0]
    assert kw["area"] == "consumidor"
    assert kw["opcoes"] == {"tipo_peca": "contestação"}
    assert "cobrança indevida fictícia" in kw["mensagem"]
    assert FATOS in kw["mensagem"]

    # 3. O contrato antigo da RESPOSTA foi preservado — `resposta` é o único
    #    campo que o consumidor (RamoAnalise.tsx) lê.
    assert out["resposta"] == "minuta simulada"
    assert out["ai_log_id"] == "log-canonico"
    assert out["tokens_input"] == 11 and out["tokens_output"] == 22
    assert out["fontes"] == [{"titulo": "CDC", "categoria": "legislacao"}]

    # 4. O envelope canônico (carimbo HITL) vem junto.
    assert out["is_rascunho"] is True
    assert out["status_hitl"] == "gerado"
    assert "revisão humana" in out["aviso_hitl"]

    # 5. Não grava AILog em duplicidade: quem registra é o orquestrador.
    assert db.added == [], "AILog duplicado — o orquestrador já registrou"


async def test_gerar_minuta_propaga_403_de_ownership(ia_extra_consolidado, monkeypatch):
    """Ownership passou a ser do orquestrador; o 403/404 dele não pode virar 502."""
    from fastapi import HTTPException

    from app.services.ai.core import capacidades

    async def _nega(db, user, **kw):
        raise HTTPException(403, "caso de outro cliente")

    monkeypatch.setattr(capacidades, "redigir", _nega)
    with pytest.raises(HTTPException) as e:
        await ia_extra_consolidado.gerar_minuta(
            ia_extra_consolidado.MinutaIn(tema="tema fictício", fatos=FATOS,
                                          case_id="caso-de-terceiro"),
            db=_FakeDB(), cu=_cu(),
        )
    assert e.value.status_code == 403


async def test_pesquisar_task_de_prosa_coberto(ia_extra_consolidado, monkeypatch):
    calls: list = []
    monkeypatch.setattr(ia_extra_consolidado, "_gw_chat_consolidacao", _gw_recorder(calls))
    db = _FakeDB()
    out = await ia_extra_consolidado.pesquisar(
        ia_extra_consolidado.PesquisaIn(pergunta="Qual o prazo de contestação no rito comum?"),
        db=db, cu=_cu(),
    )
    assert out["resposta"] == "resposta simulada"
    assert calls[0]["task_type"] == "estrategia"
    assert calls[0]["task_type"] in _TASKS_COM_BASE
    assert "inventar" in calls[0]["messages"][0]["content"]
    assert _log_unico(db).modelo == "fake/fake-model"


async def test_sugestao_honorarios_json_prepende_base_estruturada(ia_extra_consolidado, monkeypatch):
    # Fluxo de saída JSON: mantém "analise_juridica" (fora da base por design)
    # e PREPENDE BASE_ESTRUTURADA no system — padrão do peca_service.
    calls: list = []
    monkeypatch.setattr(ia_extra_consolidado, "_gw_chat_consolidacao", _gw_recorder(calls))
    db = _FakeDB()
    out = await ia_extra_consolidado.sugestao_honorarios(
        ia_extra_consolidado.HonorariosIn(area="civel", descricao="elaboração de contestação"),
        db=db, cu=_cu(),
    )
    assert calls[0]["task_type"] == "analise_juridica"
    sys = calls[0]["messages"][0]
    assert sys["role"] == "system"
    assert BASE_ESTRUTURADA in sys["content"]
    # Regra inline específica preservada (mudança aditiva).
    assert "NUNCA invente valores" in sys["content"]
    assert out["ai_log_id"]
    assert _log_unico(db).modelo == "fake/fake-model"


# ══════════════════════════════════════════════════════════════════════════════
# case_intel — SYS_TRIAGEM / SYS_ENCERRAMENTO cobertos pela base
# ══════════════════════════════════════════════════════════════════════════════

def test_case_intel_usa_gateway_com_task_coberto():
    # Guard estático: os dois fluxos do case_intel chamam o gateway (gw_chat)
    # com task "estrategia" (∈ _TASKS_COM_BASE) — sem Groq direto.
    import inspect
    import app.services.case_intel as ci
    assert ci.gw_chat is not None
    src_triagem = inspect.getsource(ci.triagem_caso)
    src_encerr = inspect.getsource(ci.aprendizado_encerramento)
    assert 'task_type="estrategia"' in src_triagem
    assert 'task_type="estrategia"' in src_encerr
    assert "estrategia" in _TASKS_COM_BASE


def test_sys_classificar_prepende_base_estruturada():
    # MAPA Passo 3 (lacuna Fase 1b): a classificação de peça p/ RAG
    # (SYS_CLASSIFICAR, fluxo JSON "analise_juridica" — fora da base por
    # design) prepende BASE_ESTRUTURADA no system. Guard estático (o fluxo
    # abre sessão própria via AsyncSessionLocal), mesmo padrão do teste acima.
    import inspect
    import app.services.case_intel as ci
    src = inspect.getsource(ci.indexar_peca_rag)
    assert "BASE_ESTRUTURADA" in src
    assert 'BASE_ESTRUTURADA + "\\n\\n" + SYS_CLASSIFICAR' in src
    # E a base importada no módulo é a canônica de legal_base.
    assert ci.BASE_ESTRUTURADA is BASE_ESTRUTURADA


# ══════════════════════════════════════════════════════════════════════════════
# Invariantes da migração
# ══════════════════════════════════════════════════════════════════════════════

def test_aplicar_base_injeta_identidade_nos_tasks_migrados():
    # Sanidade ponta a ponta da barreira: os task_types escolhidos na migração
    # recebem de fato a BASE_IDENTIDADE no gateway (aplicar_base).
    for task in ("chat_rapido", "estrategia", "auditoria_peca", "elaboracao_peca"):
        msgs = legal_base.aplicar_base(
            [{"role": "system", "content": "regras inline"},
             {"role": "user", "content": "pergunta"}], task,
        )
        assert "[IDENTIDADE]" in msgs[0]["content"], task
        assert "regras inline" in msgs[0]["content"], task  # aditivo, não substitui


def test_get_groq_nao_existe_mais():
    # O bypass legado foi eliminado: nenhum módulo do backend define/importa
    # get_groq; o acesso ao Groq é exclusivo do provider oficial do gateway.
    import app.services.ai_service as svc
    import app.routers.ai as extra
    import app.services.case_intel as ci
    from app.services.providers import groq_provider
    for mod in (svc, extra, ci):
        assert not hasattr(mod, "get_groq"), mod.__name__
    assert hasattr(groq_provider, "chat")  # provider oficial permanece
