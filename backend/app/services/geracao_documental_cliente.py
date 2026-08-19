# ── app/services/geracao_documental_cliente.py ────────────────────────────────
# Geração documental NO CADASTRO DO CLIENTE (sem caso vinculado).
#
# Preenchimento de TEMPLATE determinístico (sem LLM), reaproveitando os
# modelos oficiais do escritório já existentes em documental.py:
#   1. Procuração ad judicia (geral, sem caso): _procuracao(case=None) — a
#      assinatura do template já contempla a atuação geral ao foro em geral.
#   2. Contrato de prestação de serviços advocatícios e honorários SEM caso:
#      cláusula de objeto genérica (área de interesse do cliente quando
#      informada) + estrutura de cláusulas idêntica ao kit de casos, com
#      valor SUGERIDO pela Tabela OAB/MG vigente (área de interesse, se houver)
#      ou explicitamente "a definir". NUNCA inventa valor/item/vigência.
#
# Persistência no padrão da casa (geracao_documental.kit): LegalDoc
# SEMPRE status=rascunho, human_reviewed=False, ai_generated=True (aciona o
# gate HITL — nenhuma minuta é aprovada sem revisão humana). Auditoria
# GERAR_DOCS_CLIENTE obrigatória. Case_id fica None (vínculo só com o cliente).
#
# IDEMPOTENTE: se os 2 rascunhos canônicos já existirem para o cliente,
# devolve os EXISTENTES com ja_existia=True — nada é criado/auditado.
# Regeneração explícita só com forcar_novo=True.
from __future__ import annotations

import logging
from datetime import date
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import role_str as _role_str
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.redesign import TabelaOABHonorario
from app.models.user import User
from app.services.document_format import padronizar_documento_juridico
from app.services.documental import _procuracao
from app.utils.format import formatar_brl

logger = logging.getLogger(__name__)


def _titulos_canonicos(nome_cliente: str) -> list[str]:
    """Títulos canônicos das peças de admissão de um cliente (mesmo padrão
    de idempotência da geração: reaproveitado pela listagem do Dossiê)."""
    return [
        padronizar_documento_juridico("Procuracao - " + nome_cliente)[:200],
        padronizar_documento_juridico("Contrato de Honorarios - " + nome_cliente)[:200],
    ]


async def listar_pecas_cliente(
    db: AsyncSession,
    cli: Client,
) -> list[dict]:
    """Peças de admissão (contrato + procuração) geradas no cadastro do
    cliente: peças SOLTAS (case_id=None) com título canônico. Usado pelo
    bloco "Documentos de Admissão" do Dossiê Digital — read-only."""
    nome_cliente = cli.razao_social or cli.nome or ""
    if not nome_cliente:
        return []
    docs = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.case_id.is_(None),
            LegalDoc.deleted_at.is_(None),
            LegalDoc.titulo.in_(_titulos_canonicos(nome_cliente)),
        ).order_by(LegalDoc.created_at.desc())
    )).scalars().all()
    out: list[dict] = []
    for d in docs:
        tipo = "procuracao" if d.titulo.startswith("Procuracao") else "contrato"
        out.append({
            "id": d.id,
            "titulo": d.titulo,
            "tipo": tipo,
            "status": getattr(d.status, "value", str(d.status)),
            "created_at": (
                d.created_at.isoformat() if d.created_at else None
            ),
        })
    return out

AVISO_RASCUNHO = (
    "Documentos gerados automaticamente por preenchimento de template "
    "(sem redacao por IA). Status: RASCUNHO — sujeitos a revisao e "
    "aprovacao do advogado responsavel antes de qualquer uso."
)

AVISO_SEM_AREA_OAB = (
    "Valor de referencia A DEFINIR: nenhum item aplicavel da Tabela OAB/MG "
    "vigente foi encontrado para a area de interesse do cliente. Nunca "
    "inventamos valores — consulte a tabela oficial OAB/MG."
)

AVISO_KIT_EXISTENTE = (
    "Documentos ja existentes para o cliente — os rascunhos anteriores foram "
    "reaproveitados (nenhuma duplicata criada). Para regenerar do zero, envie "
    "forcar_novo=true."
)

