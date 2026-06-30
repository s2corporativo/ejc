"""Router de modelos/prompts por tarefa. Critério: qualidade mínima × custo × velocidade.
CUSTO BAIXO: Groq (grátis) p/ tarefas simples; Claude Haiku (barato) p/ o resto;
Claude COMPLEXO via env (default Haiku — suba para sonnet quando quiser mais qualidade)."""
import os
from enum import Enum
from dataclasses import dataclass

# Modelos vêm do .env (configuráveis sem deploy). Defaults econômicos.
_RAPIDO = os.getenv("ANTHROPIC_MODEL_RAPIDO", "claude-haiku-4-5-20251001")
# Para custo baixo, COMPLEXO também default Haiku; defina claude-sonnet-4-6 no .env p/ máxima qualidade.
_COMPLEXO = os.getenv("ANTHROPIC_MODEL_COMPLEXO", _RAPIDO)
_GROQ = "llama-3.3-70b-versatile"


class TarefaIA(str, Enum):
    TRIAGEM = "triagem"
    ANALISE_CASO = "analise_caso"
    DOSSIE = "dossie"
    MINUTAS = "minutas"
    PRAZOS = "prazos"
    HONORARIOS = "honorarios"
    AMBIENTAL = "ambiental"
    TRABALHISTA = "trabalhista"
    CRIMINAL = "criminal"
    FAMILIA = "familia"
    PESQUISA_JURIDICA = "pesquisa_juridica"
    RESUMO = "resumo"
    AUDIENCIA = "audiencia"
    RAG_QUERY = "rag_query"
    DEFAULT = "default"


@dataclass
class ConfiguracaoIA:
    provider: str          # "groq" | "anthropic"
    model: str | None
    prompt_key: str
    max_tokens: int
    temperature: float
    justificativa: str


def _groq(prompt_key, mt=1000, temp=0.1, just=""):
    return ConfiguracaoIA("groq", _GROQ, prompt_key, mt, temp, just)


def _claude(prompt_key, model, mt, temp, just):
    return ConfiguracaoIA("anthropic", model, prompt_key, mt, temp, just)


CONFIGURACOES: dict[TarefaIA, ConfiguracaoIA] = {
    # Grátis (Groq) — classificação/sumarização
    TarefaIA.TRIAGEM:  _groq("triagem", 1200, 0.1, "Classificação estruturada — Groq grátis"),
    TarefaIA.RESUMO:   _groq("resumo", 900, 0.2, "Sumarização simples — Groq grátis"),
    # Barato (Claude Haiku) — tarefas factuais/médias
    TarefaIA.PRAZOS:      _claude("prazos", _RAPIDO, 1200, 0.0, "Prazo fatal — precisão (temp 0)"),
    TarefaIA.HONORARIOS:  _claude("honorarios", _RAPIDO, 1800, 0.1, "Honorários OAB/MG"),
    TarefaIA.AUDIENCIA:   _claude("audiencia", _RAPIDO, 2000, 0.2, "Preparação de audiência"),
    TarefaIA.RAG_QUERY:   _claude("rag_query", _RAPIDO, 1500, 0.1, "Síntese de RAG"),
    # Complexo (Claude — env COMPLEXO; default Haiku p/ custo baixo)
    TarefaIA.ANALISE_CASO: _claude("analise_caso", _COMPLEXO, 4000, 0.1, "Análise estratégica"),
    TarefaIA.DOSSIE:       _claude("analise_caso", _COMPLEXO, 5000, 0.1, "Dossiê completo"),
    TarefaIA.MINUTAS:      _claude("minutas", _COMPLEXO, 6000, 0.15, "Redação de peças"),
    TarefaIA.AMBIENTAL:    _claude("ambiental", _COMPLEXO, 4000, 0.1, "Direito ambiental técnico"),
    TarefaIA.TRABALHISTA:  _claude("analise_caso", _COMPLEXO, 3500, 0.1, "CLT + TST"),
    TarefaIA.CRIMINAL:     _claude("analise_caso", _COMPLEXO, 3000, 0.1, "Criminal — sensível"),
    TarefaIA.FAMILIA:      _claude("analise_caso", _COMPLEXO, 3000, 0.1, "Família — sensível"),
    TarefaIA.PESQUISA_JURIDICA: _claude("pesquisa_juridica", _COMPLEXO, 3000, 0.2, "Pesquisa jurisprudencial"),
    TarefaIA.DEFAULT:      _claude("default", _RAPIDO, 2000, 0.2, "Fallback — Haiku"),
}


def get_configuracao(tarefa: TarefaIA) -> ConfiguracaoIA:
    return CONFIGURACOES.get(tarefa, CONFIGURACOES[TarefaIA.DEFAULT])
