"""
EJC — Seed da biblioteca de templates de peças por área.
Popula doc_templates com modelos editáveis (placeholders {{var}} renderizados
por templates.py:/{id}/gerar). Idempotente por título. NÃO recria o sistema.

Execução:
    python -m app.seeds.templates_seed
    FORCE_TEMPLATES_UPDATE=true python -m app.seeds.templates_seed
"""
import os
import sys
from uuid import uuid4

# Variáveis de contexto disponíveis no /gerar (templates.py):
# cliente_nome, cliente_cpf_cnpj, cliente_endereco, numero_processo,
# parte_contraria, comarca, vara, valor_causa, area, data_hoje,
# advogado_nome, advogado_oab

_RODAPE = (
    "\n\nNestes termos,\nPede deferimento.\n\n"
    "{{comarca}}, {{data_hoje}}.\n\n"
    "{{advogado_nome}}\nOAB {{advogado_oab}}\n\n"
    "____________________________________________________________\n"
    "MINUTA gerada de modelo — revisão humana obrigatória antes do protocolo. "
    "Conferir fatos, fundamentos, jurisprudência, documentos e prazos."
)

TEMPLATES = [
    {
        "titulo": "Petição Inicial — Cível",
        "tipo_peca": "peticao_inicial",
        "area": "civil",
        "descricao": "Modelo de petição inicial cível (rito comum, CPC art. 319).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DA "
            "COMARCA DE {{comarca}}\n\n\n"
            "{{cliente_nome}}, inscrito(a) no CPF/CNPJ sob o nº {{cliente_cpf_cnpj}}, "
            "residente e domiciliado(a) em {{cliente_endereco}}, por seu advogado que esta "
            "subscreve (procuração anexa), vem, respeitosamente, à presença de Vossa "
            "Excelência propor a presente\n\n"
            "AÇÃO [DESENVOLVER: nome da ação]\n\n"
            "em face de {{parte_contraria}}, pelos fatos e fundamentos a seguir expostos.\n\n"
            "I — DOS FATOS\n[DESENVOLVER a narrativa cronológica dos fatos.]\n\n"
            "II — DO DIREITO\n[DESENVOLVER a fundamentação jurídica. Citar dispositivos legais "
            "e jurisprudência — marcar [VERIFICAR] em cada citação.]\n\n"
            "III — DA TUTELA DE URGÊNCIA (se cabível)\n[DESENVOLVER requisitos do art. 300 do CPC.]\n\n"
            "IV — DOS PEDIDOS\nAnte o exposto, requer:\n"
            "a) a citação da parte ré para responder, sob pena de revelia;\n"
            "b) [DESENVOLVER o pedido principal];\n"
            "c) a condenação da ré ao pagamento de custas e honorários advocatícios;\n"
            "d) a produção de todas as provas em direito admitidas.\n\n"
            "Dá-se à causa o valor de {{valor_causa}}." + _RODAPE
        ),
    },
    {
        "titulo": "Reclamação Trabalhista — Petição Inicial",
        "tipo_peca": "peticao_inicial",
        "area": "trabalhista",
        "descricao": "Modelo de reclamação trabalhista (CLT art. 840).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) JUIZ(A) DO TRABALHO DA {{vara}} DE {{comarca}}\n\n\n"
            "{{cliente_nome}}, CPF nº {{cliente_cpf_cnpj}}, residente em {{cliente_endereco}}, "
            "vem, por seu advogado (procuração anexa), propor\n\n"
            "RECLAMAÇÃO TRABALHISTA\n\n"
            "em face de {{parte_contraria}}, pelos fundamentos a seguir.\n\n"
            "I — DO CONTRATO DE TRABALHO\n[DESENVOLVER: função, admissão, rescisão, remuneração, jornada.]\n\n"
            "II — DAS VERBAS POSTULADAS\n[DESENVOLVER cada verba com fundamento na CLT.]\n\n"
            "III — DO DIREITO\n[DESENVOLVER. Verificar prescrição — art. 7º, XXIX, CF: 5 anos, até 2 anos após extinção.]\n\n"
            "IV — DOS PEDIDOS\nRequer:\n"
            "a) a notificação da reclamada para audiência;\n"
            "b) [DESENVOLVER as verbas e valores pleiteados];\n"
            "c) os benefícios da justiça gratuita;\n"
            "d) honorários de sucumbência (art. 791-A da CLT).\n\n"
            "Dá-se à causa o valor de {{valor_causa}}." + _RODAPE
        ),
    },
    {
        "titulo": "Petição Inicial — Consumidor",
        "tipo_peca": "peticao_inicial",
        "area": "consumidor",
        "descricao": "Inicial consumerista com inversão do ônus da prova (CDC).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DA "
            "COMARCA DE {{comarca}}\n\n\n"
            "{{cliente_nome}}, CPF nº {{cliente_cpf_cnpj}}, domiciliado(a) em {{cliente_endereco}}, "
            "vem propor\n\n"
            "AÇÃO [DESENVOLVER] COM PEDIDO DE [tutela/indenização]\n\n"
            "em face de {{parte_contraria}}, na forma do Código de Defesa do Consumidor.\n\n"
            "I — DOS FATOS\n[DESENVOLVER a relação de consumo e o vício/defeito ou cobrança indevida.]\n\n"
            "II — DO DIREITO DO CONSUMIDOR\n"
            "Trata-se de relação de consumo (CDC arts. 2º e 3º). Aplica-se a inversão do ônus "
            "da prova (art. 6º, VIII) ante a hipossuficiência e verossimilhança.\n"
            "[DESENVOLVER: responsabilidade objetiva, art. 14; devolução em dobro, art. 42; dano moral.]\n\n"
            "III — DOS PEDIDOS\nRequer:\n"
            "a) a citação da ré;\n"
            "b) a inversão do ônus da prova (art. 6º, VIII, CDC);\n"
            "c) [DESENVOLVER: restituição/indenização];\n"
            "d) condenação em custas e honorários.\n\n"
            "Dá-se à causa o valor de {{valor_causa}}." + _RODAPE
        ),
    },
    {
        "titulo": "Petição Inicial — Previdenciário (concessão/restabelecimento)",
        "tipo_peca": "peticao_inicial",
        "area": "previdenciario",
        "descricao": "Inicial contra o INSS — concessão/restabelecimento de benefício.",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) JUIZ(A) FEDERAL DA {{vara}} DE {{comarca}}\n"
            "(ou Juizado Especial Federal, se até 60 salários mínimos)\n\n\n"
            "{{cliente_nome}}, CPF nº {{cliente_cpf_cnpj}}, residente em {{cliente_endereco}}, "
            "vem propor\n\n"
            "AÇÃO PREVIDENCIÁRIA DE [concessão/restabelecimento] DE BENEFÍCIO\n\n"
            "em face do INSTITUTO NACIONAL DO SEGURO SOCIAL — INSS.\n\n"
            "I — DO PRÉVIO REQUERIMENTO ADMINISTRATIVO\n[DESENVOLVER: NB, DER e indeferimento — Tema 350 STF.]\n\n"
            "II — DA QUALIDADE DE SEGURADO E CARÊNCIA\n[DESENVOLVER: CNIS, vínculos, carência (Lei 8.213/91 art. 25).]\n\n"
            "III — DO DIREITO AO BENEFÍCIO\n[DESENVOLVER os requisitos do benefício pleiteado.]\n\n"
            "IV — DOS PEDIDOS\nRequer:\n"
            "a) a citação do INSS;\n"
            "b) a concessão/restabelecimento do benefício desde a DER;\n"
            "c) o pagamento das parcelas vencidas com correção e juros;\n"
            "d) os benefícios da justiça gratuita.\n\n"
            "Dá-se à causa o valor de {{valor_causa}}." + _RODAPE
        ),
    },
    {
        "titulo": "Contestação — Trabalhista",
        "tipo_peca": "contestacao",
        "area": "trabalhista",
        "descricao": "Defesa do reclamado em reclamação trabalhista.",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) JUIZ(A) DO TRABALHO DA {{vara}} DE {{comarca}}\n\n"
            "Processo nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, CNPJ nº {{cliente_cpf_cnpj}}, já qualificado nos autos da "
            "reclamação movida por {{parte_contraria}}, vem apresentar\n\n"
            "CONTESTAÇÃO\n\n"
            "I — DAS PRELIMINARES\n[DESENVOLVER: incompetência, inépcia, prescrição (art. 7º, XXIX, CF), etc.]\n\n"
            "II — DO MÉRITO\n[DESENVOLVER a impugnação específica de cada verba (art. 341 do CPC). "
            "Ônus da prova: arts. 818 da CLT e 373 do CPC.]\n\n"
            "III — DOS PEDIDOS\nRequer o acolhimento das preliminares e, no mérito, a total "
            "improcedência dos pedidos, com condenação do reclamante em honorários.\n\n"
            "Protesta por todos os meios de prova." + _RODAPE
        ),
    },
    {
        "titulo": "Defesa Administrativa — Auto de Infração Ambiental",
        "tipo_peca": "defesa_ambiental",
        "area": "administrativo",
        "descricao": "Defesa contra auto de infração ambiental (Lei 9.605/98; Dec. 6.514/08).",
        "conteudo": (
            "AO(À) ILUSTRÍSSIMO(A) SENHOR(A) [autoridade do órgão ambiental autuante]\n\n"
            "Referência: Auto de Infração nº [DESENVOLVER] — Processo Administrativo nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, inscrito(a) no CPF/CNPJ sob o nº {{cliente_cpf_cnpj}}, com endereço "
            "em {{cliente_endereco}}, vem apresentar\n\n"
            "DEFESA ADMINISTRATIVA\n\n"
            "em face do auto de infração lavrado por {{parte_contraria}}, no prazo legal "
            "(20 dias — Dec. 6.514/08 art. 113).\n\n"
            "I — DA TEMPESTIVIDADE\n[DESENVOLVER: data da ciência e do protocolo.]\n\n"
            "II — DAS PRELIMINARES\n[DESENVOLVER: competência do órgão, nulidades do auto, "
            "ausência de motivação (art. 50 da Lei 9.784/99).]\n\n"
            "III — DO MÉRITO\n[DESENVOLVER: inexistência da infração, ausência de nexo causal, "
            "atenuantes (Lei 9.605/98 art. 14), proporcionalidade da multa.]\n\n"
            "IV — DOS PEDIDOS\nRequer o recebimento da defesa, a nulidade/insubsistência do "
            "auto de infração e, subsidiariamente, a redução da penalidade.\n\n"
            "Termos em que pede deferimento.\n\n"
            "{{comarca}}, {{data_hoje}}.\n\n{{advogado_nome}}\nOAB {{advogado_oab}}\n\n"
            "____________________________________________________________\n"
            "MINUTA gerada de modelo — revisão humana obrigatória. Conferir prazo, órgão "
            "competente e enquadramento legal."
        ),
    },
    {
        "titulo": "Recurso Inominado — Juizado Especial",
        "tipo_peca": "recurso",
        "area": "civil",
        "descricao": "Recurso inominado contra sentença do JEC (Lei 9.099/95 art. 41).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) JUIZ(A) DE DIREITO DA {{vara}} DE {{comarca}}\n\n"
            "Processo nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, já qualificado(a) nos autos, inconformado(a) com a r. sentença, "
            "vem interpor\n\n"
            "RECURSO INOMINADO\n\n"
            "em face de {{parte_contraria}}, com fundamento no art. 41 da Lei 9.099/95, "
            "requerendo o recebimento e a remessa à Turma Recursal.\n\n"
            "I — DA TEMPESTIVIDADE\nO prazo de 10 dias encontra-se atendido (art. 42).\n\n"
            "II — DAS RAZÕES RECURSAIS\n[DESENVOLVER a fundamentação do inconformismo; impugnar "
            "os fundamentos da sentença.]\n\n"
            "III — DO PEDIDO\nRequer o provimento do recurso para reformar a sentença, [DESENVOLVER].\n\n"
            "Pugna pelo preparo na forma da lei." + _RODAPE
        ),
    },
    {
        "titulo": "Parecer Jurídico",
        "tipo_peca": "parecer",
        "area": "civil",
        "descricao": "Estrutura de parecer jurídico consultivo.",
        "conteudo": (
            "PARECER JURÍDICO\n\n"
            "Consulente: {{cliente_nome}} (CPF/CNPJ {{cliente_cpf_cnpj}})\n"
            "Data: {{data_hoje}}\n\n"
            "I — DA CONSULTA\n[DESENVOLVER a questão submetida à análise.]\n\n"
            "II — DOS FATOS RELEVANTES\n[DESENVOLVER o contexto fático pertinente.]\n\n"
            "III — DA ANÁLISE JURÍDICA\n[DESENVOLVER: legislação aplicável, doutrina e "
            "jurisprudência — marcar [VERIFICAR]. Apresentar riscos e cenários.]\n\n"
            "IV — DA CONCLUSÃO\n[DESENVOLVER resposta objetiva à consulta, com recomendações.]\n\n"
            "É o parecer, salvo melhor juízo.\n\n"
            "{{comarca}}, {{data_hoje}}.\n\n{{advogado_nome}}\nOAB {{advogado_oab}}\n\n"
            "____________________________________________________________\n"
            "MINUTA — revisão humana obrigatória."
        ),
    },
    {
        "titulo": "Contrato de Honorários Advocatícios",
        "tipo_peca": "contrato",
        "area": "civil",
        "descricao": "Minuta de contrato de prestação de serviços advocatícios.",
        "conteudo": (
            "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS\n\n"
            "CONTRATANTE: {{cliente_nome}}, CPF/CNPJ {{cliente_cpf_cnpj}}, residente em "
            "{{cliente_endereco}}.\n"
            "CONTRATADO(A): {{advogado_nome}}, advogado(a), OAB {{advogado_oab}}.\n\n"
            "CLÁUSULA 1ª — DO OBJETO\nPrestação de serviços advocatícios consistentes em "
            "[DESENVOLVER: ação/consultoria].\n\n"
            "CLÁUSULA 2ª — DOS HONORÁRIOS\nA título de honorários, o contratante pagará "
            "[DESENVOLVER valor/percentual], observada a Tabela da OAB.\n\n"
            "CLÁUSULA 3ª — DOS HONORÁRIOS DE SUCUMBÊNCIA\nOs honorários de sucumbência "
            "pertencem ao advogado (art. 23 da Lei 8.906/94).\n\n"
            "CLÁUSULA 4ª — DAS OBRIGAÇÕES E DESPESAS\n[DESENVOLVER: custas, diligências.]\n\n"
            "CLÁUSULA 5ª — DO FORO\nFica eleito o foro da Comarca de {{comarca}}.\n\n"
            "{{comarca}}, {{data_hoje}}.\n\n"
            "_______________________________   _______________________________\n"
            "CONTRATANTE                          CONTRATADO(A) — OAB {{advogado_oab}}\n\n"
            "____________________________________________________________\n"
            "MINUTA — revisão humana obrigatória."
        ),
    },
    {
        "titulo": "Notificação Extrajudicial",
        "tipo_peca": "notificacao_extrajudicial",
        "area": "civil",
        "descricao": "Notificação extrajudicial genérica (constituição em mora / providência).",
        "conteudo": (
            "NOTIFICAÇÃO EXTRAJUDICIAL\n\n"
            "Notificante: {{cliente_nome}} (CPF/CNPJ {{cliente_cpf_cnpj}})\n"
            "Notificado(a): {{parte_contraria}}\n"
            "Data: {{data_hoje}}\n\n"
            "Prezado(a) Senhor(a),\n\n"
            "Na qualidade de procurador(a) do(a) notificante, venho NOTIFICÁ-LO(A) para, no "
            "prazo de [DESENVOLVER] dias, [DESENVOLVER a providência exigida — ex.: quitar "
            "o débito de {{valor_causa}}; cumprir obrigação contratual].\n\n"
            "O não atendimento no prazo implicará [DESENVOLVER: adoção das medidas judiciais "
            "cabíveis, constituição em mora, rescisão], sem prejuízo de perdas e danos.\n\n"
            "Sendo o que se apresenta para os devidos fins.\n\n"
            "{{comarca}}, {{data_hoje}}.\n\n{{advogado_nome}}\nOAB {{advogado_oab}}\n\n"
            "____________________________________________________________\n"
            "MINUTA — revisão humana obrigatória."
        ),
    },
    {
        "titulo": "Apelação Cível",
        "tipo_peca": "recurso",
        "area": "civil",
        "descricao": "Recurso de apelação contra sentença (CPC art. 1.009).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DA "
            "COMARCA DE {{comarca}}\n\nProcesso nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, já qualificado(a) nos autos em que litiga com {{parte_contraria}}, "
            "inconformado(a) com a r. sentença, vem interpor\n\n"
            "APELAÇÃO\n\n"
            "com fundamento no art. 1.009 do CPC, requerendo o recebimento em ambos os efeitos "
            "e a remessa ao E. Tribunal, com as inclusas razões.\n\n"
            "RAZÕES DE APELAÇÃO\n\n"
            "EGRÉGIO TRIBUNAL, COLENDA CÂMARA,\n\n"
            "I — DA TEMPESTIVIDADE\nO prazo de 15 dias úteis (art. 1.003 §5º) está atendido.\n\n"
            "II — DA SÍNTESE\n[DESENVOLVER breve relato da demanda e da sentença recorrida.]\n\n"
            "III — DAS RAZÕES PARA REFORMA\n[DESENVOLVER o error in judicando/in procedendo; "
            "impugnar os fundamentos da sentença.]\n\n"
            "IV — DO PEDIDO\nRequer o conhecimento e provimento do recurso para reformar a "
            "sentença, [DESENVOLVER]." + _RODAPE
        ),
    },
    {
        "titulo": "Agravo de Instrumento",
        "tipo_peca": "recurso",
        "area": "civil",
        "descricao": "Agravo contra decisão interlocutória (CPC art. 1.015).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DESEMBARGADOR(A) RELATOR(A) DO E. TRIBUNAL DE JUSTIÇA\n\n"
            "Processo de origem nº {{numero_processo}} — {{vara}} de {{comarca}}\n\n\n"
            "{{cliente_nome}}, CPF/CNPJ {{cliente_cpf_cnpj}}, vem interpor\n\n"
            "AGRAVO DE INSTRUMENTO\n\n"
            "em face de {{parte_contraria}}, contra a decisão interlocutória que [DESENVOLVER], "
            "com fundamento no art. 1.015 do CPC.\n\n"
            "I — DO CABIMENTO E TEMPESTIVIDADE\n[DESENVOLVER a hipótese de cabimento; prazo 15 dias úteis.]\n\n"
            "II — DA DECISÃO AGRAVADA\n[DESENVOLVER o teor da decisão.]\n\n"
            "III — DO EFEITO SUSPENSIVO / ANTECIPAÇÃO DA TUTELA RECURSAL\n"
            "[DESENVOLVER fumus boni iuris e periculum in mora — art. 1.019, I.]\n\n"
            "IV — DO MÉRITO RECURSAL\n[DESENVOLVER as razões da reforma.]\n\n"
            "V — DO PEDIDO\nRequer o provimento do agravo para reformar a decisão agravada, "
            "[DESENVOLVER]." + _RODAPE
        ),
    },
    {
        "titulo": "Embargos de Declaração",
        "tipo_peca": "recurso",
        "area": "civil",
        "descricao": "Embargos por omissão, contradição, obscuridade ou erro (CPC art. 1.022).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DE {{comarca}}\n\n"
            "Processo nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, já qualificado(a), vem opor\n\n"
            "EMBARGOS DE DECLARAÇÃO\n\n"
            "com fundamento no art. 1.022 do CPC, pelas razões a seguir.\n\n"
            "I — DA TEMPESTIVIDADE\nOpostos no prazo de 5 dias (art. 1.023).\n\n"
            "II — DO VÍCIO\n[DESENVOLVER: apontar a omissão / contradição / obscuridade / erro "
            "material existente na decisão.]\n\n"
            "III — DO PEDIDO\nRequer o acolhimento dos embargos para sanar o vício apontado, "
            "com efeitos [infringentes, se o caso]." + _RODAPE
        ),
    },
    {
        "titulo": "Contrarrazões de Recurso",
        "tipo_peca": "contrarrazoes",
        "area": "civil",
        "descricao": "Resposta ao recurso da parte adversa.",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DE {{comarca}}\n\n"
            "Processo nº {{numero_processo}}\n\n\n"
            "{{cliente_nome}}, já qualificado(a) nos autos, vem apresentar\n\n"
            "CONTRARRAZÕES\n\n"
            "ao recurso interposto por {{parte_contraria}}, requerendo a remessa à instância "
            "superior.\n\n"
            "EGRÉGIO TRIBUNAL,\n\n"
            "I — DA ADMISSIBILIDADE\n[DESENVOLVER eventuais preliminares — intempestividade, "
            "ausência de preparo, falta de dialeticidade (Súmula 283 STF).]\n\n"
            "II — DO MÉRITO\n[DESENVOLVER a defesa da decisão recorrida; refutar as razões do recorrente.]\n\n"
            "III — DO PEDIDO\nRequer o não conhecimento ou o desprovimento do recurso, mantida "
            "a decisão por seus próprios fundamentos." + _RODAPE
        ),
    },
    {
        "titulo": "Mandado de Segurança",
        "tipo_peca": "peticao_inicial",
        "area": "administrativo",
        "descricao": "MS contra ato de autoridade (Lei 12.016/09; CF art. 5º LXIX).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} DE {{comarca}}\n"
            "(juízo competente conforme a autoridade coatora)\n\n\n"
            "{{cliente_nome}}, CPF/CNPJ {{cliente_cpf_cnpj}}, com endereço em {{cliente_endereco}}, "
            "vem impetrar\n\n"
            "MANDADO DE SEGURANÇA [com pedido de liminar]\n\n"
            "contra ato do(a) [DESENVOLVER: autoridade coatora — {{parte_contraria}}], pelos "
            "fundamentos a seguir (Lei 12.016/09).\n\n"
            "I — DOS FATOS\n[DESENVOLVER o ato coator.]\n\n"
            "II — DO DIREITO LÍQUIDO E CERTO\n[DESENVOLVER: comprovação documental pré-constituída; "
            "ilegalidade/abuso de poder.]\n\n"
            "III — DA LIMINAR\n[DESENVOLVER fumus boni iuris e periculum in mora — art. 7º, III.]\n\n"
            "IV — DOS PEDIDOS\nRequer:\n"
            "a) a concessão da liminar;\n"
            "b) a notificação da autoridade coatora para prestar informações (10 dias);\n"
            "c) a ciência ao órgão de representação judicial da pessoa jurídica;\n"
            "d) a oitiva do Ministério Público;\n"
            "e) a concessão definitiva da segurança.\n\n"
            "Dá-se à causa o valor de {{valor_causa}}." + _RODAPE
        ),
    },
    {
        "titulo": "Habeas Corpus",
        "tipo_peca": "outro",
        "area": "criminal",
        "descricao": "HC em favor do paciente (CF art. 5º LXVIII; CPP art. 647).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DESEMBARGADOR(A) / JUIZ(A) [tribunal competente]\n\n\n"
            "{{cliente_nome}}, advogado(a) [ou impetrante], vem impetrar\n\n"
            "HABEAS CORPUS [com pedido de liminar]\n\n"
            "em favor de [DESENVOLVER: paciente], apontando como autoridade coatora "
            "{{parte_contraria}}, com fundamento no art. 647 do CPP e art. 5º, LXVIII, da CF.\n\n"
            "I — DOS FATOS\n[DESENVOLVER a situação de constrangimento ilegal.]\n\n"
            "II — DO CONSTRANGIMENTO ILEGAL\n[DESENVOLVER a hipótese do art. 648 do CPP — "
            "ausência de justa causa, excesso de prazo, etc.]\n\n"
            "III — DA LIMINAR\n[DESENVOLVER fumus boni iuris e periculum libertatis.]\n\n"
            "IV — DO PEDIDO\nRequer a concessão da ordem para [DESENVOLVER: relaxamento da "
            "prisão / trancamento da ação / revogação da preventiva].\n\n"
            "Termos em que pede deferimento.\n\n"
            "{{comarca}}, {{data_hoje}}.\n\n{{advogado_nome}}\nOAB {{advogado_oab}}\n\n"
            "____________________________________________________________\n"
            "MINUTA — revisão humana obrigatória."
        ),
    },
    {
        "titulo": "Queixa-Crime",
        "tipo_peca": "peticao_inicial",
        "area": "criminal",
        "descricao": "Ação penal privada (CPP art. 41 e 44).",
        "conteudo": (
            "EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {{vara}} CRIMINAL DE "
            "{{comarca}}\n\n\n"
            "{{cliente_nome}}, CPF nº {{cliente_cpf_cnpj}}, residente em {{cliente_endereco}}, "
            "por seu advogado (procuração com poderes especiais — CPP art. 44), vem oferecer\n\n"
            "QUEIXA-CRIME\n\n"
            "em face de {{parte_contraria}}, pelos fatos a seguir.\n\n"
            "I — DA TITULARIDADE E TEMPESTIVIDADE\n[DESENVOLVER: legitimidade do querelante; "
            "prazo decadencial de 6 meses (CP art. 103).]\n\n"
            "II — DOS FATOS\n[DESENVOLVER a conduta típica com todas as circunstâncias — art. 41 CPP.]\n\n"
            "III — DO DIREITO\n[DESENVOLVER a capitulação penal e a autoria.]\n\n"
            "IV — DOS PEDIDOS\nRequer o recebimento da queixa, a citação do querelado, a "
            "designação de audiência e, ao final, a condenação. Rol de testemunhas: [DESENVOLVER]." + _RODAPE
        ),
    },
]


