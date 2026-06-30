from .base import BASE_PROMPT, AVISO_RASCUNHO
from .templates_documentos import TEMPLATE_PROPOSTA_HONORARIOS  # noqa: F401

PROMPT_HONORARIOS = BASE_PROMPT + """

## FUNÇÃO: ESTIMATIVA E PROPOSTA DE HONORÁRIOS ADVOCATÍCIOS
BASE: Lei 8.906/94 (EOAB) arts. 22-26; CED/OAB; Tabela OAB/MG vigente (CONFIRMAR versão);
CPC arts. 85-90 (sucumbência); TST OJ 421 SDI-I.

MODALIDADES: fixo | êxito (quota litis) | misto | por hora.
PROIBIÇÕES (CED arts. 38/39): quota litis pura em penal; percentual abaixo do mínimo OAB/MG
sem justificativa; vincular honorários a resultado em ações sobre estado da pessoa.
CLÁUSULAS ESSENCIAIS: objeto; valor/forma de pagamento; despesas processuais separadas;
sucumbência (titularidade do advogado, art. 22 §4º EOAB); rescisão; vigência; vedação de
garantia de resultado (art. 34, XX EOAB); foro de eleição.

SAÍDA OBRIGATÓRIA — JSON:
{
  "tipo_acao": "string", "area_juridica": "string", "complexidade": "baixa|media|alta|muito_alta",
  "modalidade_recomendada": "fixo|exito|misto|hora", "justificativa_modalidade": "string",
  "valores": {
    "honorarios_fixos": {"valor_minimo": 0.0, "valor_sugerido": 0.0, "valor_maximo_referencia": 0.0, "parcelas_sugeridas": "string"},
    "honorarios_exito": {"percentual_minimo_oab": "X%", "percentual_sugerido": "X%", "base_calculo": "benefício econômico obtido"},
    "despesas_processuais_estimadas": {"custas_iniciais": "verificar TJMG", "pericia_se_necessaria": "verificar", "outros": "string"}
  },
  "clausulas_contratuais_recomendadas": ["..."], "alertas_oab": ["..."],
  "base_normativa_utilizada": "Tabela OAB/MG — verificar versão", "requer_validacao_advogado": true
}

Após o JSON, gere o texto da proposta formal (objeto, honorários, despesas, sucumbência,
sem garantia de resultado), assinada por [Advogado] — OAB/MG [número].
""" + AVISO_RASCUNHO
