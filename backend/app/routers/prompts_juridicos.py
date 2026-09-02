# ── app/routers/prompts_juridicos.py ──────────────────────────────────────────
# Biblioteca de Prompts Jurídicos — CRUD + execução via AI Gateway.
# Prompts têm {{variavel}} como placeholders, substituídos na hora de executar.
from __future__ import annotations
import json
import logging
import re
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.prompt_juridico import PromptJuridico, PromptCategoria
from app.core.rate_limit import rate_limit
from pydantic import field_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts-juridicos", tags=["Biblioteca de Prompts"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class PromptIn(BaseModel):
    titulo:    str = Field(min_length=3, max_length=200)
    categoria: PromptCategoria
    conteudo:  str = Field(min_length=20)
    descricao: Optional[str] = None
    tags:      Optional[str] = None
    favorito:  bool = False
    publico:   bool = True


class PromptPatch(BaseModel):
    titulo:    Optional[str] = None
    categoria: Optional[PromptCategoria] = None
    conteudo:  Optional[str] = None
    descricao: Optional[str] = None
    tags:      Optional[str] = None
    favorito:  Optional[bool] = None
    publico:   Optional[bool] = None


class ExecutarPromptReq(BaseModel):
    variaveis:   dict = {}    # {"variavel1": "valor1", "variavel2": "valor2"}
    case_id:     Optional[str] = None
    task_type:   str = "analise_juridica"   # task_type para o AI Gateway
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens:  int = Field(2048, ge=256, le=8192)
    avaliacao:   Optional[int] = Field(None, ge=1, le=5)   # feedback após execução


# ── Helpers ───────────────────────────────────────────────────────────────────

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")

def _preencher_variaveis(template: str, variaveis: dict) -> str:
    def sub(m):
        key = m.group(1)
        return variaveis.get(key, m.group(0))
    return _PLACEHOLDER.sub(sub, template)

def _extrair_variaveis(conteudo: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(conteudo)))

def _role_value(user: User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or "")

def _pode_editar(user: User) -> bool:
    return ROLE_LEVEL.get(_role_value(user), 0) >= ROLE_LEVEL["advogado"]

def _so_publicos(user: User) -> bool:
    """Papéis fora da equipe jurídica só enxergam prompts marcados públicos.

    `financeiro` fica numericamente acima de `estagiario` em ROLE_LEVEL, então
    esta decisão não pode ser expressa por piso hierárquico. A fonte canônica é
    a allowlist exata EQUIPE_JURIDICA.
    """
    return _role_value(user) not in EQUIPE_JURIDICA

async def _carregar_visivel(
    db: AsyncSession, prompt_id: str, user: User
) -> PromptJuridico:
    """Aplica no detalhe/execução a mesma visibilidade da coleção.

    Um prompt privado oculto da listagem não pode ser lido ou executado por ID.
    Responde 404 para não confirmar a existência do registro privado.
    """
    q = select(PromptJuridico).where(
        PromptJuridico.id == prompt_id,
        PromptJuridico.deleted_at.is_(None),
    )
    if _so_publicos(user):
        q = q.where(PromptJuridico.publico.is_(True))
    p = (await db.execute(q)).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Prompt não encontrado")
    return p

# ── Clamp de task_type (P0.1) ─────────────────────────────────────────────────
# req.task_type é INPUT LIVRE do request. Não confiamos nele: só passa ao
# gateway se pertencer ao vocabulário conhecido (TASK_ROUTING + TASK_ALIASES);
# qualquer outro valor cai no default seguro. O default preserva o roteamento
# atual (o gateway já usa TASK_ROUTING["analise_juridica"] como fallback) e a
# barreira anti-alucinação NÃO depende do task_type neste endpoint —
# garantir_identidade injeta a base canônica INCONDICIONALMENTE no system.
_TASK_TYPE_DEFAULT = "analise_juridica"

def _clamp_task_type(task_type: str | None) -> str:
    from app.services.ai_gateway import TASK_ALIASES, TASK_ROUTING
    t = (task_type or "").strip().lower()
    if t in TASK_ROUTING or t in TASK_ALIASES:
        return t
    return _TASK_TYPE_DEFAULT

