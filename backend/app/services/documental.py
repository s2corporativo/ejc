from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.user import User
from app.services.document_format import aviso_minuta_automatica, padronizar_documento_juridico
from app.utils.format import formatar_brl


_MARCA = aviso_minuta_automatica() + "\n\n"
_settings = get_settings()

# OUTORGADO FIXO da procuração — sócio-titular do escritório. O modelo oficial
# da procuração é SEMPRE outorgado ao sócio-titular, INDEPENDENTEMENTE do
# advogado responsável pelo caso (que, quando preciso, atua por
# substabelecimento). Dado institucional fixo (não é PII de cliente).
_OUTORGADO_SOCIO = (
    "JOÃO PEDRO RODRIGUES TEIXEIRA, brasileiro, advogado, OAB/MG nº 251.174, "
    "com endereço profissional na Av. Gov. Valadares nº 851, sala 405, Centro, "
    "Betim/MG, e-mail contato@depaulateixeira.adv.br"
)

# Cabeçalho oficial (timbre textual) da procuração do escritório.
_CABECALHO_ESCRITORIO = "DE PAULA TEIXEIRA - SOCIEDADE DE ADVOGADOS"

_MESES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _data_extenso(d: date) -> str:
    """Data corrente por extenso em pt-BR (ex.: '22 de julho de 2026'). Usa o
    datetime normal do Python (permitido no service; a proibição de Date.now()
    é um padrão de front-end, não do backend)."""
    return f"{d.day} de {_MESES_PT[d.month - 1]} de {d.year}"


def _qualificacao(c: Client) -> str:
    # Cutover C6/LGPD: documento vive só cifrado — presença via cnpj_enc, valor
    # em claro via cnpj_plain/cpf_plain (decifrado para a peça).
    if (getattr(c, "tipo", "") or "").lower() in ("pj", "juridica", "pessoa_juridica") or c.cnpj_enc:
        return (
            f"{c.razao_social or c.nome}, pessoa jurídica inscrita no CNPJ sob o nº "
            f"{c.cnpj_plain or '[CNPJ]'}, com sede em "
            f"{c.logradouro or '[endereço]'}, {c.numero or ''} {c.complemento or ''}, "
            f"{c.bairro or ''}, {c.cidade or '[cidade]'}/{c.estado or 'MG'}, CEP {c.cep or '[CEP]'}"
        )
    # Nacionalidade da PF na qualificação do outorgante. O model Client ainda não
    # possui a coluna (esta fase NÃO exige migration) — sem o campo, assume o
    # default "brasileiro(a)". Quando a coluna existir e vier preenchida, é usada.
    nacionalidade = (getattr(c, "nacionalidade", "") or "").strip() or "brasileiro(a)"
    return (
        f"{c.nome}, {nacionalidade}, {c.profissao or '[profissão]'}, inscrito(a) no CPF sob o nº "
        f"{c.cpf_plain or '[CPF]'}, residente em {c.logradouro or '[endereço]'}, "
        f"{c.numero or ''} {c.complemento or ''}, {c.bairro or ''}, "
        f"{c.cidade or '[cidade]'}/{c.estado or 'MG'}, CEP {c.cep or '[CEP]'}"
    )


# Poderes especiais do art. 105 do CPC. NUNCA os outorgue por padrao: so entram
# quando o cadastro (Procuracao.tipo_poderes) diz "ad_judicia_et_extra".
_PODERES_ESPECIAIS_105 = (
    "receber citação, confessar, reconhecer a procedência do pedido, "
    "transigir, desistir, renunciar ao direito sobre que se funda a ação, "
    "receber e dar quitação, firmar compromisso"
)
# Clausula de substabelecimento (padrao do escritorio: com ou sem reserva). So
# aparece quando o cadastro autoriza (Procuracao.permite_substabelecimento).
_CLAUSULA_SUBSTAB = ", e substabelecer esta a outrem, com ou sem reserva de poderes"


