from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.services.ai.pseudonymizer import (
    pseudonimizar,
    validar_sem_pii_pseudonimizado,
)
from app.services.manus_client import ManusAPIError, ManusClient, ManusDisabledError


_SIGILO_LOCAL_TEXTO = re.compile(
    r"\b(?:"
    r"estupro|pedofil\w*|abuso\s+sexual|viol[eê]ncia\s+sexual|"
    r"ass[eé]dio\s+sexual|importuna[cç][aã]o\s+sexual|ato\s+libidinoso|"
    r"crian[cç]a|adolescente|inf[aâ]ncia|juvenil|"
    r"menor(?:es)?\s+(?:de\s+idade|imp[uú]bere)"
    r")\b",
    re.IGNORECASE,
)


MANUS_DEEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resumo_executivo": {"type": "string"},
        "questoes_juridicas": {"type": "array", "items": {"type": "string"}},
        "teses_possiveis": {"type": "array", "items": {"type": "string"}},
        "argumentos_contrarios": {"type": "array", "items": {"type": "string"}},
        "provas_necessarias": {"type": "array", "items": {"type": "string"}},
        "riscos": {"type": "array", "items": {"type": "string"}},
        "pontos_de_atencao": {"type": "array", "items": {"type": "string"}},
        "informacoes_faltantes": {"type": "array", "items": {"type": "string"}},
        "proximos_passos": {"type": "array", "items": {"type": "string"}},
        "fontes_mencionadas": {"type": "array", "items": {"type": "string"}},
        "revisao_humana_obrigatoria": {"type": "boolean"},
    },
    "required": [
        "resumo_executivo",
        "questoes_juridicas",
        "teses_possiveis",
        "argumentos_contrarios",
        "provas_necessarias",
        "riscos",
        "pontos_de_atencao",
        "informacoes_faltantes",
        "proximos_passos",
        "fontes_mencionadas",
        "revisao_humana_obrigatoria",
    ],
    "additionalProperties": False,
}


def _settings_guard() -> None:
    settings = get_settings()
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    if not settings.MANUS_ENABLED:
        raise HTTPException(503, "Manus — Raciocínio Profundo está desativado")
    if settings.MANUS_AUTO_ROUTING_ENABLED:
        raise HTTPException(
            503,
            "Configuração inválida: Manus não pode participar do roteamento automático",
        )
    if not settings.AI_EXTERNAL_PROVIDERS_ALLOWED:
        raise HTTPException(422, "Provedores externos de IA estão bloqueados")
    if not settings.MANUS_API_KEY:
        raise HTTPException(503, "Credencial Manus não configurada no runtime")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode())


def _handle(task_id: str, user_id: str) -> str:
    settings = get_settings()
    created = int(time.time())
    # O identificador do usuário NÃO viaja na URL. Ele participa apenas da
    # assinatura HMAC, vinculando o handle ao usuário autenticado.
    payload = f"{task_id}|{created}".encode()
    signed = str(user_id).encode() + b"|" + payload
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        signed,
        hashlib.sha256,
    ).digest()
    # Payload e HMAC são codificados SEPARADAMENTE: assinatura é binária e pode
    # conter qualquer byte, inclusive o separador em claro.
    return f"{_b64url(payload)}.{_b64url(signature)}"


