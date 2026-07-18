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


def _procuracao(case: Case, cli: Client, adv: str) -> str:
    # Dados FIXOS do escritório vêm das settings (fonte única). Quando ainda não
    # preenchidos no .env, os helpers devolvem placeholder EXPLÍCITO e visível.
    # A CIDADE de assinatura é a sede do escritório; a DATA depende do caso e
    # permanece como placeholder de revisão.
    texto = _MARCA + (
        "PROCURACAO AD JUDICIA ET EXTRA\n\n"
        f"OUTORGANTE: {_qualificacao(cli)}.\n\n"
        f"OUTORGADO(A): {adv}, advogado(a) inscrito(a) na OAB/MG sob o no {_settings.escritorio_oab()}, "
        f"integrante de {_settings.ESCRITORIO_NOME}, com escritorio em {_settings.escritorio_endereco()}.\n\n"
        "PODERES: Pelo presente instrumento, o(a) outorgante nomeia e constitui seu(sua) "
        "bastante procurador(a) o(a) advogado(a) acima, a quem confere os poderes da clausula "
        "ad judicia et extra, para o foro em geral, em qualquer Juizo, Instancia ou Tribunal, "
        "podendo propor as acoes competentes e defender o(a) outorgante nas contrarias, bem como "
        "os poderes especiais para receber citacao, confessar, reconhecer a procedencia do pedido, "
        "transigir, desistir, renunciar ao direito sobre que se funda a acao, receber e dar quitacao, "
        "firmar compromisso e substabelecer, com ou sem reserva de poderes, "
        f"especialmente para atuar no caso {case.titulo}"
        f"{(' (processo no ' + case.numero_processo + ')') if case.numero_processo else ''}.\n\n"
        f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        "______________________________________\n"
        f"{cli.razao_social or cli.nome}"
    )
    return padronizar_documento_juridico(texto)


def _contrato_honorarios(case: Case, cli: Client, adv: str, area: str) -> str:
    # OAB e cidade de assinatura são dados FIXOS do escritório (settings). Valor
    # dos honorários, percentual de êxito, forma de pagamento, comarca do foro e
    # data dependem do CASO/CLIENTE e continuam como placeholder de revisão.
    texto = _MARCA + (
        "CONTRATO DE PRESTACAO DE SERVICOS ADVOCATICIOS E HONORARIOS\n\n"
        f"CONTRATANTE: {_qualificacao(cli)}.\n\n"
        f"CONTRATADO: {_settings.ESCRITORIO_NOME}, por seu(sua) advogado(a) {adv} "
        f"(OAB/MG no {_settings.escritorio_oab()}).\n\n"
        f"CLAUSULA 1 - OBJETO. Prestacao de servicos advocaticios no caso {case.titulo} "
        f"(area: {area}){(', processo no ' + case.numero_processo) if case.numero_processo else ''}.\n\n"
        "CLAUSULA 2 - HONORARIOS. As partes ajustam honorarios no valor de R$ [____], "
        "tendo como referencia a Tabela de Honorarios da OAB/MG, pagos da seguinte forma: [____].\n\n"
        "CLAUSULA 3 - HONORARIOS DE EXITO. Em caso de exito, fica ajustado o percentual de "
        "[__]% sobre o proveito economico obtido.\n\n"
        "CLAUSULA 4 - HONORARIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
        "paragrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
        "CLAUSULA 5 - DESPESAS. Custas, taxas e despesas processuais correm por conta do contratante.\n\n"
        "CLAUSULA 6 - FORO. Comarca de [____]/MG.\n\n"
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


async def gerar_documentos_iniciais(case_id: str, user_id: str) -> list[dict]:
    """Gera minutas iniciais do caso. Retorna lista de {id, titulo, tipo}."""
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
            ("Procuracao - " + case.titulo, PecaTipo.procuracao, _procuracao(case, cli, adv)),
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