def _clausula_poderes(
    tipo_poderes: str,
    permite_substabelecimento: bool,
    poderes_especiais: str | None,
) -> tuple[str, str]:
    """Monta (titulo, corpo dos poderes) a partir do cadastro da Procuracao.

    Regra de ouro: nunca outorgar poderes que o cadastro nao concedeu. A
    clausula de SUBSTABELECIMENTO so entra quando ``permite_substabelecimento``
    for True; os PODERES ESPECIAIS do art. 105 do CPC (transigir, desistir,
    RENUNCIAR, firmar compromisso, etc.) so entram em ``ad_judicia_et_extra`` ou,
    de forma explicita e controlada, via texto em ``especiais``.
    """
    tipo = (tipo_poderes or "ad_judicia").strip().lower()
    substab = _CLAUSULA_SUBSTAB if permite_substabelecimento else ""

    if tipo == "ad_judicia_et_extra":
        titulo = "PROCURAÇÃO AD JUDICIA ET EXTRA"
        # Poderes gerais (modelo oficial do escritório) detalhados em alíneas
        # (a)-(j). A alínea (j) — substabelecimento — SÓ entra quando o cadastro
        # autoriza (permite_substabelecimento), preservando o gate independente
        # do art. 105 que o restante das alíneas materializa.
        alineas = [
            "(a) propor as ações e medidas cabíveis, inclusive tutelas de urgência e "
            "cautelares, defender o(a) outorgante nas contrárias e acompanhar os feitos "
            "em todas as instâncias e graus de jurisdição até o trânsito em julgado",
            "(b) confessar, reconhecer a procedência do pedido, transigir, celebrar "
            "acordos judiciais e extrajudiciais, fixar condições de pagamento e assinar "
            "os respectivos termos",
            "(c) desistir de recursos, renunciar ao direito sobre que se funda a ação "
            "(art. 105 do CPC) e praticar os demais atos de disposição processual",
            "(d) receber citações, intimações e notificações, inclusive eletrônicas "
            "(PJe, e-Proc e demais sistemas)",
            "(e) requerer os benefícios da Justiça Gratuita (Lei 1.060/50; art. 98 do CPC)",
            "(f) receber valores, dar quitação, levantar depósitos judiciais e assinar "
            "requerimentos de alvará",
            "(g) obter certidões e informações junto a cartórios, juntas comerciais, "
            "DETRAN, Receita Federal, INSS, FGTS e demais órgãos",
            "(h) representar o(a) outorgante em audiências de conciliação, mediação, "
            "instrução e julgamento",
            "(i) assinar petições, memoriais e documentos",
        ]
        if permite_substabelecimento:
            alineas.append(
                "(j) substabelecer este mandato, com ou sem reserva de poderes"
            )
        corpo = (
            "a quem confere os poderes da cláusula ad judicia et extra, para o foro em "
            "geral, em qualquer Juízo, Instância ou Tribunal, e ainda os seguintes "
            "poderes especiais: " + "; ".join(alineas)
        )
    elif tipo == "especiais":
        titulo = "PROCURAÇÃO COM PODERES ESPECIAIS"
        especiais = (poderes_especiais or "").strip() or "[especificar os poderes especiais outorgados]"
        corpo = (
            "a quem confere os poderes da cláusula ad judicia, para o foro em geral, "
            "em qualquer Juízo, Instância ou Tribunal, podendo propor as ações "
            "competentes e defender o(a) outorgante nas contrárias, além dos seguintes "
            "poderes especiais expressamente outorgados: " + especiais + substab
        )
    else:  # "ad_judicia" — default CONSERVADOR (so foro em geral, sem art. 105)
        titulo = "PROCURAÇÃO AD JUDICIA"
        corpo = (
            "a quem confere os poderes da cláusula ad judicia, para o foro em geral, "
            "em qualquer Juízo, Instância ou Tribunal, podendo propor as ações "
            "competentes e defender o(a) outorgante nas contrárias" + substab
        )
    return titulo, corpo


