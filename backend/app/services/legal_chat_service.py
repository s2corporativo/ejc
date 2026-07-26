"""Regras de negócio da Sala Jurídica Conversacional (V1).

Fluxo central: mensagem do advogado → SingleAICoreOrchestrator (sanitização
LGPD, RAG, AILog, HITL — nada é contornado aqui) → persistência da resposta
como LegalChatMessage → nova versão do estado jurídico consolidado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseArea
from app.models.client import Client
from app.models.legal_chat import (
    LegalChatAttachment,
    LegalChatMessage,
    LegalChatSession,
    LegalChatStateVersion,
)
from app.models.user import User
from app.schemas.legal_chat import ConverterRequest, MensagemCreate

# Modo do seletor → task_type do gateway (roteamento econômico: conversa
# livre fica no provider local; elaboração/estratégia sobem de tier).
MODO_TASK_TYPE: dict[str, str] = {
    "conversa_livre": "chat_rapido",
    "organizar_fatos": "analise_juridica",
    "analisar_provas": "analise_juridica",
    "detectar_contradicoes": "analise_juridica",
    "estrategia_da_parte": "estrategia",
    "simular_defesa": "estrategia",
    "julgar_caso": "analise_juridica",
    "pesquisar_direito": "pesquisa_juridica",
    "elaborar_documento": "elaboracao_peca",
    "revisar_documento": "analise_juridica",
}

# Instrução de método por modo — complementa (não substitui) os prompts de
# ramo resolvidos pelo núcleo de IA.
MODO_INSTRUCAO: dict[str, str] = {
    "conversa_livre": "",
    "organizar_fatos": (
        "Organize os fatos em cronologia, distinguindo expressamente: "
        "comprovado, alegado, inferido, controvertido, ausente e superado."
    ),
    "analisar_provas": (
        "Relacione cada fato às provas existentes (documento, trecho, origem) "
        "e aponte a força probatória aparente e o que exige perícia."
    ),
    "detectar_contradicoes": (
        "Compare documentos, valores, datas, nomes, locais e versões; liste "
        "cada divergência com as fontes confrontadas."
    ),
    "estrategia_da_parte": (
        "Construa a melhor tese para o cliente: tese favorável, tese contrária "
        "provável, fragilidades, documentos faltantes e próximos passos."
    ),
    "simular_defesa": (
        "Atue como advogado da parte contrária: ataque os pontos frágeis e "
        "liste as impugnações prováveis, com fundamento."
    ),
    "julgar_caso": (
        "Analise como magistrado: pontos controvertidos, provas necessárias e "
        "provável distribuição do ônus probatório."
    ),
    "pesquisar_direito": (
        "Pesquise legislação e fontes oficiais; cite somente fontes "
        "verificáveis e sinalize expressamente o que ainda exige verificação."
    ),
    "elaborar_documento": (
        "Antes de redigir, confirme polo, objetivo, fase e prazo se não "
        "estiverem evidentes. Não insira dados fictícios: lacunas viram "
        "campos [PREENCHER]."
    ),
    "revisar_documento": (
        "Revise coerência, fatos, pedidos, fundamentação, competência, "
        "legitimidade, valores, dispositivos citados e contradições."
    ),
}

_GESTAO = {"superadmin", "admin", "socio"}
_CONVERSION_ROLES = _GESTAO | {"advogado"}


def _role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


async def obter_sessao(
    db: AsyncSession, session_id: str, user: User
) -> LegalChatSession:
    """Ownership fail-closed: criador, responsável ou gestão. 404 se inexistente."""
    sessao = await db.get(LegalChatSession, session_id)
    if sessao is None or sessao.deleted_at is not None:
        raise HTTPException(404, "Análise não encontrada")
    if _role(user) in _GESTAO:
        return sessao
    if user.id not in {sessao.created_by, sessao.advogado_responsavel_id}:
        raise HTTPException(403, "Sem acesso a esta análise")
    return sessao


def exigir_nao_congelada(sessao: LegalChatSession) -> None:
    if sessao.frozen_at is not None:
        raise HTTPException(
            409, "Análise convertida em caso está congelada para auditoria"
        )


async def ultima_versao_estado(
    db: AsyncSession, session_id: str
) -> LegalChatStateVersion | None:
    res = await db.execute(
        select(LegalChatStateVersion)
        .where(LegalChatStateVersion.session_id == session_id)
        .order_by(LegalChatStateVersion.versao.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def gravar_versao_estado(
    db: AsyncSession,
    sessao: LegalChatSession,
    *,
    estado: dict,
    resumo: str | None,
    origem: str,
    created_by: str | None,
) -> LegalChatStateVersion:
    atual = await ultima_versao_estado(db, sessao.id)
    versao = (atual.versao if atual else 0) + 1
    nova = LegalChatStateVersion(
        id=str(uuid4()),
        session_id=sessao.id,
        versao=versao,
        resumo=resumo,
        estado=estado,
        origem=origem,
        created_by=created_by,
    )
    db.add(nova)
    return nova


def _montar_mensagem_ia(payload: MensagemCreate, sessao: LegalChatSession) -> str:
    """Mensagem efetiva enviada ao núcleo: instrução do modo + workspace + texto."""
    partes: list[str] = []
    instrucao = MODO_INSTRUCAO.get(payload.modo) or ""
    if instrucao:
        partes.append(f"[MÉTODO DO MODO '{payload.modo}'] {instrucao}")
    if payload.incluir_workspace and (sessao.workspace_texto or "").strip():
        partes.append(
            "[ÁREA DE TRABALHO DO ADVOGADO — fatos, anotações e rascunhos]\n"
            + sessao.workspace_texto.strip()
        )
    partes.append(payload.conteudo)
    return "\n\n".join(partes)


async def enviar_mensagem(
    db: AsyncSession,
    sessao: LegalChatSession,
    payload: MensagemCreate,
    user: User,
) -> dict[str, Any]:
    """Persiste a pergunta, roda o núcleo único de IA e persiste a resposta."""
    exigir_nao_congelada(sessao)

    msg_user = LegalChatMessage(
        id=str(uuid4()),
        session_id=sessao.id,
        autor="user",
        user_id=user.id,
        modo=payload.modo,
        conteudo=payload.conteudo,
    )
    db.add(msg_user)
    await db.flush()

    # Import tardio: mantém o service importável em testes sem stack de IA.
    from app.services.ai.core.orchestrator import run_ai_task

    resultado = await run_ai_task(
        db=db,
        user=user,
        task_type=MODO_TASK_TYPE[payload.modo],
        mensagem=_montar_mensagem_ia(payload, sessao),
        case_id=sessao.convertido_case_id,
        params={"module_key": "sala-juridica", "surface": "sala_juridica"},
        usar_rag=payload.usar_rag,
    )

    custo = Decimal(str(resultado.get("custo_estimado_brl") or 0))
    msg_ia = LegalChatMessage(
        id=str(uuid4()),
        session_id=sessao.id,
        autor="ia",
        modo=payload.modo,
        conteudo=resultado.get("conteudo") or "",
        modelo=resultado.get("modelo"),
        agente=resultado.get("agente"),
        skills=list(resultado.get("skills_nativas") or []),
        fontes=list(resultado.get("fontes") or []),
        citacoes=list(resultado.get("citacoes") or []),
        alertas=list(resultado.get("alertas") or []),
        tokens_input=resultado.get("tokens_input"),
        tokens_output=resultado.get("tokens_output"),
        custo_estimado=custo,
        ai_log_id=resultado.get("log_id"),
    )
    db.add(msg_ia)

    # Estado: V1 acumula fontes/alertas automaticamente; a curadoria fina
    # (fatos/teses/riscos) é do advogado via PATCH /estado.
    atual = await ultima_versao_estado(db, sessao.id)
    estado = dict((atual.estado if atual else {}) or {})
    fontes = {(f.get("titulo"), f.get("fonte")): f for f in estado.get("fontes", [])}
    for f in resultado.get("fontes") or []:
        fontes.setdefault((f.get("titulo"), f.get("fonte")), f)
    estado["fontes"] = list(fontes.values())
    versao = await gravar_versao_estado(
        db, sessao,
        estado=estado,
        resumo=None,
        origem="ia",
        created_by=None,
    )
    msg_ia.estado_versao = versao.versao
    sessao.custo_ia_total = (sessao.custo_ia_total or Decimal("0")) + custo
    await db.flush()

    return {
        "mensagem_user": serializar_mensagem(msg_user),
        "mensagem_ia": serializar_mensagem(msg_ia),
        "estado_versao": versao.versao,
        "is_rascunho": resultado.get("is_rascunho", True),
        "aviso_hitl": resultado.get("aviso_hitl"),
        "critica_adversarial": resultado.get("critica_adversarial"),
    }


async def converter_em_caso(
    db: AsyncSession,
    sessao: LegalChatSession,
    payload: ConverterRequest,
    user: User,
) -> dict[str, Any]:
    """Conversão controlada: cliente → conflito confirmado → caso → congelamento."""
    if _role(user) not in _CONVERSION_ROLES:
        raise HTTPException(
            403, "Seu perfil não possui autorização para criar casos oficiais"
        )
    if sessao.convertido_case_id:
        return {"case_id": sessao.convertido_case_id, "ja_convertido": True}
    if payload.area not in {a.value for a in CaseArea}:
        raise HTTPException(422, "Área do caso inválida")
    if bool(payload.client_id) == bool(payload.novo_cliente_nome):
        raise HTTPException(
            422, "Informe client_id OU novo_cliente_nome (exatamente um)"
        )

    if payload.client_id:
        client = await db.get(Client, payload.client_id)
        if client is None or client.deleted_at is not None:
            raise HTTPException(404, "Cliente não encontrado")
    else:
        client = Client(
            id=str(uuid4()),
            nome=payload.novo_cliente_nome,
            responsavel_id=payload.advogado_responsavel_id,
        )
        db.add(client)
        await db.flush()

    numero = await _proximo_numero_interno(db)
    case = Case(
        id=str(uuid4()),
        numero_interno=numero,
        titulo=payload.titulo_caso,
        area=CaseArea(payload.area),
        descricao_fatos=payload.descricao,
        client_id=client.id,
        advogado_responsavel_id=payload.advogado_responsavel_id,
    )
    db.add(case)
    await db.flush()

    agora = datetime.now(timezone.utc)
    sessao.client_id = client.id
    sessao.convertido_case_id = case.id
    sessao.converted_at = agora
    sessao.frozen_at = agora  # congelada para auditoria — imutável daqui em diante
    sessao.status = "convertida_em_caso"
    await db.flush()
    return {"case_id": case.id, "client_id": client.id, "ja_convertido": False}


async def _proximo_numero_interno(db: AsyncSession) -> str:
    ano = datetime.now(timezone.utc).year
    res = await db.execute(
        select(func.count()).select_from(Case).where(
            Case.numero_interno.like(f"{ano}-%")
        )
    )
    seq = (res.scalar() or 0) + 1
    return f"{ano}-{seq:04d}"


def serializar_mensagem(m: LegalChatMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "autor": m.autor,
        "modo": m.modo,
        "conteudo": m.conteudo,
        "modelo": m.modelo,
        "agente": m.agente,
        "skills": m.skills or [],
        "fontes": m.fontes or [],
        "citacoes": m.citacoes or [],
        "alertas": m.alertas or [],
        "tokens_input": m.tokens_input,
        "tokens_output": m.tokens_output,
        "custo_estimado": float(m.custo_estimado) if m.custo_estimado is not None else None,
        "ai_log_id": m.ai_log_id,
        "estado_versao": m.estado_versao,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def serializar_anexo(a: LegalChatAttachment) -> dict[str, Any]:
    return {
        "id": a.id,
        "nome_original": a.nome_original,
        "mimetype": a.mimetype,
        "size_bytes": a.size_bytes,
        "sha256": a.sha256,
        "tipo_documento": a.tipo_documento,
        "ocr_utilizado": a.ocr_utilizado,
        "resultado_analise": a.resultado_analise or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def serializar_sessao(
    s: LegalChatSession,
    *,
    incluir_relacionados: bool = False,
    estado: LegalChatStateVersion | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": s.id,
        "titulo": s.titulo,
        "status": s.status,
        "favorita": s.favorita,
        "cliente_potencial": s.cliente_potencial,
        "area_sugerida": s.area_sugerida,
        "advogado_responsavel_id": s.advogado_responsavel_id,
        "workspace_versao": s.workspace_versao,
        "client_id": s.client_id,
        "convertido_case_id": s.convertido_case_id,
        "frozen": s.frozen_at is not None,
        "custo_ia_total": float(s.custo_ia_total or 0),
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if incluir_relacionados:
        base["workspace_texto"] = s.workspace_texto
        base["mensagens"] = [serializar_mensagem(m) for m in s.mensagens]
        base["anexos"] = [serializar_anexo(a) for a in s.anexos]
        base["estado"] = (
            {
                "versao": estado.versao,
                "resumo": estado.resumo,
                "estado": estado.estado,
                "origem": estado.origem,
                "created_at": estado.created_at.isoformat() if estado.created_at else None,
            }
            if estado
            else None
        )
    return base
