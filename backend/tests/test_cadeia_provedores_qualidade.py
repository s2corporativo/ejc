"""Cadeia de provedores e piso de raciocínio (decisão do titular, 18/08).

O titular reportou que o nível de inteligência precisava ser "altíssimo" e
perguntou por que o Ollama estava na configuração. A auditoria do módulo achou
três coisas que puxavam a qualidade para baixo, todas por DEFAULT do código:

  1. `AI_PROVIDER_PRIORITY` começava por "ollama" — um modelo local de 8-14B
     na frente do Claude para redigir peça e analisar caso;
  2. `OLLAMA_ENABLED` nascia True, mas o stack padrão não sobe o serviço
     (profile opt-in "ia-local") — provider morto na frente da cadeia;
  3. o gateway ignorava a priorização por complexidade que a AIProviderPolicy
     já calculava ("tarefa complexa — Anthropic priorizado"), e o piso de
     raciocínio era "padrao" para todo call site que não pedisse nível — que
     é a maioria.

O docker-compose de produção já corrigia (1) e (2) por env; o default do código
não, e valia para tudo que roda fora do compose. Estes testes fixam os defaults
e as regras, para que a próxima mudança de configuração seja deliberada.
"""
from app.core.config import Settings
from app.services import ai_gateway as g


# ── Defaults de configuração ─────────────────────────────────────────────────

def test_prioridade_default_comeca_pelo_modelo_forte():
    ordem = [p.strip() for p in Settings().AI_PROVIDER_PRIORITY.split(",")]
    assert ordem[0] == "anthropic"
    # A IA local fica por último: é rede de segurança, não caminho padrão.
    assert ordem[-1] == "ollama"
    # Sabiá (PT-BR jurídico) antes do generalista.
    assert ordem.index("maritaca") < ordem.index("groq")


def test_ollama_nasce_desligado():
    """Opt-in, como toda integração externa do repo — e como o compose já fazia."""
    assert Settings().OLLAMA_ENABLED is False


def test_piso_de_raciocinio_tem_default_alto():
    s = Settings()
    assert s.AI_NIVEL_INTELIGENCIA_MERITO == "maximo"
    assert s.AI_NIVEL_INTELIGENCIA_PADRAO == "alto"


# ── Piso de raciocínio por perfil de tarefa ──────────────────────────────────

def test_tarefa_de_merito_nasce_no_nivel_maximo():
    for tarefa in ("elaboracao_peca", "analise_juridica", "estrategia",
                   "auditoria_peca", "analise_contrato"):
        assert g._nivel_piso(tarefa) == "maximo", tarefa


def test_alias_de_tarefa_nao_escapa_do_piso_de_merito():
    """"redacao_peca"/"analise_caso" são aliases — normalizados antes do perfil."""
    assert g._nivel_piso("redacao_peca") == "maximo"
    assert g._nivel_piso("analise_caso") == "maximo"


def test_tarefa_de_saida_json_nao_recebe_instrucao_de_prosa():
    """O valor de prazos/honorários/triagem está na fidelidade do formato; a
    elevação delas veio pelo MODELO forte, não por instrução de raciocínio."""
    for tarefa in ("prazos", "honorarios", "triagem"):
        assert g._nivel_piso(tarefa) == "padrao", tarefa


def test_tarefa_economica_continua_economica():
    for tarefa in ("resumo", "chat_rapido"):
        assert g._nivel_piso(tarefa) == "padrao", tarefa


def test_nivel_explicito_do_chamador_prevalece_sobre_o_piso():
    msgs = [{"role": "user", "content": "x"}]
    saida = g._aplicar_nivel(msgs, "padrao", task_label="elaboracao_peca")
    assert "PADRAO" in saida[0]["content"]


def test_sem_nivel_o_piso_entra_no_system(monkeypatch):
    msgs = [{"role": "user", "content": "x"}]
    saida = g._aplicar_nivel(msgs, None, task_label="elaboracao_peca")
    assert saida[0]["role"] == "system"
    assert "MAXIMO" in saida[0]["content"]
    # A mensagem original é preservada (o nível PREPENDA, nunca substitui).
    assert saida[-1] == msgs[0]


# ── Elegibilidade: uma fonte só ──────────────────────────────────────────────

def test_elegibilidade_do_gateway_honra_o_kill_switch_do_groq(monkeypatch):
    """Havia três cópias da regra e só a do registry checava GROQ_ENABLED — o
    kill-switch do Groq dependia de o patch de runtime ter sido instalado."""
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "GROQ_API_KEY", "gk")
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(s, "GROQ_ENABLED", False)
    assert g._provider_elegivel("groq") is False

    from app.services.ai.provider_policy import AIProviderPolicy

    assert AIProviderPolicy._elegivel("groq") is False

    monkeypatch.setattr(s, "GROQ_ENABLED", True)
    assert g._provider_elegivel("groq") is True


# ── Efeito colateral de não haver IA local ───────────────────────────────────

def test_areas_de_sigilo_reforcado_sao_nomeadas():
    """Sem IA local, a IA destas áreas fica indisponível — fail-closed."""
    from app.services.ai.sanitization_policy import areas_que_exigem_ia_local

    areas = areas_que_exigem_ia_local()
    for area in ("criminal", "familia", "saude", "menores", "violencia"):
        assert area in areas, area


def test_painel_de_saude_avisa_quando_essas_areas_ficam_sem_ia(monkeypatch):
    """O advogado não pode descobrir isso só ao tentar usar e receber erro."""
    from app.core.config import get_settings
    from app.routers.ia_saude import _estado_sigilo_reforcado

    monkeypatch.setattr(get_settings(), "OLLAMA_ENABLED", False)
    estado = _estado_sigilo_reforcado()
    assert estado["ia_local_disponivel"] is False
    assert estado["ia_indisponivel_nessas_areas"] is True
    assert estado["areas"]

    monkeypatch.setattr(get_settings(), "OLLAMA_ENABLED", True)
    estado = _estado_sigilo_reforcado()
    assert estado["ia_local_disponivel"] is True
    assert estado["ia_indisponivel_nessas_areas"] is False


def test_mensagem_de_bloqueio_diz_as_duas_saidas():
    """"Habilite o Ollama" não era a única saída — e nem sempre é a certa."""
    from app.services.ai_gateway import _MSG_BLOQUEIO_LOCAL_COMPLETO as msg

    assert "OLLAMA_ENABLED=true" in msg
    assert "AI_SANITIZATION_MODE_MAP" in msg
    assert "decisão do titular" in msg


# ── Retrieval RAG: pernas aditivas ligadas por padrão (18/08) ───────────────

def test_hyde_e_fts_nascem_ligados():
    """Decisão do titular: nível de inteligência altíssimo. Ambas as pernas são
    ADITIVAS à fusão RRF e fail-safe (erro cai no comportamento de antes) — não
    há como piorar recall, só somar candidato. O reranker continua OFF: é o
    único item aqui genuinamente bloqueado (licença não comercial do único
    cross-encoder multilíngue do fastembed pinado; o MIT precisa de eval em
    corpus jurídico pt-BR antes de entrar)."""
    s = Settings()
    assert s.RAG_HYDE_ENABLED is True
    assert s.RAG_FTS_ENABLED is True
    assert s.RAG_RERANK_ENABLED is False
