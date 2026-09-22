"""NER LOCAL (issue #102) — nomes próprios residuais reforçando a barreira LGPD.

Dados FICTÍCIOS (nomes inventados). 100% local: nenhum teste toca rede nem baixa
modelo. Contrato coberto:
  - nome de vítima/testemunha/terceiro em texto livre → pseudonimizado ([PESSOA_n])
    antes do externo (round-trip preservado) OU bloqueia (alta confiança residual);
  - ANTI-REGRESSÃO de super-bloqueio: peça cheia de termos institucionais/jurídicos
    ("Tribunal de Justiça de Minas Gerais", "Ministério Público", "Código de
    Processo Civil", "Banco Central", "São Paulo") NÃO é marcada como pessoa nem
    bloqueia — a chamada externa procede normal;
  - nomes cadastrados no Case (entidades) continuam pseudonimizados (sem regressão);
  - identidade do escritório ("Dr. Clovis José Soares", "De Paula Teixeira
    Advogados") não é tratada como PII de titular;
  - rede de segurança: nome de ALTA confiança EM CLARO → residual 'PESSOA'.
"""
from __future__ import annotations

import pytest

from app.services.ai.ner_local import (
    contem_nome_alta_confianca,
    detectar_nomes,
)
from app.services.ai.pseudonymizer import (
    pseudonimizar,
    reidratar,
    validar_sem_pii_pseudonimizado,
)

# Texto institucional realista — nada aqui é pessoa física.
TEXTO_INSTITUCIONAL = (
    "O Tribunal de Justiça de Minas Gerais negou provimento ao recurso. "
    "O Ministério Público opinou pela improcedência com base no Código de "
    "Processo Civil. O Banco Central regulou a matéria. A audiência ocorreu "
    "em São Paulo perante o Superior Tribunal de Justiça (STJ) e o STF."
)


# ── 1. Detecção de nomes por gatilho (ALTA) e capitalização (MÉDIA) ──────────

def test_detecta_vitima_testemunha_terceiro():
    assert "Maria Oliveira Souza" in detectar_nomes(
        "a vítima Maria Oliveira Souza relatou os fatos"
    )
    assert "Pedro Henrique" in detectar_nomes("o depoente Pedro Henrique afirmou")
    # Terceiro citado só no texto (sem gatilho) mas com nome de 2+ tokens.
    assert "Roberto Carlos Mendes" in detectar_nomes(
        "Depois disso, Roberto Carlos Mendes assinou o documento."
    )


def test_gatilho_pega_nome_de_token_unico():
    # Sem gatilho, um único capitalizado NÃO é nome (evita falso-positivo de
    # início de frase); COM gatilho, um token já basta.
    assert detectar_nomes("Compareceu ao fórum na data marcada.") == []
    assert "Joana" in detectar_nomes("a ré Joana compareceu")


# ── 2. ANTI-REGRESSÃO de super-bloqueio (termos institucionais) ───────────────

def test_institucional_nao_e_pessoa():
    assert detectar_nomes(TEXTO_INSTITUCIONAL) == []
    assert contem_nome_alta_confianca(TEXTO_INSTITUCIONAL) is False


def test_identidade_escritorio_nao_e_pessoa():
    # A identidade do escritório é injetada no system prompt; não é PII de titular.
    texto = (
        "Você é assistente do escritório De Paula Teixeira Advogados Associados "
        "(Betim/MG), do Dr. Clovis José Soares."
    )
    assert detectar_nomes(texto) == []
    assert contem_nome_alta_confianca(texto) is False


# ── 3. Pseudonimização de nomes livres (reforço da barreira) ──────────────────

def test_pseudonimiza_nome_livre_round_trip():
    texto = "A vítima Maria Oliveira Souza relatou que Roberto Carlos Mendes fugiu."
    ps, mapa = pseudonimizar(texto)
    for nome in ("Maria Oliveira Souza", "Roberto Carlos Mendes"):
        assert nome not in ps
    assert "[PESSOA_1]" in ps and "[PESSOA_2]" in ps
    assert reidratar(ps, mapa) == texto  # reversível


def test_mesmo_nome_livre_mesmo_marcador():
    texto = "A testemunha Ana Beatriz Lima confirmou; Ana Beatriz Lima assinou."
    ps, mapa = pseudonimizar(texto)
    assert ps.count("[PESSOA_1]") == 2 and "[PESSOA_2]" not in ps
    assert mapa == {"[PESSOA_1]": "Ana Beatriz Lima"}


