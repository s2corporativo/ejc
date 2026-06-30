"""
Templates de formatação para documentos jurídicos profissionais.
Padrão: De Paula Teixeira Advogados Associados — Betim/MG.
Todos os documentos gerados pela IA usam estes templates como base estrutural.
"""

DADOS_ESCRITORIO = {
    "nome": "De Paula Teixeira Advogados Associados",
    "cnpj": "A PREENCHER",
    "oab_registro": "A PREENCHER",
    "endereco": "A PREENCHER",
    "cep": "A PREENCHER",
    "cidade": "Betim",
    "estado": "MG",
    "telefone": "A PREENCHER",
    "email": "A PREENCHER",
    "site": "A PREENCHER",
}

ADVOGADOS = {
    "clovis": {"nome": "Dr. Clovis José Soares", "oab": "A PREENCHER", "cargo": "Sócio Administrador"},
    "guilherme": {"nome": "Guilherme de Paula", "oab": "A PREENCHER", "cargo": "Sócio"},
    "joao_pedro": {"nome": "João Pedro Teixeira", "oab": "A PREENCHER", "cargo": "Sócio"},
}

TIMBRADO = """
================================================================================
DE PAULA TEIXEIRA ADVOGADOS ASSOCIADOS
Civil | Trabalhista | Consumidor | Família | Ambiental | Criminal
OAB/MG {oab_registro}
{endereco} — {cidade}/{estado} — CEP {cep}
Tel: {telefone} | {email} | {site}
================================================================================
""".format(**DADOS_ESCRITORIO)

RODAPE = """
---
De Paula Teixeira Advogados Associados — OAB/MG {oab_registro}
CNPJ: {cnpj}
{endereco} — {cidade}/{estado}
Tel: {telefone} | {email}
""".format(**DADOS_ESCRITORIO)

TEMPLATE_PETICAO_INICIAL = """
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {vara}
DA COMARCA DE {comarca} — ESTADO DE MINAS GERAIS

{qualificacao_autor}, doravante denominado(a) AUTOR(A), por meio de seu(sua)
advogado(a), {nome_advogado}, inscrito(a) na OAB/MG sob n.º {oab_advogado},
com endereço profissional na {endereco_escritorio}, onde recebe intimações,
nos termos dos artigos 319 e seguintes do Código de Processo Civil (Lei
n.º 13.105/2015), vem, respeitosamente, à presença de Vossa Excelência
propor a presente

AÇÃO {tipo_acao}

em face de {qualificacao_reu}, doravante denominado(a) RÉU/RÉ, pelos fatos
e fundamentos jurídicos a seguir expostos:

I — DOS FATOS
{narrativa_fatos}

II — DO DIREITO
{fundamentacao_juridica}

III — DOS PEDIDOS
Diante do exposto, requer a Vossa Excelência:
{pedidos_numerados}

Atribui-se à causa o valor de R$ {valor_causa} ({valor_causa_extenso}),
nos termos do artigo 292 do Código de Processo Civil.

{cidade}, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
"""

TEMPLATE_CONTESTACAO = """
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA {vara}
DA COMARCA DE {comarca} — ESTADO DE MINAS GERAIS

Processo n.º {numero_processo}

{qualificacao_reu}, devidamente qualificado(a) nos autos do processo
em epígrafe, por meio de seu(sua) advogado(a), {nome_advogado}, inscrito(a)
na OAB/MG sob n.º {oab_advogado}, com endereço profissional na
{endereco_escritorio}, onde recebe intimações, vem, tempestivamente,
com fundamento nos artigos 335 e seguintes do Código de Processo Civil,
apresentar

CONTESTAÇÃO

pelos fatos e fundamentos jurídicos a seguir expostos:

I — PRELIMINARES
{preliminares}

II — DO MÉRITO
{merito}

III — DAS PROVAS
Protesta pela produção de todos os meios de prova em direito admitidos,
em especial: {meios_de_prova}.

IV — DOS PEDIDOS
Diante do exposto, requer a Vossa Excelência:
{pedidos_numerados}

Dá-se à causa, para fins processuais, o valor atribuído pelo(a) Autor(a).

{cidade}, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
"""

TEMPLATE_PARECER = """
{timbrado}

PARECER JURÍDICO N.º {numero_parecer}/{ano}

CONSULENTE: {nome_consulente}
ASSUNTO: {assunto}
ADVOGADO RESPONSÁVEL: {nome_advogado} — OAB/MG {oab_advogado}
DATA: {data}

I — RELATÓRIO
{relatorio}

II — ANÁLISE JURÍDICA
{analise_juridica}

III — CONCLUSÃO
{conclusao}

Betim/MG, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados

AVISO LEGAL: Este parecer é destinado exclusivamente ao consulente acima
identificado e não pode ser reproduzido sem autorização expressa.
{rodape}
"""

