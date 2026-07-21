"""Análise de Caso IA — chat conversacional multi-turno (advogado sênior).

O usuário abre uma sessão (opcionalmente atada a um caso), anexa documento
(OCR) ou cola texto, e conversa com a IA que age como advogado sênior
brasileiro. Análise conversacional PURA (sem ações agênticas internas), com
histórico persistido.

Regras de segurança (CLAUDE.md — não negociar):
  • TODA chamada de IA passa pelo `ai_gateway.chat` (nunca provider direto). A
    barreira final de PII para provedor externo já vive DENTRO do gateway.
  • `ai_guard.sanitizar_ou_abortar` na ENTRADA (barreira adicional) e
    `ai_guard.registrar_ai_log` OBRIGATÓRIO por resposta (erro propaga).
  • `citation_gate.validar_citacoes` sobre a resposta, anexado ao SSE. Cada
    resposta assistant nasce rascunho (is_rascunho=True) — HITL preservado.
  • Rota protegida: usuário autenticado + allowlist jurídico (financeiro,
    secretaria e cliente_externo barrados; espelha ROLES.juridico do frontend).
    Sessão com case_id → `verificar_acesso_caso`, reexecutado também na LEITURA
    da thread (não só nas escritas).
  • `rate_limit` no endpoint de mensagem (custo de IA).
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
from datetime import datetime, timezone
from uuid import uuid4

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.ai_log import AITipoUso
from app.models.analise_caso_ia import AnaliseCasoMensagem, AnaliseCasoSessao
from app.models.user import User
from app.services import ai_gateway, ai_guard, case_context, citation_gate, ocr_service

logger = logging.getLogger("ejc.analise_caso_ia")
settings = get_settings()

router = APIRouter(prefix="/analise-caso-ia", tags=["Análise de Caso IA"])

# ── Limites defensivos ────────────────────────────────────────────────────────
_MAX_CONTEXTO_ANEXO = 40_000        # cap do OCR / texto colado por mensagem
_MAX_PROMPT_BUDGET = 60_000         # teto de chars (dossiê + histórico) enviado à IA
_MIN_HIST_BUDGET = 8_000            # piso do orçamento do histórico após o dossiê
_MAX_CONTEUDO = 20_000              # teto do texto digitado pelo usuário
_MAX_HIST_TURNOS = 300             # LIMIT defensivo de turnos lidos do histórico
_NIVEIS_VALIDOS = {"padrao", "alto", "maximo"}
_TITULO_PADRAO = "Nova análise"
_EXT_OCR = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}
# MIME por extensão para o OCR ramificar corretamente (evita depender de libmagic).
_MIME_POR_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}

_PERSONA = (
    "Você é um advogado sênior brasileiro do escritório, com décadas de banca. "
    "Analise o caso com rigor de detalhe: separe FATO de INFERÊNCIA e de LACUNA, "
    "aponte teses e contra-teses, riscos, cronologia, provas e próximos passos. "
    "Faça o que for pedido (análise, resumo, teses, minuta, perguntas). "
    "Fundamente em base normativa quando citar; NUNCA invente jurisprudência, "
    "dispositivo ou número de processo — na dúvida, escreva 'verificar fonte'. "
    "Não prometa resultado. A resposta é um rascunho para revisão do advogado."
)


# ── Schemas ───────────────────────────────────────────────────────────────────
class SessaoCriar(BaseModel):
    case_id: str | None = Field(default=None, max_length=36)
    titulo: str | None = Field(default=None, max_length=200)
    nivel: str | None = Field(default=None)
    area: str | None = Field(default=None, max_length=80)


class SessaoPatch(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)
    arquivada: bool | None = None


class MensagemEnviar(BaseModel):
    conteudo: str = Field(min_length=1, max_length=_MAX_CONTEUDO)
    texto_colado: str | None = Field(default=None, max_length=200_000)


class SessaoOut(BaseModel):
    id: str
    case_id: str | None
    titulo: str
    nivel: str
    area: str | None
    arquivada: bool
    created_at: datetime | None
    updated_at: datetime | None


class SessaoResumo(SessaoOut):
    total_mensagens: int
    ultima_mensagem_preview: str | None
    ultima_atividade: datetime | None


class MensagemOut(BaseModel):
    id: str
    sessao_id: str
    papel: str
    conteudo: str
    anexo_nome: str | None
    ai_log_id: str | None
    is_rascunho: bool
    created_at: datetime | None


class SessaoDetalhe(SessaoOut):
    mensagens: list[MensagemOut]


# ── Gate de acesso (allowlist jurídico; espelha ROLES.juridico do frontend) ───
# Conjunto EXATO de papéis autorizados a usar a Análise de Caso IA — idêntico ao
# allowlist da rota no frontend (moduleRegistry / canRoleAccessPath). Exclui
# financeiro, secretaria e cliente_externo, que não fazem análise jurídica.
_ROLES_JURIDICO = frozenset({
    "superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario",
})


def _role_str(cu: User) -> str:
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


async def usuario_juridico(cu: User = Depends(get_current_user)) -> User:
    """Defesa em profundidade: além do AuthMiddleware, restringe o endpoint ao
    allowlist jurídico (mesmo conjunto da rota no frontend). Barra financeiro,
    secretaria e cliente_externo com 403."""
    if _role_str(cu) not in _ROLES_JURIDICO:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu


# ── Helpers ───────────────────────────────────────────────────────────────────
def _to_sessao_out(s: AnaliseCasoSessao) -> SessaoOut:
    return SessaoOut(
        id=s.id, case_id=s.case_id, titulo=s.titulo, nivel=s.nivel,
        area=s.area, arquivada=bool(s.arquivada),
        created_at=s.created_at, updated_at=s.updated_at,
    )


def _to_mensagem_out(m: AnaliseCasoMensagem) -> MensagemOut:
    return MensagemOut(
        id=m.id, sessao_id=m.sessao_id, papel=m.papel, conteudo=m.conteudo,
        anexo_nome=m.anexo_nome, ai_log_id=m.ai_log_id,
        is_rascunho=bool(m.is_rascunho), created_at=m.created_at,
    )


async def _carregar_sessao(
    db: AsyncSession, sessao_id: str, cu: User, checar_caso: bool = False,
) -> AnaliseCasoSessao:
    """Carrega a sessão e impõe ownership (só o próprio user_id). Retorna 404
    tanto quando a sessão não existe QUANTO quando pertence a outro usuário —
    o mesmo status nos dois casos não vaza a existência de sessões alheias.

    Quando `checar_caso=True` e a sessão está vinculada a um caso, reexecuta o
    gate canônico `verificar_acesso_caso` (levanta 403/404 se o acesso ao caso
    foi revogado por reatribuição/soft-delete). A thread é conteúdo derivado do
    caso — a leitura que expõe mensagens deve passar por esse gate; PATCH/DELETE
    (que só mexem em título/arquivamento do próprio usuário) usam o default
    False para o dono ainda conseguir gerenciar a sessão."""
    s = (await db.execute(
        select(AnaliseCasoSessao).where(AnaliseCasoSessao.id == sessao_id)
    )).scalar_one_or_none()
    if s is None or s.user_id != cu.id:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if checar_caso and s.case_id:
        await verificar_acesso_caso(db, cu, s.case_id)
    return s


def _titulo_curto(texto: str) -> str:
    """Título curto a partir da 1ª mensagem do usuário (heurística, sem IA)."""
    limpo = " ".join((texto or "").split())
    if not limpo:
        return _TITULO_PADRAO
    return (limpo[:57] + "…") if len(limpo) > 60 else limpo


async def _construir_messages(
    db: AsyncSession, sessao: AnaliseCasoSessao,
) -> tuple[list[dict], bool, list[str], str]:
    """Monta as mensagens para o gateway a partir do histórico persistido.

    Retorna (messages, pii_removida, nomes_proteger, resumo_prompt_log).
    """
    messages: list[dict] = [{"role": "system", "content": _PERSONA}]
    nomes_proteger: list[str] = []

    # Orçamento de chars COMPARTILHADO entre dossiê e histórico: o dossiê consome
    # parte do teto e o histórico usa apenas o que sobrar (com piso), evitando que
    # o total chegue a ~2x _MAX_PROMPT_BUDGET e estoure providers menores.
    orcamento = _MAX_PROMPT_BUDGET

    # Contexto do caso (dossiê já sanitizado por montar_dossie).
    if sessao.case_id:
        dossie = await case_context.montar_dossie(db, sessao.case_id)
        if dossie:
            nomes_proteger = dossie.get("nomes_proteger") or []
            texto_dossie = (
                "[CONTEXTO DO CASO VINCULADO]\n" + (dossie.get("texto") or "")
            )[:_MAX_PROMPT_BUDGET]
            messages.append({"role": "user", "content": texto_dossie})
            # Subtrai o tamanho REAL do dossiê incluído, com piso para o histórico.
            orcamento = max(_MIN_HIST_BUDGET, orcamento - len(texto_dossie))

    # LIMIT defensivo: só os turnos mais recentes (desc), já do mais recente ao
    # mais antigo, respeitando o orçamento; depois reinverte para a ordem
    # cronológica do diálogo.
    historico = (await db.execute(
        select(AnaliseCasoMensagem)
        .where(AnaliseCasoMensagem.sessao_id == sessao.id)
        .order_by(AnaliseCasoMensagem.created_at.desc())
        .limit(_MAX_HIST_TURNOS)
    )).scalars().all()

    pii_removida = False
    ultimo_user = ""
    turnos: list[dict] = []
    for m in historico:
        anexo = (m.contexto_anexo or "").strip()
        base = (f"{anexo}\n\n" if anexo else "") + (m.conteudo or "")
        role = "assistant" if m.papel == "assistant" else "user"
        if role == "user":
            base, houve = ai_guard.sanitizar_ou_abortar(base, nomes_proteger or None)
            pii_removida = pii_removida or houve
            if not ultimo_user:
                ultimo_user = base
        # A mensagem mais recente (turnos ainda vazio) SEMPRE entra, mesmo que
        # sozinha estoure o orçamento — garante que a msg recém-enviada vai à IA.
        if orcamento - len(base) < 0 and turnos:
            break
        orcamento -= len(base)
        turnos.append({"role": role, "content": base})
    messages.extend(reversed(turnos))
    return messages, pii_removida, nomes_proteger, ultimo_user[:8000]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/sessoes", response_model=SessaoOut, status_code=201)
async def criar_sessao(
    body: SessaoCriar,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    nivel = (body.nivel or "alto").strip().lower()
    if nivel not in _NIVEIS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Nível inválido. Use: {', '.join(sorted(_NIVEIS_VALIDOS))}")

    if body.case_id:
        # Ownership do caso (404/403) — reaproveita o gate canônico.
        await verificar_acesso_caso(db, cu, body.case_id)

    sessao = AnaliseCasoSessao(
        id=str(uuid4()),
        user_id=cu.id,
        case_id=body.case_id or None,
        titulo=(body.titulo or _TITULO_PADRAO).strip()[:200] or _TITULO_PADRAO,
        nivel=nivel,
        area=(body.area or None),
    )
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return _to_sessao_out(sessao)


@router.get("/sessoes", response_model=list[SessaoResumo])
async def listar_sessoes(
    arquivadas: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    sessoes = (await db.execute(
        select(AnaliseCasoSessao)
        .where(
            AnaliseCasoSessao.user_id == cu.id,
            AnaliseCasoSessao.arquivada == arquivadas,
        )
        .order_by(AnaliseCasoSessao.updated_at.desc())
    )).scalars().all()

    resumos: list[SessaoResumo] = []
    for s in sessoes:
        total = (await db.execute(
            select(func.count(AnaliseCasoMensagem.id))
            .where(AnaliseCasoMensagem.sessao_id == s.id)
        )).scalar_one()
        ultima = (await db.execute(
            select(AnaliseCasoMensagem)
            .where(AnaliseCasoMensagem.sessao_id == s.id)
            .order_by(AnaliseCasoMensagem.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        preview = None
        if ultima is not None:
            preview = " ".join((ultima.conteudo or "").split())[:140]
        # Se o acesso ao caso vinculado foi revogado (reatribuição/soft-delete),
        # NÃO expõe o preview (conteúdo derivado do caso), mas mantém a sessão na
        # listagem — o título é do próprio usuário e ela segue gerenciável
        # (renomear/arquivar/apagar).
        if s.case_id:
            try:
                await verificar_acesso_caso(db, cu, s.case_id)
            except HTTPException:
                preview = None
        resumos.append(SessaoResumo(
            **_to_sessao_out(s).model_dump(),
            total_mensagens=int(total or 0),
            ultima_mensagem_preview=preview,
            ultima_atividade=(ultima.created_at if ultima is not None else s.updated_at),
        ))
    return resumos


@router.get("/sessoes/{sessao_id}", response_model=SessaoDetalhe)
async def obter_sessao(
    sessao_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    # checar_caso=True: a leitura expõe as mensagens (conteúdo derivado do caso),
    # então reexecuta o gate de acesso ao caso vinculado (403/404 se revogado).
    sessao = await _carregar_sessao(db, sessao_id, cu, checar_caso=True)
    mensagens = (await db.execute(
        select(AnaliseCasoMensagem)
        .where(AnaliseCasoMensagem.sessao_id == sessao.id)
        .order_by(AnaliseCasoMensagem.created_at.asc())
    )).scalars().all()
    return SessaoDetalhe(
        **_to_sessao_out(sessao).model_dump(),
        mensagens=[_to_mensagem_out(m) for m in mensagens],
    )


@router.patch("/sessoes/{sessao_id}", response_model=SessaoOut)
async def atualizar_sessao(
    sessao_id: str,
    body: SessaoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    sessao = await _carregar_sessao(db, sessao_id, cu)
    if body.titulo is not None:
        novo = body.titulo.strip()[:200]
        if not novo:
            raise HTTPException(status_code=422, detail="Título não pode ser vazio")
        sessao.titulo = novo
    if body.arquivada is not None:
        sessao.arquivada = body.arquivada
    await db.commit()
    await db.refresh(sessao)
    return _to_sessao_out(sessao)


@router.delete("/sessoes/{sessao_id}", status_code=204)
async def apagar_sessao(
    sessao_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    sessao = await _carregar_sessao(db, sessao_id, cu)
    await db.delete(sessao)   # cascade delete-orphan apaga as mensagens
    await db.commit()
    return None


@router.post(
    "/sessoes/{sessao_id}/documento",
    response_model=MensagemOut,
    dependencies=[Depends(rate_limit("analise-caso-ia-doc", 10))],
)
async def anexar_documento(
    sessao_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    sessao = await _carregar_sessao(db, sessao_id, cu)
    if sessao.case_id:
        await verificar_acesso_caso(db, cu, sessao.case_id)

    filename = file.filename or "documento"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _EXT_OCR:
        raise HTTPException(
            status_code=422,
            detail=f"Extensão não permitida: {ext or '(sem extensão)'}. "
                   f"Use: {', '.join(sorted(_EXT_OCR))}",
        )

    conteudo_bytes = await file.read()
    if not conteudo_bytes:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    if len(conteudo_bytes) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {settings.MAX_UPLOAD_MB}MB")

    # Gate de conteúdo por magic bytes (levanta 415 se o conteúdo não bate com a
    # extensão), reusando o validador canônico de documents.py. Import LOCAL para
    # não acoplar o import de topo. NÃO troca o dispatch de MIME do OCR abaixo
    # (_MIME_POR_EXT segue como fonte do mimetype passado ao ocr_service).
    from app.routers.documents import _validar_conteudo
    _validar_conteudo(ext, conteudo_bytes)

    # Persistência efêmera para o OCR (síncrono → thread). Removido ao final.
    subdir = os.path.join(settings.UPLOAD_DIR, "analise_caso_ia")
    try:
        os.makedirs(subdir, exist_ok=True)
        destino = subdir
    except OSError:
        import tempfile
        destino = tempfile.gettempdir()
    full_path = os.path.join(destino, f"{uuid4()}{ext}")

    ocr_text: str | None = None
    try:
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(conteudo_bytes)
        mime = file.content_type or _MIME_POR_EXT.get(ext) or mimetypes.guess_type(filename)[0]
        if ext in _MIME_POR_EXT:  # força o MIME confiável (não confiar no cliente)
            mime = _MIME_POR_EXT[ext]
        ocr_text = await asyncio.to_thread(ocr_service.extrair_texto, full_path, mime)
    except Exception as e:  # OCR nunca deve derrubar o endpoint
        logger.warning("OCR falhou no anexo da sessão %s: %s", sessao_id, e)
    finally:
        try:
            os.remove(full_path)
        except OSError:
            pass

    if not (ocr_text or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Não foi possível extrair texto do documento (arquivo vazio, "
                   "protegido ou imagem sem texto legível).",
        )

    msg = AnaliseCasoMensagem(
        id=str(uuid4()),
        sessao_id=sessao.id,
        papel="user",
        conteudo=f"📎 Documento anexado: {filename}",
        contexto_anexo=ocr_text[:_MAX_CONTEXTO_ANEXO],
        anexo_nome=filename,
        is_rascunho=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    sessao.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return _to_mensagem_out(msg)


@router.post(
    "/sessoes/{sessao_id}/mensagem",
    dependencies=[Depends(rate_limit("analise-caso-ia", 15))],
)
async def enviar_mensagem(
    sessao_id: str,
    body: MensagemEnviar,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(usuario_juridico),
):
    # ── Pré-stream: ownership + acesso ao caso + criação da mensagem do usuário.
    # (Erros aqui viram HTTP real 403/404, não evento SSE.)
    sessao = await _carregar_sessao(db, sessao_id, cu)
    if sessao.case_id:
        await verificar_acesso_caso(db, cu, sessao.case_id)

    conteudo = body.conteudo.strip()
    if not conteudo:
        raise HTTPException(status_code=422, detail="Mensagem vazia")

    texto_colado = (body.texto_colado or "").strip() or None
    msg_user = AnaliseCasoMensagem(
        id=str(uuid4()),
        sessao_id=sessao.id,
        papel="user",
        conteudo=conteudo,
        contexto_anexo=(texto_colado[:_MAX_CONTEXTO_ANEXO] if texto_colado else None),
        anexo_nome=("Texto colado" if texto_colado else None),
        is_rascunho=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg_user)
    # Sobe a sessão na lista (ordenada por updated_at.desc) já neste commit, para
    # que ela apareça no topo mesmo que a geração da IA falhe depois.
    sessao.updated_at = datetime.now(timezone.utc)
    # É a 1ª troca? (nenhuma resposta assistant ainda) — para gerar o título.
    ja_tem_assistant = (await db.execute(
        select(func.count(AnaliseCasoMensagem.id)).where(
            AnaliseCasoMensagem.sessao_id == sessao.id,
            AnaliseCasoMensagem.papel == "assistant",
        )
    )).scalar_one()
    await db.commit()
    await db.refresh(msg_user)

    async def stream():
        yield _sse("inicio", {"sessao_id": sessao.id, "mensagem_user_id": msg_user.id})
        try:
            messages, pii_removida, _nomes, resumo_log = await _construir_messages(db, sessao)

            resp = await ai_gateway.chat(
                messages,
                task_type="analise_juridica",
                nivel_inteligencia=sessao.nivel,
                max_tokens=4096,
            )

            # Fallback de PII: se _construir_messages não devolveu resumo (ex.:
            # histórico ainda vazio), sanitiza o conteúdo CRU antes de gravar — o
            # campo prompt_sanitizado NÃO passa pelo @validates de pseudonimização,
            # então nunca pode receber texto cru.
            prompt_log = resumo_log or ai_guard.sanitizar_ou_abortar(conteudo)[0]

            # Auditoria OBRIGATÓRIA (HITL/LGPD): erro de gravação PROPAGA.
            ai_log_id = await ai_guard.registrar_ai_log(
                db,
                user_id=cu.id,
                tipo_uso=AITipoUso.analise_caso,
                case_id=sessao.case_id,
                prompt_sanitizado=prompt_log,
                pii_removida=pii_removida,
                resposta=resp.texto,
                modelo=f"{resp.provedor}/{resp.modelo}",
                tokens_input=resp.input_tokens,
                tokens_output=resp.output_tokens,
                custo_estimado=resp.custo_estimado_brl,
            )

            # Gate anti-alucinação de citações (relatório anexado ao SSE).
            citacoes = await citation_gate.validar_citacoes(db, resp.texto)

            # Resposta assistant nasce rascunho (HITL/OAB).
            msg_ai = AnaliseCasoMensagem(
                id=str(uuid4()),
                sessao_id=sessao.id,
                papel="assistant",
                conteudo=resp.texto,
                ai_log_id=ai_log_id,
                is_rascunho=True,
                # Estritamente > created_at do msg_user (ordenação determinística).
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg_ai)
            if not ja_tem_assistant and (sessao.titulo or "").strip() == _TITULO_PADRAO:
                sessao.titulo = _titulo_curto(conteudo)
            sessao.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(msg_ai)

            # Efeito de digitação: fatia a resposta JÁ completa/reidratada.
            texto = resp.texto or ""
            for i in range(0, len(texto), 50):
                yield _sse("chunk", {"delta": texto[i:i + 50]})

            yield _sse("concluido", {
                "mensagem_id": msg_ai.id,
                "ai_log_id": ai_log_id,
                "titulo": sessao.titulo,
                "modelo": resp.modelo,
                "provedor": resp.provedor,
                "is_rascunho": True,
                "tokens_input": resp.input_tokens,
                "tokens_output": resp.output_tokens,
                "custo_estimado_brl": resp.custo_estimado_brl,
                "citacoes": citacoes.model_dump(),
                "conteudo": texto,
            })
        except Exception as e:
            logger.error("[AnaliseCasoIA] falha na geração (sessão %s): %s", sessao_id, e)
            try:
                await db.rollback()
            except Exception:
                pass
            yield _sse("erro", {
                "detail": "IA indisponível no momento. Tente novamente em instantes "
                          "ou contate o administrador."
            })

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
