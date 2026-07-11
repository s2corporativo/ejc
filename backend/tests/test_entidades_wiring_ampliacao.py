"""PR #85 (ampliação) — fiação de `entidades` (pseudonimização REVERSÍVEL de
nomes) nos call sites de IA migrados de `nomes_proteger` (irreversível):

  • app/services/analise_estrategica.py::analisar_caso     (task estrategia)
  • app/services/peca_service.py::gerar_peca_pipeline        (task minutas/peça)
  • app/services/ai_service.py::detectar_teses_ocultas       (task estrategia)

Objetivo dos testes: com um Case REAL (servido por fake de sessão, sem
Postgres), o provider EXTERNO recebe o marcador ([CLIENTE_1]) e NÃO o nome real,
e a resposta devolvida ao chamador volta REIDRATADA com o nome real. Todos os
dados são FICTÍCIOS.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.models.case import Case
from app.models.client import Client, ClientTipo


# ── Fakes de sessão (sem banco; padrão de test_entidades_caso.py) ────────────
class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def all(self):
        # Padrão-ouro: a etapa 7 do pipeline consulta as provas do caso via
        # .all(); estes testes exercitam o wiring de entidades SEM acervo
        # probatório — lista vazia cai no caminho de placeholders.
        return []


class _FakeDB:
    """execute() sempre devolve o mesmo Case; add() captura as linhas gravadas."""

    def __init__(self, caso):
        self._caso = caso
        self.added: list = []

    async def execute(self, *a, **k):
        return _Res(self._caso)

    def add(self, obj, *a, **k):
        self.added.append(obj)

    async def commit(self):
        return None


def _caso_com_cliente(nome: str = "João da Silva") -> Case:
    cli = Client(id="cli1", tipo=ClientTipo.PF, nome=nome)
    return Case(
        id="c1", titulo="Ação fictícia", client_id="cli1", deleted_at=None,
        client=cli, partes=[], advogado_responsavel=None, parte_contraria=None,
    )


@pytest.fixture
def s(monkeypatch):
    """Settings determinística: Anthropic/Groq com chave fake, Ollama off,
    externos permitidos e barreira de sanitização ligada (força o caminho de
    pseudonimização reversível antes do provider externo)."""
    st = get_settings()
    monkeypatch.setattr(st, "AI_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
    monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    return st


# ══════════════════════════════════════════════════════════════════════════════
# 1. analise_estrategica.analisar_caso — end-to-end via gateway real
# ══════════════════════════════════════════════════════════════════════════════
class TestAnaliseEstrategicaWiring:
    async def test_pseudonimiza_e_reidrata(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services import analise_estrategica as mod

        caso = _caso_com_cliente("João da Silva")
        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            # Provider "externo" responde em JSON referindo-se ao marcador.
            return (
                '{"tese_principal": "responsabilidade civil de [CLIENTE_1]", '
                '"riscos": []}',
                {"model": model or provider, "input_tokens": 3, "output_tokens": 4},
            )

        async def _rag_vazio(*a, **k):
            return []

        async def _sem_citacoes(db, material):
            return {"confirmadas": 0, "total": 0}

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)
        # buscar_contexto_rag é importado em runtime de app.services.ai_service.
        import app.services.ai_service as ai_service
        monkeypatch.setattr(ai_service, "buscar_contexto_rag", _rag_vazio)
        import app.services.citation_check as citation_check
        monkeypatch.setattr(citation_check, "verificar_citacoes", _sem_citacoes)

        resultado = await mod.analisar_caso(
            titulo="Ação de indenização",
            fatos="O cliente João da Silva sofreu dano moral pela negativação indevida.",
            area="civel",
            case_id="c1",
            db=_FakeDB(caso),
        )

        # provider externo recebeu o MARCADOR, nunca o nome real.
        assert "[CLIENTE_1]" in capturado["conteudo"]
        assert "João da Silva" not in capturado["conteudo"]
        # resposta devolvida ao chamador foi REIDRATADA com o nome real.
        assert resultado.get("tese_principal") == "responsabilidade civil de João da Silva"
        assert "[CLIENTE_1]" not in resultado.get("tese_principal", "")

    async def test_sem_case_id_mantem_mascaramento_legado(self, s, monkeypatch):
        """Sem case_id/db o nome é mascarado IRREVERSÍVEL via nomes_proteger
        (comportamento legado preservado): não reidrata."""
        from app.services import ai_gateway
        from app.services import analise_estrategica as mod

        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            return (
                '{"tese_principal": "análise de [PARTE_1]"}',
                {"model": model or provider, "input_tokens": 1, "output_tokens": 1},
            )

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        resultado = await mod.analisar_caso(
            titulo="Ação",
            fatos="Fatos do caso envolvendo Maria Oliveira e a parte adversa.",
            area="civel",
            nomes_proteger=["Maria Oliveira"],
            db=None,  # sem db → sem entidades → mascaramento legado
        )
        # nome mascarado (irreversível) antes de sair; não reidrata.
        assert "Maria Oliveira" not in capturado["conteudo"]
        assert "[PARTE_1]" in capturado["conteudo"]
        assert resultado.get("tese_principal") == "análise de [PARTE_1]"


# ══════════════════════════════════════════════════════════════════════════════
# 2. ai_service.detectar_teses_ocultas — end-to-end via gateway real
# ══════════════════════════════════════════════════════════════════════════════
class TestTesesOcultasWiring:
    async def test_pseudonimiza_e_reidrata(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services import ai_service

        caso = _caso_com_cliente("João da Silva")
        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            return (
                "Tese oculta aplicável a [CLIENTE_1]: prescrição intercorrente.",
                {"model": model or provider, "input_tokens": 2, "output_tokens": 3},
            )

        async def _rag_vazio(*a, **k):
            return []

        log_capt: dict = {}

        async def _cap_log(db, user_id, tipo, prompt, resposta, *a, **k):
            log_capt["prompt"] = prompt
            log_capt["resposta"] = resposta
            return None

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)
        monkeypatch.setattr(ai_service, "buscar_contexto_rag", _rag_vazio)
        monkeypatch.setattr(ai_service, "_log_ai", _cap_log)

        r = await ai_service.detectar_teses_ocultas(
            _FakeDB(caso), "u1",
            "Os fatos narram que João da Silva teve o nome negativado por engano.",
            "civel", tese_principal="dano moral", case_id="c1",
        )

        assert "[CLIENTE_1]" in capturado["conteudo"]
        assert "João da Silva" not in capturado["conteudo"]   # não vaza ao externo
        assert "João da Silva" in r["resposta"]               # resposta reidratada
        assert "[CLIENTE_1]" not in r["resposta"]
        # AILog.prompt_sanitizado (SEM PII): nome pseudonimizado, não em claro.
        assert "João da Silva" not in log_capt["prompt"]
        assert "[CLIENTE_1]" in log_capt["prompt"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. peca_service.gerar_peca_pipeline — fiação (entidades ao gateway; fatos não
#    pré-mascarados) via captura das chamadas gw_chat.
# ══════════════════════════════════════════════════════════════════════════════
class TestPecaPipelineWiring:
    async def test_entidades_passadas_e_fatos_nao_pre_mascarados(self, s, monkeypatch):
        from app.services import peca_service

        chamadas: list[dict] = []

        async def _fake_gw_chat(messages, **kw):
            chamadas.append({
                "entidades": kw.get("entidades"),
                "conteudo": " ".join(m.get("content", "") for m in messages),
                "task_type": kw.get("task_type"),
            })
            from app.services.ai_gateway import GatewayResponse
            # devolve JSON simples p/ etapa 1 e texto para as demais.
            return GatewayResponse(
                texto='{"tipo_confirmado": "peticao_inicial"}',
                modelo="fake", provedor="ollama", task_type=kw.get("task_type"),
                input_tokens=1, output_tokens=1,
            )

        async def _entidades(db, case_id):
            return {"cliente": ["João da Silva"]}

        async def _rag_vazio(*a, **k):
            return []

        async def _sem_citacoes(db, material):
            return {"confirmadas": 0, "total": 0}

        monkeypatch.setattr(peca_service, "gw_chat", _fake_gw_chat)
        monkeypatch.setattr(peca_service, "buscar_contexto_rag", _rag_vazio)
        import app.services.ai.entidades_caso as ent_mod
        monkeypatch.setattr(ent_mod, "entidades_do_caso", _entidades)
        import app.services.citation_check as citation_check
        monkeypatch.setattr(citation_check, "verificar_citacoes", _sem_citacoes)

        # consome o gerador SSE por completo.
        db = _FakeDB(_caso_com_cliente("João da Silva"))
        chunks = []
        async for chunk in peca_service.gerar_peca_pipeline(
            db=db,
            user_id="u1",
            tipo_peca="peticao_inicial",
            area_direito="consumidor",
            descricao_fatos="João da Silva foi cobrado indevidamente pelo banco.",
            pedidos="Restituição em dobro para João da Silva.",
            nomes_proteger=["João da Silva"],
            case_id="c1",
            instrucoes_adicionais=None,
        ):
            chunks.append(chunk)

        # Todas as chamadas de IA receberam as entidades do caso.
        assert chamadas, "nenhuma chamada gw_chat capturada"
        assert all(c["entidades"] == {"cliente": ["João da Silva"]} for c in chamadas)
        # Com entidades, os fatos NÃO são pré-mascarados: o nome real chega ao
        # gateway (que fará a pseudonimização reversível), não [PARTE_1].
        etapa_com_fatos = next(
            (c for c in chamadas if "João da Silva" in c["conteudo"]), None
        )
        assert etapa_com_fatos is not None
        assert not any("[PARTE_1]" in c["conteudo"] for c in chamadas)

        # AILog.prompt_sanitizado (contrato "SEM PII"): com entidades ativo, o
        # valor gravado é PSEUDONIMIZADO — sem nome em claro, com marcador.
        from app.models.ai_log import AILog
        log = next(o for o in db.added if isinstance(o, AILog))
        assert "João da Silva" not in (log.prompt_sanitizado or "")
        assert "[CLIENTE_1]" in (log.prompt_sanitizado or "")
