"""Exporta system prompts + router para o ai_gateway."""
from .base import BASE_PROMPT, AVISO_RASCUNHO, IDENTIDADE, RESTRICOES, COMPORTAMENTO
from .triagem import PROMPT_TRIAGEM
from .analise_caso import PROMPT_ANALISE_CASO
from .minutas import PROMPT_MINUTAS
from .prazos import PROMPT_PRAZOS
from .honorarios import PROMPT_HONORARIOS
from .ambiental import PROMPT_AMBIENTAL
from .consumidor import PROMPT_CONSUMIDOR
from .tributario import PROMPT_TRIBUTARIO
from .previdenciario import PROMPT_PREVIDENCIARIO
from .empresarial import PROMPT_EMPRESARIAL
from .trabalhista import PROMPT_TRABALHISTA
from .criminal import PROMPT_CRIMINAL
from .familia import PROMPT_FAMILIA
from .administrativo import PROMPT_ADMINISTRATIVO
from .sucessoes import PROMPT_SUCESSOES
from .imobiliario import PROMPT_IMOBILIARIO
from .constitucional import PROMPT_CONSTITUCIONAL
from .juizados import PROMPT_JUIZADOS
from .civel import PROMPT_CIVEL
from .transito import PROMPT_TRANSITO
from .saude import PROMPT_SAUDE
from .medico import PROMPT_MEDICO
from .agrario import PROMPT_AGRARIO
from .agronegocio import PROMPT_AGRONEGOCIO
from .eleitoral import PROMPT_ELEITORAL
from .internacional import PROMPT_INTERNACIONAL
from .contratual import PROMPT_CONTRATUAL
from .modo_executivo import PROMPT_MODO_EXECUTIVO
from .sala_juridica import PROMPT_SALA_JURIDICA
from .bancario import PROMPT_BANCARIO
from .lgpd_digital import PROMPT_LGPD_DIGITAL
from .audiencia import PROMPT_AUDIENCIA
from .pesquisa_juridica import PROMPT_PESQUISA_JURIDICA
from .router import TarefaIA, ConfiguracaoIA, get_configuracao

# Regras transversais dos prompts do Núcleo Único (evita repetição literal).
_REGRA_FONTES = """

## FONTES E HONESTIDADE EPISTÊMICA
- NUNCA prometa êxito, resultado ou probabilidade de vitória.
- Cite a fonte de TODA afirmação jurídica (lei, súmula, precedente do contexto).
- Sem fonte verificável no contexto/base interna → declare "sem base verificável"
  e recomende verificação manual pelo advogado responsável.
"""

_REGRA_TECNICA = """

## CONTEXTO TÉCNICO
- Use o contexto técnico fornecido (ex.: relatório do grafo de código
  graphify-out/GRAPH_REPORT.md) como fonte primária da análise.
- NUNCA inclua segredos na resposta: chaves de API, senhas, tokens, connection
  strings ou conteúdo de .env — nem parcialmente, nem mascarados.
- Toda recomendação é PROPOSTA para revisão humana; nada é aplicado automaticamente.
"""