def _task_from_handle(handle: str, user_id: str) -> str:
    settings = get_settings()
    try:
        payload_part, signature_part = handle.split(".", 1)
        payload = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
        signed = str(user_id).encode() + b"|" + payload
        expected = hmac.new(
            settings.SECRET_KEY.encode(),
            signed,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("assinatura")
        task_id, created_raw = payload.decode().rsplit("|", 1)
        created = int(created_raw)
        now = int(time.time())
        if created > now + 60 or now - created > 86400:
            raise ValueError("expirado")
        if not task_id or len(task_id) > 128:
            raise ValueError("task")
        return task_id
    except Exception as exc:
        raise HTTPException(404, "Tarefa Manus não encontrada") from exc


def _prompt(*, texto_pseudo: str, area: str | None) -> str:
    return (
        "Você atua como analista jurídico auxiliar de um escritório brasileiro. "
        "Faça raciocínio profundo e crítico, mas trate toda conclusão como RASCUNHO. "
        "Não invente fatos, leis, precedentes, números processuais, endereços ou fontes. "
        "Diferencie fato informado, inferência, hipótese e lacuna. "
        "Aponte teses favoráveis e contrárias, provas necessárias, riscos, pontos que "
        "podem mudar a análise e próximos passos. Fontes mencionadas precisam ser "
        "conferidas pelo advogado antes de qualquer uso. Não execute ações externas.\n\n"
        f"ÁREA INFORMADA: {area or 'não informada'}\n\n"
        "CONTEÚDO PSEUDONIMIZADO:\n"
        f"{texto_pseudo}\n\n"
        "Retorne a saída estruturada solicitada. "
        "Marque revisao_humana_obrigatoria=true."
    )


async def iniciar_raciocinio(
    db: AsyncSession,
    *,
    user: User,
    texto: str,
    area: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    _settings_guard()
    settings = get_settings()

    if case_id:
        caso = await verificar_acesso_caso(db, user, case_id)
        if getattr(caso, "sigilo_reforcado", False):
            raise HTTPException(
                422,
                "Caso com sigilo reforçado exige IA local e não pode usar Manus",
            )

    # Sem case_id não existe flag de sigilo do caso. Mantemos fail-closed para
    # as duas categorias que a política do EJC exige LOCAL_COMPLETO:
    # crimes sexuais e menores/infância e juventude.
    from app.services.ai.sanitization_policy import rotulo_de_sigilo_reforcado

    if rotulo_de_sigilo_reforcado(area) or _SIGILO_LOCAL_TEXTO.search(texto):
        raise HTTPException(
            422,
            "Conteúdo de sigilo reforçado exige IA local e não pode usar Manus",
        )

    texto_pseudo, _mapa_descartado = pseudonimizar(texto)
    residual = validar_sem_pii_pseudonimizado(texto_pseudo)
    if residual:
        raise HTTPException(
            422,
            "O conteúdo ainda contém dado pessoal não apto para provedor externo",
        )

    prompt = _prompt(texto_pseudo=texto_pseudo, area=area)
    if len(prompt) > settings.MANUS_MAX_INPUT_CHARS:
        raise HTTPException(
            422,
            "Conteúdo excede o limite do Raciocínio Profundo",
        )

    try:
        data = await ManusClient().create_task(
            content=prompt,
            structured_output_schema=MANUS_DEEP_SCHEMA,
            title="EJC — Raciocínio Profundo (rascunho)",
            agent_profile=settings.MANUS_AGENT_PROFILE,
        )
    except ManusDisabledError as exc:
        raise HTTPException(503, "Credencial Manus não configurada no runtime") from exc
    except ManusAPIError as exc:
        raise HTTPException(502, str(exc)) from exc

    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        raise HTTPException(502, "Manus não retornou task_id")

    return {
        "status": "running",
        "handle": _handle(task_id, str(user.id)),
        "task_url": data.get("task_url"),
        "provider": "manus",
        "modelo": f"agent-profile:{settings.MANUS_AGENT_PROFILE}",
        "conteudo": "",
        "fontes": [],
        "alertas": [
            "Conteúdo enviado ao Manus foi pseudonimizado; o resultado exige revisão humana."
        ],
        "aviso_hitl": "Raciocínio externo em andamento — revisão humana obrigatória.",
        "requer_revisao": True,
    }


def _formatar_resultado(value: dict[str, Any]) -> str:
    secoes = [
        ("Resumo executivo", value.get("resumo_executivo")),
        ("Questões jurídicas", value.get("questoes_juridicas")),
        ("Teses possíveis", value.get("teses_possiveis")),
        ("Argumentos contrários", value.get("argumentos_contrarios")),
        ("Provas necessárias", value.get("provas_necessarias")),
        ("Riscos", value.get("riscos")),
        ("Pontos de atenção", value.get("pontos_de_atencao")),
        ("Informações faltantes", value.get("informacoes_faltantes")),
        ("Próximos passos", value.get("proximos_passos")),
    ]
    blocos: list[str] = []
    for titulo, valor in secoes:
        if isinstance(valor, str) and valor.strip():
            blocos.append(f"## {titulo}\n{valor.strip()}")
        elif isinstance(valor, list) and valor:
            itens = "\n".join(
                f"- {str(item).strip()}"
                for item in valor
                if str(item).strip()
            )
            if itens:
                blocos.append(f"## {titulo}\n{itens}")
    return "\n\n".join(blocos)


async def consultar_raciocinio(*, user: User, handle: str) -> dict[str, Any]:
    _settings_guard()
    settings = get_settings()
    task_id = _task_from_handle(handle, str(user.id))

    try:
        data = await ManusClient().list_messages(task_id)
    except ManusDisabledError as exc:
        raise HTTPException(503, "Credencial Manus não configurada no runtime") from exc
    except ManusAPIError as exc:
        raise HTTPException(502, str(exc)) from exc

    messages = data.get("messages") if isinstance(data.get("messages"), list) else []
    status = "running"
    waiting_description: str | None = None
    error_message: str | None = None
    structured: dict[str, Any] | None = None

    for event in messages:
        if not isinstance(event, dict):
            continue
        typ = event.get("type")
        if typ == "structured_output_result" and structured is None:
            result = event.get("structured_output_result") or {}
            if isinstance(result, dict) and result.get("success") is True:
                value = result.get("value")
                if isinstance(value, dict):
                    structured = value
        elif typ == "status_update" and status == "running":
            upd = event.get("status_update") or {}
            if isinstance(upd, dict):
                agent_status = upd.get("agent_status")
                if agent_status in {"running", "stopped", "waiting", "error"}:
                    status = "completed" if agent_status == "stopped" else agent_status
                detail = upd.get("status_detail") or {}
                if isinstance(detail, dict):
                    waiting_description = detail.get("waiting_description")
        elif typ == "error_message" and error_message is None:
            err = event.get("error_message") or {}
            if isinstance(err, dict):
                error_message = str(err.get("content") or "Falha na tarefa Manus")[:500]

    if structured is not None:
        status = "completed"
    if error_message:
        status = "error"

    fontes_raw = (
        structured.get("fontes_mencionadas", [])
        if isinstance(structured, dict)
        else []
    )
    fontes = [
        {"titulo": str(item)[:500], "categoria": "manus_nao_verificada"}
        for item in fontes_raw
        if str(item).strip()
    ]

    alertas = [
        "Resultado Manus é rascunho. Confira fatos, fundamentos, jurisprudência e fontes antes de usar."
    ]
    if status == "waiting":
        alertas.append(
            "A tarefa pediu interação adicional. O EJC não confirma ações externas automaticamente."
        )
    if waiting_description:
        alertas.append(str(waiting_description)[:500])
    if error_message:
        alertas.append(error_message)

    return {
        "status": status,
        "handle": handle,
        "provider": "manus",
        "modelo": f"agent-profile:{settings.MANUS_AGENT_PROFILE}",
        "conteudo": _formatar_resultado(structured or {}),
        "resultado_estruturado": structured,
        "fontes": fontes,
        "alertas": alertas,
        "aviso_hitl": "Rascunho sujeito à revisão humana obrigatória.",
        "requer_revisao": True,
    }
