# ── app/routers/teses.py ─────────────────────────────────────────────────────
# Banco de Teses Jurídicas — CRUD + ranking + sugestão por IA.
# Acesso: staff (advogado+). Criação: advogado+.
from __future__ import annotations
import logging
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL, EQUIPE_JURIDICA
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.case import Case
from app.models.tese import (
    Tese, TeseCasoLink, TeseTipo, TeseStatus,
    ORIENTACOES, STATUS_VALIDACAO, TRANSICOES_VALIDACAO, TRANSICOES_QUE_EXIGEM_VALIDACAO,
)
from app.models.tese_extensoes import (
    TeseFundamentacao, TeseRelacao, TIPOS_RELACAO,
    TeseJurisprudenciaLink, TIPOS_RELACAO_JURISPRUDENCIA,
    LegalEvidence, STATUS_LEGAL_EVIDENCE,
)
from app.models.jurisprudencia_interna import JurisprudenciaInterna
from app.models.audit_log import criar_audit_log
from app.core.rate_limit import rate_limit
from app.models.diario_oficial import DiarioOficialAlerta
from app.modules.dpt360.access_scope import visible_alerts_query
from app.services.impacto_regulatorio import (
    MAX_PUBLICACOES_VARRIDAS, MAX_TESES_VARRIDAS, ranquear_teses_afetadas,
)
from app.services.tese_caso_matcher import (
    MAX_CASOS_VARRIDOS, PISO_RELEVANCIA_PADRAO, extrair_termos, ranquear_candidatos,
)
from app.services.verificador_jurisprudencia import verificar_jurisprudencia
from app.services.radar_jurisprudencial_embedding import atualizar_embedding_tese_job

# Campos de Tese que compõem o texto vetorizado da Camada 2 do Radar
# Jurisprudencial (radar_jurisprudencial_embedding._texto_tese) — um PATCH que
# só toca outro campo (ex.: tribunal, magistrado) não precisa recalcular.
_CAMPOS_TEXTO_EMBEDDING = frozenset({"titulo", "descricao", "fundamentacao", "jurisprudencia"})

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teses", tags=["Banco de Teses"])


# ── Schemas ───────────────────────────────────────────────────────────────────

def _validar_orientacao(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in ORIENTACOES:
        raise ValueError(f"orientacao inválida; use uma de {ORIENTACOES}")
    return v


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
    # ── extensão do Banco Nacional de Teses Jurídicas (migração 148) ──
    orientacao:        Optional[str] = None   # ataque|defesa|ambos — ver ORIENTACOES
    pressupostos:      Optional[str] = None
    excecoes:          Optional[str] = None
    estrategia:        Optional[str] = None
    instancia:         Optional[str] = None
    procedimento:      Optional[str] = None
    parte_favorecida:  Optional[str] = None
    requisitos:         Optional[list[str]] = None
    provas_necessarias: Optional[list[str]] = None
    riscos:             Optional[list[str]] = None
    fontes:              Optional[list[dict]] = None  # [{referencia, situacao, url_oficial}]

    _valida_orientacao = field_validator("orientacao")(_validar_orientacao)


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
    orientacao:        Optional[str] = None
    pressupostos:      Optional[str] = None
    excecoes:          Optional[str] = None
    estrategia:        Optional[str] = None
    instancia:         Optional[str] = None
    procedimento:      Optional[str] = None
    parte_favorecida:  Optional[str] = None
    requisitos:         Optional[list[str]] = None
    provas_necessarias: Optional[list[str]] = None
    riscos:             Optional[list[str]] = None
    fontes:              Optional[list[dict]] = None

    _valida_orientacao = field_validator("orientacao")(_validar_orientacao)


class LinkIn(BaseModel):
    case_id:    str
    resultado:  Optional[str] = None   # procedente|improcedente|acordo|pendente
    observacao: Optional[str] = None


class SugestaoIARequest(BaseModel):
    descricao_fatos: str = Field(min_length=30)
    area: str
    case_id: Optional[str] = None


class FundamentacaoIn(BaseModel):
    norma:         str = Field(min_length=1, max_length=120)
    artigo:        Optional[str] = None
    paragrafo:     Optional[str] = None
    inciso:        Optional[str] = None
    alinea:        Optional[str] = None
    texto:         Optional[str] = None
    interpretacao: Optional[str] = None
    tipo:          Optional[str] = None  # constituicao|lei_federal|lei_estadual|sumula|decreto|regulamento|principio


class RelacaoIn(BaseModel):
    tese_destino_id: str
    tipo_relacao:    str          # ver TIPOS_RELACAO
    observacao:      Optional[str] = None


class JurisprudenciaLinkIn(BaseModel):
    jurisprudencia_id: str
    tipo_relacao:       str       # favoravel|contrario|distinguishing
    observacao:         Optional[str] = None


class ValidacaoIn(BaseModel):
    novo_status: str              # ver STATUS_VALIDACAO/TRANSICOES_VALIDACAO
    observacao:  Optional[str] = None


class EvidenciaIn(BaseModel):
    tipo_fonte:   str = Field(min_length=1, max_length=30)
    tribunal:     Optional[str] = None
    numero:       Optional[str] = None
    url_oficial:  Optional[str] = None
    inteiro_teor_disponivel: Optional[bool] = None
    orgao_julgador: Optional[str] = None
    relator:      Optional[str] = None
    data_julgamento: Optional[date] = None
    data_publicacao: Optional[date] = None
    trecho_relevante: Optional[str] = None
    hash_fingerprint: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff(user: User) -> bool:
    # Issue #694: allowlist EXATA — financeiro não acessa o banco de teses
    # jurídicas, mesmo com ROLE_LEVEL acima de estagiario.
    return user.role.value in EQUIPE_JURIDICA

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
        # ── extensão do Banco Nacional de Teses Jurídicas (migração 148) ──
        "codigo": t.codigo, "orientacao": t.orientacao,
        "status_validacao": t.status_validacao,
        "score": t.score, "score_calculos": t.score_calculos,
        "pressupostos": t.pressupostos, "excecoes": t.excecoes, "estrategia": t.estrategia,
        "instancia": t.instancia, "procedimento": t.procedimento,
        "parte_favorecida": t.parte_favorecida,
        "requisitos": t.requisitos, "provas_necessarias": t.provas_necessarias,
        "riscos": t.riscos, "fontes": t.fontes,
        "versao": t.versao,
        "ultima_validacao_em": t.ultima_validacao_em.isoformat() if t.ultima_validacao_em else None,
        "validada_por": t.validada_por,
    }


