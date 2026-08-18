"""
Templates de formatação para documentos jurídicos profissionais.
Padrão: De Paula Teixeira Advogados Associados — Betim/MG.
Todos os documentos gerados pela IA usam estes templates como base estrutural.

Os dados FIXOS do escritório (nome, CNPJ, OAB, endereço, CEP, cidade, email)
vêm da FONTE ÚNICA em app.core.config (settings ESCRITORIO_*). Quando OAB/
endereço/CEP ainda não foram preenchidos no .env, o SEGMENTO INTEIRO some do
timbre (rótulo incluído) — nunca placeholder de pendência interna nem rótulo
órfão no documento. A pendência fica visível ao operador em
Settings.escritorio_pendencias().
"""

from app.core.config import get_settings
from app.services.document_format import juntar_segmentos

_settings = get_settings()

DADOS_ESCRITORIO = {
    "nome": _settings.ESCRITORIO_NOME,
    "cnpj": _settings.escritorio_cnpj(),
    "oab_registro": _settings.escritorio_oab(),
    "endereco": _settings.escritorio_endereco(),
    "cep": _settings.escritorio_cep(),
    "cidade": _settings.ESCRITORIO_CIDADE,
    "estado": _settings.ESCRITORIO_ESTADO,
    "telefone": "[telefone - preencher]",
    "email": _settings.ESCRITORIO_EMAIL,
    "site": "[site - preencher]",
}

# OAB individual de cada advogado não é dado do escritório (setting única): fica
# como placeholder explícito até ser informado no cadastro do profissional.
ADVOGADOS = {
    "clovis": {"nome": "Dr. Clovis José Soares", "oab": "[OAB/MG - preencher]", "cargo": "Sócio Administrador"},
    "guilherme": {"nome": "Guilherme de Paula", "oab": "[OAB/MG - preencher]", "cargo": "Sócio"},
    "joao_pedro": {"nome": "João Pedro Teixeira", "oab": "[OAB/MG - preencher]", "cargo": "Sócio"},
}

# Linhas montadas por SEGMENTO: o que não está preenchido no .env não vira linha
# nem rótulo solto no timbre.
_LINHA_OAB = f"OAB/MG {DADOS_ESCRITORIO['oab_registro']}" if DADOS_ESCRITORIO["oab_registro"] else ""
# CNPJ vazio (default desde a auditoria jul/2026) NÃO vira rótulo órfão
# "CNPJ:" no rodapé — o segmento inteiro some (juntar_segmentos descarta).
_LINHA_CNPJ = f"CNPJ: {DADOS_ESCRITORIO['cnpj']}" if DADOS_ESCRITORIO["cnpj"] else ""
_LINHA_ENDERECO = juntar_segmentos(
    (
        DADOS_ESCRITORIO["endereco"],
        f"{DADOS_ESCRITORIO['cidade']}/{DADOS_ESCRITORIO['estado']}",
        f"CEP {DADOS_ESCRITORIO['cep']}" if DADOS_ESCRITORIO["cep"] else "",
    ),
    " — ",
)

TIMBRADO = "\n" + juntar_segmentos(
    (
        "=" * 80,
        "DE PAULA TEIXEIRA ADVOGADOS ASSOCIADOS",
        "Civil | Trabalhista | Consumidor | Família | Ambiental | Criminal",
        _LINHA_OAB,
        _LINHA_ENDERECO,
        "Tel: {telefone} | {email} | {site}".format(**DADOS_ESCRITORIO),
        "=" * 80,
    ),
    "\n",
) + "\n"

RODAPE = "\n" + juntar_segmentos(
    (
        "---",
        juntar_segmentos(("De Paula Teixeira Advogados Associados", _LINHA_OAB), " — "),
        _LINHA_CNPJ,
        juntar_segmentos(
            (DADOS_ESCRITORIO["endereco"], f"{DADOS_ESCRITORIO['cidade']}/{DADOS_ESCRITORIO['estado']}"),
            " — ",
        ),
        "Tel: {telefone} | {email}".format(**DADOS_ESCRITORIO),
    ),
    "\n",
) + "\n"

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

TEMPLATE_RESPOSTA_NOTIFICACAO = """
{timbrado}

RESPOSTA À NOTIFICAÇÃO EXTRAJUDICIAL

NOTIFICANTE ORIGINAL: {nome_notificante}
NOTIFICADO(A) / ORA RESPONDENTE: {nome_notificado}
REFERÊNCIA: Notificação recebida em {data_notificacao_original}
DATA: {data}

Senhor(a) {nome_notificante},

Em atenção à notificação extrajudicial em referência, vem o(a) respondente,
respeitosamente, apresentar sua RESPOSTA, nos seguintes termos:

I — DAS ALEGAÇÕES DA NOTIFICAÇÃO
{sintese_alegacoes}

II — DA RESPOSTA
{corpo_resposta}

III — DA POSIÇÃO DO RESPONDENTE
{posicao_final}

A presente resposta é apresentada com expressa RESSALVA de todos os direitos
do(a) respondente e NÃO importa reconhecimento de qualquer dívida, culpa ou
obrigação não expressamente admitida.

{cidade}, {data_por_extenso}.

_____________________________________________
{nome_advogado}
OAB/MG {oab_advogado}
De Paula Teixeira Advogados Associados
{rodape}
"""

