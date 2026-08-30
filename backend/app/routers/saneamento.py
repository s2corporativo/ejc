# ── app/routers/saneamento.py ────────────────────────────────────────────────
# Módulo de saneamento de base processual. Todas as rotas exigem autenticação
# + RBAC (nenhuma rota pública — CLAUDE.md, regra 4). Leitura é liberada a
# partir de advogado_auxiliar; escrita de decisão/aplicação de plano exige
# advogado ou superior — regra de negócio inegociável do PROMPT 1 (passo 5):
# o módulo SINALIZA, quem decide é sempre um advogado, nunca um job.
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.saneamento import (
    Divergencia,
    ExcecaoNumero,
    IndicativoEncerramento,
    PlanoDedup,
)
from app.models.user import User
from app.schemas.saneamento import AplicarDedupIn, DecidirIndicativoIn
from app.services.saneamento.tpu import carregar_catalogo

router = APIRouter(prefix="/saneamento", tags=["Saneamento processual"])

_LEITURA = require_roles(["advogado_auxiliar", "advogado", "socio", "admin", "superadmin"])
_DECISAO = require_roles(["advogado", "socio", "admin", "superadmin"])


@router.get("/excecoes")
async def listar_excecoes(
    resolvido: bool = Query(False, description="False = fila pendente (default)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Fila de números que falharam na validação do dígito verificador —
    ERRO DE DIGITAÇÃO, nunca duplicata (regra de negócio inegociável)."""
    q = (
        select(ExcecaoNumero)
        .where(ExcecaoNumero.resolvido == resolvido)
        .order_by(ExcecaoNumero.criado_em.desc())
    )
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return [
        {
            "id": r.id, "id_interno": r.id_interno, "numero_bruto": r.numero_bruto,
            "motivo": r.motivo, "resolvido": r.resolvido,
            "resolvido_por": r.resolvido_por, "resolvido_em": r.resolvido_em,
            "numero_corrigido": r.numero_corrigido, "criado_em": r.criado_em,
        }
        for r in rows
    ]


@router.get("/duplicatas")
async def listar_duplicatas(
    aplicado: bool = Query(False, description="False = plano pendente (default)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Plano de deduplicação pendente. Nada aqui já foi aplicado à base."""
    q = (
        select(PlanoDedup)
        .where(PlanoDedup.aplicado == aplicado)
        .order_by(PlanoDedup.criado_em.desc())
    )
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return [
        {
            "id": r.id, "numero_cnj": r.numero_cnj,
            "id_interno_principal": r.id_interno_principal,
            "ids_absorvidos": r.ids_absorvidos, "tipo": r.tipo,
            "aplicado": r.aplicado, "aplicado_por": r.aplicado_por,
            "aplicado_em": r.aplicado_em, "criado_em": r.criado_em,
        }
        for r in rows
    ]


@router.post("/duplicatas/{plano_id}/aplicar")
async def aplicar_duplicata(
    plano_id: int,
    body: AplicarDedupIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_DECISAO),
):
    """Marca um item do plano de deduplicação como aplicado.

    Esta rota registra a decisão (quem/quando); a fusão efetiva dos registros
    da base interna (cases/processos) é responsabilidade do chamador —
    `tipo='multi_grau'` ou `'conexo_sugerido'` NUNCA devem ser fundidos
    (regra de negócio inegociável), só relacionados/sugeridos.
    """
    if not body.confirmar:
        raise HTTPException(status_code=422, detail="Confirmação explícita exigida (confirmar=true).")

    plano = (
        await db.execute(select(PlanoDedup).where(PlanoDedup.id == plano_id))
    ).scalar_one_or_none()
    if plano is None:
        raise HTTPException(status_code=404, detail="Plano de deduplicação não encontrado.")
    if plano.aplicado:
        raise HTTPException(status_code=409, detail="Este item já foi aplicado.")
    if plano.tipo != "duplicata":
        raise HTTPException(
            status_code=422,
            detail=(
                f"tipo='{plano.tipo}' não pode ser fundido por esta rota — "
                "apenas 'duplicata' é colapsável; multi_grau/conexo_sugerido "
                "exigem relacionamento manual, nunca fusão automática."
            ),
        )

    await db.execute(
        update(PlanoDedup)
        .where(PlanoDedup.id == plano_id)
        .values(aplicado=True, aplicado_por=cu.id, aplicado_em=datetime.now(timezone.utc))
    )
    await criar_audit_log(
        db, cu.id, cu.role.value,
        "APLICAR", "saneamento.plano_dedup", str(plano_id),
        dados_depois={"numero_cnj": plano.numero_cnj, "tipo": plano.tipo},
    )
    await db.commit()
    return {"id": plano_id, "aplicado": True}


@router.get("/indicativos")
async def listar_indicativos(
    somente_pendentes: bool = Query(True, description="True = sem decisão humana ainda."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Candidatos a encerramento — sinalização automática, nunca decisão."""
    q = select(IndicativoEncerramento).where(IndicativoEncerramento.candidato.is_(True))
    if somente_pendentes:
        q = q.where(IndicativoEncerramento.decisao.is_(None))
    q = q.order_by(IndicativoEncerramento.avaliado_em.desc())
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return [
        {
            "id": r.id, "numero_cnj": r.numero_cnj, "candidato": r.candidato,
            "confianca": r.confianca, "motivos": r.motivos,
            "dias_de_silencio": r.dias_de_silencio,
            "movimento_terminativo": r.movimento_terminativo,
            "avaliado_em": r.avaliado_em, "decisao": r.decisao,
            "decidido_por": r.decidido_por, "decidido_em": r.decidido_em,
            "justificativa": r.justificativa,
            "exige_revisao_humana": True,
        }
        for r in rows
    ]


@router.post("/indicativos/{indicativo_id}/decidir")
async def decidir_indicativo(
    indicativo_id: int,
    body: DecidirIndicativoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_DECISAO),
):
    """Grava a decisão do advogado sobre um indicativo. ÚNICO caminho de
    escrita da coluna `decisao` — nenhum job/varredura grava aqui."""
    indicativo = (
        await db.execute(
            select(IndicativoEncerramento).where(IndicativoEncerramento.id == indicativo_id)
        )
    ).scalar_one_or_none()
    if indicativo is None:
        raise HTTPException(status_code=404, detail="Indicativo não encontrado.")
    if indicativo.decisao is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Indicativo já decidido ({indicativo.decisao}) por {indicativo.decidido_por}.",
        )

    agora = datetime.now(timezone.utc)
    await db.execute(
        update(IndicativoEncerramento)
        .where(IndicativoEncerramento.id == indicativo_id)
        .values(
            decisao=body.decisao,
            decidido_por=cu.id,
            decidido_em=agora,
            justificativa=body.justificativa,
        )
    )
    await criar_audit_log(
        db, cu.id, cu.role.value,
        "DECIDIR", "saneamento.indicativo_encerramento", str(indicativo_id),
        dados_depois={"numero_cnj": indicativo.numero_cnj, "decisao": body.decisao},
    )
    await db.commit()
    return {"id": indicativo_id, "decisao": body.decisao, "decidido_por": cu.id, "decidido_em": agora}


@router.get("/divergencias")
async def listar_divergencias(
    tratada: bool = Query(False, description="False = painel pendente (default)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Painel de divergências base interna × DataJud. Todo item é apontamento
    — nenhuma correção automática é aplicada pela reconciliação."""
    q = (
        select(Divergencia)
        .where(Divergencia.tratada == tratada)
        .order_by(Divergencia.criado_em.desc())
    )
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return [
        {
            "id": r.id, "numero_cnj": r.numero_cnj, "tipo": r.tipo,
            "valor_interno": r.valor_interno, "valor_datajud": r.valor_datajud,
            "observacao": r.observacao, "tratada": r.tratada,
            "tratada_por": r.tratada_por, "tratada_em": r.tratada_em,
            "criado_em": r.criado_em,
        }
        for r in rows
    ]


@router.get("/tpu/cobertura")
async def cobertura_tpu(
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Diagnóstico: quantos códigos TPU já receberam revisão jurídica.

    Enquanto a cobertura estiver baixa, o indicativo de encerramento opera em
    modo degradado (menos sinalização, nunca sinalização a mais).
    """
    catalogo = await carregar_catalogo(db)
    return catalogo.cobertura
