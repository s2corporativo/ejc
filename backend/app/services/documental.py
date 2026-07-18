from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.user import User
from app.services.document_format import aviso_minuta_automatica, padronizar_documento_juridico


_MARCA = aviso_minuta_automatica() + "\n\n"
_settings = get_settings()


def _qualificacao(c: Client) -> str:
    if (getattr(c, "tipo", "") or "").lower() in ("pj", "juridica", "pessoa_juridica") or c.cnpj:
        return (
            f"{c.razao_social or c.nome}, pessoa juridica inscrita no CNPJ sob o no "
            f"{c.cnpj or '[CNPJ]'}, com sede em "
            f"{c.logradouro or '[endereco]'}, {c.numero or ''} {c.complemento or ''}, "
            f"{c.bairro or ''}, {c.cidade or '[cidade]'}/{c.estado or 'MG'}, CEP {c.cep or '[CEP]'}"
        )
    return (
        f"{c.nome}, {c.profissao or '[profissao]'}, inscrito(a) no CPF sob o no "
        f"{c.cpf or '[CPF]'}, residente em {c.logradouro or '[endereco]'}, "
        f"{c.numero or ''} {c.complemento or ''}, {c.bairro or ''}, "
        f"{c.cidade or '[cidade]'}/{c.estado or 'MG'}, CEP {c.cep or '[CEP]'}"
    )


