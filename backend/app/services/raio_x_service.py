"""Regras determinísticas, conversão e trilha humana do Raio-X.

O serviço não inventa conclusão jurídica. Informações sem origem suficiente
permanecem marcadas para conferência. A conversão é transacional, respeita a
segregação de carteira e transporta a inteligência preliminar para um snapshot
versionado do caso oficial.
"""
from __future__ import annotations

import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.client_ownership import (
    obter_cliente_autorizado,
    pode_ver_caso_resumido,
    pode_ver_cliente,
)
from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseArea, CaseFase, CasePrioridade, CaseStatus
from app.models.case_intelligence import CaseIntelligenceSnapshot
from app.models.client import Client, ClientOrigem, ClientStatus, ClientTipo
from app.models.deadline import Deadline, DeadlinePrioridade, DeadlineStatus, DeadlineTipo
from app.models.document import DocConfidencialidade, Document
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.raio_x import RaioXConverterRequest
from app.services.case_intelligence_service import compactar_payload
from app.services.conflito_service import _padrao_like
from app.services.case_numeracao import proximo_numero_interno as _proximo_numero_interno
from app.services.raio_x_enrichment import (
    data_iso,
    enriquecer_relatorio,
    lista,
    normalizar,
    unicos,
    valor,
)

settings = get_settings()
_CONVERSION_ROLES = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _valor(campo: Any) -> Any:
    return valor(campo)


def _lista(value: Any) -> list[Any]:
    return lista(value)


def _unicos(values: Iterable[Any]) -> list[Any]:
    return unicos(values)


def _data_iso(value: Any) -> str | None:
    return data_iso(value)


def _intake(documento: RaioXDocumento) -> dict[str, Any]:
    result = documento.resultado_analise or {}
    intake = result.get("intake_result") or result
    return intake if isinstance(intake, dict) else {}


