"""Router de modelos/prompts por tarefa.

O router define preferência de qualidade/custo/latência, mas os nomes reais dos
modelos vêm exclusivamente de Settings/.env. A política e o gateway continuam
responsáveis por elegibilidade, sigilo, fallback e kill-switch.
"""
from enum import Enum
from dataclasses import dataclass

from app.core.config import get_settings

_settings = get_settings()
_RAPIDO = _settings.ANTHROPIC_MODEL_RAPIDO
_COMPLEXO = _settings.ANTHROPIC_MODEL_COMPLEXO or _RAPIDO
_GROQ = _settings.GROQ_MODEL


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
    ADMINISTRATIVO = "administrativo"
    SUCESSOES = "sucessoes"
    IMOBILIARIO = "imobiliario"
    CONSTITUCIONAL = "constitucional"
    JUIZADOS = "juizados"
    CIVEL = "civel"
    PESQUISA_JURIDICA = "pesquisa_juridica"
    RESUMO = "resumo"
    AUDIENCIA = "audiencia"
    RAG_QUERY = "rag_query"
    DEFAULT = "default"


@dataclass
class ConfiguracaoIA:
    provider: str
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
    TarefaIA.TRIAGEM: _groq("triagem", 1200, 0.1, "Classificação estruturada — rota econômica"),
    TarefaIA.RESUMO: _groq("resumo", 900, 0.2, "Sumarização simples — rota econômica"),
    TarefaIA.PRAZOS: _claude("prazos", _COMPLEXO, 1200, 0.0, "Prazo fatal — precisão (temp 0) + modelo forte (A-4)"),
    TarefaIA.HONORARIOS: _claude("honorarios", _RAPIDO, 1800, 0.1, "Honorários OAB/MG"),
    TarefaIA.AUDIENCIA: _claude("audiencia", _RAPIDO, 2000, 0.2, "Preparação de audiência"),
    TarefaIA.RAG_QUERY: _claude("rag_query", _COMPLEXO, 2500, 0.1, "Síntese de RAG — fundamentação vira resposta (A-4)"),
    TarefaIA.ANALISE_CASO: _claude("analise_caso", _COMPLEXO, 4000, 0.1, "Análise estratégica"),
    TarefaIA.DOSSIE: _claude("analise_caso", _COMPLEXO, 5000, 0.1, "Dossiê completo"),
    TarefaIA.MINUTAS: _claude("minutas", _COMPLEXO, 6000, 0.15, "Redação de peças"),
    TarefaIA.AMBIENTAL: _claude("ambiental", _COMPLEXO, 4000, 0.1, "Direito ambiental técnico"),
    TarefaIA.TRABALHISTA: _claude("trabalhista", _COMPLEXO, 3500, 0.1, "CLT + TST"),
    TarefaIA.CRIMINAL: _claude("criminal", _COMPLEXO, 3000, 0.1, "Criminal — sensível"),
    TarefaIA.FAMILIA: _claude("familia", _COMPLEXO, 3000, 0.1, "Família — sensível"),
    TarefaIA.ADMINISTRATIVO: _claude("administrativo", _COMPLEXO, 3000, 0.1, "Lei 9.784, improbidade e Lei 14.133"),
    TarefaIA.SUCESSOES: _claude("sucessoes", _COMPLEXO, 3000, 0.1, "Inventário e partilha"),
    TarefaIA.IMOBILIARIO: _claude("imobiliario", _COMPLEXO, 3000, 0.1, "Locação, usucapião e registros"),
    TarefaIA.CONSTITUCIONAL: _claude("constitucional", _COMPLEXO, 3500, 0.1, "Constitucional e remédios"),
    TarefaIA.JUIZADOS: _claude("juizados", _COMPLEXO, 3000, 0.1, "JEC, JEF e JEFP"),
    TarefaIA.CIVEL: _claude("civel", _COMPLEXO, 3500, 0.1, "Responsabilidade, prescrição e tutelas"),
    TarefaIA.PESQUISA_JURIDICA: _claude("pesquisa_juridica", _COMPLEXO, 3000, 0.2, "Pesquisa jurídica"),
    TarefaIA.DEFAULT: _claude("default", _RAPIDO, 2000, 0.2, "Fallback configurável"),
}


def get_configuracao(tarefa: TarefaIA) -> ConfiguracaoIA:
    return CONFIGURACOES.get(tarefa, CONFIGURACOES[TarefaIA.DEFAULT])
