# ── tests/test_ai_log_prompt_composto_sem_pii.py ──────────────────────────────
# Módulo 1 (P0) do programa TRANSFORMACAO_INTELIGENCIA_EJC — baseline 7034f2b.
#
# Defeito reproduzido (A): `ai_service.analisar_caso` grava em
# `AILog.prompt_sanitizado` o prompt COMPOSTO (dossiê + precedentes internos +
# contexto RAG + fatos) sem sanitização final. A sanitização do chamador cobre
# só `descricao_fatos`; o resto do prompt é inserido cru. A coluna cujo contrato
# é "sem PII" recebia nome de cliente, parte-contrária e trecho de precedente.
#
# Defeito relacionado (o `resposta` já era coberto por `@validates` do model —
# este arquivo trava essa paridade para o PROMPT): a garantia passou a viver
# na barreira (`AILog.pseudonimizar_texto_auditoria`), não na disciplina de
# cada call site.
#
# PII sintética apenas. Sem banco, sem rede, sem provider real.
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.ai_log import AILog
from app.services.ai_gateway import GatewayResponse

# PII sintética — não corresponde a pessoa real.
NOME_CLIENTE = "Maria Sintetica da Silva"
PARTE = "Joao Sintetico de Souza"
CPF = "529.982.247-25"


def _log_objeto(prompt: str, resposta: str) -> AILog:
    """Constrói o MESMO objeto que o call site entrega ao INSERT — a barreira
    do model roda aqui, como roda em produção."""
    return AILog(
        id="log-1",
        user_id="u1",
        case_id="c1",
        tipo_uso="analise_caso",
        modelo="groq/modelo-x",
        prompt_sanitizado=prompt[:8000],
        pii_removida=True,
        resposta=resposta,
        status_hitl="gerado",
    )


# ── 1) a barreira do model ──────────────────────────────────────────────────

def test_prompt_composto_com_pii_e_pseudonimizado_na_persistencia():
    prompt = (
        "ÁREA JURÍDICA: consumidor\n\n"
        f"[DOSSIÊ] Cliente: {NOME_CLIENTE}, CPF {CPF}\n"
        f"[PRECEDENTES INTERNOS] ContraParte: {PARTE}\n"
        f"[FONTES] Proc. 1234567-89.2024.8.13.0100涉及 {NOME_CLIENTE}\n"
        f"FATOS DO CASO (sanitizados): contrato_failado.\n"
    )
    log = _log_objeto(prompt, "RASCUNHO: tese de revisão contratual.")
    persistido = str(log.prompt_sanitizado)
    assert NOME_CLIENTE not in persistido
    assert PARTE not in persistido
    assert CPF not in persistido
    # o identificador do processo (numeração CNJ) é preservado: é citação
    # verificável, não PII, e a coluna precisa dele para rastrear a fonte.
    assert "1234567-89.2024.8.13.0100" in persistido


def test_resposta_reidratada_e_pseudonimizada_na_persistencia():
    """Paridade com o prompt: a resposta que o gateway reidratou (nomes reais
    trocados de volta) não pode chegar ao banco em claro."""
    resposta = f"Proposta: revisar o contrato de {NOME_CLIENTE} (CPF {CPF})."
    log = _log_objeto("prompt", resposta)
    persistido = str(log.resposta)
    assert NOME_CLIENTE not in persistido
    assert CPF not in persistido


def test_marcadores_estruturais_sobrevive_ao_pseudonimizador():
    """O pseudonimizador não pode corromper o cabeçalho estrutural que
    `citation_gate` usa para localizar a peça no relatório."""
    log = _log_objeto(
        "═══ CRÍTICA ADVERSARIAL ═══\ntexto", "resposta"
    )
    assert "═══ CRÍTICA ADVERSARIAL ═══" in str(log.prompt_sanitizado)


# ── 2) o gateway transporta as DUAS versões ─────────────────────────────────

def test_gateway_response_transporta_versao_de_log_sem_pii_real():
    resp = GatewayResponse(
        texto=f"Tese sobre {PARTE}.",
        texto_para_log="Tese sobre [PARTE_1].",
        modelo="m", provedor="groq", task_type="estrategia",
    )
    assert resp.texto_para_log == "Tese sobre [PARTE_1]."
    assert resp.texto != resp.texto_para_log