PODERES_VALIDOS = {"ad_judicia", "ad_judicia_et_extra", "especiais"}

# Aliases de grafia usados em tabela_oab_honorarios.area_juridica (o seed
# importado usa "civel"; o enum de área do caso usa "civil") — só mapeamento
# de grafia, nunca para área diferente.
_AREA_ALIASES: dict[str, list[str]] = {
    "civil": ["civil", "civel"],
}


def _aliases_area(area: str) -> list[str]:
    return _AREA_ALIASES.get((area or "").strip().lower(), [(area or "").strip().lower()])


async def _itens_oab_vigentes(db, area: str, hoje: date, limite: int = 5):
    """Itens VIGENTES da tabela OAB/MG para a área (idem kit de caso)."""
    aliases = [a for a in _aliases_area(area) if a]
    if not aliases:
        return []
    from sqlalchemy import or_
    q = (
        select(TabelaOABHonorario)
        .where(
            TabelaOABHonorario.ativo.is_(True),
            or_(*[TabelaOABHonorario.area_juridica.ilike(f"%{a}%") for a in aliases]),
            or_(TabelaOABHonorario.vigencia_fim.is_(None),
                TabelaOABHonorario.vigencia_fim >= hoje),
            or_(TabelaOABHonorario.vigencia_inicio.is_(None),
                TabelaOABHonorario.vigencia_inicio <= hoje),
        )
        .order_by(TabelaOABHonorario.vigencia_inicio.desc().nullslast(),
                  TabelaOABHonorario.item_codigo)
        .limit(limite)
    )
    return (await db.execute(q)).scalars().all()


def _referencia_oab_txt(item) -> str:
    partes = []
    if item.valor_minimo is not None:
        partes.append(f"minimo {formatar_brl(item.valor_minimo)}")
    if item.percentual is not None:
        partes.append(f"{float(item.percentual):g}%")
    valores = " + ".join(partes) if partes else "ver tabela"
    return (
        f"sugestao nao vinculante — item {item.item_codigo} "
        f"({item.descricao}): {valores}; fonte: {item.fonte}"
    )


def _item_dict(i) -> dict:
    return {
        "item_codigo": i.item_codigo,
        "descricao": i.descricao,
        "valor_minimo": float(i.valor_minimo) if i.valor_minimo is not None else None,
        "percentual": float(i.percentual) if i.percentual is not None else None,
        "unidade": i.unidade,
        "vigencia_inicio": i.vigencia_inicio.isoformat() if i.vigencia_inicio else None,
        "vigencia_fim": i.vigencia_fim.isoformat() if i.vigencia_fim else None,
        "fonte": i.fonte,
    }