TEMPLATE_CONFISSAO_DIVIDA = """
INSTRUMENTO PARTICULAR DE CONFISSÃO DE DÍVIDA

CREDOR(A): {qualificacao_credor}
DEVEDOR(A): {qualificacao_devedor}

As partes acima qualificadas têm, entre si, justo e acordado o presente
Instrumento Particular de Confissão de Dívida, que se regerá pelas cláusulas
seguintes (título executivo extrajudicial — art. 784, III, do CPC):

CLÁUSULA 1ª — DA ORIGEM E DO RECONHECIMENTO DA DÍVIDA
{origem_divida}
O(A) DEVEDOR(A) reconhece e confessa dever ao(à) CREDOR(A) a quantia certa,
líquida e atualizada de R$ {valor_divida} ({valor_divida_extenso}).

CLÁUSULA 2ª — DA FORMA DE PAGAMENTO
{forma_pagamento}

CLÁUSULA 3ª — DA CORREÇÃO, JUROS E ENCARGOS
{encargos_mora}

CLÁUSULA 4ª — DO VENCIMENTO ANTECIPADO
O inadimplemento de qualquer parcela acarretará o vencimento antecipado de
toda a dívida, independentemente de notificação, sujeitando o débito aos
encargos moratórios pactuados.

CLÁUSULA 5ª — DO FORO
Fica eleito o foro da Comarca de {comarca_foro}, com renúncia a qualquer outro.
[Preencha comarca_foro com foro PERTINENTE ao domicílio das partes ou ao local da
obrigação — CPC art. 63, red. Lei 14.879/2024: foro aleatório é ineficaz e pode ser
reconhecido de ofício.]

E, por estarem assim justas e acordadas, firmam o presente em duas vias, na
presença das testemunhas abaixo.

{cidade}, {data_por_extenso}.

_____________________________________  _____________________________________
CREDOR(A)                              DEVEDOR(A)

TESTEMUNHAS:
1. _______________________________ CPF: ______________________
2. _______________________________ CPF: ______________________
"""

TEMPLATE_TERMO_QUITACAO = """
TERMO DE QUITAÇÃO

Pelo presente instrumento, {qualificacao_credor}, doravante denominado(a)
CREDOR(A)/OUTORGANTE, DECLARA ter recebido de {qualificacao_devedor},
doravante denominado(a) DEVEDOR(A)/OUTORGADO(A), a importância de
R$ {valor_recebido} ({valor_recebido_extenso}), referente a
{objeto_quitacao}.

Diante do integral recebimento, o(a) CREDOR(A) outorga ao(à) DEVEDOR(A) a mais
plena, geral, rasa, irrevogável e irretratável QUITAÇÃO quanto ao objeto acima,
para nada mais reclamar, a qualquer tempo ou título, com relação à obrigação
ora quitada.
{ressalvas}

{cidade}, {data_por_extenso}.

_____________________________________________
{qualificacao_credor}
(CREDOR(A) / OUTORGANTE DA QUITAÇÃO)
"""

TEMPLATE_DISTRATO = """
INSTRUMENTO PARTICULAR DE DISTRATO

{qualificacao_parte1} e {qualificacao_parte2}, doravante denominadas
DISTRATANTES, tendo firmado {identificacao_contrato} em {data_contrato_original},
resolvem, de comum acordo e na melhor forma de direito (art. 472 do Código
Civil), celebrar o presente DISTRATO, mediante as cláusulas seguintes:

CLÁUSULA 1ª — DA RESCISÃO
As DISTRATANTES rescindem, por mútuo consenso, o contrato acima identificado,
que se dá por extinto a partir de {data_efeito_distrato}.

CLÁUSULA 2ª — DO ACERTO DE OBRIGAÇÕES PENDENTES
{acerto_obrigacoes}

CLÁUSULA 3ª — DA QUITAÇÃO RECÍPROCA
Cumpridas as obrigações da Cláusula 2ª, as DISTRATANTES dão-se mútua, plena e
irrevogável quitação quanto ao contrato distratado, nada mais tendo a reclamar
uma da outra em razão dele.

CLÁUSULA 4ª — DO FORO
Fica eleito o foro da Comarca de {comarca_foro} para dirimir eventuais dúvidas.
[comarca_foro deve guardar pertinência com o domicílio das partes ou o local da
obrigação — CPC art. 63, red. Lei 14.879/2024.]

E, por estarem assim justas e acordadas, firmam o presente em duas vias.

{cidade}, {data_por_extenso}.

_____________________________________  _____________________________________
{qualificacao_parte1}                  {qualificacao_parte2}
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