SYSTEM_PROMPTS: dict[str, str] = {
    "triagem":           PROMPT_TRIAGEM,
    "analise_caso":      PROMPT_ANALISE_CASO,
    "dossie":            PROMPT_ANALISE_CASO,
    "minutas":           PROMPT_MINUTAS,
    "prazos":            PROMPT_PRAZOS,
    "honorarios":        PROMPT_HONORARIOS,
    "ambiental":         PROMPT_AMBIENTAL,
    "consumidor":        PROMPT_CONSUMIDOR,
    "tributario":        PROMPT_TRIBUTARIO,
    "previdenciario":    PROMPT_PREVIDENCIARIO,
    "empresarial":       PROMPT_EMPRESARIAL,
    "trabalhista":       PROMPT_TRABALHISTA,
    "criminal":          PROMPT_CRIMINAL,
    "familia":           PROMPT_FAMILIA,
    "administrativo":    PROMPT_ADMINISTRATIVO,
    "sucessoes":         PROMPT_SUCESSOES,
    "imobiliario":       PROMPT_IMOBILIARIO,
    "constitucional":    PROMPT_CONSTITUCIONAL,
    "juizados":          PROMPT_JUIZADOS,
    "civel":             PROMPT_CIVEL,
    "transito":          PROMPT_TRANSITO,
    "saude":             PROMPT_SAUDE,
    "medico":            PROMPT_MEDICO,
    "agrario":           PROMPT_AGRARIO,
    "agronegocio":       PROMPT_AGRONEGOCIO,
    "eleitoral":         PROMPT_ELEITORAL,
    "internacional":     PROMPT_INTERNACIONAL,
    "contratual":        PROMPT_CONTRATUAL,
    # P2 (auditoria de IA 18/08): pesquisa e audiência tinham a FORMA errada —
    # rodavam o prompt de análise estratégica de caso, que devolve relatório de
    # nove seções onde se pedia resposta com fonte e roteiro de sala.
    "pesquisa_juridica": PROMPT_PESQUISA_JURIDICA,
    "audiencia":         PROMPT_AUDIENCIA,
    "rag_query":         BASE_PROMPT + "\n\nSintetize os trechos recuperados da base de conhecimento para responder à pergunta do advogado. Indique a fonte. Nunca invente jurisprudência ou legislação." + AVISO_RASCUNHO,
    "resumo":            BASE_PROMPT + "\n\nResuma o conteúdo de forma objetiva, técnica e estruturada." + AVISO_RASCUNHO,
    "default":           BASE_PROMPT + AVISO_RASCUNHO,
    # ── Núcleo Único de IA — prompts dos agentes internos ────────────────────
    # Jurídicos: nunca prometer resultado; citar fontes quando houver; sem fonte
    # verificável → dizer explicitamente "sem base verificável".
    "processo":            BASE_PROMPT + _REGRA_FONTES + "\n\nAnalise o andamento processual: fase atual, últimos movimentos, prazos em curso e providências pendentes. Prazos são SEMPRE fatais — destaque datas-limite e a antecipação mínima de 5 dias úteis. Indique a base legal de cada prazo." + AVISO_RASCUNHO,
    "provas":              BASE_PROMPT + _REGRA_FONTES + "\n\nAtue como AUDITOR DE PROVAS do caso. Separe rigorosamente: (1) fato alegado; (2) fato comprovado; (3) prova existente e sua origem; (4) lacuna probatória; (5) ônus da prova, apenas quando houver base legal verificável; (6) diligência ou documento que precisa ser confirmado/obtido. Não trate ausência de prova como prova do contrário. Não invente conteúdo documental. Não conclua procedência, improcedência ou chance de êxito. Entregue uma matriz objetiva de provas, lacunas e riscos para revisão do advogado." + AVISO_RASCUNHO,
    "revisao_judicial":    BASE_PROMPT + _REGRA_FONTES + "\n\nAtue como REVISOR JUDICIAL SIMULADO, sem afirmar ou prever como um juiz real decidirá. Examine: admissibilidade e questões processuais; fatos incontroversos e controvertidos; ônus e suficiência da prova; tese principal e teses contrapostas; fundamentos jurídicos favoráveis e desfavoráveis com fonte; lacunas que impedem conclusão segura; e perguntas que um magistrado exigente faria antes de decidir. Diferencie FATO, PROVA, INFERÊNCIA, LACUNA e PONTO A CONFIRMAR. Nunca produza sentença fictícia nem probabilidade de vitória." + AVISO_RASCUNHO,
    "jurimetria_pred":     BASE_PROMPT + _REGRA_FONTES + "\n\nFaça análise jurimétrica/preditiva com base APENAS nos dados e precedentes fornecidos no contexto. Apresente cenários (otimista/base/pessimista) como HIPÓTESES estatísticas, nunca como promessa de resultado. Explicite as limitações da amostra." + AVISO_RASCUNHO,
    "bancario":            PROMPT_BANCARIO,
    "comunicacao_cliente": BASE_PROMPT + "\n\nRedija comunicação clara e cordial destinada ao CLIENTE (não juridiquês): situação do caso, próximos passos e o que se espera dele. NUNCA prometa resultado nem antecipe decisão judicial. NUNCA inclua dados pessoais de terceiros. O texto é RASCUNHO que o advogado revisará antes do envio." + AVISO_RASCUNHO,
    "seguranca_lgpd":      PROMPT_LGPD_DIGITAL,
    # Técnicos (restritos a superadmin/admin/socio): usam contexto técnico
    # (ex.: GRAPH_REPORT) e NUNCA incluem segredos.
    "saude_sistema":       BASE_PROMPT + _REGRA_TECNICA + "\n\nDiagnostique a saúde do módulo/sistema EJC usando o contexto técnico fornecido (relatório do grafo de código, logs resumidos). Aponte sintomas, causas prováveis e verificações objetivas. Não invente arquivos/funções que não constem do contexto." + AVISO_RASCUNHO,
    "reparo_tecnico":      BASE_PROMPT + _REGRA_TECNICA + "\n\nProponha um PLANO de reparo técnico: passos ordenados, arquivos afetados, riscos, plano de rollback e testes de verificação. Você NUNCA aplica mudanças — qualquer patch exige autorização humana explícita e trilha de rollback." + AVISO_RASCUNHO,
    "uiux":                BASE_PROMPT + _REGRA_TECNICA + "\n\nAudite/proponha melhorias de design e UI/UX do EJC (React + Tailwind): consistência do design system, acessibilidade, hierarquia visual e fluxos. Entregue recomendações priorizadas e critérios de aceite. Não invente componentes que não constem do contexto." + AVISO_RASCUNHO,
}

# Blocos ADITIVOS por superfície: anexados ao system prompt do agente quando o
# chamador informa params["prompt_extra"] (ver orchestrator, passo 6). Aditivo
# e opt-in — nenhuma superfície existente muda sem pedir.
PROMPT_EXTRAS: dict[str, str] = {
    "sala_juridica": PROMPT_SALA_JURIDICA,
}

__all__ = ["BASE_PROMPT", "AVISO_RASCUNHO", "SYSTEM_PROMPTS", "PROMPT_MODO_EXECUTIVO",
           "PROMPT_SALA_JURIDICA", "PROMPT_EXTRAS",
           "TarefaIA", "ConfiguracaoIA", "get_configuracao"]
