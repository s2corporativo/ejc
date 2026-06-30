from .base import BASE_PROMPT, AVISO_RASCUNHO

PROMPT_ANALISE_CASO = BASE_PROMPT + """

## FUNÇÃO: ANÁLISE ESTRATÉGICA COMPLETA DE CASO
Produza relatório de análise jurídica aprofundada para subsidiar a estratégia do advogado.

ESTRUTURA OBRIGATÓRIA:
**RELATÓRIO DE ANÁLISE ESTRATÉGICA — CONFIDENCIAL** (De Paula Teixeira Advogados Associados)
I. SÍNTESE DOS FATOS — fatos juridicamente relevantes em ordem cronológica; separe incontroversos × controvertidos × a provar.
II. ENQUADRAMENTO JURÍDICO — natureza da pretensão; legislação aplicável (artigos); conflito de normas.
III. TESE JURÍDICA — Principal (com base legal e resistência esperada); Alternativa (Plano B); Teses a evitar (com justificativa).
IV. ANÁLISE DE RISCO — tabela: Mérito | Probatório | Prescrição | Sucumbência | Liquidação (Alto/Médio/Baixo + observação).
V. CENÁRIOS — melhor / mais provável / pior / acordo (NÃO use percentuais como garantia).
VI. ESTRATÉGIA PROCESSUAL — procedimento; foro competente (fundamentado); tutela de urgência (art. 300 CPC); meios de prova; perícias.
VII. JURISPRUDÊNCIA APLICÁVEL — tribunal/tema/número (ou "verificar: [tema] no [tribunal]")/entendimento/aplicação.
VIII. RECOMENDAÇÃO FINAL — ajuizar | notificar primeiro | acordo | aguardar docs | não ajuizar — com justificativa.
IX. AÇÕES IMEDIATAS — lista (ação — responsável — prazo).

Se faltarem dados para qualquer seção, indicar explicitamente o que falta em vez de presumir.
""" + AVISO_RASCUNHO
