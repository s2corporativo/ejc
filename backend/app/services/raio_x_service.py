"""Regras determinísticas, conversão e trilha humana do Raio-X.

O serviço não inventa conclusão jurídica: informações sem origem suficiente
ficam marcadas para conferência. A IA é usada pelo pipeline documental já
existente; aqui consolidamos a saída, enriquecemos a análise e congelamos a
versão revisada quando ela é convertida em caso oficial.
"""
from __future__ import annotations

import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseArea, CaseFase, CasePrioridade, CaseStatus
from app.models.client import Client, ClientOrigem, ClientStatus, ClientTipo
from app.models.deadline import Deadline, DeadlinePrioridade, DeadlineStatus, DeadlineTipo
from app.models.document import DocConfidencialidade, Document
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.raio_x import RaioXConverterRequest
from app.services.raio_x_enrichment import data_iso, enriquecer_relatorio, lista, normalizar, unicos, valor

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

    faltantes: list[str] = []
    if not identificacao["numero_processo"]:
        faltantes.append("Número do processo não identificado")
    if not partes:
        faltantes.append("Partes não identificadas com segurança")
    if not provas:
        faltantes.append("Provas ainda não classificadas")
    faltantes.extend(str(_valor(item)) for item in pendencias if _valor(item))

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
        "pontos_fortes": [],
        "pontos_fracos": faltantes,
        "proximos_passos": faltantes or ["Revisar o relatório e definir a providência jurídica."],
        "documentos_pendentes": faltantes,
        "confianca_global": "insuficiente_para_automatizacao",
    }
    return enriquecer_relatorio(documentos, base)


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


async def _proximo_numero_interno(db: AsyncSession) -> str:
    ano = date.today().year
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:chave))"), {"chave": f"numero_interno_{ano}"})
    result = await db.execute(
        text(
            r"""
            SELECT numero_interno FROM cases WHERE numero_interno LIKE :pref
            ORDER BY CAST(substring(numero_interno FROM '\d+$') AS INTEGER) DESC LIMIT 1
            """
        ),
        {"pref": f"DPT-{ano}-%"},
    )
    ultimo = result.scalar()
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"DPT-{ano}-{seq:04d}"


async def _detectar_conflitos(
    db: AsyncSession,
    analise: RaioXAnalise,
    payload: RaioXConverterRequest | None = None,
) -> list[dict[str, Any]]:
    """Localiza correspondências que exigem revisão, sem concluir conflito ético."""
    report = analise.relatorio or {}
    potential = normalizar(
        (payload.cliente.nome if payload and payload.cliente.nome else None)
        or analise.potencial_cliente
        or (report.get("identificacao") or {}).get("cliente_potencial")
    )
    names = []
    for item in report.get("partes") or []:
        name = _nome_item(item)
        if len(name) >= 3 and normalizar(name) != potential:
            names.append(name)
    names = [str(item) for item in _unicos(names)][:20]
    if not names:
        return list(analise.alertas_conflito or [])

    conditions_clients = [
        or_(Client.nome.ilike(f"%{name}%"), Client.razao_social.ilike(f"%{name}%"))
        for name in names
    ]
    clients = (
        await db.execute(
            select(Client)
            .where(or_(*conditions_clients), Client.deleted_at.is_(None))
            .limit(30)
        )
    ).scalars().all()

    conditions_cases = [Case.parte_contraria.ilike(f"%{name}%") for name in names]
    cases = (
        await db.execute(
            select(Case)
            .where(or_(*conditions_cases), Case.deleted_at.is_(None))
            .limit(30)
        )
    ).scalars().all()

    alerts: list[dict[str, Any]] = list(analise.alertas_conflito or [])
    for client in clients:
        alerts.append({
            "tipo": "parte_corresponde_a_cliente",
            "nome": client.nome_exibicao,
            "client_id": client.id,
            "mensagem": "Parte do documento possui nome semelhante a cliente atual ou anterior. Revisar conflito sem revelar dados protegidos.",
            "confirmado": False,
        })
    for case in cases:
        alerts.append({
            "tipo": "parte_corresponde_a_parte_contraria",
            "nome": case.parte_contraria,
            "case_id": case.id,
            "mensagem": "Parte do documento possui nome semelhante a parte contrária de caso cadastrado. Revisar conflito e grupo econômico.",
            "confirmado": False,
        })
    return _unicos(alerts)


