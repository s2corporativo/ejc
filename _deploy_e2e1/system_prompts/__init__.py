"""Exporta system prompts + router para o ai_gateway."""
from .base import BASE_PROMPT, AVISO_RASCUNHO, IDENTIDADE, RESTRICOES, COMPORTAMENTO
from .triagem import PROMPT_TRIAGEM
from .analise_caso import PROMPT_ANALISE_CASO
from .minutas import PROMPT_MINUTAS
from .prazos import PROMPT_PRAZOS
from .honorarios import PROMPT_HONORARIOS
from .ambiental import PROMPT_AMBIENTAL
from .router import TarefaIA, ConfiguracaoIA, get_configuracao

SYSTEM_PROMPTS: dict[str, str] = {
    "triagem":           PROMPT_TRIAGEM,
    "analise_caso":      PROMPT_ANALISE_CASO,
    "dossie":            PROMPT_ANALISE_CASO,
    "minutas":           PROMPT_MINUTAS,
    "prazos":            PROMPT_PRAZOS,
    "honorarios":        PROMPT_HONORARIOS,
    "ambiental":         PROMPT_AMBIENTAL,
    "trabalhista":       PROMPT_ANALISE_CASO,
    "criminal":          PROMPT_ANALISE_CASO,
    "familia":           PROMPT_ANALISE_CASO,
    "pesquisa_juridica": PROMPT_ANALISE_CASO,
    "audiencia":         PROMPT_ANALISE_CASO,
    "rag_query":         BASE_PROMPT + "\n\nSintetize os trechos recuperados da base de conhecimento para responder à pergunta do advogado. Indique a fonte. Nunca invente jurisprudência ou legislação." + AVISO_RASCUNHO,
    "resumo":            BASE_PROMPT + "\n\nResuma o conteúdo de forma objetiva, técnica e estruturada." + AVISO_RASCUNHO,
    "default":           BASE_PROMPT + AVISO_RASCUNHO,
}

__all__ = ["BASE_PROMPT", "AVISO_RASCUNHO", "SYSTEM_PROMPTS", "TarefaIA", "ConfiguracaoIA", "get_configuracao"]