def seed():
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
    except ImportError:
        print("❌ SQLAlchemy não encontrado.")
        sys.exit(1)

    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    if not url:
        print("❌ DATABASE_URL(_SYNC) não configurada.")
        sys.exit(1)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://") and "+" not in url.split("://")[0] + "://":
        url = url.replace("postgresql://", "postgresql+psycopg2://")

    force = os.getenv("FORCE_TEMPLATES_UPDATE", "false").lower() == "true"
    engine = create_engine(url)
    ins = upd = skip = 0
    with Session(engine) as s:
        for t in TEMPLATES:
            row = s.execute(
                text("SELECT id FROM doc_templates WHERE titulo = :tit AND deleted_at IS NULL"),
                {"tit": t["titulo"]},
            ).fetchone()
            if row is None:
                s.execute(text("""
                    INSERT INTO doc_templates (id, titulo, tipo_peca, area, descricao, conteudo, ativo)
                    VALUES (:id, :titulo, :tipo_peca, :area, :descricao, :conteudo, true)
                """), {"id": str(uuid4()), **t})
                print(f"  ✅ Inserido: {t['titulo']}")
                ins += 1
            elif force:
                s.execute(text("""
                    UPDATE doc_templates SET tipo_peca=:tipo_peca, area=:area,
                        descricao=:descricao, conteudo=:conteudo, updated_at=now()
                    WHERE id=:id
                """), {"id": row[0], **t})
                print(f"  🔄 Atualizado: {t['titulo']}")
                upd += 1
            else:
                print(f"  ⏭️  Já existe: {t['titulo']}")
                skip += 1
        s.commit()
    print(f"\n{'─'*50}\nTEMPLATES SEED: inseridos={ins} atualizados={upd} ignorados={skip} total={len(TEMPLATES)}\n{'─'*50}")


if __name__ == "__main__":
    print("EJC — Templates Seed\n")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    seed()
