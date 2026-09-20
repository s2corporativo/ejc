"""Router de modelos/prompts por tarefa.

O router define preferência de qualidade/custo/latência. Política operacional:
Groq para tarefas corriqueiras; Maritaca/Sabiá para leitura, mérito e pesquisa.
Claude não é escolhido aqui: fica disponível somente por requisição explícita
no gateway/interface. Os nomes reais dos modelos vêm de Settings/.env. A política e o gateway continuam
responsáveis por elegibilidade, sigilo, fallback e kill-switch.
"""
from enum import Enum
from dataclasses import dataclass

from app.core.config import get_settings

_settings = get_settings()
_MARITACA = _settings.MARITACA_MODEL
_MARITACA_MARITACA_RAPIDO = _settings.MARITACA_MODEL_MARITACA_RAPIDO or _MARITACA
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


def _maritaca(prompt_key, model, mt, temp, just):
    return ConfiguracaoIA("maritaca", model, prompt_key, mt, temp, just)


CONFIGURACOES: dict[TarefaIA, ConfiguracaoIA] = {
    TarefaIA.TRIAGEM: _groq("triagem", 1200, 0.1, "Classificação estruturada — rota econômica"),
    TarefaIA.RESUMO: _groq("resumo", 900, 0.2, "Sumarização simples — rota econômica"),
    TarefaIA.PRAZOS: _maritaca("prazos", _MARITACA, 1200, 0.0, "Prazo fatal — precisão (temp 0) + modelo forte (A-4)"),
    TarefaIA.HONORARIOS: _maritaca("honorarios", _MARITACA_RAPIDO, 1800, 0.1, "Honorários OAB/MG"),
    # Audiência é ato irrepetível e o roteiro traz as perguntas escritas na
    # íntegra: modelo forte e teto maior (auditoria de 18/08).
    TarefaIA.AUDIENCIA: _maritaca("audiencia", _MARITACA, 3000, 0.2, "Preparação de audiência"),
    TarefaIA.RAG_QUERY: _maritaca("rag_query", _MARITACA, 2500, 0.1, "Síntese de RAG — fundamentação vira resposta (A-4)"),
    TarefaIA.ANALISE_CASO: _maritaca("analise_caso", _MARITACA, 4000, 0.1, "Análise estratégica"),
    # A chave "dossie" existe em SYSTEM_PROMPTS (hoje com o mesmo texto de
    # "analise_caso") e não era consumida por ninguém — órfã. Consumi-la aqui
    # não muda o texto atual e permite que o dossiê divirja sem mexer no router.
    TarefaIA.DOSSIE: _maritaca("dossie", _MARITACA, 5000, 0.1, "Dossiê completo"),
    TarefaIA.MINUTAS: _maritaca("minutas", _MARITACA, 6000, 0.15, "Redação de peças"),
    TarefaIA.AMBIENTAL: _maritaca("ambiental", _MARITACA, 4000, 0.1, "Direito ambiental técnico"),
    TarefaIA.TRABALHISTA: _maritaca("trabalhista", _MARITACA, 3500, 0.1, "CLT + TST"),
    TarefaIA.CRIMINAL: _maritaca("criminal", _MARITACA, 3000, 0.1, "Criminal — sensível"),
    TarefaIA.FAMILIA: _maritaca("familia", _MARITACA, 3000, 0.1, "Família — sensível"),
    TarefaIA.ADMINISTRATIVO: _maritaca("administrativo", _MARITACA, 3000, 0.1, "Lei 9.784, improbidade e Lei 14.133"),
    TarefaIA.SUCESSOES: _maritaca("sucessoes", _MARITACA, 3000, 0.1, "Inventário e partilha"),
    TarefaIA.IMOBILIARIO: _maritaca("imobiliario", _MARITACA, 3000, 0.1, "Locação, usucapião e registros"),
    TarefaIA.CONSTITUCIONAL: _maritaca("constitucional", _MARITACA, 3500, 0.1, "Constitucional e remédios"),
    TarefaIA.JUIZADOS: _maritaca("juizados", _MARITACA, 3000, 0.1, "JEC, JEF e JEFP"),
    TarefaIA.CIVEL: _maritaca("civel", _MARITACA, 3500, 0.1, "Responsabilidade, prescrição e tutelas"),
    TarefaIA.PESQUISA_JURIDICA: _maritaca("pesquisa_juridica", _MARITACA, 3000, 0.2, "Pesquisa jurídica"),
    TarefaIA.DEFAULT: _groq("default", 2000, 0.2, "Tarefa corriqueira/fallback econômico"),
}


def get_configuracao(tarefa: TarefaIA) -> ConfiguracaoIA:
    return CONFIGURACOES.get(tarefa, CONFIGURACOES[TarefaIA.DEFAULT])