def _procuracao(
    case: Case | None,
    cli: Client,
    adv: str,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
    foro_restrito: str | None = None,
) -> str:
    # PODERES: derivados do cadastro Procuracao (tipo_poderes /
    # permite_substabelecimento / poderes_especiais). DEFAULTS CONSERVADORES,
    # alinhados ao kit documental (KitDocumentalIn) e ao model Procuracao:
    # "ad_judicia" SEM os poderes especiais do art. 105 do CPC — renuncia,
    # transacao, quitacao etc. SO entram com marcacao explicita
    # ("ad_judicia_et_extra" ou "especiais"); o substabelecimento segue o flag
    # permite_substabelecimento (padrao do escritorio, default True como no
    # kit). O comportamento historico do fluxo legado (et extra + substab por
    # omissao) foi DESCONTINUADO: quem precisar do escopo amplo deve pedir
    # explicitamente (parametros do endpoint gerar-documentos / kit).
    #
    # OUTORGADO FIXO: o modelo oficial do escritório é SEMPRE outorgado ao
    # sócio-titular (_OUTORGADO_SOCIO), independentemente do advogado responsável
    # pelo caso — por isso o parâmetro `adv` NÃO é mais usado no corpo (mantido só
    # por compatibilidade da assinatura dos call-sites; o outorgado é fixo e a
    # única assinatura no rodapé é a do OUTORGANTE/cliente). A CIDADE de assinatura
    # é a sede do escritório e a DATA é a corrente por extenso (fuso de Brasília).
    tipo = (tipo_poderes or "ad_judicia").strip().lower()
    titulo, corpo_poderes = _clausula_poderes(tipo_poderes, permite_substabelecimento, poderes_especiais)

    # Cabeçalho oficial: no modelo de PODERES GERAIS (ad_judicia_et_extra) sai o
    # timbre completo; nos demais tipos, o timbre do escritório + o título do
    # instrumento (mantém "PROCURAÇÃO AD JUDICIA"/"...ESPECIAIS" visível).
    if tipo == "ad_judicia_et_extra":
        cabecalho = (
            _CABECALHO_ESCRITORIO + "\n"
            "PROCURAÇÃO\n"
            "AD JUDICIA ET EXTRA - PODERES GERAIS"
        )
    else:
        cabecalho = _CABECALHO_ESCRITORIO + "\n" + titulo

    if case is not None:
        alvo = (
            f", especialmente para atuar no caso {case.titulo}"
            f"{(' (processo nº ' + case.numero_processo + ')') if case.numero_processo else ''}"
        )
    elif foro_restrito:
        alvo = f", com atuação adstrita ao foro/comarca de {foro_restrito}"
    else:
        alvo = ""

    texto = _MARCA + (
        cabecalho + "\n\n"
        f"OUTORGANTE: {_qualificacao(cli)}.\n\n"
        f"OUTORGADO: {_OUTORGADO_SOCIO}.\n\n"
        "PODERES: Pelo presente instrumento, o(a) outorgante nomeia e constitui seu(sua) "
        "bastante procurador(a) o(a) advogado(a) acima, "
        + corpo_poderes + alvo + ".\n\n"
        f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, {_data_extenso(datetime.now(timezone(timedelta(hours=-3))).date())}.\n\n"
        "______________________________________\n"
        f"{cli.razao_social or cli.nome}"
    )
    return padronizar_documento_juridico(texto)


# ── Cláusulas FIXAS de template do contrato COMPLETO (FASE 4) ────────────────
# Texto padrão do escritório, 100% determinístico (SEM LLM). Só entram quando
# há proposta de honorários APROVADA (fee_proposal_service) — sem proposta, o
# contrato mantém EXATAMENTE o comportamento histórico (placeholders de revisão).
_CLAUSULAS_FIXAS_CONTRATO = (
    "RESCISÃO. O presente contrato poderá ser rescindido por qualquer das partes, "
    "mediante comunicação escrita, sendo devidos ao contratado os honorários "
    "proporcionais ao trabalho já realizado até a data da rescisão, na forma do "
    "artigo 22 da Lei 8.906/94.",
    "INADIMPLEMENTO. O atraso no pagamento de qualquer parcela sujeitará o "
    "contratante a multa de 2% (dois por cento), juros de mora de 1% (um por "
    "cento) ao mês e correção monetária, autorizada a suspensão dos serviços "
    "não urgentes após notificação, ressalvados os deveres legais do advogado.",
    "REVOGAÇÃO E RENÚNCIA. A revogação do mandato pelo contratante não o exime "
    "do pagamento dos honorários proporcionais ao trabalho realizado. Em caso "
    "de renúncia, o contratado observará o artigo 112 do CPC, permanecendo "
    "responsável pelos atos urgentes pelo prazo legal.",
    "PROTEÇÃO DE DADOS (LGPD). Os dados pessoais do contratante serão tratados "
    "exclusivamente para a execução deste contrato e o cumprimento de "
    "obrigações legais e regulatórias, nos termos da Lei 13.709/2018 (LGPD), "
    "observado o sigilo profissional do advogado (Lei 8.906/94).",
    "COMUNICAÇÃO ELETRÔNICA. As partes reconhecem como válidas as comunicações "
    "realizadas pelos e-mails e telefones informados no cadastro, inclusive "
    "por aplicativos de mensagens, cabendo a cada parte manter seus dados de "
    "contato atualizados.",
)


