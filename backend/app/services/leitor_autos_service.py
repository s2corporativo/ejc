"""Agregador determinístico de múltiplos documentos dos autos.

Reutiliza ``DocumentoIntakeResult`` e preserva a referência documental de cada
informação consolidada. Não chama IA, não abre banco e não materializa prazos.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas.document_intake import CampoExtraido, DocumentoIntakeResult
from app.schemas.leitor_autos import (
    DocumentoAutosEntrada,
    DocumentoIndiceAutos,
    EstatisticasAutos,
    EventoAutos,
    ItemTextoAutos,
    LacunaAutos,
    LeitorAutosResultado,
    ParteAutos,
    PrazoAutos,
    ReferenciaAutos,
)
from app.services.extracao_estruturada import parse_data_br


def _texto(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _chave(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _referencia(
    doc: DocumentoAutosEntrada,
    campo: CampoExtraido | None = None,
) -> ReferenciaAutos:
    return ReferenciaAutos(
        documento_id=doc.fonte.documento_id,
        nome_arquivo=doc.fonte.nome_arquivo,
        pagina=doc.fonte.pagina,
        trecho_origem=(campo.trecho_origem if campo else None),
        confianca=(campo.confianca if campo else None),
        status_fonte=doc.fonte.status_fonte,
    )


def _ref_key(ref: ReferenciaAutos) -> tuple:
    return (
        ref.documento_id,
        ref.pagina,
        ref.trecho_origem,
        ref.confianca,
        ref.status_fonte,
    )


def _mesclar_referencia(
    referencias: list[ReferenciaAutos],
    referencia: ReferenciaAutos,
) -> None:
    existentes = {_ref_key(item) for item in referencias}
    if _ref_key(referencia) not in existentes:
        referencias.append(referencia)


def _adicionar_texto(
    mapa: dict[str, ItemTextoAutos],
    texto: str | None,
    referencia: ReferenciaAutos,
) -> None:
    valor = _texto(texto)
    if not valor:
        return
    key = _chave(valor)
    if key not in mapa:
        mapa[key] = ItemTextoAutos(texto=valor, fontes=[referencia])
    else:
        _mesclar_referencia(mapa[key].fontes, referencia)


def _texto_prova(prova) -> str | None:
    partes = []
    titulo = _texto(getattr(prova, "titulo", None))
    tipo = _texto(getattr(prova, "tipo", None))
    finalidade = _texto(getattr(prova, "finalidade", None))
    if titulo:
        partes.append(titulo)
    if tipo:
        partes.append(f"tipo: {tipo}")
    if finalidade:
        partes.append(f"finalidade: {finalidade}")
    return " — ".join(partes) if partes else None


def _texto_risco(risco) -> str | None:
    descricao = _texto(getattr(risco, "descricao", None))
    if not descricao:
        return None
    complementos = []
    prob = _texto(getattr(risco, "probabilidade", None))
    impacto = _texto(getattr(risco, "impacto", None))
    if prob:
        complementos.append(f"probabilidade: {prob}")
    if impacto:
        complementos.append(f"impacto: {impacto}")
    return descricao + (f" ({'; '.join(complementos)})" if complementos else "")


def _texto_tese(tese) -> str | None:
    titulo = _texto(getattr(tese, "titulo", None))
    fundamento = _texto(getattr(tese, "fundamento", None))
    if titulo and fundamento:
        return f"{titulo} — {fundamento}"
    return titulo or fundamento


def _resumo(intake: DocumentoIntakeResult) -> str | None:
    return _texto(intake.resumo_fatos) or _texto(
        intake.caso.resumo_fatos if intake.caso else None
    )


def _ordenar_eventos(eventos: list[EventoAutos]) -> list[EventoAutos]:
    def _sort_key(evento: EventoAutos):
        parsed = parse_data_br(evento.data)
        return (parsed is None, parsed.isoformat() if parsed else evento.data)

    return sorted(eventos, key=_sort_key)


def agregar_autos(documentos: Iterable[DocumentoAutosEntrada]) -> LeitorAutosResultado:
    """Consolida documentos mantendo lacunas e revisão humana obrigatória."""

    docs = sorted(list(documentos), key=lambda item: item.ordem)
    indice: list[DocumentoIndiceAutos] = []
    partes_map: dict[str, ParteAutos] = {}
    fatos_map: dict[str, ItemTextoAutos] = {}
    pedidos_map: dict[str, ItemTextoAutos] = {}
    provas_map: dict[str, ItemTextoAutos] = {}
    riscos_map: dict[str, ItemTextoAutos] = {}
    teses_map: dict[str, ItemTextoAutos] = {}
    prazos_map: dict[tuple, PrazoAutos] = {}
    cronologia: list[EventoAutos] = []
    lacunas: list[LacunaAutos] = []
    avisos: list[str] = []

    if not docs:
        avisos.append("Nenhum documento foi fornecido ao leitor de autos.")

    for doc in docs:
        intake = doc.intake
        ref = _referencia(doc)
        resumo = _resumo(intake)
        indice.append(
            DocumentoIndiceAutos(
                ordem=doc.ordem,
                documento_id=doc.fonte.documento_id,
                nome_arquivo=doc.fonte.nome_arquivo,
                tipo_documento=intake.tipo_documento,
                resumo=resumo,
                data_documento=doc.fonte.data_documento,
                processo_origem=doc.fonte.processo_origem,
                status_fonte=doc.fonte.status_fonte,
                parcial=doc.parcial,
                necessita_revisao_humana=intake.necessita_revisao_humana,
            )
        )

        status = (doc.fonte.status_fonte or "").strip().lower()
        if status != "confirmada":
            nome = doc.fonte.nome_arquivo or doc.fonte.documento_id
            avisos.append(
                f"{nome}: fonte ainda não confirmada ({status or 'sem status'})."
            )
        if doc.parcial:
            nome = doc.fonte.nome_arquivo or doc.fonte.documento_id
            avisos.append(f"{nome}: análise documental parcial.")

        _adicionar_texto(fatos_map, resumo, ref)

        for parte in intake.partes:
            nome = _texto(parte.nome)
            if not nome:
                continue
            key = _chave(nome)
            if key not in partes_map:
                partes_map[key] = ParteAutos(nome=nome)
            papel = _texto(parte.papel)
            if papel and papel not in partes_map[key].papeis:
                partes_map[key].papeis.append(papel)
            _mesclar_referencia(partes_map[key].fontes, ref)

        if intake.cliente and _texto(intake.cliente.nome):
            nome = _texto(intake.cliente.nome)
            assert nome is not None
            key = _chave(nome)
            if key not in partes_map:
                partes_map[key] = ParteAutos(nome=nome)
            if "provavel_cliente" not in partes_map[key].papeis:
                partes_map[key].papeis.append("provavel_cliente")
            _mesclar_referencia(partes_map[key].fontes, ref)

        for pedido in intake.pedidos:
            _adicionar_texto(pedidos_map, pedido.descricao, ref)
        for prova in intake.provas:
            _adicionar_texto(provas_map, _texto_prova(prova), ref)
        for risco in intake.riscos:
            _adicionar_texto(riscos_map, _texto_risco(risco), ref)
        for tese in intake.teses:
            _adicionar_texto(teses_map, _texto_tese(tese), ref)

        for prazo in intake.prazos:
            termo = _texto(prazo.termo_final)
            if not termo:
                continue
            key = (
                _chave(_texto(prazo.tipo) or ""),
                termo,
                _chave(_texto(prazo.base_legal) or ""),
            )
            if key not in prazos_map:
                prazos_map[key] = PrazoAutos(
                    tipo=_texto(prazo.tipo),
                    data_base=_texto(prazo.data_base),
                    termo_final=termo,
                    fatal=bool(prazo.fatal),
                    base_legal=_texto(prazo.base_legal),
                    fontes=[ref],
                )
            else:
                _mesclar_referencia(prazos_map[key].fontes, ref)

            if parse_data_br(termo):
                cronologia.append(
                    EventoAutos(
                        data=termo,
                        tipo="prazo_explicito",
                        descricao=_texto(prazo.tipo) or "Prazo identificado",
                        documento_id=doc.fonte.documento_id,
                        nome_arquivo=doc.fonte.nome_arquivo,
                        pagina=doc.fonte.pagina,
                        status_fonte=doc.fonte.status_fonte,
                    )
                )

        data_doc = _texto(doc.fonte.data_documento)
        if data_doc and parse_data_br(data_doc):
            cronologia.append(
                EventoAutos(
                    data=data_doc,
                    tipo="documento",
                    descricao=intake.tipo_documento or "Documento dos autos",
                    documento_id=doc.fonte.documento_id,
                    nome_arquivo=doc.fonte.nome_arquivo,
                    pagina=doc.fonte.pagina,
                    status_fonte=doc.fonte.status_fonte,
                )
            )

        for pendencia in intake.pendencias:
            descricao = _texto(pendencia.descricao)
            if descricao:
                lacunas.append(
                    LacunaAutos(
                        descricao=descricao,
                        campo_alvo=_texto(pendencia.campo_alvo),
                        severidade=_texto(pendencia.severidade),
                        documento_id=doc.fonte.documento_id,
                        nome_arquivo=doc.fonte.nome_arquivo,
                    )
                )

        if not intake.tipo_documento:
            lacunas.append(
                LacunaAutos(
                    descricao="Tipo do documento não confirmado.",
                    campo_alvo="tipo_documento",
                    severidade="media",
                    documento_id=doc.fonte.documento_id,
                    nome_arquivo=doc.fonte.nome_arquivo,
                )
            )
        if not resumo:
            lacunas.append(
                LacunaAutos(
                    descricao="Fatos principais não foram extraídos do documento.",
                    campo_alvo="resumo_fatos",
                    severidade="media",
                    documento_id=doc.fonte.documento_id,
                    nome_arquivo=doc.fonte.nome_arquivo,
                )
            )
        if doc.parcial:
            lacunas.append(
                LacunaAutos(
                    descricao="A interpretação por IA ficou indisponível; revisar o OCR e completar manualmente.",
                    campo_alvo="analise_documental",
                    severidade="alta",
                    documento_id=doc.fonte.documento_id,
                    nome_arquivo=doc.fonte.nome_arquivo,
                )
            )

    partes = list(partes_map.values())
    pedidos = list(pedidos_map.values())
    provas = list(provas_map.values())
    prazos = list(prazos_map.values())
    riscos = list(riscos_map.values())
    teses = list(teses_map.values())
    fatos = list(fatos_map.values())

    estatisticas = EstatisticasAutos(
        documentos=len(indice),
        partes=len(partes),
        pedidos=len(pedidos),
        provas=len(provas),
        prazos_explicitos=len(prazos),
        riscos=len(riscos),
        teses=len(teses),
        lacunas=len(lacunas),
    )
    return LeitorAutosResultado(
        indice=indice,
        partes=partes,
        fatos=fatos,
        pedidos=pedidos,
        provas=provas,
        prazos=prazos,
        cronologia=_ordenar_eventos(cronologia),
        riscos=riscos,
        teses=teses,
        lacunas=lacunas,
        avisos=list(dict.fromkeys(avisos)),
        necessita_revisao_humana=True,
        estatisticas=estatisticas,
    )
