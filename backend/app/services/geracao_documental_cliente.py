"""Geração determinística de documentos de admissão vinculados ao cliente.

Contrato e procuração nascem como rascunho, sem LLM e sem aprovação automática.
A identidade do kit usa ``client_id`` + ``client_admission_kind``; título/nome do
cliente é apenas apresentação e nunca chave de domínio.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import role_str as _role_str
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.fee import Fee, FeePayment, FeeStatus, FeeTipo
from app.models.redesign import TabelaOABHonorario
from app.models.template import DocTemplate
from app.models.user import User
from app.services.document_format import padronizar_documento_juridico
from app.services.documental import (
    _CLAUSULAS_FIXAS_CONTRATO,
    _MARCA,
    _procuracao,
    _qualificacao,
)
from app.utils.format import formatar_brl

_settings = get_settings()
PODERES_VALIDOS = {"ad_judicia", "ad_judicia_et_extra", "especiais"}
_AREA_ALIASES = {"civil": ["civil", "civel"]}

ADMISSION_KIND_PROCURACAO = "procuracao_ad_judicia"
ADMISSION_KIND_CONTRATO = "contrato_honorarios"
ADMISSION_KINDS = (ADMISSION_KIND_PROCURACAO, ADMISSION_KIND_CONTRATO)

AVISO_RASCUNHO = (
    "Documentos gerados por template determinístico. Status: RASCUNHO — "
    "validação e revisão profissional são obrigatórias antes do uso."
)
AVISO_KIT_EXISTENTE = (
    "Rascunhos de admissão já existentes para este cliente foram reaproveitados. "
    "Para gerar nova versão, envie forcar_novo=true."
)
AVISO_SEM_AREA_OAB = (
    "Valor a definir: nenhum item vigente da Tabela OAB/MG foi localizado para "
    "a área informada. Consulte a fonte oficial antes da aprovação."
)

_CONTRATO_SYNC_ROLES = {"superadmin", "admin", "socio", "advogado"}
_FEE_CONTRATO_DESCRICAO = "Contrato de honorários — admissão"
_FEE_CONTRATO_MARCADOR = "[origem=contrato_admissao_cliente]"


def _titulos(nome_cliente: str) -> dict[str, str]:
    return {
        ADMISSION_KIND_PROCURACAO: padronizar_documento_juridico(
            f"Procuracao - {nome_cliente}"
        )[:200],
        ADMISSION_KIND_CONTRATO: padronizar_documento_juridico(
            f"Contrato de Honorarios - {nome_cliente}"
        )[:200],
    }


def _nome_advogado(cu: User) -> str:
    """Nome que assina o CONTRATO como contratado.

    Só um papel jurídico (advogado+) pode figurar como contratado — o cadastro
    de cliente também é feito por secretaria, e antes o nome de quem digitou ia
    para a linha de assinatura do contrato. Fora do papel jurídico, o documento
    sai com o placeholder, que o advogado preenche na revisão do rascunho.
    (A procuração não depende disto: o outorgado é fixo, o sócio-titular.)
    """
    from app.core.security import ROLE_LEVEL

    placeholder = "[advogado responsável]"
    if ROLE_LEVEL.get(_role_str(cu), 0) < ROLE_LEVEL["advogado"]:
        return placeholder
    return (getattr(cu, "full_name", None) or "").strip() or placeholder


def _doc_dict(doc: LegalDoc) -> dict:
    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "tipo": getattr(doc.tipo_peca, "value", str(doc.tipo_peca)),
        "status": getattr(doc.status, "value", str(doc.status)),
        "admission_kind": doc.client_admission_kind,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


async def listar_pecas_cliente(db: AsyncSession, cli: Client) -> list[dict]:
    """Lista documentos de admissão e os honorários estruturados do contrato."""
    docs = (
        await db.execute(
            select(LegalDoc)
            .where(
                LegalDoc.client_id == cli.id,
                LegalDoc.case_id.is_(None),
                LegalDoc.deleted_at.is_(None),
                LegalDoc.client_admission_kind.in_(ADMISSION_KINDS),
            )
            .order_by(LegalDoc.created_at.desc())
        )
    ).scalars().all()

    fee = (
        await db.execute(
            select(Fee)
            .where(
                Fee.client_id == cli.id,
                Fee.case_id.is_(None),
                Fee.deleted_at.is_(None),
                Fee.descricao == _FEE_CONTRATO_DESCRICAO,
                Fee.status != FeeStatus.cancelado,
            )
            .order_by(Fee.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    financeiro = None
    if fee is not None:
        forma = None
        prefixo = "Forma de pagamento: "
        for linha in (fee.observacoes or "").splitlines():
            if linha.startswith(prefixo):
                forma = linha[len(prefixo):].rstrip(".").strip() or None
                break
        financeiro = {
            "fee_id": fee.id,
            "valor_contratual": float(fee.valor) if fee.valor is not None else None,
            "percentual_exito": (
                float(fee.percentual_exito)
                if fee.percentual_exito is not None
                else None
            ),
            "forma_pagamento": forma,
            "status": getattr(fee.status, "value", str(fee.status)),
        }

    saida = []
    for doc in docs:
        item = _doc_dict(doc)
        if doc.client_admission_kind == ADMISSION_KIND_CONTRATO:
            item["financeiro"] = financeiro
        saida.append(item)
    return saida


def _aliases_area(area: str) -> list[str]:
    chave = (area or "").strip().lower()
    return _AREA_ALIASES.get(chave, [chave]) if chave else []


async def _itens_oab_vigentes(
    db: AsyncSession, area: str, hoje: date, limite: int = 5
) -> list[TabelaOABHonorario]:
    aliases = _aliases_area(area)
    if not aliases:
        return []
    q = (
        select(TabelaOABHonorario)
        .where(
            TabelaOABHonorario.ativo.is_(True),
            or_(
                *[
                    TabelaOABHonorario.area_juridica.ilike(f"%{alias}%")
                    for alias in aliases
                ]
            ),
            or_(
                TabelaOABHonorario.vigencia_fim.is_(None),
                TabelaOABHonorario.vigencia_fim >= hoje,
            ),
            or_(
                TabelaOABHonorario.vigencia_inicio.is_(None),
                TabelaOABHonorario.vigencia_inicio <= hoje,
            ),
        )
        .order_by(
            TabelaOABHonorario.vigencia_inicio.desc().nullslast(),
            TabelaOABHonorario.item_codigo,
        )
        .limit(limite)
    )
    return list((await db.execute(q)).scalars().all())


def _item_dict(item: TabelaOABHonorario) -> dict:
    return {
        "item_codigo": item.item_codigo,
        "descricao": item.descricao,
        "valor_minimo": (
            float(item.valor_minimo) if item.valor_minimo is not None else None
        ),
        "percentual": float(item.percentual) if item.percentual is not None else None,
        "unidade": item.unidade,
        "vigencia_inicio": (
            item.vigencia_inicio.isoformat() if item.vigencia_inicio else None
        ),
        "vigencia_fim": item.vigencia_fim.isoformat() if item.vigencia_fim else None,
        "fonte": item.fonte,
    }


def _referencia_oab(item: TabelaOABHonorario) -> str:
    valores: list[str] = []
    if item.valor_minimo is not None:
        valores.append(f"mínimo {formatar_brl(item.valor_minimo)}")
    if item.percentual is not None:
        valores.append(f"{float(item.percentual):g}%")
    detalhe = " + ".join(valores) if valores else "consultar tabela"
    return (
        f"referência não vinculante — item {item.item_codigo} "
        f"({item.descricao}): {detalhe}; fonte: {item.fonte}"
    )


async def _modelo_por_area(
    db: AsyncSession, tipo_peca: str, area: str
) -> DocTemplate | None:
    """Modelo cadastrado em Templates de Peças para (tipo_peca, área).

    Preferência: modelo da área do cliente; senão, modelo genérico (área
    vazia). Nenhum modelo cadastrado → texto determinístico do escritório.
    """
    q = (
        select(DocTemplate)
        .where(
            DocTemplate.deleted_at.is_(None),
            DocTemplate.ativo.is_(True),
            DocTemplate.tipo_peca == tipo_peca,
        )
        .order_by(DocTemplate.updated_at.desc().nullslast())
    )
    modelos = list((await db.execute(q)).scalars().all())
    aliases = set(_aliases_area(area))
    for m in modelos:
        if (m.area or "").strip().lower() in aliases:
            return m
    for m in modelos:
        if not (m.area or "").strip():
            return m
    return None


def _render_modelo(modelo: DocTemplate, ctx: dict) -> str:
    """Renderiza {{variaveis}} com o MESMO substituidor literal do módulo de
    Templates (sem Jinja, sem código) e mantém a marca de minuta/rascunho."""
    from app.routers.templates import _render

    return padronizar_documento_juridico(_MARCA + _render(modelo.conteudo, ctx))


def _modelo_dict(modelo: DocTemplate | None) -> dict | None:
    if modelo is None:
        return None
    return {"id": modelo.id, "titulo": modelo.titulo, "area": modelo.area}


def _contrato_cliente(
    cli: Client,
    advogado: str,
    area: str,
    referencia_oab: str | None,
    *,
    valor_contratual: float | Decimal | None = None,
    percentual_exito: float | Decimal | None = None,
    forma_pagamento: str | None = None,
) -> str:
    ref = f" ({referencia_oab})" if referencia_oab else ""
    objeto = f" na área de {area}" if area else " em área a definir pelas partes"
    valor_txt = (
        formatar_brl(Decimal(str(valor_contratual)))
        if valor_contratual is not None
        else "R$ [____]"
    )
    forma_txt = (forma_pagamento or "").strip() or "[____]"
    exito_txt = (
        f"{Decimal(str(percentual_exito)):g}%"
        if percentual_exito is not None
        else "[__]%"
    )
    clausulas = (
        "CLÁUSULA 1 - OBJETO. Prestação de serviços advocatícios ao CONTRATANTE"
        f"{objeto}, abrangendo consultoria e as medidas judiciais ou extrajudiciais "
        "que forem expressamente definidas e aprovadas.\n\n"
        f"CLÁUSULA 2 - HONORÁRIOS. As partes ajustam honorários no valor de {valor_txt}, "
        f"tendo como referência a Tabela de Honorários da OAB/MG{ref}, "
        f"com forma de pagamento {forma_txt}.\n\n"
        "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Se aplicável e expressamente pactuado, "
        f"o percentual será de {exito_txt} sobre o proveito econômico obtido.\n\n"
        "CLÁUSULA 4 - HONORÁRIOS SUCUMBENCIAIS. Pertencem ao advogado, nos termos "
        "da legislação aplicável.\n\n"
        "CLÁUSULA 5 - DESPESAS. Custas, taxas e despesas processuais correm por "
        "conta do contratante, salvo ajuste escrito diverso.\n\n"
        + "".join(
            f"CLÁUSULA {numero} - {texto}\n\n"
            for numero, texto in enumerate(_CLAUSULAS_FIXAS_CONTRATO, start=6)
        )
        + f"CLÁUSULA {6 + len(_CLAUSULAS_FIXAS_CONTRATO)} - FORO. Fica eleito o "
        f"foro da Comarca de {_settings.ESCRITORIO_CIDADE}/"
        f"{_settings.ESCRITORIO_ESTADO}, observadas as regras legais de competência.\n\n"
    )
    oab = _settings.escritorio_oab()
    texto = _MARCA + (
        "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS E HONORÁRIOS\n\n"
        f"CONTRATANTE: {_qualificacao(cli)}.\n\n"
        f"CONTRATADO: {_settings.ESCRITORIO_NOME}, por seu(sua) advogado(a) "
        f"{advogado}{(' (OAB/MG nº ' + oab + ')') if oab else ''}.\n\n"
        + clausulas
        + f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        "____________________________   ____________________________\n"
        f"{cli.razao_social or cli.nome} (contratante)        {advogado} (contratado)"
    )
    return padronizar_documento_juridico(texto)


async def _sincronizar_financeiro_contrato(
    db: AsyncSession,
    cli: Client,
    cu: User,
    *,
    valor_contratual: float | Decimal | None,
    percentual_exito: float | Decimal | None,
    forma_pagamento: str | None,
    contrato_doc_id: str,
) -> dict:
    """Sincroniza os honorários estruturados do contrato com o financeiro.

    Perfis não fiduciários podem preencher a minuta, mas não mutam o ledger.
    Honorários que já tenham recebimentos nunca são alterados silenciosamente.
    """
    if valor_contratual is None and percentual_exito is None:
        return {"status": "sem_valores", "fee_id": None}

    role = _role_str(cu)
    if role not in _CONTRATO_SYNC_ROLES:
        return {
            "status": "pendente_permissao",
            "fee_id": None,
            "aviso": "Contrato preenchido; sincronização financeira requer advogado ou gestão autorizada.",
        }

    valor = (
        Decimal(str(valor_contratual)).quantize(Decimal("0.01"))
        if valor_contratual is not None
        else None
    )
    percentual = (
        Decimal(str(percentual_exito)).quantize(Decimal("0.01"))
        if percentual_exito is not None
        else None
    )
    if valor is not None and valor < 0:
        raise HTTPException(status_code=422, detail="valor_contratual não pode ser negativo")
    if percentual is not None and not (Decimal("0") <= percentual <= Decimal("100")):
        raise HTTPException(status_code=422, detail="percentual_exito deve estar entre 0 e 100")

    tipo = (
        FeeTipo.misto
        if valor is not None and percentual is not None
        else FeeTipo.fixo
        if valor is not None
        else FeeTipo.exito
    )
    forma = (forma_pagamento or "").strip() or None
    obs = (
        f"{_FEE_CONTRATO_MARCADOR}\n"
        f"Documento origem: {contrato_doc_id}.\n"
        f"Forma de pagamento: {forma or 'a definir'}."
    )

    existente = (
        await db.execute(
            select(Fee)
            .where(
                Fee.client_id == cli.id,
                Fee.case_id.is_(None),
                Fee.deleted_at.is_(None),
                Fee.descricao == _FEE_CONTRATO_DESCRICAO,
                Fee.status != FeeStatus.cancelado,
            )
            .order_by(Fee.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existente is not None:
        tem_pagamento = (
            await db.execute(
                select(FeePayment.id).where(FeePayment.fee_id == existente.id).limit(1)
            )
        ).scalar_one_or_none() is not None
        forma_anterior = "Forma de pagamento: " + (forma or "a definir") + "."
        mudou = (
            existente.tipo != tipo
            or existente.valor != valor
            or existente.percentual_exito != percentual
            or forma_anterior not in (existente.observacoes or "")
        )
        if tem_pagamento and mudou:
            raise HTTPException(
                status_code=409,
                detail=(
                    "O honorário deste contrato já possui recebimentos no financeiro. "
                    "Ajuste ou estorne pelo módulo Financeiro antes de emitir contrato "
                    "com valores diferentes."
                ),
            )
        if not tem_pagamento:
            existente.tipo = tipo
            existente.valor = valor
            existente.percentual_exito = percentual
            existente.observacoes = obs
            await criar_audit_log(
                db, cu.id, role, "SYNC_CONTRATO_FINANCEIRO", "fees", existente.id,
                detalhes=(
                    "Honorário atualizado a partir do contrato de admissão; "
                    f"legal_doc_id={contrato_doc_id}."
                ),
            )
        return {
            "status": "sincronizado",
            "fee_id": existente.id,
            "atualizado": not tem_pagamento,
        }

    fee = Fee(
        id=str(uuid4()),
        tipo=tipo,
        status=FeeStatus.pendente,
        descricao=_FEE_CONTRATO_DESCRICAO,
        valor=valor,
        percentual_exito=percentual,
        client_id=cli.id,
        case_id=None,
        observacoes=obs,
    )
    db.add(fee)
    await criar_audit_log(
        db, cu.id, role, "SYNC_CONTRATO_FINANCEIRO", "fees", fee.id,
        detalhes=(
            "Honorário criado a partir do contrato de admissão; "
            f"legal_doc_id={contrato_doc_id}."
        ),
    )
    return {"status": "sincronizado", "fee_id": fee.id, "atualizado": False}


async def gerar_documentos_cliente(
    db: AsyncSession,
    cli: Client,
    cu: User,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
    forcar_novo: bool = False,
    valor_contratual: float | Decimal | None = None,
    percentual_exito: float | Decimal | None = None,
    forma_pagamento: str | None = None,
    sincronizar_financeiro: bool = True,
) -> dict:
    """Gera procuração + contrato vinculados inequivocamente ao cliente."""
    if valor_contratual is not None and Decimal(str(valor_contratual)) < 0:
        raise HTTPException(status_code=422, detail="valor_contratual não pode ser negativo")
    if percentual_exito is not None:
        percentual_validado = Decimal(str(percentual_exito))
        if not (Decimal("0") <= percentual_validado <= Decimal("100")):
            raise HTTPException(
                status_code=422,
                detail="percentual_exito deve estar entre 0 e 100",
            )

    tipo = (tipo_poderes or "ad_judicia").strip().lower()
    if tipo not in PODERES_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"tipo_poderes deve ser um de {sorted(PODERES_VALIDOS)}",
        )

    # Serializa a idempotência por cliente na mesma transação.
    await db.execute(select(Client.id).where(Client.id == cli.id).with_for_update())

    if not forcar_novo:
        existentes = (
            await db.execute(
                select(LegalDoc)
                .where(
                    LegalDoc.client_id == cli.id,
                    LegalDoc.case_id.is_(None),
                    LegalDoc.deleted_at.is_(None),
                    LegalDoc.status == PecaStatus.rascunho,
                    LegalDoc.client_admission_kind.in_(ADMISSION_KINDS),
                )
                .order_by(LegalDoc.created_at.desc())
            )
        ).scalars().all()
        por_kind: dict[str, LegalDoc] = {}
        for doc in existentes:
            kind = (doc.client_admission_kind or "").strip()
            if kind:
                por_kind.setdefault(kind, doc)
        if all(kind in por_kind for kind in ADMISSION_KINDS):
            proc = por_kind[ADMISSION_KIND_PROCURACAO]
            contrato = por_kind[ADMISSION_KIND_CONTRATO]
            return {
                "client_id": cli.id,
                "status": PecaStatus.rascunho.value,
                "ja_existia": True,
                "aviso": AVISO_KIT_EXISTENTE,
                "procuracao": {
                    "legal_doc_id": proc.id,
                    "titulo": proc.titulo,
                    "conteudo": proc.conteudo,
                },
                "contrato": {
                    "legal_doc_id": contrato.id,
                    "titulo": contrato.titulo,
                    "conteudo": contrato.conteudo,
                },
            }

    advogado = _nome_advogado(cu)
    area = (getattr(cli, "area_interesse", None) or "").strip()
    itens = await _itens_oab_vigentes(db, area, date.today()) if area else []
    referencia: str | None
    if itens:
        referencia = _referencia_oab(itens[0])
        valor_sugerido = {
            "origem": "tabela_oab_estruturada",
            "sugerido": _item_dict(itens[0]),
            "itens_referencia": [_item_dict(item) for item in itens],
            "aviso": "Referência não vinculante; o advogado define o valor final.",
        }
    else:
        referencia = None
        valor_sugerido = {
            "origem": None,
            "sugerido": None,
            "itens_referencia": [],
            "aviso": AVISO_SEM_AREA_OAB,
        }

    nome_cliente = cli.razao_social or cli.nome or "Cliente"
    titulos = _titulos(nome_cliente)

    # Modelos por área jurídica (módulo Templates de Peças): quando o
    # escritório cadastrou um modelo ativo de contrato/procuração para a área
    # do cliente (ou genérico), ele prevalece sobre o texto determinístico.
    modelo_proc = await _modelo_por_area(db, PecaTipo.procuracao.value, area)
    modelo_contr = await _modelo_por_area(db, PecaTipo.contrato.value, area)
    ctx: dict = {}
    if modelo_proc or modelo_contr:
        from app.routers.templates import contexto_cliente

        ctx = {
            **contexto_cliente(cli),
            "area": area or "—",
            "advogado_nome": advogado,
            "advogado_oab": getattr(cu, "oab_number", None) or "—",
            "tipo_poderes": tipo,
            "poderes_especiais": (poderes_especiais or "").strip() or "—",
            "referencia_oab": referencia or "—",
            "valor_honorarios": (
                formatar_brl(Decimal(str(valor_contratual)))
                if valor_contratual is not None else "—"
            ),
            "percentual_exito": (
                f"{Decimal(str(percentual_exito)):g}%"
                if percentual_exito is not None else "—"
            ),
            "forma_pagamento": (forma_pagamento or "").strip() or "—",
            "numero_processo": "—", "parte_contraria": "—",
            "comarca": _settings.ESCRITORIO_CIDADE, "vara": "—", "valor_causa": "—",
        }

    texto_proc = (
        _render_modelo(modelo_proc, ctx) if modelo_proc else
        _procuracao(
            None,
            cli,
            advogado,
            tipo_poderes=tipo,
            permite_substabelecimento=permite_substabelecimento,
            poderes_especiais=poderes_especiais,
        )
    )
    texto_contr = (
        _render_modelo(modelo_contr, ctx) if modelo_contr else
        _contrato_cliente(
            cli,
            advogado,
            area,
            referencia,
            valor_contratual=valor_contratual,
            percentual_exito=percentual_exito,
            forma_pagamento=forma_pagamento,
        )
    )
    conteudos = [
        (titulos[ADMISSION_KIND_PROCURACAO], PecaTipo.procuracao,
         ADMISSION_KIND_PROCURACAO, texto_proc),
        (titulos[ADMISSION_KIND_CONTRATO], PecaTipo.contrato,
         ADMISSION_KIND_CONTRATO, texto_contr),
    ]

    criados: list[LegalDoc] = []
    for titulo, tipo_peca, admission_kind, conteudo in conteudos:
        doc = LegalDoc(
            id=str(uuid4()),
            titulo=titulo,
            tipo_peca=tipo_peca,
            conteudo=conteudo,
            status=PecaStatus.rascunho,
            area=area or None,
            # Template determinístico, sem LLM. Continua rascunho e passa pelos
            # gates canônicos de validação/revisão antes de aprovação.
            ai_generated=False,
            human_reviewed=False,
            case_id=None,
            client_id=cli.id,
            client_admission_kind=admission_kind,
            created_by=cu.id,
        )
        db.add(doc)
        criados.append(doc)

    proc, contrato = criados
    financeiro = (
        await _sincronizar_financeiro_contrato(
            db,
            cli,
            cu,
            valor_contratual=valor_contratual,
            percentual_exito=percentual_exito,
            forma_pagamento=forma_pagamento,
            contrato_doc_id=contrato.id,
        )
        if sincronizar_financeiro
        else {"status": "nao_solicitado", "fee_id": None}
    )

    await criar_audit_log(
        db,
        cu.id,
        _role_str(cu),
        "GERAR_DOCS_CLIENTE",
        "clients",
        cli.id,
        detalhes=(
            "Procuração e contrato gerados como rascunhos de admissão "
            f"(tipo_poderes={tipo}); ids=" + ",".join(doc.id for doc in criados)
        ),
        dados_depois={
            "legal_doc_ids": [doc.id for doc in criados],
            "oab_item_aplicado": valor_sugerido["sugerido"] is not None,
            "modelo_procuracao": _modelo_dict(modelo_proc),
            "modelo_contrato": _modelo_dict(modelo_contr),
            "financeiro": financeiro,
        },
    )
    await db.commit()

    return {
        "client_id": cli.id,
        "status": PecaStatus.rascunho.value,
        "ja_existia": False,
        "aviso": AVISO_RASCUNHO,
        "financeiro": financeiro,
        "procuracao": {
            "legal_doc_id": proc.id,
            "titulo": proc.titulo,
            "tipo_poderes": tipo,
            "permite_substabelecimento": permite_substabelecimento,
            "modelo": _modelo_dict(modelo_proc),
            "conteudo": proc.conteudo,
        },
        "contrato": {
            "legal_doc_id": contrato.id,
            "titulo": contrato.titulo,
            "valor_sugerido": valor_sugerido,
            "modelo": _modelo_dict(modelo_contr),
            "conteudo": contrato.conteudo,
        },
    }
