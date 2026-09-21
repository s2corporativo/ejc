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
_MARITACA = _settings.MARITACA_MODEL
_MARITACA_RAPIDO = _settings.MARITACA_MODEL_RAPIDO or _MARITACA


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
    # Mantido apenas para chamadas que selecionem Claude explicitamente.
    return ConfiguracaoIA("anthropic", model, prompt_key, mt, temp, just)


def _maritaca(prompt_key, mt=3000, temp=0.1, just=""):
    return ConfiguracaoIA("maritaca", _MARITACA, prompt_key, mt, temp, just)


CONFIGURACOES: dict[TarefaIA, ConfiguracaoIA] = {
    # Rotina/custo/latência → Groq.
    TarefaIA.TRIAGEM: _groq("triagem", 1200, 0.1, "Classificação estruturada — Groq"),
    TarefaIA.RESUMO: _groq("resumo", 900, 0.2, "Sumarização simples — Groq"),
    TarefaIA.HONORARIOS: _groq("honorarios", 1800, 0.1, "Consulta estruturada de honorários — Groq"),
    TarefaIA.DEFAULT: _groq("default", 2000, 0.2, "Conversa e rotina — Groq"),

    # Leitura, interpretação, raciocínio e pesquisa jurídica → Maritaca/Sabiá.
    TarefaIA.PRAZOS: _maritaca("prazos", 1200, 0.0, "Leitura documental e prazo — Maritaca"),
    TarefaIA.AUDIENCIA: _maritaca("audiencia", 3000, 0.2, "Preparação jurídica — Maritaca"),
    TarefaIA.RAG_QUERY: _maritaca("rag_query", 2500, 0.1, "Síntese de RAG — Maritaca"),
    TarefaIA.ANALISE_CASO: _maritaca("analise_caso", 4000, 0.1, "Análise estratégica — Maritaca"),
    TarefaIA.DOSSIE: _maritaca("dossie", 5000, 0.1, "Leitura e dossiê completo — Maritaca"),
    TarefaIA.MINUTAS: _maritaca("minutas", 6000, 0.15, "Redação jurídica — Maritaca"),
    TarefaIA.AMBIENTAL: _maritaca("ambiental", 4000, 0.1, "Direito ambiental — Maritaca"),
    TarefaIA.TRABALHISTA: _maritaca("trabalhista", 3500, 0.1, "CLT + TST — Maritaca"),
    TarefaIA.CRIMINAL: _maritaca("criminal", 3000, 0.1, "Criminal — Maritaca; sigilo continua governado"),
    TarefaIA.FAMILIA: _maritaca("familia", 3000, 0.1, "Família — Maritaca; sigilo continua governado"),
    TarefaIA.ADMINISTRATIVO: _maritaca("administrativo", 3000, 0.1, "Administrativo — Maritaca"),
    TarefaIA.SUCESSOES: _maritaca("sucessoes", 3000, 0.1, "Sucessões — Maritaca"),
    TarefaIA.IMOBILIARIO: _maritaca("imobiliario", 3000, 0.1, "Imobiliário — Maritaca"),
    TarefaIA.CONSTITUCIONAL: _maritaca("constitucional", 3500, 0.1, "Constitucional — Maritaca"),
    TarefaIA.JUIZADOS: _maritaca("juizados", 3000, 0.1, "Juizados — Maritaca"),
    TarefaIA.CIVEL: _maritaca("civel", 3500, 0.1, "Civil — Maritaca"),
    TarefaIA.PESQUISA_JURIDICA: _maritaca("pesquisa_juridica", 3000, 0.2, "Pesquisa e jurisprudência — Maritaca"),
}


def get_configuracao(tarefa: TarefaIA) -> ConfiguracaoIA:
    return CONFIGURACOES.get(tarefa, CONFIGURACOES[TarefaIA.DEFAULT])