TEMPLATE_NOTIFICACAO = """
{timbrado}

NOTIFICAÇÃO EXTRAJUDICIAL

NOTIFICANTE: {nome_notificante}
NOTIFICADO(A): {nome_notificado}
DATA: {data}

Senhor(a) {nome_notificado},

{corpo_notificacao}

Diante do exposto, NOTIFICA-SE Vossa Senhoria para que, no prazo de
{prazo_dias} ({prazo_extenso}) dias úteis contados do recebimento desta,
{obrigacao_exigida}.

O não atendimento desta notificação no prazo acima fixado implicará
{consequencia_descumprimento}, sem prejuízo das demais medidas legais cabíveis.

{cidade}, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
{rodape}
"""

TEMPLATE_RELATORIO_CASO = """
RELATÓRIO DE CASO — USO INTERNO — CONFIDENCIAL
De Paula Teixeira Advogados Associados

CASO N.º: {numero_caso}
ÁREA: {area_juridica}
ADVOGADO RESPONSÁVEL: {advogado_responsavel}
DATA DO RELATÓRIO: {data}
GERADO POR: Assistente IA EJC (RASCUNHO — revisão obrigatória)

1. SÍNTESE DO CASO
{sintese}

2. STATUS ATUAL
Fase processual: {fase_processual}
Último movimento: {ultimo_movimento}
Próximo prazo: {proximo_prazo}

3. ANÁLISE ESTRATÉGICA
{analise_estrategica}

4. PONTOS FORTES
{pontos_fortes}

5. RISCOS E PONTOS FRACOS
{riscos}

6. PRÓXIMAS AÇÕES
{proximas_acoes}

7. PRAZOS IDENTIFICADOS
{prazos}

8. OBSERVAÇÕES ADICIONAIS
{observacoes}

⚠️ RASCUNHO GERADO POR IA — REVISÃO HUMANA OBRIGATÓRIA
"""

TEMPLATE_PROPOSTA_HONORARIOS = """
{timbrado}

PROPOSTA DE HONORÁRIOS ADVOCATÍCIOS
N.º {numero_proposta}/{ano}

DATA: {data}
VÁLIDA ATÉ: {validade}

CLIENTE: {nome_cliente}
OBJETO: {objeto_servico}
ADVOGADO RESPONSÁVEL: {nome_advogado} — OAB/MG {oab_advogado}

I — DESCRIÇÃO DOS SERVIÇOS
{descricao_servicos}

II — HONORÁRIOS PROPOSTOS
{detalhamento_honorarios}
Valor total dos honorários: R$ {valor_total} ({valor_total_extenso})

III — CONDIÇÕES DE PAGAMENTO
{condicoes_pagamento}

IV — DISPOSIÇÕES GERAIS
1. Os honorários são calculados conforme a Tabela de Honorários da OAB/MG.
2. Honorários de sucumbência são de titularidade do advogado (art. 85 CPC, art. 22 EOAB).
3. Despesas processuais não estão incluídas e serão cobradas à parte.
4. Esta proposta não constitui garantia de resultado (vedada pelo CED/OAB).
5. O contrato de honorários formalizará os termos acordados.

Atenciosamente,

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
{rodape}
"""

TEMPLATE_DEFESA_IBAMA = """
{timbrado}

DEFESA ADMINISTRATIVA
AUTO DE INFRAÇÃO N.º {numero_auto}
PROCESSO ADMINISTRATIVO N.º {numero_processo_admin}

AO ILUSTRÍSSIMO SENHOR
{autoridade_julgadora}
{orgao_julgador}

{qualificacao_autuado}, doravante denominado(a) AUTUADO(A), por meio de
seu(sua) advogado(a), {nome_advogado}, inscrito(a) na OAB/MG sob n.º
{oab_advogado}, com endereço profissional na {endereco_escritorio}, onde
recebe intimações, nos termos do artigo 71 do Decreto Federal n.º
6.514/2008, vem, tempestivamente, apresentar sua

DEFESA ADMINISTRATIVA

I — TEMPESTIVIDADE
{tempestividade}

II — DOS FATOS
{narrativa_fatos}

III — DO DIREITO
{fundamentacao_juridica}

IV — DOS VÍCIOS FORMAIS (se houver)
{vicios_formais}

V — DA DOSIMETRIA DA MULTA (subsidiário)
{dosimetria}

VI — DOS PEDIDOS
{pedidos_numerados}

Nesses termos, pede deferimento.

{cidade}, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
{rodape}
"""
