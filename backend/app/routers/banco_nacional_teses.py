# ── app/routers/banco_nacional_teses.py ──────────────────────────────────────
# Fundação do Banco Nacional de Teses Jurídicas — API curatorial V1.
#
# Esta API não coleta fontes externas sozinha. Ela recebe registros provenientes
# de fonte pública/autorizada, preserva snapshot/hash e impede publicação de tese
# sem evento de validação rastreável e decisão humana.
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, ROLE_LEVEL, get_current_user
from app.models.legal_thesis_bank import (
    LegalIngestionRun,
    LegalPrecedent,
    LegalSource,
    LegalSourceSnapshot,
    LegalThesis,
    LegalThesisPrecedent,
    LegalThesisValidationEvent,
    LegalThesisVersion,
)
from app.models.user import User
from app.services.legal_thesis_bank_service import (
    hash_conteudo,
    normalizar_chave,
    precedente_pode_ser_recomendado,
    tese_pode_ser_recomendada,
)

router = APIRouter(prefix="/banco-nacional-teses", tags=["Banco Nacional de Teses"])


class FonteIn(BaseModel):
    slug: str = Field(min_length=2, max_length=80)
    nome: str = Field(min_length=2, max_length=255)
    categoria: str = Field(min_length=2, max_length=40)
    autoridade: str | None = Field(default=None, max_length=255)
    tipo_acesso: str = Field(min_length=2, max_length=40)
    url_base: str = Field(min_length=8, max_length=2000)
    url_validacao: str | None = Field(default=None, max_length=2000)
    url_termos: str | None = Field(default=None, max_length=2000)
    exige_autenticacao: bool = False
    permite_uso_derivado: bool | None = None
    observacoes: str | None = None


class SnapshotIn(BaseModel):
    chave_origem: str = Field(min_length=1, max_length=500)
    titulo: str | None = Field(default=None, max_length=500)
    conteudo_normalizado: str = Field(min_length=1)
    url_origem: str | None = Field(default=None, max_length=2000)
    data_publicacao: date | None = None
    capturado_em: datetime | None = None
    metadados: dict[str, Any] | None = None


class PrecedenteIn(BaseModel):
    source_id: str
    snapshot_id: str
    chave_origem: str = Field(min_length=1, max_length=500)
    tribunal: str | None = Field(default=None, max_length=60)
    instancia: str | None = Field(default=None, max_length=40)
    orgao_julgador: str | None = Field(default=None, max_length=160)
    classe_processual: str | None = Field(default=None, max_length=120)
    numero_processo: str | None = Field(default=None, max_length=80)
    relator: str | None = Field(default=None, max_length=200)
    data_julgamento: date | None = None
    data_publicacao: date | None = None
    ementa: str | None = None
    fundamento_relevante: str | None = None
    resultado: str | None = Field(default=None, max_length=30)
    tema: str | None = Field(default=None, max_length=300)
    url_oficial: str | None = Field(default=None, max_length=2000)
    publicidade: str = Field(default="publico", max_length=20)
    dados_minimizados: bool = True


class PrecedenteDecisaoIn(BaseModel):
    status: str = Field(pattern="^(validado|revisar|superado|bloqueado)$")
    justificativa: str = Field(min_length=10, max_length=4000)


class TeseIn(BaseModel):
    chave_canonica: str | None = Field(default=None, max_length=180)
    titulo: str = Field(min_length=5, max_length=500)
    area: str = Field(min_length=2, max_length=80)
    subarea: str | None = Field(default=None, max_length=120)
    instituto: str | None = Field(default=None, max_length=120)
    tema: str | None = Field(default=None, max_length=200)
    subtema: str | None = Field(default=None, max_length=200)
    situacao_fatica: str | None = None
    tipo: str = Field(default="material", max_length=30)
    lado: str = Field(default="ambos", max_length=10)
    parte_favorecida: str | None = Field(default=None, max_length=80)
    procedimento: str | None = Field(default=None, max_length=100)
    instancia: str | None = Field(default=None, max_length=40)
    tese_principal: str = Field(min_length=20)
    fundamento_resumido: str | None = None
    argumento_juridico: str | None = None
    raciocinio_juridico: str | None = None
    pressupostos: list[Any] = Field(default_factory=list)
    fatos_necessarios: list[Any] = Field(default_factory=list)
    elementos_demonstrar: list[Any] = Field(default_factory=list)
    fatos_impeditivos: list[Any] = Field(default_factory=list)
    excecoes: list[Any] = Field(default_factory=list)
    fundamentacao_legal: list[Any] = Field(default_factory=list)
    estrategia: dict[str, Any] = Field(default_factory=dict)
    provas_necessarias: list[Any] = Field(default_factory=list)
    documentos_necessarios: list[Any] = Field(default_factory=list)
    argumento_adversario: str | None = None
    resposta_adversaria: str | None = None
    riscos: list[Any] = Field(default_factory=list)