def _nome_item(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("nome", "razao_social", "parte", "valor", "texto", "descricao"):
            candidate = _valor(item.get(key))
            if candidate:
                return str(candidate).strip()
    return str(_valor(item) or "").strip()


def consolidar_relatorio(documentos: list[RaioXDocumento]) -> dict[str, Any]:
    """Consolida as extrações e executa enriquecimento determinístico auditável."""
    resultados = [documento.resultado_analise or {} for documento in documentos]
    intakes = [resultado.get("intake_result") or resultado for resultado in resultados]
    intakes = [item if isinstance(item, dict) else {} for item in intakes]
    fontes = [
        {
            "documento_id": documento.id,
            "arquivo": documento.nome_original,
            "tipo": documento.tipo_documento,
            "hash": documento.sha256,
        }
        for documento in documentos
    ]

    clientes = [_valor(item.get("cliente")) for item in intakes if item.get("cliente")]
    casos = [_valor(item.get("caso")) for item in intakes if item.get("caso")]
    partes = _unicos(element for item in intakes for element in _lista(item.get("partes")))
    pedidos = _unicos(element for item in intakes for element in _lista(item.get("pedidos")))
    provas = _unicos(element for item in intakes for element in _lista(item.get("provas")))
    riscos = _unicos(element for item in intakes for element in _lista(item.get("riscos")))
    teses = _unicos(element for item in intakes for element in _lista(item.get("teses")))
    pendencias = _unicos(element for item in intakes for element in _lista(item.get("pendencias")))
    prazos = _unicos(element for item in intakes for element in _lista(item.get("prazos")))
    resumos = _unicos(str(_valor(item.get("resumo_fatos")) or "").strip() for item in intakes)

    identificacao: dict[str, Any] = {
        "cliente_potencial": clientes[0] if clientes else None,
        "caso": casos[0] if casos else None,
        "numero_processo": None,
        "area": None,
        "subarea": None,
        "rito": None,
        "fase": None,
        "tribunal": None,
        "orgao": None,
        "unidade": None,
        "posicao_cliente": None,
        "confianca": "revisao_humana_obrigatoria",
    }
    campos_identificacao = (
        "numero_processo", "area", "subarea", "rito", "fase", "tribunal",
        "orgao", "unidade", "posicao_cliente", "instancia", "classe", "assunto",
    )
    for intake in intakes:
        case_data = _valor(intake.get("caso"))
        if isinstance(case_data, dict):
            for key in campos_identificacao:
                identificacao[key] = identificacao.get(key) or _valor(case_data.get(key))
        classificacao = intake.get("classificacao")
        if isinstance(classificacao, dict):
            for key in ("area", "subarea", "rito", "fase"):
                identificacao[key] = identificacao.get(key) or _valor(classificacao.get(key))
        for key in campos_identificacao:
            identificacao[key] = identificacao.get(key) or _valor(intake.get(key))

    # Onda 4 — separar STATUS TÉCNICO do pipeline (o que a extração não
    # conseguiu identificar) de MÉRITO jurídico (fraqueza do caso em si).
    # Antes, esta mesma lista alimentava `pontos_fracos`: "não achei o número
    # do processo" chegava ao advogado como se fosse uma fraqueza da causa.
    lacunas_da_analise: list[str] = []
    if not identificacao["numero_processo"]:
        lacunas_da_analise.append("Número do processo não identificado")
    if not partes:
        lacunas_da_analise.append("Partes não identificadas com segurança")
    if not provas:
        lacunas_da_analise.append("Provas ainda não classificadas")

    # `pendencias` vem da extração de IA como pendência processual/documental
    # concreta (ex.: "juntar procuração", "aguardando perícia") — pertence a
    # "o que falta resolver no caso", não ao diagnóstico do pipeline.
    pendencias_texto = [str(_valor(item)) for item in pendencias if _valor(item)]

    # `documentos_pendentes` preserva o significado combinado que já tinha
    # (o que falta para a análise ficar completa: identificação + pendências
    # levantadas) — só deixou de ser reaproveitado como fraqueza jurídica.
    faltantes = lacunas_da_analise + pendencias_texto

    _ACAO_POR_LACUNA = {
        "Número do processo não identificado": "Informar o número do processo (CNJ), se houver.",
        "Partes não identificadas com segurança": "Confirmar nome e qualificação completa das partes.",
        "Provas ainda não classificadas": "Classificar as provas anexadas ou indicar as que faltam.",
    }
    proximos_passos_iniciais = [
        _ACAO_POR_LACUNA.get(item, item) for item in lacunas_da_analise
    ] + pendencias_texto

    base = {
        "versao": 2,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "aviso": (
            "Análise preliminar. Nenhum prazo, rito, conclusão ou providência é oficial "
            "antes da confirmação humana. Correlações entre fatos e provas são indicativas."
        ),
        "fontes": fontes,
        "identificacao": identificacao,
        "sintese_executiva": "\n\n".join(resumos) if resumos else "Síntese pendente de conferência documental.",
        "partes": partes,
        "cronologia": [],
        "fatos_provas": [],
        "pedidos": pedidos,
        "provas": provas,
        "contradicoes": [],
        "decisoes": [],
        "prazos_potenciais": prazos,
        "riscos": riscos,
        "teses": teses,
        # Status técnico do pipeline — NÃO é fraqueza do caso. Consumido pela
        # UI numa seção própria ("Lacunas da análise"), separada do mérito.
        "lacunas_da_analise": lacunas_da_analise,
        "pontos_fortes": [],
        # Substantivo: só recebe fraqueza JURÍDICA (enriquecer_relatorio
        # adiciona fato sem prova / contradição). Nasce vazio de propósito.
        "pontos_fracos": [],
        "proximos_passos": proximos_passos_iniciais or ["Revisar o relatório e definir a providência jurídica."],
        "documentos_pendentes": faltantes,
        "confianca_global": "insuficiente_para_automatizacao",
    }
    enriquecido = enriquecer_relatorio(documentos, base)

    # `pontos_fortes` nunca pode ficar vazio quando há teses identificadas —
    # regra explícita da Onda 4. enriquecer_relatorio só preenche a partir de
    # decisão/correlação de prova; um caso com teses mas sem nenhuma das duas
    # ficaria sem nenhum ponto forte, mesmo tendo mérito a favor do cliente.
    if teses and not enriquecido.get("pontos_fortes"):
        primeiras = [str(_valor(item)) for item in teses[:3] if _valor(item)]
        resumo = "; ".join(primeiras)
        if len(teses) > 3:
            resumo += "…"
        enriquecido["pontos_fortes"] = [
            f"{len(teses)} tese(s) jurídica(s) identificada(s) para avaliação"
            + (f": {resumo}" if resumo else ".")
        ]
    return enriquecido


def serializar_analise(analise: RaioXAnalise, incluir_documentos: bool = True) -> dict[str, Any]:
    report = analise.relatorio or {}
    risk = analise.risco_nivel or report.get("risco_nivel")
    urgent = bool(analise.prazo_urgente or report.get("prazo_urgente"))
    result = {
        "id": analise.id,
        "titulo": analise.titulo,
        "potencial_cliente": analise.potencial_cliente,
        "numero_processo": analise.numero_processo,
        "area": analise.area,
        "subarea": analise.subarea,
        "rito": analise.rito,
        "fase": analise.fase,
        "tribunal": analise.tribunal,
        "orgao": analise.orgao,
        "unidade": analise.unidade,
        "posicao_cliente": analise.posicao_cliente,
        "status": analise.status,
        "risco_nivel": risk,
        "prazo_urgente": urgent,
        "relatorio": report,
        "revisao_humana": analise.revisao_humana or {},
        "alertas_conflito": analise.alertas_conflito or [],
        "custo_ia": analise.custo_ia or {},
        "convertido_case_id": analise.convertido_case_id,
        "retention_until": analise.retention_until.isoformat() if analise.retention_until else None,
        "created_by": analise.created_by,
        "created_at": analise.created_at.isoformat() if analise.created_at else None,
        "updated_at": analise.updated_at.isoformat() if analise.updated_at else None,
    }
    if incluir_documentos:
        result["documentos"] = [
            {
                "id": documento.id,
                "nome_original": documento.nome_original,
                "mimetype": documento.mimetype,
                "size_bytes": documento.size_bytes,
                "sha256": documento.sha256,
                "tipo_documento": documento.tipo_documento,
                "paginas": documento.paginas,
                "ocr_utilizado": documento.ocr_utilizado,
                "created_at": documento.created_at.isoformat() if documento.created_at else None,
            }
            for documento in analise.documentos
        ]
    return result


async def _usuario_escopo(
    db: AsyncSession,
    analise: RaioXAnalise,
    user: User | None,
) -> User | None:
    if user is not None:
        return user
    if not analise.created_by:
        return None
    return (
        await db.execute(select(User).where(User.id == analise.created_by))
    ).scalar_one_or_none()


def _alerta_protegido(tipo: str, mensagem: str) -> dict[str, Any]:
    return {
        "tipo": tipo,
        "nome": "Correspondência protegida na base do escritório",
        "mensagem": mensagem,
        "protegido": True,
        "confirmado": False,
    }


async def _detectar_conflitos(
    db: AsyncSession,
    analise: RaioXAnalise,
    payload: RaioXConverterRequest | None = None,
    user: User | None = None,
) -> list[dict[str, Any]]:
    """Cruza a base inteira por dever ético sem expor outra carteira."""
    report = analise.relatorio or {}
    potential = normalizar(
        (payload.cliente.nome if payload and payload.cliente.nome else None)
        or analise.potencial_cliente
        or (report.get("identificacao") or {}).get("cliente_potencial")
    )
    names: list[str] = []
    for item in report.get("partes") or []:
        name = _nome_item(item)
        if len(name) >= 3 and normalizar(name) != potential:
            names.append(name)
    names = [str(item) for item in _unicos(names)][:20]
    if not names:
        return list(analise.alertas_conflito or [])

    # Wildcards do input escapados (núcleo compartilhado): nome com `%`/`_`
    # transformaria a checagem ética em oráculo de substring da base.
    conditions_clients = [
        or_(
            Client.nome.ilike(_padrao_like(name), escape="\\"),
            Client.razao_social.ilike(_padrao_like(name), escape="\\"),
        )
        for name in names
    ]
    clients = (
        await db.execute(
            select(Client)
            .where(or_(*conditions_clients), Client.deleted_at.is_(None))
            .limit(30)
        )
    ).scalars().all()

    conditions_cases = [
        Case.parte_contraria.ilike(_padrao_like(name), escape="\\") for name in names
    ]
    cases = (
        await db.execute(
            select(Case)
            .where(or_(*conditions_cases), Case.deleted_at.is_(None))
            .limit(30)
        )
    ).scalars().all()

    scope_user = await _usuario_escopo(db, analise, user)
    alerts: list[dict[str, Any]] = []
    # Não reaproveitar alertas antigos sem revalidar a visibilidade: registros
    # persistidos por versões anteriores podem conter ids/nomes transcarteira.
    for client in clients:
        visible = bool(scope_user and await pode_ver_cliente(db, scope_user, client))
        if visible:
            alerts.append({
                "tipo": "parte_corresponde_a_cliente",
                "nome": client.nome_exibicao,
                "client_id": client.id,
                "mensagem": "Parte do documento possui nome semelhante a cliente atual ou anterior. Revisar conflito sem revelar dados além da carteira autorizada.",
                "protegido": False,
                "confirmado": False,
            })
        else:
            alerts.append(_alerta_protegido(
                "parte_corresponde_a_cliente_protegido",
                "Foi encontrada correspondência em carteira protegida. Solicite revisão de conflito à gestão antes de prosseguir.",
            ))

    for case in cases:
        visible = bool(scope_user and pode_ver_caso_resumido(scope_user, case))
        if visible:
            alerts.append({
                "tipo": "parte_corresponde_a_parte_contraria",
                "nome": case.parte_contraria,
                "case_id": case.id,
                "mensagem": "Parte do documento possui nome semelhante a parte contrária de caso acessível. Revisar conflito e grupo econômico.",
                "protegido": False,
                "confirmado": False,
            })
        else:
            alerts.append(_alerta_protegido(
                "parte_corresponde_a_caso_protegido",
                "Foi encontrada correspondência em caso protegido. Solicite revisão de conflito à gestão antes de prosseguir.",
            ))

    # Deduplicação segura sem depender de ids protegidos.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for alert in alerts:
        key = (
            str(alert.get("tipo") or ""),
            str(alert.get("nome") or ""),
            str(alert.get("mensagem") or ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(alert)
    return unique


async def preview_conversao(
    db: AsyncSession,
    analise: RaioXAnalise,
    payload: RaioXConverterRequest | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    relatorio = analise.relatorio or {}
    identificacao = relatorio.get("identificacao") or {}
    numero = (
        (payload.caso.numero_processo if payload else None)
        or analise.numero_processo
        or identificacao.get("numero_processo")
    )
    nomes = [analise.potencial_cliente]
    if payload and payload.cliente.nome:
        nomes.append(payload.cliente.nome)
    nomes = [item.strip() for item in nomes if isinstance(item, str) and item.strip()]
    scope_user = await _usuario_escopo(db, analise, user)

    casos: list[dict[str, Any]] = []
    if numero:
        rows = (
            await db.execute(
                select(Case).where(Case.numero_processo == numero, Case.deleted_at.is_(None))
            )
        ).scalars().all()
        for case in rows:
            if scope_user and pode_ver_caso_resumido(scope_user, case):
                casos.append({
                    "id": case.id,
                    "titulo": case.titulo,
                    "numero_processo": case.numero_processo,
                    "protegido": False,
                })
            else:
                casos.append({
                    "id": None,
                    "titulo": "Caso protegido na base do escritório",
                    "numero_processo": None,
                    "protegido": True,
                })

    clientes: list[dict[str, Any]] = []
    if nomes:
        conditions = [
            or_(
                Client.nome.ilike(_padrao_like(name), escape="\\"),
                Client.razao_social.ilike(_padrao_like(name), escape="\\"),
            )
            for name in nomes
        ]
        rows = (
            await db.execute(
                select(Client)
                .where(or_(*conditions), Client.deleted_at.is_(None))
                .limit(10)
            )
        ).scalars().all()
        for client in rows:
            if scope_user and await pode_ver_cliente(db, scope_user, client):
                clientes.append({
                    "id": client.id,
                    "nome": client.nome_exibicao,
                    "cpf": bool(client.cpf_enc),
                    "cnpj": bool(client.cnpj_enc),
                    "protegido": False,
                })
            else:
                # A existência influencia o bloqueio ético/deduplicação, mas UUID,
                # nome e tipo documental não são expostos à carteira não autorizada.
                clientes.append({
                    "id": None,
                    "nome": "Cliente protegido na base do escritório",
                    "cpf": False,
                    "cnpj": False,
                    "protegido": True,
                })

    conflict_alerts = await _detectar_conflitos(db, analise, payload, scope_user)
    return {
        "analise_id": analise.id,
        "casos_possivelmente_duplicados": casos,
        "clientes_possivelmente_duplicados": clientes,
        "alertas_conflito": conflict_alerts,
        "documentos_disponiveis": [
            {"id": documento.id, "nome": documento.nome_original, "tipo": documento.tipo_documento}
            for documento in analise.documentos
        ],
        "prazos_potenciais": relatorio.get("prazos_potenciais", []),
        "tarefas_sugeridas": relatorio.get("proximos_passos", []),
        "risco_nivel": relatorio.get("risco_nivel"),
        "prazo_urgente": bool(relatorio.get("prazo_urgente")),
        "rito_jornada": relatorio.get("rito_jornada") or {},
        "bloqueia": bool(casos or conflict_alerts),
    }


async def _resolver_cliente(db: AsyncSession, payload: RaioXConverterRequest, user: User) -> Client:
    req = payload.cliente
    if req.modo == "existente":
        return await obter_cliente_autorizado(db, user, req.client_id)

    digits_cpf = re.sub(r"\D", "", req.cpf or "")[:11] or None
    digits_cnpj = re.sub(r"\D", "", req.cnpj or "")[:14] or None

    from app.services.pii_crypto import encrypt, hash_documento

    existing = None
    if digits_cpf:
        existing = (
            await db.execute(
                select(Client).where(
                    Client.cpf_hash == hash_documento(digits_cpf),
                    Client.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if not existing and digits_cnpj:
        existing = (
            await db.execute(
                select(Client).where(
                    Client.cnpj_hash == hash_documento(digits_cnpj),
                    Client.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if existing:
        if not await pode_ver_cliente(db, user, existing):
            # Não criar duplicata e não confirmar que o documento pertence a
            # outra carteira. O 404 segue o contrato canônico do CRM.
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return existing
    if not (req.nome or digits_cpf or digits_cnpj):
        raise ValueError("Informe os dados mínimos do novo cliente")

    tipo = ClientTipo.PJ if digits_cnpj else ClientTipo.PF
    client = Client(
        id=str(uuid4()),
        tipo=tipo,
        nome=req.nome if tipo == ClientTipo.PF else None,
        razao_social=req.nome if tipo == ClientTipo.PJ else None,
        cpf_enc=encrypt(digits_cpf) if digits_cpf else None,
        cnpj_enc=encrypt(digits_cnpj) if digits_cnpj else None,
        cpf_hash=hash_documento(digits_cpf) if digits_cpf else None,
        cnpj_hash=hash_documento(digits_cnpj) if digits_cnpj else None,
        email=req.email,
        telefone=req.telefone,
        status=ClientStatus.ativo,
        origem=ClientOrigem.escritorio,
        responsavel_id=user.id,
        observacoes="Criado por conversão confirmada do Raio-X preliminar; revisar dados.",
    )
    db.add(client)
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "CREATE_AUTO",
        "clients",
        client.id,
        detalhes="Conversão do Raio-X",
    )
    return client


def _copiar_documento(
    documento: RaioXDocumento,
    case: Case,
    client: Client,
    user: User,
) -> tuple[Document, Path]:
    source = Path(settings.UPLOAD_DIR) / documento.filepath
    if not source.exists() or not source.is_file():
        raise ValueError(f"Arquivo físico indisponível para transferência: {documento.nome_original}")
    rel = Path("raio-x-convertidos") / case.id / f"{uuid4()}{source.suffix}"
    target = Path(settings.UPLOAD_DIR) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    model = Document(
        id=str(uuid4()),
        titulo=documento.nome_original[:255],
        descricao="Documento transferido de análise preliminar Raio-X.",
        tipo=documento.tipo_documento or "outro",
        filename=documento.nome_original,
        filepath=str(rel),
        mimetype=documento.mimetype,
        size_bytes=documento.size_bytes,
        confidencialidade=DocConfidencialidade.interno,
        case_id=case.id,
        client_id=client.id,
        uploaded_by=user.id,
    )
    return model, target


def _fase_case(relatorio: dict[str, Any], has_process: bool) -> CaseFase:
    stage = normalizar(((relatorio.get("rito_jornada") or {}).get("etapa_atual")))
    if "administr" in stage:
        return CaseFase.administrativo
    if any(marker in stage for marker in ("recurso", "recursal", "tribunal", "superior", "pos sentenca")):
        return CaseFase.recursal
    if any(marker in stage for marker in ("execucao", "cumprimento", "liquidacao")):
        return CaseFase.execucao
    if has_process:
        return CaseFase.conhecimento
    return CaseFase.pre_processual


def _risco_case(level: str | None) -> str | None:
    return {
        "baixo": "baixo",
        "moderado": "medio",
        "elevado": "alto",
        "critico": "alto",
    }.get(str(level or "").lower())


def _snapshot_payload(
    analise: RaioXAnalise,
    report: dict[str, Any],
    payload: RaioXConverterRequest,
) -> dict[str, Any]:
    fontes = []
    for item in report.get("fontes") or []:
        if isinstance(item, dict):
            fontes.append({
                "documento_id": item.get("documento_id"),
                "arquivo": item.get("arquivo"),
                "hash": item.get("hash"),
                "pagina": item.get("pagina"),
            })
    data = {
        "area": payload.caso.area,
        "fatos": report.get("sintese_executiva"),
        "fatos_provas": report.get("fatos_provas") or [],
        "cronologia": report.get("cronologia") or [],
        "contradicoes": report.get("contradicoes") or [],
        "teses": {
            "principal": None,
            "secundarias": report.get("teses") or [],
        },
        "riscos": report.get("riscos") or [],
        "provas": report.get("provas") or [],
        "pedidos": report.get("pedidos") or [],
        "prazos_projetados": report.get("prazos_potenciais") or [],
        "checklist": {
            "itens": report.get("documentos_pendentes") or [],
            "pronto": not bool(report.get("documentos_pendentes")),
        },
        "fontes": fontes,
        "proximos_passos": report.get("proximos_passos") or [],
        "raio_x_analise_id": analise.id,
        "confianca_global": report.get("confianca_global"),
        "revisao_humana_obrigatoria": True,
    }
    return compactar_payload(
        data,
        descartaveis=("cronologia", "fatos_provas", "provas"),
    )


async def converter_em_caso(
    db: AsyncSession,
    analise: RaioXAnalise,
    payload: RaioXConverterRequest,
    user: User,
) -> dict[str, Any]:
    if _role(user) not in _CONVERSION_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Seu perfil pode analisar documentos, mas não possui autorização para criar casos oficiais.",
        )

    # Idempotência concorrente: o objeto recebido pelo router pode estar stale.
    # O lock pessimista serializa todas as conversões da MESMA análise; após a
    # primeira transação comitar, a segunda relê `convertido_case_id` sob lock e
    # devolve o mesmo caso em vez de criar um segundo caso oficial.
    locked = await db.execute(
        select(RaioXAnalise)
        .options(selectinload(RaioXAnalise.documentos))
        .where(
            RaioXAnalise.id == analise.id,
            RaioXAnalise.deleted_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    analise = locked.scalar_one_or_none()
    if analise is None:
        raise HTTPException(404, "Análise Raio-X não encontrada")
    if analise.convertido_case_id:
        return {"case_id": analise.convertido_case_id, "ja_convertido": True}

    preview = await preview_conversao(db, analise, payload, user=user)
    if preview["casos_possivelmente_duplicados"] and not payload.duplicate_confirmed:
        raise ValueError("Há caso possivelmente duplicado; confira os achados antes de continuar")
    if preview["alertas_conflito"] and not payload.conflict_confirmed:
        raise ValueError("Há alerta de conflito; confirme a revisão antes de continuar")

    ids_disponiveis = {documento.id for documento in analise.documentos}
    ids_solicitados = set(payload.documento_ids)
    ids_invalidos = ids_solicitados - ids_disponiveis
    if ids_invalidos:
        raise ValueError("A seleção contém documento que não pertence a esta análise")
    documents = [documento for documento in analise.documentos if documento.id in ids_solicitados]
    for item in documents:
        source = Path(settings.UPLOAD_DIR) / item.filepath
        if not source.exists() or not source.is_file():
            raise ValueError(f"Arquivo físico indisponível para transferência: {item.nome_original}")

    valid_areas = {area.value for area in CaseArea}
    if payload.caso.area not in valid_areas:
        raise ValueError("Área do caso inválida; confirme manualmente a área antes da conversão")

    client = await _resolver_cliente(db, payload, user)
    report = analise.relatorio or {}
    urgent = bool(report.get("prazo_urgente"))
    priority = "critica" if urgent else payload.caso.prioridade
    has_process = bool(payload.caso.numero_processo)
    case = Case(
        id=str(uuid4()),
        numero_interno=await _proximo_numero_interno(db),
        titulo=payload.caso.titulo,
        area=CaseArea(payload.caso.area),
        status=CaseStatus.aberto,
        fase=_fase_case(report, has_process),
        prioridade=CasePrioridade(priority),
        risco=_risco_case(report.get("risco_nivel")),
        numero_processo=payload.caso.numero_processo,
        tribunal=payload.caso.tribunal,
        comarca=payload.caso.comarca,
        vara=payload.caso.vara,
        parte_contraria=payload.caso.parte_contraria,
        descricao_fatos=payload.caso.descricao_fatos or report.get("sintese_executiva"),
        case_type=payload.caso.case_type,
        has_judicial_process=has_process,
        client_id=client.id,
        advogado_responsavel_id=user.id,
        observacoes=f"Originado do Raio-X preliminar {analise.id}. Relatório preservado na origem.",
        # G1 (mesma guarda de cases.py / entrada_service.py / legal_chat_service.py):
        # caso em triagem nunca nasce sem "o que fazer agora". Esta era a única das
        # 4 portas de criação que deixava `proxima_acao` NULL — Case nascia aberto
        # sem próxima ação, driblando o gate que cases.py::atualizar() exige em toda
        # atualização subsequente.
        proxima_acao="Revisar a análise convertida do Raio-X e definir a próxima providência",
    )
    db.add(case)

    snapshot = CaseIntelligenceSnapshot(
        id=str(uuid4()),
        case_id=case.id,
        versao=1,
        origem="raio_x",
        payload=_snapshot_payload(analise, report, payload),
        resumo=str(report.get("sintese_executiva") or "")[:2000] or None,
        ai_log_ids=[],
        criado_por=user.id,
        congelado=False,
        aprovado_por=None,
        aprovado_em=None,
    )
    db.add(snapshot)

    official_documents: list[str] = []
    copied_paths: list[Path] = []
    try:
        for item in documents:
            document, copied_path = _copiar_documento(item, case, client, user)
            db.add(document)
            official_documents.append(document.id)
            copied_paths.append(copied_path)

        created_deadlines: list[str] = []
        if payload.transferir_prazos:
            for item in report.get("prazos_potenciais", []):
                if not isinstance(item, dict):
                    continue
                raw_date = _data_iso(item.get("termo_final") or item.get("data") or item.get("data_prazo"))
                if not raw_date:
                    continue
                deadline = Deadline(
                    id=str(uuid4()),
                    titulo=str(_valor(item.get("titulo") or item.get("descricao") or "Prazo extraído"))[:255],
                    descricao="Importado do Raio-X; revisão humana obrigatória.",
                    tipo=DeadlineTipo.processual,
                    prioridade=DeadlinePrioridade.alta,
                    status=DeadlineStatus.pendente,
                    data_prazo=date.fromisoformat(raw_date),
                    base_legal=str(_valor(item.get("base_legal")) or "")[:255] or None,
                    case_id=case.id,
                    responsavel_id=user.id,
                    origem="importacao_ia",
                    confirmado=False,
                )
                db.add(deadline)
                created_deadlines.append(deadline.id)

        created_tasks: list[str] = []
        if payload.transferir_tarefas:
            for item in report.get("proximos_passos", []):
                title = str(_valor(item) or "").strip()
                if not title:
                    continue
                task = Task(
                    id=str(uuid4()),
                    titulo=title[:255],
                    descricao="Sugestão transferida do Raio-X; validar escopo.",
                    status=TaskStatus.a_fazer,
                    prioridade="alta" if urgent else "media",
                    case_id=case.id,
                    responsavel_id=user.id,
                    criado_por=user.id,
                )
                db.add(task)
                created_tasks.append(task.id)

        analise.status = "convertido_em_caso"
        analise.convertido_case_id = case.id
        analise.converted_at = datetime.now(timezone.utc)
        analise.alertas_conflito = preview.get("alertas_conflito") or []
        analise.risco_nivel = report.get("risco_nivel")
        analise.prazo_urgente = urgent
        await criar_audit_log(
            db,
            user.id,
            _role(user),
            "CONVERT",
            "raio_x_analises",
            analise.id,
            detalhes=f"Raio-X convertido no caso {case.id} com snapshot {snapshot.id}",
            dados_depois={
                "case_id": case.id,
                "client_id": client.id,
                "snapshot_id": snapshot.id,
                "documentos": official_documents,
                "prazos": created_deadlines,
                "tarefas": created_tasks,
                "conflito_revisado": bool(preview.get("alertas_conflito")),
                "risco_nivel": report.get("risco_nivel"),
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        for path in copied_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return {
        "case_id": case.id,
        "client_id": client.id,
        "snapshot_id": snapshot.id,
        "ja_convertido": False,
        "documentos_transferidos": official_documents,
        "prazos_criados": created_deadlines,
        "tarefas_criadas": created_tasks,
        "risco_nivel": report.get("risco_nivel"),
        "prazo_urgente": urgent,
        "aviso": "Caso criado em triagem. A inteligência do Raio-X foi preservada em snapshot não aprovado; prazos importados permanecem não confirmados.",
    }
