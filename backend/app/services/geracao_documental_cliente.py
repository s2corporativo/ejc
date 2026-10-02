"""Geração determinística de documentos de admissão vinculados ao cliente.

Contrato e procuração nascem como rascunho, sem LLM e sem aprovação automática.
A identidade do kit usa ``client_id`` + ``client_admission_kind``; título/nome do
cliente é apenas apresentação e nunca chave de domínio.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import role_str as _role_str
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.fee import Fee, FeeEstorno, FeePayment, FeeStatus, FeeTipo
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


def _somar_meses(data: date, meses: int) -> date:
    """Soma meses preservando o dia quando possível (31/01 → 28/29/02)."""
    indice = data.month - 1 + meses
    ano = data.year + indice // 12
    mes = indice % 12 + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _moeda(valor: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def _cronograma_fixo(
    valor_contratual: Decimal | None,
    entrada: Decimal | None,
    numero_parcelas: int,
    primeiro_vencimento: date | None,
    *,
    data_entrada: date,
) -> list[dict]:
    """Cronograma determinístico: entrada + N parcelas mensais.

    O valor contratual é o TOTAL. A entrada é abatida antes da divisão.
    Centavos residuais são distribuídos nas primeiras parcelas, garantindo
    soma exata sem arredondamento financeiro silencioso.
    """
    if valor_contratual is None:
        return []
    total = _moeda(valor_contratual)
    valor_entrada = _moeda(entrada)
    if total < 0 or valor_entrada < 0:
        raise ValueError("valores financeiros não podem ser negativos")
    if valor_entrada > total:
        raise ValueError("entrada não pode ser maior que o valor contratual")
    if numero_parcelas < 1:
        raise ValueError("numero_parcelas deve ser pelo menos 1")
    saldo = total - valor_entrada
    if saldo > 0 and numero_parcelas > 1 and primeiro_vencimento is None:
        raise ValueError("parcelamento exige o primeiro vencimento")

    cronograma: list[dict] = []
    if valor_entrada > 0:
        cronograma.append(
            {
                "chave": "entrada",
                "rotulo": "Entrada",
                "valor": valor_entrada,
                "vencimento": data_entrada,
            }
        )

    if saldo <= 0:
        return cronograma

    centavos = int((saldo * 100).to_integral_value())
    base, resto = divmod(centavos, numero_parcelas)
    for indice in range(numero_parcelas):
        parcela_centavos = base + (1 if indice < resto else 0)
        if parcela_centavos <= 0:
            continue
        vencimento = (
            _somar_meses(primeiro_vencimento, indice)
            if primeiro_vencimento is not None
            else None
        )
        cronograma.append(
            {
                "chave": f"parcela-{indice + 1}-de-{numero_parcelas}",
                "rotulo": f"Parcela {indice + 1}/{numero_parcelas}",
                "valor": Decimal(parcela_centavos) / Decimal("100"),
                "vencimento": vencimento,
            }
        )
    return cronograma


def _descricao_cronograma(
    cronograma: list[dict], forma_pagamento: str | None
) -> str:
    partes: list[str] = []
    entrada = next((item for item in cronograma if item["chave"] == "entrada"), None)
    parcelas = [item for item in cronograma if item["chave"] != "entrada"]
    if entrada:
        partes.append(f"entrada de {formatar_brl(entrada['valor'])} na assinatura")
    if parcelas:
        grupos: dict[Decimal, int] = {}
        for item in parcelas:
            grupos[item["valor"]] = grupos.get(item["valor"], 0) + 1
        valores = " + ".join(
            f"{quantidade}x {formatar_brl(valor)}"
            for valor, quantidade in grupos.items()
        )
        venc = parcelas[0]["vencimento"]
        sufixo = (
            f", com primeiro vencimento em {venc.strftime('%d/%m/%Y')}"
            if venc is not None
            else ""
        )
        partes.append(
            f"{len(parcelas)} parcela(s) mensal(is) ({valores}){sufixo}"
        )
    livre = (forma_pagamento or "").strip()
    if livre:
        partes.append(f"condição adicional: {livre}")
    return "; ".join(partes) if partes else "[____]"


async def _total_pago_efetivo(db: AsyncSession, fee_ids: list[str]) -> Decimal:
    if not fee_ids:
        return Decimal("0.00")
    pagos = (await db.execute(
        select(func.coalesce(func.sum(FeePayment.valor), 0)).where(
            FeePayment.fee_id.in_(fee_ids)
        )
    )).scalar() or 0
    estornos = (await db.execute(
        select(func.coalesce(func.sum(FeeEstorno.valor), 0)).where(
            FeeEstorno.fee_id.in_(fee_ids)
        )
    )).scalar() or 0
    return max(_moeda(pagos) - _moeda(estornos), Decimal("0.00"))


async def _sincronizar_financeiro_contrato(
    db: AsyncSession,
    cli: Client,
    *,
    nome_cliente: str,
    valor_contratual: Decimal | None,
    entrada: Decimal | None,
    numero_parcelas: int,
    primeiro_vencimento: date | None,
    percentual_exito: Decimal | None,
    forma_pagamento: str | None,
    case_id: str | None,
) -> dict:
    """Materializa o contrato em parcelas do subledger canônico de honorários.

    Reemissão cancela somente cobranças antigas ainda abertas e cria o novo
    cronograma do saldo remanescente. Pagamentos/estornos são append-only e
    nunca são alterados. Honorário de êxito já recebido exige ajuste financeiro
    manual, pois não há base segura para reinterpretar o percentual.
    """
    raiz = f"[origem:contrato-admissao;client={cli.id};case={case_id or '-'}"
    cond_case = Fee.case_id == case_id if case_id else Fee.case_id.is_(None)
    historico = list((await db.execute(
        select(Fee).where(
            Fee.client_id == cli.id,
            cond_case,
            Fee.deleted_at.is_(None),
            Fee.observacoes.ilike(f"%{raiz}%"),
        )
    )).scalars().all())

    fixos = [
        fee for fee in historico
        if ";component=fixo;" in (fee.observacoes or "")
        or (
            fee.valor is not None
            and ";component=exito;" not in (fee.observacoes or "")
        )
    ]
    exitos = [
        fee for fee in historico
        if ";component=exito;" in (fee.observacoes or "")
        or (fee.percentual_exito is not None and fee.valor is None)
    ]
    pago_fixo = await _total_pago_efetivo(db, [fee.id for fee in fixos])
    pago_exito = await _total_pago_efetivo(db, [fee.id for fee in exitos])

    total = _moeda(valor_contratual) if valor_contratual is not None else None
    if pago_fixo > 0 and total is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "O contrato já possui recebimentos de honorários fixos. "
                "Defina o valor contratual ou ajuste o financeiro manualmente."
            ),
        )
    if total is not None and pago_fixo > total:
        raise HTTPException(
            status_code=409,
            detail=(
                "O novo valor contratual é menor que o total já recebido. "
                "Ajuste o financeiro manualmente antes de regerar o contrato."
            ),
        )

    if pago_exito > 0:
        percentuais_anteriores = {
            _moeda(fee.percentual_exito)
            for fee in exitos
            if fee.percentual_exito is not None
        }
        novo = _moeda(percentual_exito) if percentual_exito is not None else None
        if (
            novo is None
            or (percentuais_anteriores and novo not in percentuais_anteriores)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Honorários de êxito deste contrato já possuem recebimento. "
                    "O percentual não pode ser alterado automaticamente."
                ),
            )

    for fee in fixos:
        if fee.status in (FeeStatus.pendente, FeeStatus.atrasado):
            fee.status = FeeStatus.cancelado
    if pago_exito == 0:
        for fee in exitos:
            if fee.status in (FeeStatus.pendente, FeeStatus.atrasado):
                fee.status = FeeStatus.cancelado

    criados: list[Fee] = []
    restante = (
        max((total or Decimal("0.00")) - pago_fixo, Decimal("0.00"))
        if total is not None
        else Decimal("0.00")
    )
    entrada_restante = _moeda(entrada) if pago_fixo == 0 else Decimal("0.00")
    if entrada_restante > restante:
        entrada_restante = restante

    cronograma = _cronograma_fixo(
        restante if total is not None else None,
        entrada_restante,
        numero_parcelas,
        primeiro_vencimento,
        data_entrada=date.today(),
    )
    descricao_condicao = _descricao_cronograma(cronograma, forma_pagamento)
    for item in cronograma:
        marcador = f"{raiz};component=fixo;item={item['chave']}]"
        fee = Fee(
            id=str(uuid4()),
            tipo=FeeTipo.fixo,
            status=FeeStatus.pendente,
            descricao=(
                f"Contrato de honorários — {item['rotulo']} — {nome_cliente}"
            )[:255],
            valor=item["valor"],
            percentual_exito=None,
            data_vencimento=item["vencimento"],
            client_id=cli.id,
            case_id=case_id,
            observacoes=(
                f"{marcador} Sincronizado a partir do contrato de honorários. "
                f"Condição: {descricao_condicao}."
            ),
        )
        db.add(fee)
        criados.append(fee)

    if percentual_exito is not None and pago_exito == 0:
        marcador = f"{raiz};component=exito;item=percentual]"
        fee = Fee(
            id=str(uuid4()),
            tipo=FeeTipo.exito,
            status=FeeStatus.pendente,
            descricao=f"Honorários de êxito — {nome_cliente}"[:255],
            valor=None,
            percentual_exito=percentual_exito,
            data_vencimento=None,
            client_id=cli.id,
            case_id=case_id,
            observacoes=(
                f"{marcador} Percentual previsto no contrato; valor monetário "
                "depende do proveito econômico efetivamente apurado."
            ),
        )
        db.add(fee)
        criados.append(fee)

    return {
        "fee_ids": [fee.id for fee in criados],
        "parcelas_criadas": len(
            [fee for fee in criados if fee.tipo == FeeTipo.fixo]
        ),
        "pago_fixo_preservado": float(pago_fixo),
        "exito_preservado": bool(pago_exito > 0),
    }


async def contexto_financeiro_contrato(
    db: AsyncSession,
    cli: Client,
    *,
    case_id: str | None = None,
) -> dict:
    """Reconstrói os termos financeiros correntes a partir do subledger.

    O total contratual atual é o que já foi efetivamente recebido somado ao
    saldo ainda aberto das parcelas ativas. Parcelas canceladas sem pagamento
    ficam apenas no histórico e não voltam ao formulário.
    """
    raiz = f"[origem:contrato-admissao;client={cli.id};case={case_id or '-'}"
    cond_case = Fee.case_id == case_id if case_id else Fee.case_id.is_(None)
    historico = list((await db.execute(
        select(Fee)
        .where(
            Fee.client_id == cli.id,
            cond_case,
            Fee.deleted_at.is_(None),
            Fee.observacoes.ilike(f"%{raiz}%"),
        )
        .order_by(Fee.created_at.asc())
    )).scalars().all())

    fixos = [
        fee for fee in historico
        if ";component=fixo;" in (fee.observacoes or "")
        or (
            fee.valor is not None
            and ";component=exito;" not in (fee.observacoes or "")
        )
    ]
    ativos = [
        fee for fee in fixos
        if fee.status in (FeeStatus.pendente, FeeStatus.atrasado)
    ]
    pago_total = await _total_pago_efetivo(db, [fee.id for fee in fixos])
    pago_ativos = await _total_pago_efetivo(db, [fee.id for fee in ativos])
    saldo_aberto = max(
        sum((_moeda(fee.valor) for fee in ativos), Decimal("0.00"))
        - pago_ativos,
        Decimal("0.00"),
    )
    total_atual = pago_total + saldo_aberto

    entrada_aberta = next(
        (
            _moeda(fee.valor)
            for fee in ativos
            if "item=entrada]" in (fee.observacoes or "")
        ),
        Decimal("0.00"),
    )
    totais_parcelas: list[int] = []
    parcelas_ativas: list[Fee] = []
    for fee in ativos:
        obs = fee.observacoes or ""
        match = re.search(r"item=parcela-\d+-de-(\d+)\]", obs)
        if match:
            totais_parcelas.append(int(match.group(1)))
            parcelas_ativas.append(fee)
    primeiro_vencimento = min(
        (fee.data_vencimento for fee in parcelas_ativas if fee.data_vencimento),
        default=None,
    )

    exitos = [
        fee for fee in historico
        if (
            ";component=exito;" in (fee.observacoes or "")
            or (fee.percentual_exito is not None and fee.valor is None)
        )
        and fee.status != FeeStatus.cancelado
    ]
    percentual_exito = next(
        (
            _moeda(fee.percentual_exito)
            for fee in reversed(exitos)
            if fee.percentual_exito is not None
        ),
        None,
    )

    return {
        "valor_contratual": float(total_atual) if fixos else None,
        "valor_pago": float(pago_total),
        "saldo_aberto": float(saldo_aberto),
        "entrada": float(entrada_aberta) if entrada_aberta > 0 else None,
        "numero_parcelas": max(totais_parcelas, default=max(len(parcelas_ativas), 1)),
        "primeiro_vencimento": (
            primeiro_vencimento.isoformat() if primeiro_vencimento else None
        ),
        "percentual_exito": (
            float(percentual_exito) if percentual_exito is not None else None
        ),
        "cronograma": [
            {
                "fee_id": fee.id,
                "descricao": fee.descricao,
                "valor": float(fee.valor or 0),
                "vencimento": (
                    fee.data_vencimento.isoformat() if fee.data_vencimento else None
                ),
                "status": getattr(fee.status, "value", fee.status),
            }
            for fee in ativos
        ],
    }


def _contrato_cliente(
    cli: Client, advogado: str, area: str, referencia_oab: str | None,
    *, valor_contratual: Decimal | None = None,
    percentual_exito: Decimal | None = None,
    forma_pagamento: str | None = None,
) -> str:
    ref = f" ({referencia_oab})" if referencia_oab else ""
    objeto = f" na área de {area}" if area else " em área a definir pelas partes"
    valor_txt = formatar_brl(valor_contratual) if valor_contratual is not None else "R$ [____]"
    exito_txt = f"{float(percentual_exito):g}%" if percentual_exito is not None else "[__]%"
    pagamento_txt = (forma_pagamento or "").strip() or "[____]"
    clausulas = (
        "CLÁUSULA 1 - OBJETO. Prestação de serviços advocatícios ao CONTRATANTE"
        f"{objeto}, abrangendo consultoria e as medidas judiciais ou extrajudiciais "
        "que forem expressamente definidas e aprovadas.\n\n"
        f"CLÁUSULA 2 - HONORÁRIOS. As partes ajustam o valor final em {valor_txt}, "
        f"tendo como referência a Tabela de Honorários da OAB/MG{ref}, "
        f"com forma de pagamento {pagamento_txt}.\n\n"
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


async def gerar_documentos_cliente(
    db: AsyncSession,
    cli: Client,
    cu: User,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
    valor_contratual: Decimal | None = None,
    entrada: Decimal | None = None,
    numero_parcelas: int = 1,
    percentual_exito: Decimal | None = None,
    forma_pagamento: str | None = None,
    data_vencimento: date | None = None,
    case_id: str | None = None,
    sincronizar_financeiro: bool | None = None,
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
    try:
        cronograma_contratual = _cronograma_fixo(
            valor_contratual,
            entrada,
            numero_parcelas,
            data_vencimento,
            data_entrada=date.today(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    forma_pagamento_contrato = _descricao_cronograma(
        cronograma_contratual, forma_pagamento
    )

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
            "valor_contratual": (
                formatar_brl(valor_contratual)
                if valor_contratual is not None else "R$ [____]"
            ),
            "percentual_exito": (
                f"{float(percentual_exito):g}%"
                if percentual_exito is not None else "[__]%"
            ),
            "forma_pagamento": forma_pagamento_contrato,
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
            cli, advogado, area, referencia,
            valor_contratual=valor_contratual,
            percentual_exito=percentual_exito,
            forma_pagamento=forma_pagamento_contrato,
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

    if sincronizar_financeiro is None:
        sincronizar_financeiro = any(
            (
                valor_contratual is not None,
                entrada is not None,
                numero_parcelas != 1,
                percentual_exito is not None,
                bool((forma_pagamento or "").strip()),
                data_vencimento is not None,
            )
        )
    if sincronizar_financeiro:
        financeiro = await _sincronizar_financeiro_contrato(
            db,
            cli,
            nome_cliente=nome_cliente,
            valor_contratual=valor_contratual,
            entrada=entrada,
            numero_parcelas=numero_parcelas,
            primeiro_vencimento=data_vencimento,
            percentual_exito=percentual_exito,
            forma_pagamento=forma_pagamento,
            case_id=case_id,
        )
    else:
        financeiro = {
            "fee_ids": [],
            "parcelas_criadas": 0,
            "pago_fixo_preservado": 0.0,
            "exito_preservado": False,
        }
    financeiro_ids = financeiro["fee_ids"]
    financeiro_id = financeiro_ids[0] if financeiro_ids else None

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
            "financeiro_fee_id": financeiro_id,
            "financeiro_fee_ids": financeiro_ids,
            "parcelas_criadas": financeiro["parcelas_criadas"],
            "pago_fixo_preservado": financeiro["pago_fixo_preservado"],
        },
    )
    await db.commit()

    proc, contrato = criados
    return {
        "client_id": cli.id,
        "status": PecaStatus.rascunho.value,
        "ja_existia": False,
        "financeiro_fee_id": financeiro_id,
        "financeiro_fee_ids": financeiro_ids,
        "parcelas_criadas": financeiro["parcelas_criadas"],
        "pago_fixo_preservado": financeiro["pago_fixo_preservado"],
        "aviso": AVISO_RASCUNHO,
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