def _contrato_honorarios_cliente(
    cli: Client,
    adv: str,
    area: str,
    referencia_oab: str | None = None,
) -> str:
    """Contrato de prestação de serviços advocatícios SEM caso vinculado.

    Estrutura de cláusulas idêntica ao kit de casos (_contrato_honorarios),
    com objeto genérico (área de interesse do cliente quando informada) e
    valor como placeholder "a definir" + referência da tabela OAB/MG vigente
    quando existe item aplicável. Cláusulas fixas de template do escritório
    aplicadas na íntegra (rescisão, inadimplemento, revogação, LGPD,
    comunicação eletrônica). Foro: comarca da sede do escritório.
    100% determinístico — nenhuma redação por LLM.
    """
    from app.services.documental import _CLAUSULAS_FIXAS_CONTRATO, _MARCA, _qualificacao
    from app.core.config import get_settings
    _settings = get_settings()

    ref = f" ({referencia_oab})" if referencia_oab else ""
    objeto = (f" na área de {area}" if area else " em área a definir pelas partes")
    clausulas = (
        "CLÁUSULA 1 - OBJETO. Prestação de serviços advocatícios ao CONTRATANTE"
        f"{objeto}, abrangendo a consultoria, a propositura e o acompanhamento "
        "das medidas judiciais e extrajudiciais cabíveis.\n\n"
        "CLÁUSULA 2 - HONORÁRIOS. As partes ajustam honorários no valor de R$ [____], "
        f"tendo como referência a Tabela de Honorários da OAB/MG{ref}, pagos da seguinte forma: [____].\n\n"
        "CLÁUSULA 3 - HONORÁRIOS DE ÊXITO. Em caso de êxito, fica ajustado o percentual de "
        "[__]% sobre o proveito econômico obtido.\n\n"
        "CLÁUSULA 4 - HONORÁRIOS SUCUMBENCIAIS. Pertencem ao contratado, na forma do artigo 85, "
        "parágrafo 14, do CPC e do artigo 22 da Lei 8.906/94.\n\n"
        "CLÁUSULA 5 - DESPESAS. Custas, taxas e despesas processuais correm por conta do contratante.\n\n"
        + "".join(
            f"CLÁUSULA {n} - {texto}\n\n"
            for n, texto in enumerate(_CLAUSULAS_FIXAS_CONTRATO, start=6)
        )
        + f"CLÁUSULA {6 + len(_CLAUSULAS_FIXAS_CONTRATO)} - FORO. Fica eleito o foro da "
        f"Comarca de {_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, "
        "sede do escritório contratado, para dirimir quaisquer controvérsias "
        "oriundas deste contrato.\n\n"
    )
    texto = _MARCA + (
        "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS E HONORÁRIOS\n\n"
        f"CONTRATANTE: {_qualificacao(cli)}.\n\n"
        f"CONTRATADO: {_settings.ESCRITORIO_NOME}, por seu(sua) advogado(a) {adv}"
        f"{(' (OAB/MG nº ' + _settings.escritorio_oab()) if _settings.escritorio_oab() else ''}.\n\n"
        + clausulas
        + f"{_settings.ESCRITORIO_CIDADE}/{_settings.ESCRITORIO_ESTADO}, [data].\n\n"
        f"____________________________   ____________________________\n"
        f"{cli.razao_social or cli.nome} (contratante)        {adv} (contratado)"
    )
    return padronizar_documento_juridico(texto)


