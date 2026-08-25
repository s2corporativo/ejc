"""Geração determinística de documentos de admissão vinculados ao cliente.

Contrato e procuração nascem como rascunho, sem LLM e sem aprovação automática.
A identidade do kit usa ``client_id`` + ``client_admission_kind``; título/nome do
cliente é apenas apresentação e nunca chave de domínio.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import role_str as _role_str
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.redesign import TabelaOABHonorario
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


def _titulos(nome_cliente: str) -> dict[str, str]:
    return {
        ADMISSION_KIND_PROCURACAO: padronizar_documento_juridico(
            f"Procuracao - {nome_cliente}"
        )[:200],
        ADMISSION_KIND_CONTRATO: padronizar_documento_juridico(
            f"Contrato de Honorarios - {nome_cliente}"
        )[:200],
    }


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
    """Lista somente documentos de admissão vinculados ao ``cli.id``."""
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
    return [_doc_dict(doc) for doc in docs]


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


def _contrato_cliente(
    cli: Client, advogado: str, area: str, referencia_oab: str | None
) -> str:
    ref = f" ({referencia_oab})" if referencia_oab else ""
    objeto = f" na área de {area}" if area else " em área a definir pelas partes"
    clausulas = (
        "CLÁUSULA 1 - OBJETO. Prestação de serviços advocatícios ao CONTRATANTE"
        f"{objeto}, abrangendo consultoria e as medidas judiciais ou extrajudiciais "
        "que forem expressamente definidas e aprovadas.\n\n"
        "CLÁUSULA 2 - HONORÁRIOS. As partes ajustarão o valor final em R$ [____], "
        f"tendo como referência a Tabela de Honorários da OAB/MG{ref}, "
        "com forma de pagamento [____].\n\n"
        "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Se aplicável e expressamente pactuado, "
        "o percentual será de [__]% sobre o proveito econômico obtido.\n\n"
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


async def gerar_documentos_cliente(
    db: AsyncSession,
    cli: Client,
    cu: User,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
    forcar_novo: bool = False,
) -> dict:
    """Gera procuração + contrato vinculados inequivocamente ao cliente."""
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

    advogado = getattr(cu, "full_name", None) or "[advogado responsável]"
    area = (getattr(cli, "area_interesse", None) or "").strip()
    itens = await _itens_oab_vigentes(db, area, date.today()) if area else []
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
    conteudos = [
        (
            titulos[ADMISSION_KIND_PROCURACAO],
            PecaTipo.procuracao,
            ADMISSION_KIND_PROCURACAO,
            _procuracao(
                None,
                cli,
                advogado,
                tipo_poderes=tipo,
                permite_substabelecimento=permite_substabelecimento,
                poderes_especiais=poderes_especiais,
            ),
        ),
        (
            titulos[ADMISSION_KIND_CONTRATO],
            PecaTipo.contrato,
            ADMISSION_KIND_CONTRATO,
            _contrato_cliente(cli, advogado, area, referencia),
        ),
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
        },
    )
    await db.commit()

    proc, contrato = criados
    return {
        "client_id": cli.id,
        "status": PecaStatus.rascunho.value,
        "ja_existia": False,
        "aviso": AVISO_RASCUNHO,
        "procuracao": {
            "legal_doc_id": proc.id,
            "titulo": proc.titulo,
            "tipo_poderes": tipo,
            "permite_substabelecimento": permite_substabelecimento,
            "conteudo": proc.conteudo,
        },
        "contrato": {
            "legal_doc_id": contrato.id,
            "titulo": contrato.titulo,
            "valor_sugerido": valor_sugerido,
            "conteudo": contrato.conteudo,
        },
    }
