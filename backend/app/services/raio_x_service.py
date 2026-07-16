"""Regras determinísticas, conversão e trilha humana do Raio-X.

O serviço não inventa conclusão jurídica: informações sem origem suficiente
ficam marcadas para conferência. A IA é usada pelo pipeline documental já
existente; aqui consolidamos a saída e congelamos a versão revisada.
"""
from __future__ import annotations

import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

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

settings = get_settings()


def _valor(campo: Any) -> Any:
    if isinstance(campo, dict):
        return campo.get("valor", campo.get("value", campo.get("texto", campo)))
    return campo


def _lista(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _unicos(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = str(value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _data_iso(value: Any) -> str | None:
    value = _valor(value)
    if not value:
        return None
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def consolidar_relatorio(documentos: list[RaioXDocumento]) -> dict[str, Any]:
    resultados = [d.resultado_analise or {} for d in documentos]
    intakes = [r.get("intake_result") or r for r in resultados]
    fontes = [
        {
            "documento_id": d.id,
            "arquivo": d.nome_original,
            "tipo": d.tipo_documento,
            "hash": d.sha256,
        }
        for d in documentos
    ]

    clientes = [_valor(i.get("cliente")) for i in intakes if i.get("cliente")]
    casos = [_valor(i.get("caso")) for i in intakes if i.get("caso")]
    partes = _unicos(item for i in intakes for item in _lista(i.get("partes")))
    pedidos = _unicos(item for i in intakes for item in _lista(i.get("pedidos")))
    provas = _unicos(item for i in intakes for item in _lista(i.get("provas")))
    riscos = _unicos(item for i in intakes for item in _lista(i.get("riscos")))
    teses = _unicos(item for i in intakes for item in _lista(i.get("teses")))
    pendencias = _unicos(item for i in intakes for item in _lista(i.get("pendencias")))
    prazos = _unicos(item for i in intakes for item in _lista(i.get("prazos")))
    resumos = _unicos(str(_valor(i.get("resumo_fatos")) or "").strip() for i in intakes)

    identificacao: dict[str, Any] = {
        "cliente_potencial": clientes[0] if clientes else None,
        "caso": casos[0] if casos else None,
        "numero_processo": None,
        "area": None,
        "fase": None,
        "tribunal": None,
        "confianca": "revisao_humana_obrigatoria",
    }
    for intake in intakes:
        case_data = _valor(intake.get("caso"))
        if isinstance(case_data, dict):
            for key in ("numero_processo", "area", "fase", "tribunal"):
                identificacao[key] = identificacao[key] or _valor(case_data.get(key))
        for key in ("numero_processo", "area", "fase", "tribunal"):
            identificacao[key] = identificacao[key] or _valor(intake.get(key))

    cronologia: list[dict[str, Any]] = []
    for prazo in prazos:
        if isinstance(prazo, dict):
            when = _data_iso(prazo.get("termo_final") or prazo.get("data") or prazo.get("data_prazo"))
            cronologia.append({
                "data": when,
                "evento": _valor(prazo.get("titulo") or prazo.get("descricao") or "Prazo potencial"),
                "origem": "extração documental",
                "confirmado": False,
            })
    cronologia.sort(key=lambda x: x.get("data") or "9999-12-31")

    matriz = []
    for resumo in resumos:
        matriz.append({
            "fato": resumo,
            "provas_relacionadas": [],
            "estado": "correlacao_pendente",
            "observacao": "A correlação fato/prova exige conferência do advogado.",
        })

    faltantes = []
    if not identificacao["numero_processo"]:
        faltantes.append("Número do processo não identificado")
    if not partes:
        faltantes.append("Partes não identificadas com segurança")
    if not provas:
        faltantes.append("Provas ainda não classificadas")
    faltantes.extend(str(_valor(p)) for p in pendencias)

    return {
        "versao": 1,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "aviso": "Análise preliminar. Nenhum prazo, conclusão ou providência é oficial antes da confirmação humana.",
        "fontes": fontes,
        "identificacao": identificacao,
        "sintese_executiva": "\n\n".join(resumos) if resumos else "Síntese pendente de conferência documental.",
        "partes": partes,
        "cronologia": cronologia,
        "fatos_provas": matriz,
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


def serializar_analise(analise: RaioXAnalise, incluir_documentos: bool = True) -> dict[str, Any]:
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
        "risco_nivel": analise.risco_nivel,
        "prazo_urgente": analise.prazo_urgente,
        "relatorio": analise.relatorio or {},
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
                "id": d.id, "nome_original": d.nome_original, "mimetype": d.mimetype,
                "size_bytes": d.size_bytes, "sha256": d.sha256,
                "tipo_documento": d.tipo_documento, "paginas": d.paginas,
                "ocr_utilizado": d.ocr_utilizado,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in analise.documentos
        ]
    return result


async def _proximo_numero_interno(db: AsyncSession) -> str:
    ano = date.today().year
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:chave))"), {"chave": f"numero_interno_{ano}"})
    result = await db.execute(text(r"""
        SELECT numero_interno FROM cases WHERE numero_interno LIKE :pref
        ORDER BY CAST(substring(numero_interno FROM '\d+$') AS INTEGER) DESC LIMIT 1
    """), {"pref": f"DPT-{ano}-%"})
    ultimo = result.scalar()
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"DPT-{ano}-{seq:04d}"


async def preview_conversao(db: AsyncSession, analise: RaioXAnalise, payload: RaioXConverterRequest | None = None) -> dict[str, Any]:
    relatorio = analise.relatorio or {}
    identificacao = relatorio.get("identificacao") or {}
    numero = (payload.caso.numero_processo if payload else None) or analise.numero_processo or identificacao.get("numero_processo")
    nomes = [analise.potencial_cliente]
    if payload and payload.cliente.nome:
        nomes.append(payload.cliente.nome)
    nomes = [n.strip() for n in nomes if isinstance(n, str) and n.strip()]

    casos = []
    if numero:
        rows = (await db.execute(select(Case).where(Case.numero_processo == numero, Case.deleted_at.is_(None)))).scalars().all()
        casos = [{"id": c.id, "titulo": c.titulo, "numero_processo": c.numero_processo} for c in rows]
    clientes = []
    if nomes:
        conditions = [or_(Client.nome.ilike(f"%{n}%"), Client.razao_social.ilike(f"%{n}%")) for n in nomes]
        rows = (await db.execute(select(Client).where(or_(*conditions), Client.deleted_at.is_(None)).limit(10))).scalars().all()
        clientes = [{"id": c.id, "nome": c.nome_exibicao, "cpf": bool(c.cpf), "cnpj": bool(c.cnpj)} for c in rows]

    return {
        "analise_id": analise.id,
        "casos_possivelmente_duplicados": casos,
        "clientes_possivelmente_duplicados": clientes,
        "alertas_conflito": analise.alertas_conflito or [],
        "documentos_disponiveis": [{"id": d.id, "nome": d.nome_original, "tipo": d.tipo_documento} for d in analise.documentos],
        "prazos_potenciais": relatorio.get("prazos_potenciais", []),
        "tarefas_sugeridas": relatorio.get("proximos_passos", []),
        "bloqueia": bool(casos or analise.alertas_conflito),
    }


async def _resolver_cliente(db: AsyncSession, payload: RaioXConverterRequest, user: User) -> Client:
    req = payload.cliente
    if req.modo == "existente":
        client = (await db.execute(select(Client).where(Client.id == req.client_id, Client.deleted_at.is_(None)))).scalar_one_or_none()
        if not client:
            raise ValueError("Cliente selecionado não existe")
        return client

    digits_cpf = re.sub(r"\D", "", req.cpf or "")[:11] or None
    digits_cnpj = re.sub(r"\D", "", req.cnpj or "")[:14] or None
    existing = None
    if digits_cpf:
        existing = (await db.execute(select(Client).where(Client.cpf == digits_cpf, Client.deleted_at.is_(None)))).scalar_one_or_none()
    if not existing and digits_cnpj:
        existing = (await db.execute(select(Client).where(Client.cnpj == digits_cnpj, Client.deleted_at.is_(None)))).scalar_one_or_none()
    if existing:
        return existing
    if not (req.nome or digits_cpf or digits_cnpj):
        raise ValueError("Informe os dados mínimos do novo cliente")

    from app.services.pii_crypto import encrypt, hash_documento
    tipo = ClientTipo.PJ if digits_cnpj else ClientTipo.PF
    client = Client(
        id=str(uuid4()), tipo=tipo,
        nome=req.nome if tipo == ClientTipo.PF else None,
        razao_social=req.nome if tipo == ClientTipo.PJ else None,
        cpf=digits_cpf if tipo == ClientTipo.PF else None,
        cnpj=digits_cnpj if tipo == ClientTipo.PJ else None,
        cpf_enc=encrypt(digits_cpf) if digits_cpf else None,
        cnpj_enc=encrypt(digits_cnpj) if digits_cnpj else None,
        cpf_hash=hash_documento(digits_cpf) if digits_cpf else None,
        cnpj_hash=hash_documento(digits_cnpj) if digits_cnpj else None,
        email=req.email, telefone=req.telefone,
        status=ClientStatus.ativo, origem=ClientOrigem.escritorio,
        responsavel_id=user.id,
        observacoes="Criado por conversão confirmada do Raio-X preliminar; revisar dados.",
    )
    db.add(client)
    await criar_audit_log(db, user.id, user.role.value, "CREATE_AUTO", "clients", client.id, detalhes="Conversão do Raio-X")
    return client


def _copiar_documento(documento: RaioXDocumento, case: Case, client: Client, user: User) -> Document:
    source = Path(settings.UPLOAD_DIR) / documento.filepath
    rel = Path("raio-x-convertidos") / case.id / f"{uuid4()}{source.suffix}"
    target = Path(settings.UPLOAD_DIR) / rel
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        stored_path = str(rel)
    else:
        stored_path = documento.filepath
    return Document(
        id=str(uuid4()), titulo=documento.nome_original[:255],
        descricao="Documento transferido de análise preliminar Raio-X.",
        tipo=documento.tipo_documento or "outro", filename=documento.nome_original,
        filepath=stored_path, mimetype=documento.mimetype, size_bytes=documento.size_bytes,
        confidencialidade=DocConfidencialidade.interno,
        case_id=case.id, client_id=client.id, uploaded_by=user.id,
    )


async def converter_em_caso(db: AsyncSession, analise: RaioXAnalise, payload: RaioXConverterRequest, user: User) -> dict[str, Any]:
    preview = await preview_conversao(db, analise, payload)
    if preview["casos_possivelmente_duplicados"] and not payload.duplicate_confirmed:
        raise ValueError("Há caso possivelmente duplicado; confirme conscientemente para continuar")
    if preview["alertas_conflito"] and not payload.conflict_confirmed:
        raise ValueError("Há alerta de conflito; confirme a revisão para continuar")
    if analise.convertido_case_id:
        return {"case_id": analise.convertido_case_id, "ja_convertido": True}

    client = await _resolver_cliente(db, payload, user)
    area = payload.caso.area if payload.caso.area in {a.value for a in CaseArea} else CaseArea.civil.value
    case = Case(
        id=str(uuid4()), numero_interno=await _proximo_numero_interno(db),
        titulo=payload.caso.titulo, area=CaseArea(area), status=CaseStatus.triagem,
        fase=CaseFase.pre_processual, prioridade=CasePrioridade(payload.caso.prioridade),
        numero_processo=payload.caso.numero_processo, tribunal=payload.caso.tribunal,
        comarca=payload.caso.comarca, vara=payload.caso.vara,
        parte_contraria=payload.caso.parte_contraria,
        descricao_fatos=payload.caso.descricao_fatos or (analise.relatorio or {}).get("sintese_executiva"),
        case_type=payload.caso.case_type, has_judicial_process=bool(payload.caso.numero_processo),
        client_id=client.id, advogado_responsavel_id=user.id,
        observacoes=f"Originado do Raio-X preliminar {analise.id}. Relatório preservado na origem.",
    )
    db.add(case)

    selected = set(payload.documento_ids)
    docs = [d for d in analise.documentos if not selected or d.id in selected]
    official_documents = []
    for item in docs:
        doc = _copiar_documento(item, case, client, user)
        db.add(doc)
        official_documents.append(doc.id)

    prazos_criados = []
    if payload.transferir_prazos:
        for item in (analise.relatorio or {}).get("prazos_potenciais", []):
            if not isinstance(item, dict):
                continue
            raw_date = _data_iso(item.get("termo_final") or item.get("data") or item.get("data_prazo"))
            if not raw_date:
                continue
            deadline = Deadline(
                id=str(uuid4()), titulo=str(_valor(item.get("titulo") or item.get("descricao") or "Prazo extraído"))[:255],
                descricao="Importado do Raio-X; revisão humana obrigatória.",
                tipo=DeadlineTipo.processual, prioridade=DeadlinePrioridade.alta,
                status=DeadlineStatus.pendente, data_prazo=date.fromisoformat(raw_date),
                base_legal=str(_valor(item.get("base_legal")) or "")[:255] or None,
                case_id=case.id, responsavel_id=user.id,
                origem="importacao_ia", confirmado=False,
            )
            db.add(deadline)
            prazos_criados.append(deadline.id)

    tarefas_criadas = []
    if payload.transferir_tarefas:
        for item in (analise.relatorio or {}).get("proximos_passos", []):
            title = str(_valor(item) or "").strip()
            if not title:
                continue
            task = Task(
                id=str(uuid4()), titulo=title[:255], descricao="Sugestão transferida do Raio-X; validar escopo.",
                status=TaskStatus.a_fazer, prioridade="media", case_id=case.id,
                responsavel_id=user.id, criado_por=user.id,
            )
            db.add(task)
            tarefas_criadas.append(task.id)

    analise.status = "convertido_em_caso"
    analise.convertido_case_id = case.id
    analise.converted_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, user.id, user.role.value, "CONVERT", "raio_x_analises", analise.id,
        detalhes=f"Raio-X convertido no caso {case.id}",
        dados_depois={"case_id": case.id, "client_id": client.id, "documentos": official_documents,
                       "prazos": prazos_criados, "tarefas": tarefas_criadas},
    )
    await db.commit()
    return {
        "case_id": case.id, "client_id": client.id, "ja_convertido": False,
        "documentos_transferidos": official_documents,
        "prazos_criados": prazos_criados, "tarefas_criadas": tarefas_criadas,
        "aviso": "Caso criado em triagem. Prazos importados permanecem não confirmados.",
    }