async def preview_conversao(
    db: AsyncSession,
    analise: RaioXAnalise,
    payload: RaioXConverterRequest | None = None,
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

    casos = []
    if numero:
        rows = (
            await db.execute(
                select(Case).where(Case.numero_processo == numero, Case.deleted_at.is_(None))
            )
        ).scalars().all()
        casos = [
            {"id": case.id, "titulo": case.titulo, "numero_processo": case.numero_processo}
            for case in rows
        ]

    clientes = []
    if nomes:
        conditions = [
            or_(Client.nome.ilike(f"%{name}%"), Client.razao_social.ilike(f"%{name}%"))
            for name in nomes
        ]
        rows = (
            await db.execute(
                select(Client)
                .where(or_(*conditions), Client.deleted_at.is_(None))
                .limit(10)
            )
        ).scalars().all()
        clientes = [
            {"id": client.id, "nome": client.nome_exibicao, "cpf": bool(client.cpf), "cnpj": bool(client.cnpj)}
            for client in rows
        ]

    conflict_alerts = await _detectar_conflitos(db, analise, payload)
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
        client = (
            await db.execute(
                select(Client).where(Client.id == req.client_id, Client.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not client:
            raise ValueError("Cliente selecionado não existe")
        return client

    digits_cpf = re.sub(r"\D", "", req.cpf or "")[:11] or None
    digits_cnpj = re.sub(r"\D", "", req.cnpj or "")[:14] or None
    existing = None
    if digits_cpf:
        existing = (
            await db.execute(
                select(Client).where(Client.cpf == digits_cpf, Client.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    if not existing and digits_cnpj:
        existing = (
            await db.execute(
                select(Client).where(Client.cnpj == digits_cnpj, Client.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    if existing:
        return existing
    if not (req.nome or digits_cpf or digits_cnpj):
        raise ValueError("Informe os dados mínimos do novo cliente")

    from app.services.pii_crypto import encrypt, hash_documento

    tipo = ClientTipo.PJ if digits_cnpj else ClientTipo.PF
    client = Client(
        id=str(uuid4()),
        tipo=tipo,
        nome=req.nome if tipo == ClientTipo.PF else None,
        razao_social=req.nome if tipo == ClientTipo.PJ else None,
        cpf=digits_cpf if tipo == ClientTipo.PF else None,
        cnpj=digits_cnpj if tipo == ClientTipo.PJ else None,
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
    await criar_audit_log(db, user.id, _role(user), "CREATE_AUTO", "clients", client.id, detalhes="Conversão do Raio-X")
    return client


def _copiar_documento(documento: RaioXDocumento, case: Case, client: Client, user: User) -> tuple[Document, Path]:
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

    preview = await preview_conversao(db, analise, payload)
    if preview["casos_possivelmente_duplicados"] and not payload.duplicate_confirmed:
        raise ValueError("Há caso possivelmente duplicado; confirme conscientemente para continuar")
    if preview["alertas_conflito"] and not payload.conflict_confirmed:
        raise ValueError("Há alerta de conflito; confirme a revisão para continuar")
    if analise.convertido_case_id:
        return {"case_id": analise.convertido_case_id, "ja_convertido": True}

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
        status=CaseStatus.triagem,
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
    )
    db.add(case)

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
            detalhes=f"Raio-X convertido no caso {case.id}",
            dados_depois={
                "case_id": case.id,
                "client_id": client.id,
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
        "ja_convertido": False,
        "documentos_transferidos": official_documents,
        "prazos_criados": created_deadlines,
        "tarefas_criadas": created_tasks,
        "risco_nivel": report.get("risco_nivel"),
        "prazo_urgente": urgent,
        "aviso": "Caso criado em triagem. Prazos importados permanecem não confirmados.",
    }