def _contrato_honorarios(
    case: Case, cli: Client, adv: str, area: str,
    referencia_oab: str | None = None,
    proposta: dict | None = None,
) -> str:
    # OAB e cidade de assinatura são dados FIXOS do escritório (settings). Valor
    # dos honorários, percentual de êxito, forma de pagamento, comarca do foro e
    # data dependem do CASO/CLIENTE e continuam como placeholder de revisão.
    #
    # `referencia_oab` (kit documental P0.3): texto de referencia extraido da
    # tabela estruturada TabelaOABHonorario (ou o aviso explicito de "a definir"
    # quando nao ha item aplicavel). NUNCA substitui o valor contratado — o
    # R$ [____] permanece placeholder de revisao do advogado.
    #
    # `proposta` (FASE 4): parâmetros derivados de proposta de honorários
    # APROVADA (fee_proposal_service.proposta_para_contrato). Quando presente,
    # o contrato sai COMPLETO: valor/forma/êxito/despesas preenchidos +
    # cláusulas fixas de template (_CLAUSULAS_FIXAS_CONTRATO) + foro na comarca
    # do escritório. Sem proposta → comportamento atual EXATO (placeholders).
    ref = f" ({referencia_oab})" if referencia_oab else ""

    if proposta is None:
        clausulas = (
            "CLÁUSULA 2 - HONORÁRIOS. As partes ajustam honorários no valor de R$ [____], "
            f"tendo como referência a Tabela de Honorários da OAB/MG{ref}, pagos da seguinte forma: [____].\n\n"
            "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Em caso de êxito, fica ajustado o percentual de "
            "[__]% sobre o proveito econômico obtido.\n\n"
            "CLÁUSULA 4 - HONORÁRIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
            "parágrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
            "CLÁUSULA 5 - DESPESAS. Custas, taxas e despesas processuais correm por conta do contratante.\n\n"
            "CLÁUSULA 6 - FORO. Comarca de [____]/MG.\n\n"
        )
    else:
        valor = proposta.get("valor")
        valor_txt = formatar_brl(valor) if valor is not None else "R$ [____]"
        forma = proposta.get("forma_pagamento") or "[____]"
        versao = proposta.get("versao")
        origem = (f", conforme proposta de honorários aprovada"
                  f"{(' (versão ' + str(versao) + ')') if versao else ''}")
        exito = proposta.get("exito_percentual")
        exito_txt = (
            "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Em caso de êxito, fica ajustado o percentual de "
            f"{float(exito):g}% sobre o proveito econômico obtido.\n\n"
            if exito is not None else
            "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Não foram ajustados honorários de êxito "
            "entre as partes.\n\n"
        )
        despesas = proposta.get("despesas_criterio") or (
            "Custas, taxas e despesas processuais correm por conta do contratante."
        )
        clausulas_fixas = "".join(
            f"CLÁUSULA {n} - {texto}\n\n"
            for n, texto in enumerate(_CLAUSULAS_FIXAS_CONTRATO, start=6)
        )
        clausulas = (
            f"CLÁUSULA 2 - HONORÁRIOS. As partes ajustam honorários no valor de {valor_txt}, "
            f"tendo como referência a Tabela de Honorários da OAB/MG{ref}{origem}, "
            f"pagos da seguinte forma: {forma}.\n\n"
            + exito_txt +
            "CLÁUSULA 4 - HONORÁRIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
            "parágrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
            f"CLÁUSULA 5 - DESPESAS. {despesas}\n\n"
            + clausulas_fixas +
            f"CLÁUSULA {6 + len(_CLAUSULAS_FIXAS_CONTRATO)} - FORO. Fica eleito o foro da "
            f"Comarca de {_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, "
            "sede do escritório contratado, para dirimir quaisquer controvérsias "
            "oriundas deste contrato.\n\n"
        )

    texto = _MARCA + (
        "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS E HONORÁRIOS\n\n"
        f"CONTRATANTE: {_qualificacao(cli)}.\n\n"
        f"CONTRATADO: {_settings.ESCRITORIO_NOME}, por seu(sua) advogado(a) {adv}"
        f"{(' (OAB/MG nº ' + _settings.escritorio_oab() + ')') if _settings.escritorio_oab() else ''}.\n\n"
        f"CLÁUSULA 1 - OBJETO. Prestação de serviços advocatícios no caso {case.titulo} "
        f"(área: {area}){(', processo nº ' + case.numero_processo) if case.numero_processo else ''}.\n\n"
        + clausulas +
        f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        f"____________________________   ____________________________\n"
        f"{cli.razao_social or cli.nome} (contratante)        {adv} (contratado)"
    )
    return padronizar_documento_juridico(texto)


