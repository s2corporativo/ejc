"""Router de modelos/prompts por tarefa. Critério: qualidade mínima × custo × velocidade.
Groq (grátis) p/ tarefas simples; Claude Haiku (barato) p/ tarefas factuais;
Claude COMPLEXO via env (default claude-opus-4-8 — máxima qualidade jurídica;
para reduzir custo, defina claude-sonnet-5 ou Haiku no .env)."""
from enum import Enum
from dataclasses import dataclass

from app.core.config import get_settings

# Modelos vêm da Settings/.env (configuráveis sem deploy).
_settings = get_settings()
_RAPIDO = _settings.ANTHROPIC_MODEL_RAPIDO
_COMPLEXO = _settings.ANTHROPIC_MODEL_COMPLEXO or _RAPIDO
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
    # Complexo (Claude — env COMPLEXO; default Opus 4.8 p/ máxima qualidade)
    TarefaIA.ANALISE_CASO: _claude("analise_caso", _COMPLEXO, 4000, 0.1, "Análise estratégica"),
    TarefaIA.DOSSIE:       _claude("analise_caso", _COMPLEXO, 5000, 0.1, "Dossiê completo"),
    TarefaIA.MINUTAS:      _claude("minutas", _COMPLEXO, 6000, 0.15, "Redação de peças"),
    TarefaIA.AMBIENTAL:    _claude("ambiental", _COMPLEXO, 4000, 0.1, "Direito ambiental técnico"),
    TarefaIA.TRABALHISTA:  _claude("trabalhista", _COMPLEXO, 3500, 0.1, "CLT + TST"),
    TarefaIA.CRIMINAL:     _claude("criminal", _COMPLEXO, 3000, 0.1, "Criminal — sensível"),
    TarefaIA.FAMILIA:      _claude("familia", _COMPLEXO, 3000, 0.1, "Família — sensível"),
    TarefaIA.PESQUISA_JURIDICA: _claude("pesquisa_juridica", _COMPLEXO, 3000, 0.2, "Pesquisa jurisprudencial"),
    TarefaIA.DEFAULT:      _claude("default", _RAPIDO, 2000, 0.2, "Fallback — Haiku"),
}


def get_configuracao(tarefa: TarefaIA) -> ConfiguracaoIA:
    return CONFIGURACOES.get(tarefa, CONFIGURACOES[TarefaIA.DEFAULT])
