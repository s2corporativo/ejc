# ── app/routers/movimentos.py ─────────────────────────────────────────────────
# Timeline unificada do caso: registro central de todos os acontecimentos.
# RECOMENDAÇÃO 4: Linha do tempo verdadeiramente única
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.models.case import CaseMovimento, CaseMovimentoTipo
from app.models.case import Case
from datetime import datetime, date, timedelta
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(prefix="/movimentos", tags=["Movimentações / Timeline"])


class MovimentoCreate(BaseModel):
    """Schema para criação de movimento na timeline."""
    case_id: str
    tipo: str  # peticao, decisao, audiencia, nota, intimacao, ia, documento_recebido, etc.
    descricao: str
    data_evento: Optional[datetime] = None
    autor_nome: Optional[str] = None
    origem: Optional[str] = None  # manual, datajud, integracao, ia
    caso_relacionado_id: Optional[str] = None
    informacao_anterior: Optional[str] = None
    informacao_posterior: Optional[str] = None
    deadline_id: Optional[str] = None
    document_id: Optional[str] = None
    task_id: Optional[str] = None
    atendimento_id: Optional[str] = None


class MovimentoResponse(BaseModel):
    """Schema de resposta para movimento."""
    id: str
    case_id: str
    tipo: str
    descricao: str
    data_evento: datetime
    created_by: Optional[str]
    created_at: datetime
    resumo_ia: Optional[str]
    autor_nome: Optional[str]
    origem: Optional[str]
    caso_relacionado_id: Optional[str]
    deadline_id: Optional[str]
    document_id: Optional[str]
    task_id: Optional[str]
    atendimento_id: Optional[str]
    case_titulo: Optional[str]
    numero_interno: Optional[str]

    class Config:
        from_attributes = True


@router.post("/", response_model=MovimentoResponse)
async def criar_movimento(
    movimento: MovimentoCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Adiciona um novo evento na timeline do caso.
    
    RECOMENDAÇÃO 4: Registro unificado de todos os acontecimentos do caso.
    """
    # Validar tipo de movimento
    try:
        tipo_enum = CaseMovimentoTipo(movimento.tipo)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de movimento inválido. Válidos: {[t.value for t in CaseMovimentoTipo]}"
        )
    
    # Verificar acesso ao caso
    caso = await db.get(Case, movimento.case_id)
    if not caso or caso.deleted_at:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    
    if not is_gestao(cu):
        if (caso.advogado_responsavel_id != cu.id and 
            caso.advogado_auxiliar_id != cu.id and
            not (caso.advogado_responsavel_id is None and caso.advogado_auxiliar_id is None)):
            raise HTTPException(status_code=403, detail="Sem acesso a este caso")
    
    # Criar movimento
    db_movimento = CaseMovimento(
        case_id=movimento.case_id,
        tipo=tipo_enum,
        descricao=movimento.descricao,
        data_evento=movimento.data_evento or datetime.now(),
        created_by=cu.id,
        autor_nome=movimento.autor_nome or cu.nome,
        origem=movimento.origem or "manual",
        caso_relacionado_id=movimento.caso_relacionado_id,
        informacao_anterior=movimento.informacao_anterior,
        informacao_posterior=movimento.informacao_posterior,
        deadline_id=movimento.deadline_id,
        document_id=movimento.document_id,
        task_id=movimento.task_id,
        atendimento_id=movimento.atendimento_id,
    )
    
    db.add(db_movimento)
    await db.commit()
    await db.refresh(db_movimento)
    
    # Atualizar próxima ação do caso se for movimento relevante
    if tipo_enum in [CaseMovimentoTipo.decisao, CaseMovimentoTipo.intimacao, CaseMovimentoTipo.audiencia]:
        caso.operacional_status = CaseMovimentoTipo.providencia_urgente.value if tipo_enum == CaseMovimentoTipo.intimacao else CaseMovimentoTipo.em_andamento.value
        caso.proxima_acao = f"Analisar {tipo_enum.value}: {movimento.descricao[:100]}"
        caso.responsavel_proxima_acao_id = cu.id
        caso.data_esperada_proxima_acao = datetime.now().date() + timedelta(days=3)
        caso.evento_origem_acao = db_movimento.id
        await db.merge(caso)
        await db.commit()
    
    return db_movimento


@router.get("/timeline/{case_id}", response_model=List[MovimentoResponse])
async def get_timeline_caso(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    tipo: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Retorna a timeline completa de um caso, ordenada cronologicamente.
    
    RECOMENDAÇÃO 4: Visão unificada de todos os eventos do caso.
    """
    # Verificar acesso ao caso
    caso = await db.get(Case, case_id)
    if not caso or caso.deleted_at:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    
    if not is_gestao(cu):
        if (caso.advogado_responsavel_id != cu.id and 
            caso.advogado_auxiliar_id != cu.id and
            not (caso.advogado_responsavel_id is None and caso.advogado_auxiliar_id is None)):
            raise HTTPException(status_code=403, detail="Sem acesso a este caso")
    
    # Construir query
    stmt = (
        select(CaseMovimento, Case.titulo, Case.numero_interno)
        .join(Case, CaseMovimento.case_id == Case.id)
        .where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.data_evento.desc())
        .limit(limit)
    )
    
    if tipo:
        try:
            tipo_enum = CaseMovimentoTipo(tipo)
            stmt = stmt.where(CaseMovimento.tipo == tipo_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo inválido. Válidos: {[t.value for t in CaseMovimentoTipo]}"
            )
    
    result = await db.execute(stmt)
    movimentos = []
    for row in result.all():
        movimento = row[0]
        movimentos.append(MovimentoResponse(
            id=movimento.id,
            case_id=movimento.case_id,
            tipo=movimento.tipo.value if hasattr(movimento.tipo, 'value') else movimento.tipo,
            descricao=movimento.descricao,
            data_evento=movimento.data_evento,
            created_by=movimento.created_by,
            created_at=movimento.created_at,
            resumo_ia=movimento.resumo_ia,
            autor_nome=movimento.autor_nome,
            origem=movimento.origem,
            caso_relacionado_id=movimento.caso_relacionado_id,
            deadline_id=movimento.deadline_id,
            document_id=movimento.document_id,
            task_id=movimento.task_id,
            atendimento_id=movimento.atendimento_id,
            case_titulo=row[1],
            numero_interno=row[2],
        ))
    
    return movimentos


@router.get("/recentes")
async def recentes(
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Feed de movimentos recentes para dashboard.
    Gestão vê todos; equipe vê apenas casos em que atua.
    """
    params: dict = {"lim": limit}
    escopo = ""
    if not is_gestao(cu):
        escopo = """
            AND (c.advogado_responsavel_id = :uid
                 OR c.advogado_auxiliar_id = :uid
                 OR (c.advogado_responsavel_id IS NULL
                     AND c.advogado_auxiliar_id IS NULL))
        """
        params["uid"] = cu.id
    res = await db.execute(
        text(f"""
            SELECT m.id, m.case_id, m.tipo, m.descricao,
                   COALESCE(m.data_evento, m.created_at) AS quando,
                   c.titulo AS case_titulo, c.numero_interno,
                   m.autor_nome, m.origem
            FROM case_movimentos m
            JOIN cases c ON c.id = m.case_id
            WHERE c.deleted_at IS NULL{escopo}
            ORDER BY COALESCE(m.data_evento, m.created_at) DESC
            LIMIT :lim
        """),
        params,
    )
    return [dict(r) for r in res.mappings().all()]