async def gerar_documentos_cliente(
    db,
    cli: Client,
    cu: User,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
    forcar_novo: bool = False,
) -> dict:
    """Gera procuração ad judicia + contrato de honorários para o cliente,
    SEM caso vinculado (rascunhos sujeitos a revisão humana; auditoria
    obrigatória). Idempotente (ver cabeçalho do módulo)."""
    if (tipo_poderes or "ad_judicia").strip().lower() not in PODERES_VALIDOS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"tipo_poderes deve ser um de {sorted(PODERES_VALIDOS)}",
        )

    hoje = date.today()
    adv = getattr(cu, "full_name", None) or "[advogado responsavel]"
    papel = _role_str(cu)
    nome_cliente = cli.razao_social or cli.nome or "Cliente"
    area = (getattr(cli, "area_interesse", None) or "").strip()

    titulos = {
        "procuracao": padronizar_documento_juridico(
            "Procuracao - " + nome_cliente)[:200],
        "contrato": padronizar_documento_juridico(
            "Contrato de Honorarios - " + nome_cliente)[:200],
    }

    # ── Idempotência: reaproveitar rascunhos canônicos existentes ────────────
    if not forcar_novo:
        existentes = (await db.execute(
            select(LegalDoc).where(
                LegalDoc.case_id.is_(None),
                LegalDoc.deleted_at.is_(None),
                LegalDoc.status == PecaStatus.rascunho,
                LegalDoc.titulo.in_(list(titulos.values())),
            ).order_by(LegalDoc.created_at.desc())
        )).scalars().all()
        por_titulo: dict[str, LegalDoc] = {}
        for d in existentes:
            por_titulo.setdefault(d.titulo, d)
        if all(t in por_titulo for t in titulos.values()):
            return {
                "client_id": cli.id,
                "status": PecaStatus.rascunho.value,
                "ja_existia": True,
                "aviso": AVISO_KIT_EXISTENTE,
                "procuracao": {
                    "legal_doc_id": por_titulo[titulos["procuracao"]].id,
                    "titulo": por_titulo[titulos["procuracao"]].titulo,
                    "conteudo": por_titulo[titulos["procuracao"]].conteudo,
                },
                "contrato": {
                    "legal_doc_id": por_titulo[titulos["contrato"]].id,
                    "titulo": por_titulo[titulos["contrato"]].titulo,
                    "conteudo": por_titulo[titulos["contrato"]].conteudo,
                },
            }

    # ── 1. Procuração ad judicia geral (sem caso) ─────────────────────────────
    # _procuracao aceita case=None: cláusula ao foro em geral (ad judicia),
    # sem poderes especiais do art. 105 do CPC (defaults conservadores).
    minuta_procuracao = _procuracao(
        None, cli, adv,
        tipo_poderes=tipo_poderes,
        permite_substabelecimento=permite_substabelecimento,
        poderes_especiais=poderes_especiais,
    )

    # ── 2. Contrato sem caso: referência OAB/MG pela área de interesse ────────
    itens = await _itens_oab_vigentes(db, area, hoje) if area else []
    if itens:
        referencia = _referencia_oab_txt(itens[0])
        valor_sugerido = {
            "origem": "tabela_oab_estruturada",
            "sugerido": _item_dict(itens[0]),
            "itens_referencia": [_item_dict(i) for i in itens],
            "aviso": "Referencia da tabela OAB/MG — nao vinculante; o advogado define o valor final.",
        }
    else:
        referencia = None
        valor_sugerido = {"origem": None, "sugerido": None,
                          "itens_referencia": [], "aviso": AVISO_SEM_AREA_OAB}

    minuta_contrato = _contrato_honorarios_cliente(
        cli, adv, area, referencia_oab=referencia,
    )

    # ── Persistência: sempre RASCUNHO (gate HITL) ────────────────────────────
    docs = [
        (titulos["procuracao"], PecaTipo.procuracao, minuta_procuracao),
        (titulos["contrato"], PecaTipo.contrato, minuta_contrato),
    ]
    criados: list[LegalDoc] = []
    for titulo, tipo, conteudo in docs:
        d = LegalDoc(
            id=str(uuid4()),
            titulo=titulo,
            tipo_peca=tipo,
            conteudo=conteudo,
            status=PecaStatus.rascunho,
            area=(area or None) or None,
            ai_generated=True,
            human_reviewed=False,
            case_id=None,
            # Nota: legal_docs NÃO possui client_id (vinculado só a casos ou
            # solto). A rastreabilidade cliente→peça é feita por título
            # canônico ("Procuracao - {cliente}"), pela auditoria
            # GERAR_DOCS_CLIENTE e pela criação de caso futuro com vínculo.
            created_by=cu.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(d)
        criados.append(d)

    # ── Auditoria obrigatória ────────────────────────────────────────────────
    await criar_audit_log(
        db, cu.id, papel, "GERAR_DOCS_CLIENTE", "clients", cli.id,
        detalhes=(f"Procuracao e contrato gerados no cadastro do cliente "
                  f"(rascunhos, tipo_poderes={tipo_poderes}): " + ", ".join(d.id for d in criados)),
        dados_depois={
            "legal_doc_ids": [d.id for d in criados],
            "oab_item_aplicado": valor_sugerido["sugerido"] is not None,
        },
    )
    await db.commit()

    doc_proc, doc_contrato = criados
    return {
        "client_id": cli.id,
        "status": PecaStatus.rascunho.value,
        "ja_existia": False,
        "aviso": AVISO_RASCUNHO,
        "procuracao": {
            "legal_doc_id": doc_proc.id,
            "titulo": doc_proc.titulo,
            "tipo_poderes": tipo_poderes,
            "permite_substabelecimento": permite_substabelecimento,
            "conteudo": doc_proc.conteudo,
            "aviso": ("Minuta pendente de assinatura — o registro formal de "
                      "procuração é emitido no módulo Procurações após a outorga."),
        },
        "contrato": {
            "legal_doc_id": doc_contrato.id,
            "titulo": doc_contrato.titulo,
            "valor_sugerido": valor_sugerido,
            "conteudo": doc_contrato.conteudo,
        },
    }