def test_institucional_nao_vira_marcador_de_pessoa():
    ps, mapa = pseudonimizar(TEXTO_INSTITUCIONAL)
    assert "[PESSOA_1]" not in ps
    assert not any(k.startswith("[PESSOA_") for k in mapa)
    # Barreira externa NÃO bloqueia (nenhum residual estrutural nem de pessoa).
    assert validar_sem_pii_pseudonimizado(ps) == []


def test_entidade_cadastrada_e_nome_livre_coexistem():
    # Nome cadastrado (entidades) vira [CLIENTE_1]; nome livre (testemunha) vira
    # [PESSOA_1] — sem regressão da pseudonimização de entidades (#103).
    texto = "O cliente João da Silva depôs; a testemunha Carla Menezes confirmou."
    ps, mapa = pseudonimizar(texto, {"cliente": ["João da Silva"]})
    assert "[CLIENTE_1]" in ps and "[PESSOA_1]" in ps
    assert "João da Silva" not in ps and "Carla Menezes" not in ps
    assert reidratar(ps, mapa) == texto


# ── 4. Rede de segurança: alta confiança residual bloqueia; institucional não ─

def test_residual_alta_confianca_sinaliza_pessoa():
    # Texto AINDA em claro (simula nome que escapou da pseudonimização).
    assert "PESSOA" in validar_sem_pii_pseudonimizado(
        "a testemunha Fulano de Tal Sobrinho declarou"
    )


def test_pos_pseudonimizacao_nao_ha_residual_pessoa():
    ps, _ = pseudonimizar("a testemunha Fulano de Tal Sobrinho declarou")
    # Gatilho agora seguido de marcador → sem residual → externo procede.
    assert "PESSOA" not in validar_sem_pii_pseudonimizado(ps)


# ── 5. Gateway ponta a ponta — nome livre nunca chega em claro ao externo ─────

@pytest.fixture
def s(monkeypatch):
    """Baseline determinística: externos habilitados (chaves fake), Ollama off."""
    from app.core.config import get_settings
    st = get_settings()
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
    monkeypatch.setattr(st, "MARITACA_ENABLED", True)
    monkeypatch.setattr(st, "MARITACA_API_KEY", "mk-fake-para-testes")
    monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(st, "AI_PROVIDER_PRIORITY", "groq,maritaca,ollama,anthropic")
    monkeypatch.setattr(st, "ANTHROPIC_AUTO_ROUTING_ENABLED", False)
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "ROTEAMENTO_INTELIGENTE_ENABLED", False)
    return st


async def test_gateway_nome_testemunha_livre_vira_marcador_ao_externo(s, monkeypatch):
    """Nome de testemunha em texto livre (NÃO cadastrado em `entidades`): o
    provider externo recebe [PESSOA_n], nunca o nome real; resposta reidratada."""
    from app.services import ai_gateway
    capturado: dict = {}

    async def _fake_provedor(provider, model, messages, temperature, max_tokens):
        capturado["provider"] = provider
        capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
        return "Parecer sobre [PESSOA_1] concluído.", {
            "model": model or provider, "input_tokens": 3, "output_tokens": 4,
        }

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

    resp = await ai_gateway.chat(
        [{"role": "user", "content": "Resuma: a testemunha Roberto Carlos Mendes viu o fato."}],
        task_type="analise_caso",
    )
    assert capturado["provider"] == "maritaca"
    assert "Roberto Carlos Mendes" not in capturado["conteudo"]  # não vazou
    assert "[PESSOA_1]" in capturado["conteudo"]
    assert "Roberto Carlos Mendes" in resp.texto                 # reidratado
    assert "[PESSOA_1]" not in resp.texto


async def test_gateway_texto_institucional_nao_bloqueia_nem_marca(s, monkeypatch):
    """ANTI-REGRESSÃO: peça cheia de termos institucionais NÃO bloqueia o externo
    e NÃO marca nada como pessoa — a chamada procede normalmente."""
    from app.services import ai_gateway
    capturado: dict = {}

    async def _fake_provedor(provider, model, messages, temperature, max_tokens):
        capturado["provider"] = provider
        capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
        return "Analisado.", {"model": model or provider, "input_tokens": 2, "output_tokens": 1}

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

    resp = await ai_gateway.chat(
        [{"role": "user", "content": TEXTO_INSTITUCIONAL}],
        task_type="analise_caso",
    )
    assert capturado["provider"] == "maritaca"  # não bloqueou
    assert "[PESSOA_1]" not in capturado["conteudo"]        # nada marcado como pessoa
    assert resp.texto == "Analisado."