def _relatorio_inicial(case: Case, cli: Client, area: str) -> str:
    proc = f"\nProcesso: {case.numero_processo}" if case.numero_processo else ""
    texto = (
        "RELATÓRIO JURÍDICO INICIAL\n\n"
        f"Caso: {case.titulo}\nCliente: {cli.razao_social or cli.nome}\n"
        f"Área: {area}\nNº interno: {case.numero_interno or '-'}{proc}\n\n"
        "1. FATOS\n\n" + (case.descricao_fatos or "[a preencher]") + "\n\n"
        "2. TESE PRINCIPAL\n\n" + (case.tese_principal or "[análise pendente]") + "\n\n"
        "3. PONTOS FORTES\n\n" + (case.pontos_fortes or "-") + "\n\n"
        "4. PONTOS FRACOS E RISCOS\n\n" + (case.pontos_fracos or "-") + "\n\n"
        "5. PRÓXIMAS PROVIDÊNCIAS\n\n"
        "- Reunir documentos\n"
        "- Obter procuração assinada\n"
        "- Formalizar contrato de honorários\n"
        "- Definir estratégia processual ou extrajudicial\n\n"
        "Documento de trabalho. Síntese inicial sujeita a revisão jurídica."
    )
    return padronizar_documento_juridico(texto)


async def gerar_documentos_iniciais(
    case_id: str,
    user_id: str,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
) -> list[dict]:
    """Gera minutas iniciais do caso. Retorna lista de {id, titulo, tipo}.

    Procuração com DEFAULT CONSERVADOR (ad_judicia, mesmo contrato do kit
    documental): os poderes especiais do art. 105 do CPC só entram quando o
    chamador marca explicitamente ``tipo_poderes="ad_judicia_et_extra"`` (ou
    ``"especiais"`` + ``poderes_especiais``).
    """
    async with AsyncSessionLocal() as db:
        case = await db.get(Case, case_id)
        if not case:
            return []
        cli = await db.get(Client, case.client_id) if case.client_id else None
        if not cli:
            return []
        adv_user = await db.get(User, case.advogado_responsavel_id) if case.advogado_responsavel_id else None
        adv = getattr(adv_user, "full_name", None) or "[advogado responsável]"
        area = getattr(case.area, "value", None) or str(case.area or "")

        docs = [
            ("Procuração - " + case.titulo, PecaTipo.procuracao, _procuracao(
                case, cli, adv,
                tipo_poderes=tipo_poderes,
                permite_substabelecimento=permite_substabelecimento,
                poderes_especiais=poderes_especiais,
            )),
            ("Contrato de Honorários - " + case.titulo, PecaTipo.contrato, _contrato_honorarios(case, cli, adv, area)),
            ("Relatório Jurídico Inicial - " + case.titulo, PecaTipo.parecer, _relatorio_inicial(case, cli, area)),
        ]
        criados = []
        for titulo, tipo, conteudo in docs:
            d = LegalDoc(
                id=str(uuid4()),
                titulo=padronizar_documento_juridico(titulo)[:200],
                tipo_peca=tipo,
                conteudo=conteudo,
                status=PecaStatus.rascunho,
                ai_generated=True,
                human_reviewed=False,
                case_id=case_id,
                created_by=user_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(d)
            criados.append({"id": d.id, "titulo": d.titulo, "tipo": tipo.value})
        await db.commit()
        return criados