class TeseValidacaoIn(BaseModel):
    snapshot_id: str | None = None
    precedent_id: str | None = None
    justificativa: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def exige_fonte(self):
        if not self.snapshot_id and not self.precedent_id:
            raise ValueError("snapshot_id ou precedent_id é obrigatório")
        if self.snapshot_id and self.precedent_id:
            raise ValueError("informe somente uma fonte por evento")
        return self


class TeseDecisaoIn(BaseModel):
    status: str = Field(pattern="^(validada|revisada|arquivada)$")
    justificativa: str = Field(min_length=10, max_length=4000)


class TesePrecedenteIn(BaseModel):
    precedent_id: str
    relacao: str = Field(pattern="^(favoravel|contraria|qualificada|distinguishing)$")
    trecho_relevante: str | None = None
    observacao: str | None = None


class LoteIn(BaseModel):
    source_id: str
    lote_codigo: str = Field(min_length=1, max_length=100)
    checkpoint: dict[str, Any] | None = None


def _is_staff(user: User) -> bool:
    return user.role.value in EQUIPE_JURIDICA


def _can_curate(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["advogado"]


def _can_approve(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _require_staff(user: User) -> None:
    if not _is_staff(user):
        raise HTTPException(403, "Acesso restrito à equipe jurídica")


def _require_curator(user: User) -> None:
    if not _can_curate(user):
        raise HTTPException(403, "Permissão de curadoria insuficiente")


def _require_approver(user: User) -> None:
    if not _can_approve(user):
        raise HTTPException(403, "Aprovação reservada a sócio ou administrador")


def _source_out(source: LegalSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "slug": source.slug,
        "nome": source.nome,
        "categoria": source.categoria,
        "autoridade": source.autoridade,
        "tipo_acesso": source.tipo_acesso,
        "url_base": source.url_base,
        "url_validacao": source.url_validacao,
        "url_termos": source.url_termos,
        "status": source.status,
        "exige_autenticacao": source.exige_autenticacao,
        "permite_uso_derivado": source.permite_uso_derivado,
        "ultima_verificacao": source.ultima_verificacao.isoformat() if source.ultima_verificacao else None,
    }


def _precedent_out(precedent: LegalPrecedent) -> dict[str, Any]:
    return {
        "id": precedent.id,
        "source_id": precedent.source_id,
        "snapshot_id": precedent.snapshot_id,
        "chave_origem": precedent.chave_origem,
        "tribunal": precedent.tribunal,
        "instancia": precedent.instancia,
        "orgao_julgador": precedent.orgao_julgador,
        "classe_processual": precedent.classe_processual,
        "numero_processo": precedent.numero_processo,
        "relator": precedent.relator,
        "data_julgamento": precedent.data_julgamento.isoformat() if precedent.data_julgamento else None,
        "data_publicacao": precedent.data_publicacao.isoformat() if precedent.data_publicacao else None,
        "ementa": precedent.ementa,
        "fundamento_relevante": precedent.fundamento_relevante,
        "resultado": precedent.resultado,
        "tema": precedent.tema,
        "url_oficial": precedent.url_oficial,
        "hash_conteudo": precedent.hash_conteudo,
        "status": precedent.status,
        "publicidade": precedent.publicidade,
        "dados_minimizados": precedent.dados_minimizados,
        "recomendavel": precedente_pode_ser_recomendado(
            precedent.status,
            precedent.url_oficial,
            precedent.publicidade,
            precedent.dados_minimizados,
        ),
    }


def _thesis_out(thesis: LegalThesis) -> dict[str, Any]:
    return {
        "id": thesis.id,
        "chave_canonica": thesis.chave_canonica,
        "titulo": thesis.titulo,
        "area": thesis.area,
        "subarea": thesis.subarea,
        "instituto": thesis.instituto,
        "tema": thesis.tema,
        "subtema": thesis.subtema,
        "situacao_fatica": thesis.situacao_fatica,
        "tipo": thesis.tipo,
        "lado": thesis.lado,
        "parte_favorecida": thesis.parte_favorecida,
        "procedimento": thesis.procedimento,
        "instancia": thesis.instancia,
        "tese_principal": thesis.tese_principal,
        "fundamento_resumido": thesis.fundamento_resumido,
        "argumento_juridico": thesis.argumento_juridico,
        "raciocinio_juridico": thesis.raciocinio_juridico,
        "pressupostos": thesis.pressupostos or [],
        "fatos_necessarios": thesis.fatos_necessarios or [],
        "elementos_demonstrar": thesis.elementos_demonstrar or [],
        "fatos_impeditivos": thesis.fatos_impeditivos or [],
        "excecoes": thesis.excecoes or [],
        "fundamentacao_legal": thesis.fundamentacao_legal or [],
        "estrategia": thesis.estrategia or {},
        "provas_necessarias": thesis.provas_necessarias or [],
        "documentos_necessarios": thesis.documentos_necessarios or [],
        "argumento_adversario": thesis.argumento_adversario,
        "resposta_adversaria": thesis.resposta_adversaria,
        "riscos": thesis.riscos or [],
        "score_forca": thesis.score_forca,
        "status": thesis.status,
        "versao": thesis.versao,
        "vigente": thesis.vigente,
        "recomendavel": tese_pode_ser_recomendada(thesis.status, thesis.vigente),
        "origem": thesis.origem,
        "criada_em": thesis.criada_em.isoformat() if thesis.criada_em else None,
        "revisada_em": thesis.revisada_em.isoformat() if thesis.revisada_em else None,
    }


@router.get("/fontes")
async def listar_fontes(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_staff(cu)
    fontes = list((await db.execute(select(LegalSource).order_by(LegalSource.nome))).scalars().all())
    return {"total": len(fontes), "fontes": [_source_out(f) for f in fontes]}


@router.post("/fontes", status_code=201)
async def criar_fonte(
    req: FonteIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_approver(cu)
    slug = normalizar_chave(req.slug)[:80]
    existing = (await db.execute(select(LegalSource).where(LegalSource.slug == slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Fonte já cadastrada")
    fonte = LegalSource(id=str(uuid4()), slug=slug, **req.model_dump(exclude={"slug"}))
    db.add(fonte)
    await db.commit()
    return _source_out(fonte)


@router.post("/fontes/{source_id}/snapshots", status_code=201)
async def criar_snapshot(
    source_id: str,
    req: SnapshotIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_curator(cu)
    fonte = (await db.execute(select(LegalSource).where(LegalSource.id == source_id))).scalar_one_or_none()
    if fonte is None:
        raise HTTPException(404, "Fonte não encontrada")
    conteudo_hash = hash_conteudo(req.conteudo_normalizado)
    existente = (await db.execute(
        select(LegalSourceSnapshot).where(
            LegalSourceSnapshot.source_id == source_id,
            LegalSourceSnapshot.chave_origem == req.chave_origem,
            LegalSourceSnapshot.hash_conteudo == conteudo_hash,
        )
    )).scalar_one_or_none()
    if existente:
        return {"criado": False, "duplicata": True, "id": existente.id, "hash_conteudo": conteudo_hash}
    snapshot = LegalSourceSnapshot(
        id=str(uuid4()),
        source_id=source_id,
        chave_origem=req.chave_origem,
        titulo=req.titulo,
        conteudo_normalizado=req.conteudo_normalizado,
        hash_conteudo=conteudo_hash,
        url_origem=req.url_origem,
        data_publicacao=req.data_publicacao,
        capturado_em=req.capturado_em or datetime.now(timezone.utc),
        metadados=req.metadados,
    )
    db.add(snapshot)
    await db.commit()
    return {"criado": True, "duplicata": False, "id": snapshot.id, "hash_conteudo": conteudo_hash}


@router.post("/precedentes", status_code=201)
async def criar_precedente(
    req: PrecedenteIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_curator(cu)
    fonte = (await db.execute(select(LegalSource).where(LegalSource.id == req.source_id))).scalar_one_or_none()
    if fonte is None:
        raise HTTPException(404, "Fonte não encontrada")
    snapshot = (await db.execute(select(LegalSourceSnapshot).where(
        LegalSourceSnapshot.id == req.snapshot_id,
        LegalSourceSnapshot.source_id == req.source_id,
    ))).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(422, "Snapshot não pertence à fonte informada")
    existing = (await db.execute(select(LegalPrecedent).where(
        LegalPrecedent.source_id == req.source_id,
        LegalPrecedent.chave_origem == req.chave_origem,
    ))).scalar_one_or_none()
    if existing:
        return {"criado": False, "duplicata": True, "id": existing.id, "status": existing.status}
    precedent = LegalPrecedent(
        id=str(uuid4()),
        hash_conteudo=hash_conteudo(" ".join(x for x in (req.ementa, req.fundamento_relevante) if x)),
        status="identificado",
        **req.model_dump(),
    )
    db.add(precedent)
    await db.commit()
    return {"criado": True, "duplicata": False, "precedente": _precedent_out(precedent)}


@router.post("/precedentes/{precedent_id}/decisao")
async def decidir_precedente(
    precedent_id: str,
    req: PrecedenteDecisaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_approver(cu)
    precedent = (await db.execute(select(LegalPrecedent).where(LegalPrecedent.id == precedent_id))).scalar_one_or_none()
    if precedent is None:
        raise HTTPException(404, "Precedente não encontrado")
    if req.status == "validado" and not precedente_pode_ser_recomendado(
        "validado", precedent.url_oficial, precedent.publicidade, precedent.dados_minimizados
    ):
        raise HTTPException(409, "Precedente validado exige URL oficial, publicidade e dados minimizados")
    anterior = precedent.status
    precedent.status = req.status
    db.add(LegalThesisValidationEvent(
        id=str(uuid4()),
        precedent_id=precedent.id,
        acao="validacao_precedente",
        status_anterior=anterior,
        status_novo=req.status,
        justificativa=req.justificativa,
        reviewer_id=cu.id,
    ))
    await db.commit()
    return _precedent_out(precedent)


@router.get("")
async def listar_teses_nacionais(
    busca: str | None = Query(default=None, min_length=2),
    area: str | None = Query(default=None),
    lado: str | None = Query(default=None),
    status: str = Query(default="validada,revisada"),
    incluir_rascunhos: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_staff(cu)
    permitidos = {"coletada", "em_analise", "parcialmente_validada", "validada", "revisada", "desatualizada", "superada", "arquivada"}
    statuses = {item.strip() for item in status.split(",") if item.strip()}
    if not statuses or not statuses <= permitidos:
        raise HTTPException(422, "Status de tese inválido")
    if not _can_curate(cu) or not incluir_rascunhos:
        statuses &= {"validada", "revisada"}
    if not statuses:
        return {"total": 0, "items": []}
    stmt = select(LegalThesis).where(
        LegalThesis.vigente.is_(True),
        LegalThesis.status.in_(statuses),
    )
    if area:
        stmt = stmt.where(LegalThesis.area.ilike(f"%{area}%"))
    if lado:
        stmt = stmt.where(LegalThesis.lado == lado)
    if busca:
        termo = f"%{busca}%"
        stmt = stmt.where(or_(
            LegalThesis.titulo.ilike(termo),
            LegalThesis.tese_principal.ilike(termo),
            LegalThesis.fundamento_resumido.ilike(termo),
            LegalThesis.tema.ilike(termo),
        ))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    teses = list((await db.execute(
        stmt.order_by(LegalThesis.score_forca.desc(), LegalThesis.updated_at.desc())
        .offset(offset).limit(limit)
    )).scalars().all())
    return {"total": total, "limit": limit, "offset": offset, "items": [_thesis_out(t) for t in teses]}


@router.post("", status_code=201)
async def criar_tese_nacional(
    req: TeseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_curator(cu)
    chave = normalizar_chave(req.chave_canonica or f"{req.area}-{req.tema or req.titulo}")[:180]
    duplicate = (await db.execute(select(LegalThesis).where(LegalThesis.chave_canonica == chave))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(409, "Tese equivalente já cadastrada; revisar antes de duplicar")
    thesis = LegalThesis(
        id=str(uuid4()),
        chave_canonica=chave,
        status="coletada",
        origem="manual",
        created_by=cu.id,
        **req.model_dump(exclude={"chave_canonica"}),
    )
    db.add(thesis)
    await db.flush()
    db.add(LegalThesisVersion(
        id=str(uuid4()),
        thesis_id=thesis.id,
        versao=1,
        snapshot=req.model_dump(mode="json"),
        motivo_alteracao="Registro inicial da tese; ainda não validada.",
        created_by=cu.id,
    ))
    db.add(LegalThesisValidationEvent(
        id=str(uuid4()),
        thesis_id=thesis.id,
        acao="coleta",
        status_anterior=None,
        status_novo="coletada",
        justificativa="Registro inicial; exige fonte e revisão humana.",
        reviewer_id=cu.id,
    ))
    await db.commit()
    return _thesis_out(thesis)


@router.get("/{thesis_id}")
async def obter_tese_nacional(
    thesis_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_staff(cu)
    thesis = (await db.execute(select(LegalThesis).where(LegalThesis.id == thesis_id))).scalar_one_or_none()
    if thesis is None:
        raise HTTPException(404, "Tese nacional não encontrada")
    links = list((await db.execute(select(LegalThesisPrecedent).where(
        LegalThesisPrecedent.thesis_id == thesis_id
    ))).scalars().all())
    precedents: list[dict[str, Any]] = []
    for link in links:
        precedent = (await db.execute(select(LegalPrecedent).where(LegalPrecedent.id == link.precedent_id))).scalar_one_or_none()
        if precedent:
            item = _precedent_out(precedent)
            item["relacao"] = link.relacao
            item["trecho_relevante"] = link.trecho_relevante
            item["observacao"] = link.observacao
            precedents.append(item)
    result = _thesis_out(thesis)
    result["precedentes"] = precedents
    return result


@router.post("/{thesis_id}/validacoes")
async def registrar_validacao_tese(
    thesis_id: str,
    req: TeseValidacaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_curator(cu)
    thesis = (await db.execute(select(LegalThesis).where(LegalThesis.id == thesis_id))).scalar_one_or_none()
    if thesis is None:
        raise HTTPException(404, "Tese nacional não encontrada")
    if req.snapshot_id:
        target = (await db.execute(select(LegalSourceSnapshot).where(LegalSourceSnapshot.id == req.snapshot_id))).scalar_one_or_none()
        if target is None:
            raise HTTPException(404, "Snapshot não encontrado")
        target.status = "validado"
        target.vigente = True
        acao = "validacao_fonte"
    else:
        target = (await db.execute(select(LegalPrecedent).where(LegalPrecedent.id == req.precedent_id))).scalar_one_or_none()
        if target is None:
            raise HTTPException(404, "Precedente não encontrado")
        if target.status != "validado":
            raise HTTPException(409, "O precedente precisa estar validado antes de sustentar uma tese")
        acao = "validacao_precedente"
    event = LegalThesisValidationEvent(
        id=str(uuid4()),
        thesis_id=thesis.id,
        snapshot_id=req.snapshot_id,
        precedent_id=req.precedent_id,
        acao=acao,
        status_anterior=thesis.status,
        status_novo=thesis.status,
        justificativa=req.justificativa,
        reviewer_id=cu.id,
    )
    db.add(event)
    await db.commit()
    return {"registrado": True, "evento_id": event.id, "acao": acao, "status_tese": thesis.status}


@router.post("/{thesis_id}/precedentes")
async def vincular_precedente_tese(
    thesis_id: str,
    req: TesePrecedenteIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_curator(cu)
    thesis = (await db.execute(select(LegalThesis).where(LegalThesis.id == thesis_id))).scalar_one_or_none()
    precedent = (await db.execute(select(LegalPrecedent).where(LegalPrecedent.id == req.precedent_id))).scalar_one_or_none()
    if thesis is None or precedent is None:
        raise HTTPException(404, "Tese ou precedente não encontrado")
    existing = (await db.execute(select(LegalThesisPrecedent).where(
        LegalThesisPrecedent.thesis_id == thesis_id,
        LegalThesisPrecedent.precedent_id == req.precedent_id,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Precedente já vinculado à tese")
    link = LegalThesisPrecedent(id=str(uuid4()), thesis_id=thesis_id, **req.model_dump())
    db.add(link)
    await db.commit()
    return {"vinculado": True, "id": link.id, "precedente_status": precedent.status}


@router.post("/{thesis_id}/decisao")
async def decidir_tese_nacional(
    thesis_id: str,
    req: TeseDecisaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_approver(cu)
    thesis = (await db.execute(select(LegalThesis).where(LegalThesis.id == thesis_id))).scalar_one_or_none()
    if thesis is None:
        raise HTTPException(404, "Tese nacional não encontrada")
    if req.status in {"validada", "revisada"}:
        eventos = list((await db.execute(select(LegalThesisValidationEvent).where(
            LegalThesisValidationEvent.thesis_id == thesis_id,
            LegalThesisValidationEvent.acao.in_(("validacao_fonte", "validacao_precedente", "revisao_humana")),
            or_(
                LegalThesisValidationEvent.snapshot_id.is_not(None),
                LegalThesisValidationEvent.precedent_id.is_not(None),
            ),
        ))).scalars().all())
        fonte_valida = False
        for evento in eventos:
            if evento.snapshot_id:
                snapshot = (await db.execute(select(LegalSourceSnapshot).where(
                    LegalSourceSnapshot.id == evento.snapshot_id,
                    LegalSourceSnapshot.status == "validado",
                    LegalSourceSnapshot.vigente.is_(True),
                ))).scalar_one_or_none()
                fonte_valida = fonte_valida or snapshot is not None
            if evento.precedent_id:
                precedent = (await db.execute(select(LegalPrecedent).where(
                    LegalPrecedent.id == evento.precedent_id,
                    LegalPrecedent.status == "validado",
                ))).scalar_one_or_none()
                fonte_valida = fonte_valida or precedent is not None
        if not fonte_valida:
            raise HTTPException(409, "Tese não pode ser publicada sem fonte rastreável validada")
    anterior = thesis.status
    thesis.status = req.status
    if req.status in {"validada", "revisada"}:
        thesis.revisado_por = cu.id
        thesis.revisada_em = datetime.now(timezone.utc)
    db.add(LegalThesisValidationEvent(
        id=str(uuid4()),
        thesis_id=thesis.id,
        acao="aprovacao" if req.status in {"validada", "revisada"} else "arquivamento",
        status_anterior=anterior,
        status_novo=req.status,
        justificativa=req.justificativa,
        reviewer_id=cu.id,
    ))
    await db.commit()
    return _thesis_out(thesis)


@router.post("/lotes", status_code=201)
async def abrir_lote(
    req: LoteIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Abre somente o checkpoint; a coleta continua sendo executada por conector autorizado."""
    _require_approver(cu)
    source = (await db.execute(select(LegalSource).where(LegalSource.id == req.source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Fonte não encontrada")
    run = LegalIngestionRun(
        id=str(uuid4()),
        source_id=req.source_id,
        lote_codigo=req.lote_codigo,
        iniciado_em=datetime.now(timezone.utc),
        checkpoint=req.checkpoint,
        executado_por=cu.id,
    )
    db.add(run)
    await db.commit()
    return {"id": run.id, "source_id": run.source_id, "lote_codigo": run.lote_codigo, "status": run.status}
