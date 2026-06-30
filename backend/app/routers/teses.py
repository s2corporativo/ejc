# ── app/routers/teses.py ─────────────────────────────────────────────────────
# Banco de Teses Jurídicas — CRUD + ranking + sugestão por IA.
# Acesso: staff (advogado+). Criação: advogado+.
from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.tese import Tese, TeseCasoLink, TeseTipo, TeseStatus

router = APIRouter(prefix="/teses", tags=["Banco de Teses"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeseIn(BaseModel):
    titulo:           str = Field(min_length=5, max_length=300)
    descricao:        str = Field(min_length=10)
    fundamentacao:    Optional[str] = None
    jurisprudencia:   Optional[str] = None
    contra_argumento: Optional[str] = None
    area_juridica:    Optional[str] = None
    tribunal:         Optional[str] = None
    magistrado:       Optional[str] = None
    tags:             Optional[str] = None
    observacoes:      Optional[str] = None
    tipo:             TeseTipo     = TeseTipo.escritorio
    status:           TeseStatus   = TeseStatus.ativa


class TesePatch(BaseModel):
    titulo:           Optional[str] = None
    descricao:        Optional[str] = None
    fundamentacao:    Optional[str] = None
    jurisprudencia:   Optional[str] = None
    contra_argumento: Optional[str] = None
    area_juridica:    Optional[str] = None
    tribunal:         Optional[str] = None
    magistrado:       Optional[str] = None
    tags:             Optional[str] = None
    observacoes:      Optional[str] = None
    tipo:             Optional[TeseTipo]   = None
    status:           Optional[TeseStatus] = None


class LinkIn(BaseModel):
    case_id:    str
    resultado:  Optional[str] = None   # procedente|improcedente|acordo|pendente
    observacao: Optional[str] = None


class SugestaoIARequest(BaseModel):
    descricao_fatos: str = Field(min_length=30)
    area: str
    case_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["estagiario"]

def _pode_editar(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["advogado"]

def _tese_out(t: Tese) -> dict:
    return {
        "id": t.id, "titulo": t.titulo, "descricao": t.descricao,
        "fundamentacao": t.fundamentacao, "jurisprudencia": t.jurisprudencia,
        "contra_argumento": t.contra_argumento,
        "area_juridica": t.area_juridica, "tribunal": t.tribunal,
        "magistrado": t.magistrado, "tags": t.tags, "observacoes": t.observacoes,
        "tipo": t.tipo.value, "status": t.status.value,
        "vezes_usada": t.vezes_usada, "vezes_venceu": t.vezes_venceu,
        "vezes_perdeu": t.vezes_perdeu, "taxa_sucesso": t.taxa_sucesso,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


async def _recalcular_taxa(tese: Tese):
    """Recalcula taxa_sucesso baseado nos vínculos registrados."""
    if tese.vezes_usada and tese.vezes_usada > 0:
        tese.taxa_sucesso = round(tese.vezes_venceu / tese.vezes_usada, 4)
    else:
        tese.taxa_sucesso = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_teses(
    area: Optional[str] = Query(None),
    status: Optional[str] = Query("ativa"),
    tipo: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    order_by: str = Query("taxa_sucesso"),   # taxa_sucesso|vezes_usada|created_at
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito a advogados")

    q = select(Tese).where(Tese.deleted_at.is_(None))
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    if status:
        q = q.where(Tese.status == status)
    if tipo:
        q = q.where(Tese.tipo == tipo)
    if tribunal:
        q = q.where(Tese.tribunal.ilike(f"%{tribunal}%"))
    if busca:
        termo = f"%{busca}%"
        q = q.where(or_(
            Tese.titulo.ilike(termo),
            Tese.descricao.ilike(termo),
            Tese.fundamentacao.ilike(termo),
            Tese.tags.ilike(termo),
        ))

    if order_by == "taxa_sucesso":
        q = q.order_by(Tese.taxa_sucesso.desc().nullslast())
    elif order_by == "vezes_usada":
        q = q.order_by(Tese.vezes_usada.desc())
    else:
        q = q.order_by(Tese.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    teses = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()

    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [_tese_out(t) for t in teses],
    }


@router.post("", status_code=201)
async def criar_tese(
    req: TeseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    tese = Tese(
        id=str(uuid4()), created_by=cu.id,
        **req.model_dump()
    )
    db.add(tese)
    await db.commit()
    return _tese_out(tese)


@router.get("/ranking")
async def ranking_teses(
    area: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Top teses por taxa de sucesso — painel de inteligência do escritório."""
    if not _is_staff(cu):
        raise HTTPException(403)
    q = select(Tese).where(
        Tese.deleted_at.is_(None),
        Tese.status == TeseStatus.ativa,
        Tese.vezes_usada >= 1,
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    q = q.order_by(Tese.taxa_sucesso.desc().nullslast()).limit(limit)
    teses = (await db.execute(q)).scalars().all()
    return [_tese_out(t) for t in teses]


@router.get("/caso/{case_id}")
async def teses_do_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Teses vinculadas a um caso (via tese_caso_links), com resultado da aplicação."""
    if not _is_staff(cu):
        raise HTTPException(403)
    rows = (await db.execute(
        select(Tese, TeseCasoLink)
        .join(TeseCasoLink, TeseCasoLink.tese_id == Tese.id)
        .where(TeseCasoLink.case_id == case_id, Tese.deleted_at.is_(None))
        .order_by(TeseCasoLink.created_at.desc())
    )).all()
    out = []
    for t, link in rows:
        item = _tese_out(t)
        item["link_id"] = link.id
        item["resultado"] = link.resultado
        item["observacao"] = link.observacao
        out.append(item)
    return out


@router.get("/{tese_id}")
async def obter_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tese não encontrada")
    return _tese_out(t)


@router.patch("/{tese_id}")
async def atualizar_tese(
    tese_id: str, req: TesePatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    for campo, valor in req.model_dump(exclude_none=True).items():
        setattr(t, campo, valor)
    t.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _tese_out(t)


@router.delete("/{tese_id}", status_code=204)
async def arquivar_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios podem arquivar teses")
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/{tese_id}/vincular-caso")
async def vincular_caso(
    tese_id: str, req: LinkIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vincula tese a um caso e atualiza contadores de desempenho."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)

    link = TeseCasoLink(
        id=str(uuid4()), tese_id=tese_id,
        case_id=req.case_id, resultado=req.resultado,
        observacao=req.observacao, created_by=cu.id,
    )
    db.add(link)

    # Atualiza contadores
    t.vezes_usada = (t.vezes_usada or 0) + 1
    if req.resultado == "procedente":
        t.vezes_venceu = (t.vezes_venceu or 0) + 1
    elif req.resultado == "improcedente":
        t.vezes_perdeu = (t.vezes_perdeu or 0) + 1
    await _recalcular_taxa(t)
    t.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"id": link.id, "taxa_sucesso": t.taxa_sucesso}


@router.post("/sugerir-ia")
async def sugerir_teses_ia(
    req: SugestaoIARequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    IA analisa os fatos e busca teses existentes no banco + sugere novas.
    Usa AI Gateway — preferência Ollama, fallback Groq.
    Todas as sugestões são RASCUNHO (HITL obrigatório).
    """
    if not _pode_editar(cu):
        raise HTTPException(403)

    from app.services.sanitizer import sanitizar_pii
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag

    texto_limpo, _ = sanitizar_pii(req.descricao_fatos, [])

    # Busca teses existentes por área
    teses_existentes = (await db.execute(
        select(Tese).where(
            Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa,
            Tese.area_juridica.ilike(f"%{req.area}%"),
        ).order_by(Tese.taxa_sucesso.desc().nullslast()).limit(5)
    )).scalars().all()

    catalogo = ""
    if teses_existentes:
        linhas = [f"- [{t.titulo}] (sucesso: {t.taxa_sucesso or 'N/A'}) — {t.fundamentacao or t.descricao[:100]}"
                  for t in teses_existentes]
        catalogo = "[TESES DO ESCRITÓRIO DISPONÍVEIS]\n" + "\n".join(linhas) + "\n\n"

    fontes = await buscar_contexto_rag(db, texto_limpo[:300], limite=5)
    rag_txt = ""
    if fontes:
        linhas = [f"- {f['titulo']}: {f['conteudo'][:200]}" for f in fontes]
        rag_txt = "[BASE DE CONHECIMENTO]\n" + "\n".join(linhas) + "\n\n"

    system = """Você é consultor jurídico estratégico. Identifique teses aplicáveis aos fatos apresentados.
Use APENAS as teses do escritório ou fundamentos da base de conhecimento. Não invente julgados ou artigos.

FORMATO OBRIGATÓRIO:
## Teses Recomendadas do Escritório (se aplicáveis)
- [nome] | por que se aplica
## Teses Novas Sugeridas
### [nome da tese] (RASCUNHO — verificar)
Fundamento: [artigo/súmula]
Aplicação: [como usar no caso]
Risco: [principal fragilidade]
⚠️ TODAS as sugestões são RASCUNHOS. Validação pelo advogado é obrigatória."""

    user_msg = f"Área: {req.area}\n\n{catalogo}{rag_txt}FATOS (sanitizados):\n{texto_limpo}"

    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
            task_type="analise_juridica",
            temperature=0.3,
            max_tokens=2000,
        )
        return {
            "resposta": resp.texto,
            "modelo_usado": resp.modelo,
            "provedor": resp.provedor,
            "fallback": resp.fallback_ativado,
            "teses_existentes_encontradas": len(teses_existentes),
            "aviso": "⚠️ Sugestões de IA — RASCUNHO. Revisar antes de usar.",
        }
    except Exception as e:
        raise HTTPException(502, f"IA indisponível: {str(e)[:200]}")


# ── P2.2 — Motor de Teses estruturado (viabilidade Alta/Média/Baixa) ──────────
from pydantic import BaseModel as _BM, Field as _F


class MotorTesesRequest(_BM):
    area: str
    descricao_fatos: str = _F(min_length=20, max_length=6000)
    case_id: str | None = None
    polo: str | None = "autor"   # autor | reu


def _parse_json_motor(txt: str):
    import json as _j, re as _re
    if not txt:
        return None
    try:
        return _j.loads(txt)
    except Exception:
        m = _re.search(r"\{.*\}", txt, _re.DOTALL)
        if m:
            try:
                return _j.loads(m.group(0))
            except Exception:
                return None
    return None


@router.post("/motor")
async def motor_teses(
    req: MotorTesesRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Motor de teses: recupera jurisprudência + súmulas + precedentes internos +
    doutrina + teses vencedoras do escritório e gera teses ESTRUTURADAS com
    viabilidade (alta/media/baixa) + fundamentação + contra-argumento.
    REGRAS: não inventa julgado/artigo; nunca promete resultado; tudo é RASCUNHO.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)

    from app.services.sanitizer import sanitizar_pii
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag

    texto, _ = sanitizar_pii(req.descricao_fatos, [])
    consulta = f"{req.area} {texto}"[:400]

    # Escopo de isolamento (Fase 3B): precedentes internos só do cliente do caso.
    # Sem case_id → scope None → fail-closed (não surge precedente de outro cliente).
    from sqlalchemy import text as _text
    scope_cli = None
    if req.case_id:
        scope_cli = (await db.execute(
            _text("SELECT client_id FROM cases WHERE id = :id AND deleted_at IS NULL"),
            {"id": req.case_id},
        )).scalar()

    jurisp = await buscar_contexto_rag(
        db, consulta, limite=6,
        categorias=["jurisprudencia", "sumula_stf", "sumula_stj", "sumula_tst"], modo_or=True)
    internos = await buscar_contexto_rag(db, consulta, limite=4, categorias=["precedente_interno"],
                                         modo_or=True, scope_client_id=scope_cli)
    doutrina = await buscar_contexto_rag(db, consulta, limite=3, categorias=["doutrina"], modo_or=True)

    teses_venc = (await db.execute(
        select(Tese).where(
            Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa,
            Tese.area_juridica.ilike(f"%{req.area}%"),
        ).order_by(Tese.taxa_sucesso.desc().nullslast()).limit(5)
    )).scalars().all()

    def _blk(nome, itens):
        if not itens:
            return ""
        return f"[{nome}]\n" + "\n".join(
            f"- {(i.get('titulo') or '')}: {(i.get('conteudo') or '')[:220]}" for i in itens) + "\n\n"

    ctx = _blk("JURISPRUDÊNCIA/SÚMULAS", jurisp) + _blk("PRECEDENTES INTERNOS", internos) + _blk("DOUTRINA", doutrina)
    if teses_venc:
        ctx += "[TESES VENCEDORAS DO ESCRITÓRIO]\n" + "\n".join(
            f"- {t.titulo} (sucesso {t.taxa_sucesso or 'N/A'}, {t.vezes_venceu or 0}V/{t.vezes_perdeu or 0}D): "
            f"{(t.fundamentacao or t.descricao or '')[:160]}" for t in teses_venc) + "\n\n"

    sinal = (f"Histórico interno: {len(teses_venc)} tese(s) da área com taxa registrada."
             if teses_venc else
             "Sem histórico interno nesta área (escritório novo) — avalie viabilidade pela força "
             "da jurisprudência/súmula encontrada no contexto.")

    system = (
        "Você é consultor jurídico estratégico. Gere teses APLICÁVEIS aos fatos, ANCORADAS no contexto "
        "(jurisprudência, súmulas, precedentes internos, doutrina). É PROIBIDO inventar julgado, súmula ou "
        "artigo que não esteja no contexto — se faltar base, marque viabilidade 'baixa' e escreva 'requer pesquisa'. "
        "NUNCA prometa resultado. Classifique a viabilidade: 'alta' = jurisprudência consolidada/súmula a favor; "
        "'media' = há base mas com divergência/condicionantes; 'baixa' = base fraca ou ausente. "
        "Toda saída é RASCUNHO — revisão obrigatória do advogado (OAB)."
    )
    user = (
        f"ÁREA: {req.area} | POLO: {req.polo}\n\nCONTEXTO RECUPERADO:\n{ctx or '(base escassa)'}\n"
        f"SINAL DE VIABILIDADE: {sinal}\n\nFATOS:\n{texto}\n\n"
        'Responda APENAS JSON: {"teses": [{"titulo": "...", "viabilidade": "alta|media|baixa", '
        '"justificativa_viabilidade": "...", "fundamentacao": "...", '
        '"base_legal": "<súmula/artigo presente no contexto, ou \'requer pesquisa\'>", '
        '"aplicacao": "como usar no caso", "contra_argumento": "principal fragilidade"}], '
        '"sintese": "1-2 frases"}'
    )
    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            task_type="analise_juridica", temperature=0.3, max_tokens=2600)
    except Exception as e:
        raise HTTPException(502, f"IA indisponível: {str(e)[:200]}")

    data = _parse_json_motor(resp.texto) or {"teses": [], "_bruto": resp.texto[:1500]}
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    if isinstance(data.get("teses"), list):
        data["teses"].sort(key=lambda t: ordem.get((t.get("viabilidade") or "baixa").lower(), 3))
    data["fontes_consultadas"] = {
        "jurisprudencia": len(jurisp), "precedentes_internos": len(internos),
        "doutrina": len(doutrina), "teses_escritorio": len(teses_venc),
    }
    data["modelo"] = f"{resp.provedor}/{resp.modelo}"
    data["_aviso"] = "Teses geradas por IA — RASCUNHO. Verifique cada julgado/artigo e revise antes de usar (OAB)."
    return data