async def _recalcular_taxa(tese: Tese):
    """Recalcula taxa_sucesso baseado nos vínculos registrados."""
    if tese.vezes_usada and tese.vezes_usada > 0:
        tese.taxa_sucesso = round(tese.vezes_venceu / tese.vezes_usada, 4)
    else:
        tese.taxa_sucesso = None


async def _tese_ou_404(db: AsyncSession, tese_id: str) -> Tese:
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tese não encontrada")
    return t


def _fundamentacao_out(f: TeseFundamentacao) -> dict:
    return {
        "id": f.id, "tese_id": f.tese_id, "norma": f.norma, "artigo": f.artigo,
        "paragrafo": f.paragrafo, "inciso": f.inciso, "alinea": f.alinea,
        "texto": f.texto, "interpretacao": f.interpretacao, "tipo": f.tipo,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _relacao_out(r: TeseRelacao) -> dict:
    return {
        "id": r.id, "tese_origem_id": r.tese_origem_id, "tese_destino_id": r.tese_destino_id,
        "tipo_relacao": r.tipo_relacao, "observacao": r.observacao,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _jurisprudencia_link_out(link: TeseJurisprudenciaLink) -> dict:
    return {
        "id": link.id, "tese_id": link.tese_id, "jurisprudencia_id": link.jurisprudencia_id,
        "tipo_relacao": link.tipo_relacao, "observacao": link.observacao,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _evidencia_out(e: LegalEvidence) -> dict:
    return {
        "id": e.id, "tese_id": e.tese_id, "tipo_fonte": e.tipo_fonte, "tribunal": e.tribunal,
        "numero": e.numero, "url_oficial": e.url_oficial,
        "data_consulta": e.data_consulta.isoformat() if e.data_consulta else None,
        "inteiro_teor_disponivel": e.inteiro_teor_disponivel,
        "orgao_julgador": e.orgao_julgador, "relator": e.relator,
        "data_julgamento": e.data_julgamento.isoformat() if e.data_julgamento else None,
        "data_publicacao": e.data_publicacao.isoformat() if e.data_publicacao else None,
        "status": e.status, "trecho_relevante": e.trecho_relevante,
        "hash_fingerprint": e.hash_fingerprint, "coletado_por": e.coletado_por,
        "revisado_por": e.revisado_por,
        "ultima_validacao_em": e.ultima_validacao_em.isoformat() if e.ultima_validacao_em else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


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
    background: BackgroundTasks,
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
    # Camada 2 do Radar Jurisprudencial (embedding semântico): fora da
    # transação de escrita, para não somar a latência de embedding ao POST.
    background.add_task(atualizar_embedding_tese_job, tese.id)
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


@router.get("/busca-avancada")
async def busca_avancada(
    q: Optional[str] = Query(None, description="Texto livre (título/descrição/fundamentação/tags)"),
    area: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    status: Optional[str] = Query("ativa"),
    tipo: Optional[str] = Query(None),
    taxa_minima: Optional[float] = Query(None, ge=0, le=1, description="Taxa de sucesso mínima (0–1)"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Busca avançada de teses — consumida por Biblioteca.tsx (era 404).
    Filtros combináveis: texto livre + área + tribunal + taxa mínima + status/tipo.
    Retorna {"total", "teses"} (contrato esperado pelo frontend).
    IMPORTANTE: declarada ANTES de /{tese_id} para não colidir com a rota dinâmica.
    """
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito a advogados")

    stmt = select(Tese).where(Tese.deleted_at.is_(None))
    if area:
        stmt = stmt.where(Tese.area_juridica.ilike(f"%{area}%"))
    if tribunal:
        stmt = stmt.where(Tese.tribunal.ilike(f"%{tribunal}%"))
    if status:
        stmt = stmt.where(Tese.status == status)
    if tipo:
        stmt = stmt.where(Tese.tipo == tipo)
    if taxa_minima is not None:
        stmt = stmt.where(Tese.taxa_sucesso >= taxa_minima)
    if q:
        termo = f"%{q}%"
        stmt = stmt.where(or_(
            Tese.titulo.ilike(termo),
            Tese.descricao.ilike(termo),
            Tese.fundamentacao.ilike(termo),
            Tese.jurisprudencia.ilike(termo),
            Tese.tags.ilike(termo),
        ))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    teses = (await db.execute(
        stmt.order_by(Tese.taxa_sucesso.desc().nullslast(), Tese.created_at.desc())
            .offset(offset).limit(limit)
    )).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "teses": [_tese_out(t) for t in teses],
    }


@router.get("/casos/{case_id}")
async def teses_do_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Teses vinculadas a um caso (via tese_caso_links), com resultado da aplicação."""
    if not _is_staff(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
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


@router.get("/impacto-regulatorio")
async def impacto_regulatorio(
    dias: int = Query(7, ge=1, le=90),
    limite: int = Query(20, ge=1, le=100),
    piso: int = Query(PISO_RELEVANCIA_PADRAO, ge=0, le=100,
                      description="score mínimo (0-100) para a tese entrar na lista"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Quais teses do escritório podem ter sido afetadas pelo que saiu no Diário.

    O radar do EJC já respondia "publicação nova → quais EMPRESAS ela atinge"
    (`modules/dpt360/radar_service.py`). Faltava o alvo jurídico, que é o que a
    frente 1 do plano de evolução pede: "esta publicação mexe com a tese X".

    Determinístico, sem IA (`services/impacto_regulatorio.py`), reusando o
    classificador de área e o mapa de equivalências do próprio radar — uma
    taxonomia só, não duas divergindo com o tempo.

    A saída é SUGESTÃO: diz qual tese reler e por quê (os termos que casaram).
    Nada é marcado como superado automaticamente — reavaliar uma tese à luz de
    norma nova é ato jurídico humano.

    Visibilidade: os alertas passam por `visible_alerts_query`, o contrato
    canônico do Diário Oficial (gestão vê tudo; advogado vê os office-wide e os
    dos próprios casos). Esta rota NÃO amplia essa superfície.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    alertas = (await db.execute(
        visible_alerts_query(cu)
        .where(DiarioOficialAlerta.created_at >= desde)
        .order_by(DiarioOficialAlerta.created_at.desc())
        .limit(MAX_PUBLICACOES_VARRIDAS)
    )).scalars().all()

    publicacoes = [{
        "id": a.id,
        "fonte": a.fonte,
        "titulo": a.titulo,
        "resumo": a.resumo,
        "link": a.link,
        "keyword_match": a.keyword_match,
        "data_publicacao": a.data_publicacao.isoformat() if a.data_publicacao else None,
    } for a in alertas]

    teses_rows = (await db.execute(
        select(Tese)
        .where(Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa)
        .order_by(Tese.created_at.desc())
        .limit(MAX_TESES_VARRIDAS)
    )).scalars().all()

    teses = [{
        "id": t.id,
        "titulo": t.titulo,
        "area_juridica": t.area_juridica,
        # Mesmos campos da varredura tese → caso: título, tags e descrição.
        # Fundamentação e jurisprudência ficam de fora de propósito — inflam a
        # lista de termos e o casamento vira ruído.
        "termos": extrair_termos(t.titulo, t.tags, t.descricao),
    } for t in teses_rows]

    afetadas = ranquear_teses_afetadas(teses, publicacoes, piso=piso, limite=limite)

    return {
        "periodo_dias": dias,
        "desde": desde.date().isoformat(),
        "publicacoes_varridas": len(publicacoes),
        "teto_de_varredura_atingido": len(publicacoes) >= MAX_PUBLICACOES_VARRIDAS,
        "teses_varridas": len(teses),
        "total": len(afetadas),
        "teses_afetadas": afetadas,
        "aviso": ("Sugestão determinística por casamento de termos — indica o que "
                  "RELER, não o que está superado. Confira a publicação antes de "
                  "alterar qualquer tese."),
    }


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
    background: BackgroundTasks,
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
    campos = req.model_dump(exclude_none=True)
    for campo, valor in campos.items():
        setattr(t, campo, valor)
    t.updated_at = datetime.now(timezone.utc)
    await db.commit()
    # Camada 2 do Radar Jurisprudencial: só recalcula o embedding quando um
    # campo que compõe o texto vetorizado realmente mudou — evita rodar
    # embedding em toda edição (ex.: só trocar `tribunal`/`magistrado`).
    if _CAMPOS_TEXTO_EMBEDDING & campos.keys():
        background.add_task(atualizar_embedding_tese_job, t.id)
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


# ── Fundamentações ────────────────────────────────────────────────────────────

@router.get("/{tese_id}/fundamentacoes")
async def listar_fundamentacoes(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    rows = (await db.execute(
        select(TeseFundamentacao).where(TeseFundamentacao.tese_id == tese_id)
        .order_by(TeseFundamentacao.created_at)
    )).scalars().all()
    return [_fundamentacao_out(f) for f in rows]


@router.post("/{tese_id}/fundamentacoes", status_code=201)
async def criar_fundamentacao(
    tese_id: str, req: FundamentacaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    f = TeseFundamentacao(
        id=str(uuid4()), tese_id=tese_id, created_by=cu.id,
        **req.model_dump(),
    )
    db.add(f)
    await db.commit()
    return _fundamentacao_out(f)


@router.delete("/{tese_id}/fundamentacoes/{fund_id}", status_code=204)
async def excluir_fundamentacao(
    tese_id: str, fund_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    f = (await db.execute(
        select(TeseFundamentacao).where(
            TeseFundamentacao.id == fund_id, TeseFundamentacao.tese_id == tese_id,
        )
    )).scalar_one_or_none()
    if not f:
        raise HTTPException(404)
    await db.delete(f)
    await db.commit()


# ── Relações entre teses (grafo — inclui contratese/distinguishing) ─────────

@router.get("/{tese_id}/relacoes")
async def listar_relacoes(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    saida = (await db.execute(
        select(TeseRelacao).where(TeseRelacao.tese_origem_id == tese_id)
    )).scalars().all()
    entrada = (await db.execute(
        select(TeseRelacao).where(TeseRelacao.tese_destino_id == tese_id)
    )).scalars().all()
    return {
        "saida": [_relacao_out(r) for r in saida],
        "entrada": [_relacao_out(r) for r in entrada],
    }


@router.post("/{tese_id}/relacoes", status_code=201)
async def criar_relacao(
    tese_id: str, req: RelacaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    if req.tipo_relacao not in TIPOS_RELACAO:
        raise HTTPException(422, f"tipo_relacao inválido; use um de {TIPOS_RELACAO}")
    if req.tese_destino_id == tese_id:
        raise HTTPException(422, "uma tese não pode se relacionar com ela mesma")
    await _tese_ou_404(db, tese_id)
    await _tese_ou_404(db, req.tese_destino_id)
    existente = (await db.execute(
        select(TeseRelacao).where(
            TeseRelacao.tese_origem_id == tese_id,
            TeseRelacao.tese_destino_id == req.tese_destino_id,
            TeseRelacao.tipo_relacao == req.tipo_relacao,
        )
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "relação já registrada")
    r = TeseRelacao(
        id=str(uuid4()), tese_origem_id=tese_id, tese_destino_id=req.tese_destino_id,
        tipo_relacao=req.tipo_relacao, observacao=req.observacao, created_by=cu.id,
    )
    db.add(r)
    await db.commit()
    return _relacao_out(r)


@router.delete("/{tese_id}/relacoes/{rel_id}", status_code=204)
async def excluir_relacao(
    tese_id: str, rel_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    r = (await db.execute(
        select(TeseRelacao).where(
            TeseRelacao.id == rel_id, TeseRelacao.tese_origem_id == tese_id,
        )
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(404)
    await db.delete(r)
    await db.commit()


# ── Vínculo com jurisprudência interna ───────────────────────────────────────

@router.get("/{tese_id}/jurisprudencias")
async def listar_jurisprudencias_vinculadas(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    rows = (await db.execute(
        select(TeseJurisprudenciaLink).where(TeseJurisprudenciaLink.tese_id == tese_id)
    )).scalars().all()
    return [_jurisprudencia_link_out(link) for link in rows]


@router.post("/{tese_id}/jurisprudencias", status_code=201)
async def vincular_jurisprudencia(
    tese_id: str, req: JurisprudenciaLinkIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    if req.tipo_relacao not in TIPOS_RELACAO_JURISPRUDENCIA:
        raise HTTPException(422, f"tipo_relacao inválido; use um de {TIPOS_RELACAO_JURISPRUDENCIA}")
    await _tese_ou_404(db, tese_id)
    juris = (await db.execute(
        select(JurisprudenciaInterna).where(JurisprudenciaInterna.id == req.jurisprudencia_id)
    )).scalar_one_or_none()
    if not juris:
        raise HTTPException(404, "Jurisprudência não encontrada")
    existente = (await db.execute(
        select(TeseJurisprudenciaLink).where(
            TeseJurisprudenciaLink.tese_id == tese_id,
            TeseJurisprudenciaLink.jurisprudencia_id == req.jurisprudencia_id,
        )
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "jurisprudência já vinculada a esta tese")
    link = TeseJurisprudenciaLink(
        id=str(uuid4()), tese_id=tese_id, jurisprudencia_id=req.jurisprudencia_id,
        tipo_relacao=req.tipo_relacao, observacao=req.observacao, created_by=cu.id,
    )
    db.add(link)
    juris.vezes_citada = (juris.vezes_citada or 0) + 1
    await db.commit()
    return _jurisprudencia_link_out(link)


@router.delete("/{tese_id}/jurisprudencias/{link_id}", status_code=204)
async def desvincular_jurisprudencia(
    tese_id: str, link_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    link = (await db.execute(
        select(TeseJurisprudenciaLink).where(
            TeseJurisprudenciaLink.id == link_id, TeseJurisprudenciaLink.tese_id == tese_id,
        )
    )).scalar_one_or_none()
    if not link:
        raise HTTPException(404)
    await db.delete(link)
    await db.commit()


# ── Evidência jurídica (proveniência auditável) ──────────────────────────────

@router.get("/{tese_id}/evidencias")
async def listar_evidencias(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    rows = (await db.execute(
        select(LegalEvidence).where(LegalEvidence.tese_id == tese_id)
        .order_by(LegalEvidence.created_at)
    )).scalars().all()
    return [_evidencia_out(e) for e in rows]


@router.post("/{tese_id}/evidencias", status_code=201)
async def registrar_evidencia(
    tese_id: str, req: EvidenciaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    await _tese_ou_404(db, tese_id)
    e = LegalEvidence(
        id=str(uuid4()), tese_id=tese_id, coletado_por=cu.id,
        data_consulta=datetime.now(timezone.utc),
        **req.model_dump(),
    )
    db.add(e)
    await db.commit()
    return _evidencia_out(e)


@router.post("/{tese_id}/evidencias/{evidencia_id}/revisar")
async def revisar_evidencia(
    tese_id: str, evidencia_id: str, novo_status: str = Query(...),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    if novo_status not in STATUS_LEGAL_EVIDENCE:
        raise HTTPException(422, f"status inválido; use um de {STATUS_LEGAL_EVIDENCE}")
    e = (await db.execute(
        select(LegalEvidence).where(
            LegalEvidence.id == evidencia_id, LegalEvidence.tese_id == tese_id,
        )
    )).scalar_one_or_none()
    if not e:
        raise HTTPException(404)
    e.status = novo_status
    e.revisado_por = cu.id
    e.ultima_validacao_em = datetime.now(timezone.utc)
    await db.commit()
    return _evidencia_out(e)


# ── Ciclo de validação da tese ───────────────────────────────────────────────

@router.post("/{tese_id}/validacao")
async def transicionar_validacao(
    tese_id: str, req: ValidacaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Move `status_validacao` conforme TRANSICOES_VALIDACAO. Promover a um
    status de confiança (validada/revisada/superada/parcialmente_superada)
    exige socio+ e passa pelo gate anti-alucinação de
    `verificador_jurisprudencia` — citação classificada como suspeita
    bloqueia a promoção."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    if req.novo_status not in STATUS_VALIDACAO:
        raise HTTPException(422, f"status inválido; use um de {STATUS_VALIDACAO}")
    exige_socio = req.novo_status in TRANSICOES_QUE_EXIGEM_VALIDACAO
    if exige_socio and ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios podem promover a este status")

    t = await _tese_ou_404(db, tese_id)
    atual = t.status_validacao
    permitidas = TRANSICOES_VALIDACAO.get(atual, set())
    if req.novo_status not in permitidas:
        raise HTTPException(
            422,
            f"transição inválida: '{atual or 'nulo'}' → '{req.novo_status}' "
            f"(permitidas: {sorted(permitidas) or 'nenhuma'})",
        )

    if exige_socio:
        texto = " ".join(filter(None, [t.fundamentacao, t.jurisprudencia]))
        if t.fontes:
            texto += " " + " ".join(
                str(f.get("referencia", "")) for f in t.fontes if isinstance(f, dict)
            )
        relatorio = (
            await verificar_jurisprudencia(db, texto) if texto.strip()
            else {"contagem_status": {}}
        )
        suspeitas = relatorio.get("contagem_status", {}).get("suspeita", 0)
        if suspeitas:
            raise HTTPException(422, detail={
                "erro": "citação suspeita de alucinação — corrija antes de promover",
                "relatorio": relatorio,
            })

    de = atual
    t.status_validacao = req.novo_status
    t.ultima_validacao_em = datetime.now(timezone.utc)
    t.validada_por = cu.id
    t.versao = (t.versao or 1) + 1
    await criar_audit_log(
        db, user_id=cu.id, user_role=cu.role.value,
        acao="TESE_VALIDACAO", entidade="tese", registro_id=tese_id,
        detalhes=f"{de or 'nulo'} → {req.novo_status}"
                 + (f" — {req.observacao}" if req.observacao else ""),
    )
    await db.commit()
    return _tese_out(t)


@router.get("/{tese_id}/casos-candidatos")
async def casos_candidatos(
    tese_id: str,
    limite: int = Query(20, ge=1, le=100),
    piso: int = Query(PISO_RELEVANCIA_PADRAO, ge=0, le=100,
                      description="score mínimo (0-100) para entrar na lista"),
    incluir_arquivados: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Varredura REVERSA: dada uma tese, onde ela pode caber.

    O caminho caso → teses já existia (`teses_do_caso`, `sugerir_teses_ia`).
    Este é o inverso, e é o que transforma o Banco de Teses de catálogo em
    ferramenta ativa: "a tese X é possivelmente cabível nos processos A, B e C".

    Determinístico, sem IA (ver `services/tese_caso_matcher.py`). A lista é de
    CANDIDATOS — vincular continua sendo ato humano via
    `POST /teses/{tese_id}/vincular-caso`.

    Visibilidade: reusa o mesmo critério de `cases._filtro_visibilidade`
    (advogado/auxiliar vê os próprios casos, socio+ vê todos). Sem isso a
    varredura seria um vazamento: devolveria título e área de casos que o
    usuário não pode abrir.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    tese = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not tese:
        raise HTTPException(404, "Tese não encontrada")

    termos = extrair_termos(tese.titulo, tese.tags, tese.descricao)
    if not termos:
        return {
            "tese_id": tese_id, "titulo": tese.titulo,
            "area_juridica": tese.area_juridica, "termos": [],
            "total": 0, "candidatos": [],
            "aviso": ("A tese não tem termos aproveitáveis no título, nas tags "
                      "ou na descrição — sem isso não há como procurar casos."),
        }

    # Casos já vinculados saem da lista: o pedido é "onde ela AINDA pode caber".
    ja_vinculados = set((await db.execute(
        select(TeseCasoLink.case_id).where(TeseCasoLink.tese_id == tese_id)
    )).scalars().all())

    q = select(Case).where(Case.deleted_at.is_(None))
    if not incluir_arquivados:
        q = q.where(Case.status != "arquivado")
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
        ))
    casos = (await db.execute(q.limit(MAX_CASOS_VARRIDOS))).scalars().all()

    varridos = [
        {
            "id": c.id, "titulo": c.titulo,
            "descricao_fatos": c.descricao_fatos,
            "numero_interno": c.numero_interno,
            "area": c.area.value if hasattr(c.area, "value") else c.area,
            "status": c.status.value if hasattr(c.status, "value") else c.status,
        }
        for c in casos if c.id not in ja_vinculados
    ]

    candidatos = ranquear_candidatos(
        termos, varridos, area_tese=tese.area_juridica, piso=piso, limite=limite,
    )
    return {
        "tese_id": tese_id, "titulo": tese.titulo,
        "area_juridica": tese.area_juridica,
        "termos": termos,
        "casos_varridos": len(varridos),
        "teto_de_varredura_atingido": len(casos) >= MAX_CASOS_VARRIDOS,
        "total": len(candidatos),
        "candidatos": candidatos,
        "aviso": ("Sugestão determinística por casamento de termos — não é "
                  "análise de cabimento. Conferir o caso antes de vincular."),
    }


@router.post("/{tese_id}/vincular-caso")
async def vincular_caso(
    tese_id: str, req: LinkIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vincula tese a um caso e atualiza contadores de desempenho."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, req.case_id)  # gate ownership (sigilo EOAB/LGPD)
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


@router.post("/sugerir-ia", dependencies=[Depends(rate_limit("teses-sugerir-ia", 15))])
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

    from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
    from app.models.ai_log import AITipoUso
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
    from app.core.ownership import verificar_acesso_caso

    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
    escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    texto_limpo, pii = sanitizar_ou_abortar(req.descricao_fatos)

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

    fontes = await buscar_contexto_rag(db, texto_limpo[:300], limite=5, scope_client_id=escopo_cli)
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
        # Auditoria 2026-07-02: este endpoint gerava teses sem deixar NENHUM
        # rastro em ai_logs — quebra de HITL/LGPD. Agora grava sempre.
        log_id = await registrar_ai_log(
            db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=req.case_id,
            prompt_sanitizado=user_msg, pii_removida=pii, resposta=resp.texto,
            modelo=f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo,
            tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
        )
        return {
            "ai_log_id": log_id,
            "resposta": resp.texto,
            "modelo_usado": resp.modelo,
            "provedor": resp.provedor,
            "fallback": resp.fallback_ativado,
            "teses_existentes_encontradas": len(teses_existentes),
            "aviso": "⚠️ Sugestões de IA — RASCUNHO. Revisar antes de usar.",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha na chamada de IA (teses)")
        raise HTTPException(502, "IA indisponível no momento")


# ── P2.2 — Motor de Teses estruturado (viabilidade Alta/Média/Baixa) ──────────
from pydantic import BaseModel as _BM, Field as _F


class MotorTesesRequest(_BM):
    area: str
    descricao_fatos: str = _F(min_length=20, max_length=6000)
    case_id: str | None = None
    polo: str | None = "autor"   # autor | reu


def _parse_json_motor(txt: str):
    import json as _j
    import re as _re
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


async def _gerar_teses(
    req: MotorTesesRequest,
    db: AsyncSession,
    cu: User,
) -> dict:
    # E04 (auditoria funcional): corpo da geração extraído para função pura de
    # serviço, compartilhada pela rota síncrona (/motor) e pela assíncrona
    # (/motor/async + status) — o frontend agora faz polling em vez de esperar
    # a resposta síncrona, evitando o timeout de 30s do navegador.
    # Motor de teses: recupera jurisprudência + súmulas + precedentes internos +
    # doutrina + teses vencedoras do escritório e gera teses ESTRUTURADAS com
    # viabilidade (alta/media/baixa) + fundamentação + contra-argumento.
    # REGRAS: não inventa julgado/artigo; nunca promete resultado; tudo é RASCUNHO.
    if not _pode_editar(cu):
        raise HTTPException(403)

    from app.services.ai_guard import sanitizar_ou_abortar
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
    from app.core.ownership import verificar_acesso_caso

    # Bloco 5: se o motor é invocado no contexto de um caso, exige acesso a ele
    # (antes só checava papel) e escopa os PRECEDENTES INTERNOS ao cliente desse
    # caso — precedente de um cliente nunca aparece para outro. Sem case_id, o
    # escopo é None → fail-closed (nenhum precedente interno é recuperado).
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
    escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    texto, pii = sanitizar_ou_abortar(req.descricao_fatos)
    consulta = f"{req.area} {texto}"[:400]

    # jurisp e doutrina são categorias PÚBLICAS — escopo não as afeta.
    jurisp = await buscar_contexto_rag(
        db, consulta, limite=6,
        categorias=["jurisprudencia", "sumula_stf", "sumula_stj", "sumula_tst"], modo_or=True)
    internos = await buscar_contexto_rag(db, consulta, limite=4, categorias=["precedente_interno"], modo_or=True, scope_client_id=escopo_cli)
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
    except Exception:
        logger.exception("Falha na chamada de IA (motor de teses)")
        raise HTTPException(502, "IA indisponível no momento")

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


# ── E04 (auditoria funcional): geração assíncrona com polling ───────────
# Implementação robusta em P2.2b abaixo (com RBAC, verificação de ownership,
# lock de thread, TTL de 10 min e resposta estruturada). A rota síncrona é
# mantida por compatibilidade.
@router.post("/motor", dependencies=[Depends(rate_limit("teses-motor", 15))])
async def motor_teses(
    req: MotorTesesRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Rota síncrona do Motor de Teses (mantida por compatibilidade — clientes
    antigos e testes dependem dela). Preferir /motor/async para chamadas de UI.
    """
    return await _gerar_teses(req, db, cu)


# ── P2.2b — Geração assíncrona com polling (E04) ────────────────────────────
import secrets as _secrets
import threading as _threading

_motor_tasks: dict[str, dict] = {}
_motor_lock = _threading.Lock()
_MOTOR_TASK_TTL = 600  # 10 minutos — depois o status é descartado


class MotorTesesAsyncResponse(_BM):
    task_id: str
    status: str  # pendente | em_andamento | concluido | erro
    criado_em: str
    estimativa_segundos: int | None = 60


def _expurgar_tarefas_motor() -> None:
    # Descarta tarefas concluídas/erro/estouradas do TTL — evita vazamento de
    # memória em uso intenso (resultado já entregue ao frontend no polling).
    agora = __import__("time").time()
    with _motor_lock:
        expiradas = [tid for tid, t in _motor_tasks.items()
                     if t["status"] in ("concluido", "erro") or agora - t["criado_ts"] > _MOTOR_TASK_TTL]
        for tid in expiradas:
            del _motor_tasks[tid]


async def _executar_tese_task(task_id: str, req: MotorTesesRequest, db: AsyncSession, cu: User) -> None:
    try:
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id]["status"] = "em_andamento"
        data = await _gerar_teses(req, db, cu)
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id].update({"status": "concluido", "resultado": data})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha na geração assíncrona de teses (task %s)", task_id)
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id]["status"] = "erro"


@router.post("/motor/async", response_model=MotorTesesAsyncResponse,
             dependencies=[Depends(rate_limit("teses-motor", 15))])
async def motor_teses_async(
    req: MotorTesesRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Geração assíncrona do Motor de Teses: cria uma tarefa e devolve um task_id
    imediatamente (202). O frontend consulta o status por polling em
    GET /motor/async/{task_id} até concluido/erro. O resultado fica em memória
    (com TTL de 10 minutos) — sem dependência de fila externa.
    REGRAS: não inventa julgado/artigo; nunca promete resultado; tudo é RASCUNHO.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    # Validação de acesso ANTES de criar a tarefa (mesma regra da rota síncrona).
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso  # noqa: F401
        await verificar_acesso_caso(db, cu, req.case_id)

    task_id = _secrets.token_hex(12)
    criado_em = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    with _motor_lock:
        _motor_tasks[task_id] = {
            "status": "pendente", "criado_ts": __import__("time").time(),
            "criado_em": criado_em.isoformat(),
        }
        _expurgar_tarefas_motor()
    background.add_task(_executar_tese_task, task_id, req, db, cu)
    return MotorTesesAsyncResponse(
        task_id=task_id, status="pendente", criado_em=criado_em.isoformat())


@router.get("/motor/async/{task_id}")
async def motor_teses_async_status(
    task_id: str,
    cu: User = Depends(get_current_user),
):
    """
    Status do motor assíncrono de teses: {task_id, status, resultado?, criado_em}.
    status: pendente | em_andamento | concluido | erro (404 se task_id inexistente).
    """
    with _motor_lock:
        task = _motor_tasks.get(task_id)
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada ou expirada (TTL 10 min)")
    out = {
        "task_id": task_id, "status": task["status"], "criado_em": task["criado_em"],
    }
    if task["status"] == "concluido":
        out["resultado"] = task["resultado"]
    return out