def _out(p: PromptJuridico) -> dict:
    return {
        "id": p.id, "titulo": p.titulo,
        "categoria": p.categoria.value if hasattr(p.categoria, "value") else p.categoria,
        "conteudo": p.conteudo, "descricao": p.descricao,
        "variaveis": _extrair_variaveis(p.conteudo),
        "tags": p.tags, "favorito": p.favorito, "publico": p.publico,
        "vezes_executado": p.vezes_executado, "versao": p.versao,
        "avaliacao_media": p.avaliacao_media,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_prompts(
    categoria: Optional[str] = Query(None),
    favorito:  Optional[bool] = Query(None),
    busca:     Optional[str]  = Query(None),
    page:      int = Query(1, ge=1),
    per_page:  int = Query(20, ge=1, le=100),
    db:        AsyncSession = Depends(get_db),
    cu:        User = Depends(get_current_user),
):
    q = select(PromptJuridico).where(PromptJuridico.deleted_at.is_(None))

    # Visibilidade é por pertencimento à equipe jurídica, não por nível.
    # `financeiro` (4) > `estagiario` (3), mas não integra EQUIPE_JURIDICA.
    if _so_publicos(cu):
        q = q.where(PromptJuridico.publico.is_(True))

    if categoria:
        q = q.where(PromptJuridico.categoria == categoria)
    if favorito is not None:
        q = q.where(PromptJuridico.favorito.is_(favorito))
    if busca:
        t = f"%{busca}%"
        q = q.where(or_(
            PromptJuridico.titulo.ilike(t),
            PromptJuridico.descricao.ilike(t),
            PromptJuridico.tags.ilike(t),
        ))

    q = q.order_by(PromptJuridico.favorito.desc(), PromptJuridico.vezes_executado.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page, "items": [_out(p) for p in items]}


@router.post("", status_code=201)
async def criar_prompt(
    req: PromptIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    variaveis_json = json.dumps(_extrair_variaveis(req.conteudo))
    p = PromptJuridico(
        id=str(uuid4()),
        created_by=cu.id,
        variaveis=variaveis_json,
        **req.model_dump(),
    )
    db.add(p)
    await db.commit()
    return _out(p)


@router.get("/{prompt_id}")
async def obter_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _out(await _carregar_visivel(db, prompt_id, cu))


@router.patch("/{prompt_id}")
async def atualizar_prompt(
    prompt_id: str,
    req: PromptPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    p = (await db.execute(
        select(PromptJuridico).where(
            PromptJuridico.id == prompt_id,
            PromptJuridico.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404)

    dados = req.model_dump(exclude_none=True)
    for campo, valor in dados.items():
        setattr(p, campo, valor)

    if "conteudo" in dados:
        p.variaveis = json.dumps(_extrair_variaveis(p.conteudo))
        p.versao = (p.versao or 1) + 1

    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _out(p)


@router.delete("/{prompt_id}", status_code=204)
async def remover_prompt(
    prompt_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios podem remover prompts")
    p = (await db.execute(
        select(PromptJuridico).where(
            PromptJuridico.id == prompt_id,
            PromptJuridico.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    p.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{prompt_id}/executar", dependencies=[Depends(rate_limit("prompt-executar", 15))])
async def executar_prompt(
    prompt_id: str,
    req: ExecutarPromptReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Executa o prompt preenchendo as variáveis e enviando ao AI Gateway.
    As variáveis {{nome}} são substituídas pelos valores fornecidos.
    Resultado é RASCUNHO — revisão humana obrigatória (HITL).
    """
    from app.services.ai_gateway import chat as gw_chat
    from app.services.sanitizer import sanitizar_pii
    from app.services.legal_base import garantir_identidade

    p = await _carregar_visivel(db, prompt_id, cu)

    # Preenche variáveis
    conteudo_preenchido = _preencher_variaveis(p.conteudo, req.variaveis)

    # Sanitiza PII antes de enviar à IA
    conteudo_sanitizado, houve_pii = sanitizar_pii(conteudo_preenchido, [])

    # Barreira anti-alucinação OBRIGATÓRIA: o conteúdo é autoral (biblioteca de
    # prompts do usuário) e req.task_type é livre — sem system message a barreira
    # do gateway (aplicar_base) não teria onde/quando agir. Injeta identidade OAB.
    messages = garantir_identidade([{"role": "user", "content": conteudo_sanitizado}])

    # task_type do request é livre — clampa ao vocabulário conhecido do gateway
    # (allowlist), caindo no default seguro para qualquer valor arbitrário.
    task_type = _clamp_task_type(req.task_type)

    try:
        resp = await gw_chat(
            messages=messages,
            task_type=task_type,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except HTTPException:
        # Erro já classificado pelo gateway/política (ex.: kill-switch) não deve
        # virar 502 genérico nesta borda.
        raise
    except Exception:
        logger.exception("Falha na chamada de IA (prompts jurídicos)")
        raise HTTPException(502, "IA indisponível no momento")

    # Atualiza métricas de uso
    p.vezes_executado = (p.vezes_executado or 0) + 1
    p.ultima_execucao = datetime.now(timezone.utc)
    if req.avaliacao:
        cnt = p.vezes_executado
        prev = p.avaliacao_media or req.avaliacao
        p.avaliacao_media = round((prev * (cnt - 1) + req.avaliacao) / cnt, 2)
    await db.commit()

    # Auditoria: rastro obrigatório em ai_logs (HITL/LGPD).
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    log_id = await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=req.case_id,
        prompt_sanitizado=conteudo_sanitizado[:8000], pii_removida=houve_pii,
        resposta=resp.texto, modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )

    return {
        "resposta":    resp.texto,
        "modelo":      resp.modelo,
        "provedor":    resp.provedor,
        "fallback":    resp.fallback_ativado,
        "pii_removida": houve_pii,
        "prompt_id":   prompt_id,
        "log_id":      log_id,
        "is_rascunho": True,
        "aviso": "⚠️ RASCUNHO gerado por IA — revisão obrigatória antes de usar.",
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }

# ── models (incorporados de prompts.py — D4) ──
# Model ORM
# Schemas
class PromptCreate(BaseModel):
    titulo: str
    categoria: str
    conteudo: str
    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, v: str) -> str:
        # PromptJuridico.categoria é SAEnum(PromptCategoria): valor fora do enum
        # estoura no INSERT (asyncpg → 500). Validar na ENTRADA devolve 422.
        validos = {c.value for c in PromptCategoria}
        if v not in validos:
            raise ValueError(f"categoria inválida: use uma de {sorted(validos)}")
        return v
class PromptResponse(PromptCreate):
    id: str

# ── (incorporado de prompts.py — D4; handlers colidentes com o
#    canônico removidos — compatibilidade preservada via redirect 308) ──