# Poderes especiais do art. 105 do CPC. NUNCA os outorgue por padrao: so entram
# quando o cadastro (Procuracao.tipo_poderes) diz "ad_judicia_et_extra".
_PODERES_ESPECIAIS_105 = (
    "receber citacao, confessar, reconhecer a procedencia do pedido, "
    "transigir, desistir, renunciar ao direito sobre que se funda a acao, "
    "receber e dar quitacao, firmar compromisso"
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
        titulo = "PROCURACAO AD JUDICIA ET EXTRA"
        corpo = (
            "a quem confere os poderes da clausula ad judicia et extra, para o foro "
            "em geral, em qualquer Juizo, Instancia ou Tribunal, podendo propor as "
            "acoes competentes e defender o(a) outorgante nas contrarias, bem como os "
            "poderes especiais para " + _PODERES_ESPECIAIS_105 + substab
        )
    elif tipo == "especiais":
        titulo = "PROCURACAO COM PODERES ESPECIAIS"
        especiais = (poderes_especiais or "").strip() or "[especificar os poderes especiais outorgados]"
        corpo = (
            "a quem confere os poderes da clausula ad judicia, para o foro em geral, "
            "em qualquer Juizo, Instancia ou Tribunal, podendo propor as acoes "
            "competentes e defender o(a) outorgante nas contrarias, alem dos seguintes "
            "poderes especiais expressamente outorgados: " + especiais + substab
        )
    else:  # "ad_judicia" — default CONSERVADOR (so foro em geral, sem art. 105)
        titulo = "PROCURACAO AD JUDICIA"
        corpo = (
            "a quem confere os poderes da clausula ad judicia, para o foro em geral, "
            "em qualquer Juizo, Instancia ou Tribunal, podendo propor as acoes "
            "competentes e defender o(a) outorgante nas contrarias" + substab
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
    # Dados FIXOS do escritório vêm das settings (fonte única). Quando ainda não
    # preenchidos no .env, os helpers devolvem placeholder EXPLÍCITO e visível.
    # A CIDADE de assinatura é a sede do escritório; a DATA depende do caso e
    # permanece como placeholder de revisão.
    titulo, corpo_poderes = _clausula_poderes(tipo_poderes, permite_substabelecimento, poderes_especiais)

    if case is not None:
        alvo = (
            f", especialmente para atuar no caso {case.titulo}"
            f"{(' (processo no ' + case.numero_processo + ')') if case.numero_processo else ''}"
        )
    elif foro_restrito:
        alvo = f", com atuacao adstrita ao foro/comarca de {foro_restrito}"
    else:
        alvo = ""

    texto = _MARCA + (
        titulo + "\n\n"
        f"OUTORGANTE: {_qualificacao(cli)}.\n\n"
        f"OUTORGADO(A): {adv}, advogado(a) inscrito(a) na OAB/MG sob o no {_settings.escritorio_oab()}, "
        f"integrante de {_settings.ESCRITORIO_NOME}, com escritorio em {_settings.escritorio_endereco()}.\n\n"
        "PODERES: Pelo presente instrumento, o(a) outorgante nomeia e constitui seu(sua) "
        "bastante procurador(a) o(a) advogado(a) acima, "
        + corpo_poderes + alvo + ".\n\n"
        f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        "______________________________________\n"
        f"{cli.razao_social or cli.nome}"
    )
    return padronizar_documento_juridico(texto)


# ── Cláusulas FIXAS de template do contrato COMPLETO (FASE 4) ────────────────
# Texto padrão do escritório, 100% determinístico (SEM LLM). Só entram quando
# há proposta de honorários APROVADA (fee_proposal_service) — sem proposta, o
# contrato mantém EXATAMENTE o comportamento histórico (placeholders de revisão).
_CLAUSULAS_FIXAS_CONTRATO = (
    "RESCISAO. O presente contrato podera ser rescindido por qualquer das partes, "
    "mediante comunicacao escrita, sendo devidos ao contratado os honorarios "
    "proporcionais ao trabalho ja realizado ate a data da rescisao, na forma do "
    "artigo 22 da Lei 8.906/94.",
    "INADIMPLEMENTO. O atraso no pagamento de qualquer parcela sujeitara o "
    "contratante a multa de 2% (dois por cento), juros de mora de 1% (um por "
    "cento) ao mes e correcao monetaria, autorizada a suspensao dos servicos "
    "nao urgentes apos notificacao, ressalvados os deveres legais do advogado.",
    "REVOGACAO E RENUNCIA. A revogacao do mandato pelo contratante nao o exime "
    "do pagamento dos honorarios proporcionais ao trabalho realizado. Em caso "
    "de renuncia, o contratado observara o artigo 112 do CPC, permanecendo "
    "responsavel pelos atos urgentes pelo prazo legal.",
    "PROTECAO DE DADOS (LGPD). Os dados pessoais do contratante serao tratados "
    "exclusivamente para a execucao deste contrato e o cumprimento de "
    "obrigacoes legais e regulatorias, nos termos da Lei 13.709/2018 (LGPD), "
    "observado o sigilo profissional do advogado (Lei 8.906/94).",
    "COMUNICACAO ELETRONICA. As partes reconhecem como validas as comunicacoes "
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
            "CLAUSULA 2 - HONORARIOS. As partes ajustam honorarios no valor de R$ [____], "
            f"tendo como referencia a Tabela de Honorarios da OAB/MG{ref}, pagos da seguinte forma: [____].\n\n"
            "CLAUSULA 3 - HONORARIOS DE EXITO. Em caso de exito, fica ajustado o percentual de "
            "[__]% sobre o proveito economico obtido.\n\n"
            "CLAUSULA 4 - HONORARIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
            "paragrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
            "CLAUSULA 5 - DESPESAS. Custas, taxas e despesas processuais correm por conta do contratante.\n\n"
            "CLAUSULA 6 - FORO. Comarca de [____]/MG.\n\n"
        )
    else:
        valor = proposta.get("valor")
        valor_txt = f"R$ {float(valor):,.2f}" if valor is not None else "R$ [____]"
        forma = proposta.get("forma_pagamento") or "[____]"
        versao = proposta.get("versao")
        origem = (f", conforme proposta de honorarios aprovada"
                  f"{(' (versao ' + str(versao) + ')') if versao else ''}")
        exito = proposta.get("exito_percentual")
        exito_txt = (
            "CLAUSULA 3 - HONORARIOS DE EXITO. Em caso de exito, fica ajustado o percentual de "
            f"{float(exito):g}% sobre o proveito economico obtido.\n\n"
            if exito is not None else
            "CLAUSULA 3 - HONORARIOS DE EXITO. Nao foram ajustados honorarios de exito "
            "entre as partes.\n\n"
        )
        despesas = proposta.get("despesas_criterio") or (
            "Custas, taxas e despesas processuais correm por conta do contratante."
        )
        clausulas_fixas = "".join(
            f"CLAUSULA {n} - {texto}\n\n"
            for n, texto in enumerate(_CLAUSULAS_FIXAS_CONTRATO, start=6)
        )
        clausulas = (
            f"CLAUSULA 2 - HONORARIOS. As partes ajustam honorarios no valor de {valor_txt}, "
            f"tendo como referencia a Tabela de Honorarios da OAB/MG{ref}{origem}, "
            f"pagos da seguinte forma: {forma}.\n\n"
            + exito_txt +
            "CLAUSULA 4 - HONORARIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
            "paragrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
            f"CLAUSULA 5 - DESPESAS. {despesas}\n\n"
            + clausulas_fixas +
            f"CLAUSULA {6 + len(_CLAUSULAS_FIXAS_CONTRATO)} - FORO. Fica eleito o foro da "
            f"Comarca de {_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, "
            "sede do escritorio contratado, para dirimir quaisquer controversias "
            "oriundas deste contrato.\n\n"
        )

    texto = _MARCA + (
        "CONTRATO DE PRESTACAO DE SERVICOS ADVOCATICIOS E HONORARIOS\n\n"
        f"CONTRATANTE: {_qualificacao(cli)}.\n\n"
        f"CONTRATADO: {_settings.ESCRITORIO_NOME}, por seu(sua) advogado(a) {adv} "
        f"(OAB/MG no {_settings.escritorio_oab()}).\n\n"
        f"CLAUSULA 1 - OBJETO. Prestacao de servicos advocaticios no caso {case.titulo} "
        f"(area: {area}){(', processo no ' + case.numero_processo) if case.numero_processo else ''}.\n\n"
        + clausulas +
        f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        f"____________________________   ____________________________\n"
        f"{cli.razao_social or cli.nome} (contratante)        {adv} (contratado)"
    )
    return padronizar_documento_juridico(texto)


def _relatorio_inicial(case: Case, cli: Client, area: str) -> str:
    proc = f"\nProcesso: {case.numero_processo}" if case.numero_processo else ""
    texto = (
        "RELATORIO JURIDICO INICIAL\n\n"
        f"Caso: {case.titulo}\nCliente: {cli.razao_social or cli.nome}\n"
        f"Area: {area}\nNo interno: {case.numero_interno or '-'}{proc}\n\n"
        "1. FATOS\n\n" + (case.descricao_fatos or "[a preencher]") + "\n\n"
        "2. TESE PRINCIPAL\n\n" + (case.tese_principal or "[analise pendente]") + "\n\n"
        "3. PONTOS FORTES\n\n" + (case.pontos_fortes or "-") + "\n\n"
        "4. PONTOS FRACOS E RISCOS\n\n" + (case.pontos_fracos or "-") + "\n\n"
        "5. PROXIMAS PROVIDENCIAS\n\n"
        "- Reunir documentos\n"
        "- Obter procuracao assinada\n"
        "- Formalizar contrato de honorarios\n"
        "- Definir estrategia processual ou extrajudicial\n\n"
        "Documento de trabalho. Sintese inicial sujeita a revisao juridica."
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
        adv = getattr(adv_user, "full_name", None) or "[advogado responsavel]"
        area = getattr(case.area, "value", None) or str(case.area or "")

        docs = [
            ("Procuracao - " + case.titulo, PecaTipo.procuracao, _procuracao(
                case, cli, adv,
                tipo_poderes=tipo_poderes,
                permite_substabelecimento=permite_substabelecimento,
                poderes_especiais=poderes_especiais,
            )),
            ("Contrato de Honorarios - " + case.titulo, PecaTipo.contrato, _contrato_honorarios(case, cli, adv, area)),
            ("Relatorio Juridico Inicial - " + case.titulo, PecaTipo.parecer, _relatorio_inicial(case, cli, area)),
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
