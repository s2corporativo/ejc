"""Invariante do gateway LEGADO (app.core.ai_brain) — auditoria #4a.

Trava a regressão de segurança mais perigosa da consolidação de gateways de IA:
que o shim legado `AIGateway` volte a abrir um SEGUNDO caminho de execução
(httpx direto ao Ollama/provider), FORA do gateway canônico
`app.services.ai_gateway.chat`. O caminho canônico é quem aplica a cadeia de
providers por prioridade, a barreira final de PII (LGPD) e o custo/roteamento.

Dois niveis de trava:
  1. ESTÁTICO — o fonte de ai_brain.py não pode conter transporte direto a
     provider (httpx/AsyncClient/endpoints de LLM/clients de provider).
  2. COMPORTAMENTAL — cada método público do shim delega a ai_gateway.chat e,
     em erro, devolve mensagem segura (sem propagar exceção/stack ao chamador).
"""
import ast
import inspect

import app.core.ai_brain as ai_brain_mod
from app.core.ai_brain import ai_brain, ai_gateway, _ERRO_SEGURO


class _FakeResp:
    """Mínimo do contrato GatewayResponse usado pelo shim (_chamar_central)."""

    def __init__(self, texto="RESPOSTA CANÔNICA"):
        self.texto = texto
        self.provedor = "ollama"
        self.modelo = "modelo-fake"


def _instalar_fake_chat(monkeypatch):
    """Substitui ai_gateway.chat por um espião; retorna a lista de chamadas."""
    chamadas: list[dict] = []

    async def fake_chat(messages, task_type="analise_juridica", **kwargs):
        chamadas.append({"messages": messages, "task_type": task_type, "kwargs": kwargs})
        return _FakeResp()

    # O shim faz `from app.services import ai_gateway as gateway_central` e chama
    # gateway_central.chat(...): monkeypatch no atributo do MÓDULO cobre isso.
    import app.services.ai_gateway as gateway_central
    monkeypatch.setattr(gateway_central, "chat", fake_chat)
    return chamadas


# ─────────────────────────── 1. Invariante estático ───────────────────────────

def test_ai_brain_nao_importa_transporte_de_provedor():
    """O shim não pode IMPORTAR biblioteca de transporte/cliente de provider.

    Análise por AST (não substring): menções a 'httpx' em docstring/comentário
    são documentação legítima ("não há mais httpx direto aqui") e não devem
    reprovar — o que reintroduziria um 2º caminho de execução é um IMPORT real.
    """
    arvore = ast.parse(inspect.getsource(ai_brain_mod))
    _PROIBIDOS = {"httpx", "aiohttp", "requests", "anthropic", "groq", "ollama", "openai"}
    importados: set[str] = set()
    delega_ao_gateway = False
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import):
            importados.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                importados.add(node.module.split(".")[0])
                # from app.services import ai_gateway → delegação canônica.
                if node.module.startswith("app.services") and any(
                    a.name == "ai_gateway" for a in node.names
                ):
                    delega_ao_gateway = True

    reintroduzidos = importados & _PROIBIDOS
    assert not reintroduzidos, (
        f"ai_brain.py voltou a importar transporte de provider: {reintroduzidos}. "
        "Todo tráfego de IA deve passar por app.services.ai_gateway.chat."
    )
    assert delega_ao_gateway, \
        "ai_brain.py deve delegar ao gateway canônico (from app.services import ai_gateway)."


# ────────────────────────── 2. Invariante comportamental ──────────────────────

async def test_generate_delega_ao_gateway_canonico(monkeypatch):
    chamadas = _instalar_fake_chat(monkeypatch)
    out = await ai_brain.generate("analisar contrato", modo="principal")
    assert out == "RESPOSTA CANÔNICA"
    assert len(chamadas) == 1, "generate deve chamar ai_gateway.chat exatamente uma vez"
    # modo principal → tipo juridico_profundo → task_type analise_juridica.
    assert chamadas[0]["task_type"] == "analise_juridica"


async def test_processar_demanda_delega_e_mantem_shape(monkeypatch):
    chamadas = _instalar_fake_chat(monkeypatch)
    res = await ai_gateway.processar_demanda("demanda", contexto="ctx", tipo="juridico_profundo")
    assert set(res) == {"modelo_utilizado", "tipo_demanda", "resposta", "status"}
    assert res["resposta"] == "RESPOSTA CANÔNICA"
    assert res["status"] == "sucesso"
    assert len(chamadas) == 1
    assert chamadas[0]["task_type"] == "analise_juridica"


async def test_call_ollama_legado_nao_fala_direto_com_ollama(monkeypatch):
    """O nome é histórico; o corpo DEVE delegar ao gateway canônico."""
    chamadas = _instalar_fake_chat(monkeypatch)
    out = await ai_gateway._call_ollama("deepseek-r1:14b", "prompt qualquer")
    assert out == "RESPOSTA CANÔNICA"
    assert len(chamadas) == 1, "_call_ollama deve delegar, nunca abrir conexão própria"


async def test_modo_duas_ias_faz_duas_passagens_pelo_canonico(monkeypatch):
    chamadas = _instalar_fake_chat(monkeypatch)
    res = await ai_gateway.modo_duas_ias("demanda", contexto="ctx")
    assert {"analise_principal", "analise_critica"} <= set(res)
    # IA 1 (análise) + IA 2 (crítica) = duas passagens pelo gateway canônico.
    assert len(chamadas) == 2


async def test_erro_do_gateway_vira_mensagem_segura_sem_propagar(monkeypatch):
    """Falha do provider não pode vazar exceção/stack ao chamador do shim."""
    async def chat_que_estoura(messages, task_type="analise_juridica", **kwargs):
        raise RuntimeError("provider offline: segredo-que-nao-pode-vazar")

    import app.services.ai_gateway as gateway_central
    monkeypatch.setattr(gateway_central, "chat", chat_que_estoura)

    out = await ai_brain.generate("qualquer", modo="secundario")
    assert out == _ERRO_SEGURO
    assert "segredo-que-nao-pode-vazar" not in out