@pytest.mark.anyio
async def test_chat_nao_persiste_resposta_reidratada_no_cache(monkeypatch):
    """O cache (Redis/memória) é armazenamento persistente: a resposta
    reidratada com PII real não pode ser gravada nele (paridade com
    `executar_tarefa_ia`, que já restringe o cache a `not pii_removida_log`)."""
    from app.services import ai_cache, ai_gateway as gw

    gravado: dict = {}

    async def _gravar(key, valor):
        gravado.update(valor)

    async def _obter(_key):
        return None  # sem cache prévio: exercita o caminho de gravação

    # `ai_cache` é importado DENTRO de chat() — o patch vai no módulo, não no
    # atributo do gateway.
    monkeypatch.setattr(ai_cache, "gravar", _gravar)
    monkeypatch.setattr(ai_cache, "obter", _obter)
    monkeypatch.setattr(ai_cache, "chave", lambda *a, **k: "k1")

    # Finta no `chat` do PROVIDER (mesmo contrato: (texto, usage dict)) — a
    # barreira, a cadeia, o cache e a reidratação são os reais.
    from app.services.providers import groq_provider

    async def _provedor_externo(messages, model, temperature, max_tokens):
        # devolve o marcador pseudonimizado, como o provider real receberia
        return "Tese sobre [PARTE_1].", {
            "model": "m", "input_tokens": 1, "output_tokens": 1,
            "finish_reason": "stop",
        }

    # A barreira REAL roda (só a preparação externa é finta): ela reidrata o
    # texto com o mapa e devolve as DUAS versões. É exatamente esse contrato
    # que se está travando.
    mapa = {"[PARTE_1]": PARTE}

    def _prep(messages, modo, entidades=None):  # síncrona, como no gateway
        return ([{"role": m["role"], "content": "[PARTE_1]"} for m in messages],
                [], mapa)

    monkeypatch.setattr(groq_provider, "chat", _provedor_externo)
    monkeypatch.setattr(gw, "_preparar_mensagens_externo", _prep)
    monkeypatch.setattr(gw.settings, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    # Elegibilidade real de provider depende de chave/flag; o que se mede aqui
    # é o comportamento do cache, então a cadeia é fixada.
    monkeypatch.setattr(gw, "_resolver_cadeia", lambda *a, **k: [("groq", "m")])
    monkeypatch.setattr(gw.settings, "AI_RESPONSE_CACHE_ENABLED", True)

    resp = await gw.chat(
        messages=[{"role": "user", "content": "fatos"}],
        task_type="estrategia", provider_override="groq",
    )
    assert PARTE in resp.texto               # o usuário lê a versão reidratada
    assert PARTE not in resp.texto_para_log  # o log nunca vê PII real
    assert PARTE not in str(gravado.get("texto", ""))  # o cache nunca vê PII real
    assert resp.texto_para_log in str(gravado.get("texto", ""))  # cache = versão segura


# ── 3) o call site: o que o INSERT recebe, fim a fim (sem ORM flush) ─────────

class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.anyio
async def test_analisar_caso_nao_persiste_pii_real_no_ailog(monkeypatch):
    """Cenário de produção do defeito A: PII entra pelo DOSSIÊ e pelos
    PRECEDENTES INTERNOS (não por `descricao_fatos`, que já é sanitizado) e a
    resposta volta REIDRATADA do gateway. O objeto entregue ao INSERT não pode
    conter nenhum dos dois."""
    from app.services import ai_service as svc

    async def _falsa_busca_rag(*a, **k):
        return [{
            "titulo": "Precedente interno",
            "conteudo": f"no caso anterior de {PARTE} houve leaky gasket...",
            "chunk_id": "c-1",
        }]

    async def _dossie(*a, **k):
        return {
            "texto": f"[CLIENTE] {NOME_CLIENTE} — CPF {CPF}",
            "nomes_proteger": [NOME_CLIENTE, PARTE],
        }

    async def _escopo(*a, **k):
        return "cli-1"

    async def _sigilo(*a, **k):
        return None

    async def _gateway_text(system, user_prompt, **kw):
        # devolve a resposta REIDRATADA, como o gateway faz em modo reversível
        return (
            f"TESE: exigir indenização de {NOME_CLIENTE} por {PARTE}.",
            GatewayResponse(
                texto=f"TESE: exigir indenização de {NOME_CLIENTE} por {PARTE}.",
                texto_para_log="TESE: exigir indenização de [PARTE_1] por [PARTE_2].",
                modelo="m", provedor="groq", task_type="estrategia",
                input_tokens=10, output_tokens=20,
            ),
        )

    monkeypatch.setattr(svc, "buscar_contexto_rag", _falsa_busca_rag)
    monkeypatch.setattr(svc, "montar_dossie", _dossie)
    monkeypatch.setattr(svc, "_escopo_cliente_do_caso", _escopo)
    monkeypatch.setattr(svc, "_modo_sigilo_caso", _sigilo)
    monkeypatch.setattr(svc, "_gateway_text", _gateway_text)
    monkeypatch.setattr(svc, "settings", SimpleNamespace(AI_ENABLED=True, GROQ_MODEL="m"))
    monkeypatch.setattr(svc, "_modelo_para_prompt", lambda p: None)

    db = _FakeDB()
    out = await svc.analisar_caso(
        db, "u1", "contrato failado por vazamento", "consumidor", case_id="c1",
    )
    assert "erro" not in out, out
    assert len(db.added) == 1
    log = db.added[0]
    persistido = f"{log.prompt_sanitizado}\n{log.resposta}"
    for pii in (NOME_CLIENTE, PARTE, CPF):
        assert pii not in persistido, f"PII real persistida: {pii}"
    # a rastreabilidade permanece: fonte RAG referenciada no log
    assert log.fontes_rag == "c-1"
    # o usuário continua recebendo a versão reidratada (UX não regride)
    assert NOME_CLIENTE in out["resposta"]
