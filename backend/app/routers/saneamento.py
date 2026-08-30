# ── app/routers/saneamento.py ────────────────────────────────────────────────
# Módulo de saneamento de base processual. Todas as rotas exigem autenticação
# + RBAC (nenhuma rota pública — CLAUDE.md, regra 4). Leitura é liberada a
# partir de advogado_auxiliar; escrita de decisão/aplicação de plano exige
# advogado ou superior — regra de negócio inegociável do PROMPT 1 (passo 5):
# o módulo SINALIZA, quem decide é sempre um advogado, nunca um job.
#
# ESCOPO POR TITULARIDADE DE CASO (achado ALTO da auditoria de segurança):
# o resto do EJC trata advogado/advogado_auxiliar como papéis NÃO-gestão,
# restritos aos casos em que atuam (responsável/auxiliar) — ver
# app/core/ownership.py::verificar_acesso_caso e o mesmo filtro em
# app/routers/movimentos.py. Este módulo replica esse gate: as tabelas de
# saneamento só guardam `numero_cnj` (não `case_id`), então o vínculo é
# resolvido comparando os dígitos de `Case.numero_processo` (tolerante à
# máscara) contra o `numero_cnj` normalizado.
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.saneamento import (
    Divergencia,
    ExcecaoNumero,
    IndicativoEncerramento,
    PlanoDedup,
)
from app.models.user import User
from app.schemas.saneamento import AplicarDedupIn, DecidirIndicativoIn
from app.services.saneamento.reconciliacao import TipoDivergencia
from app.services.saneamento.tpu import carregar_catalogo

router = APIRouter(prefix="/saneamento", tags=["Saneamento processual"])

_LEITURA = require_roles(["advogado_auxiliar", "advogado", "socio", "admin", "superadmin"])
_DECISAO = require_roles(["advogado", "socio", "admin", "superadmin"])


def _numero_cnj_do_caso() -> ColumnElement[str]:
    """Dígitos de Case.numero_processo, para comparar com numero_cnj (já
    normalizado a 20 dígitos nas tabelas de saneamento) — tolerante à
    máscara (NNNNNNN-DD.AAAA.J.TR.OOOO) que numero_processo pode carregar."""
    return func.regexp_replace(Case.numero_processo, r"\D", "", "g")


def _filtro_escopo_caso(query, coluna_numero_cnj: ColumnElement[str], cu: User):
    """Restringe a consulta aos registros cujo numero_cnj está ligado a um
    caso que o usuário pode ver. Gestão (socio+) não é filtrada — visão
    firm-wide. Equipe só vê caso em que é responsável/auxiliar, ou caso
    ÓRFÃO (mesma salvaguarda anti-lockout de movimentos.py/ownership.py —
    sem isso um caso sem dono ficaria invisível a todo mundo). numero_cnj
    sem NENHUM caso correspondente no sistema fica invisível à equipe
    (nega por padrão)."""
    if is_gestao(cu):
        return query
    vinculo = exists().where(
        _numero_cnj_do_caso() == coluna_numero_cnj,
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
            (Case.advogado_responsavel_id.is_(None))
            & (Case.advogado_auxiliar_id.is_(None)),
        ),
    )
    return query.where(vinculo)


async def _resolver_caso_do_numero(db: AsyncSession, numero_cnj: str) -> Case | None:
    """Caso vinculado a um numero_cnj — primeiro que casar (numeração é
    única na prática; join tolerante à máscara de numero_processo)."""
    return (
        await db.execute(
            select(Case).where(
                _numero_cnj_do_caso() == numero_cnj, Case.deleted_at.is_(None)
            )
        )
    ).scalars().first()


def _pode_agir_no_caso(cu: User, case: Case | None) -> bool:
    """Gate de ESCRITA (decidir/aplicar): gestão sempre passa. Equipe só se
    vinculada ao caso, ou caso órfão (escape-hatch de gestão continua
    disponível — não é lockout). numero_cnj sem caso correspondente no
    sistema é negado à equipe: só gestão decide nesse caso."""
    if is_gestao(cu):
        return True
    if case is None:
        return False
    if case.advogado_responsavel_id == cu.id or case.advogado_auxiliar_id == cu.id:
        return True
    return case.advogado_responsavel_id is None and case.advogado_auxiliar_id is None


@router.get("/excecoes")
async def listar_excecoes(
    resolvido: bool = Query(False, description="False = fila pendente (default)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(_LEITURA),
):
    """Fila de números que falharam na validação do dígito verificador —
    ERRO DE DIGITAÇÃO, nunca duplicata (regra de negócio inegociável).

    Sem escopo por titularidade de caso: por definição, um número aqui AINDA
    não foi validado (nem normalizado) o bastante para ser comparado com
    segurança contra `Case.numero_processo` — `numero_corrigido` só existe
    depois de resolvido, e a maioria das linhas pendentes tem esse campo
    NULL. Filtrar por caso esconderia a fila inteira da equipe sem ganho de
    segurança real: o conteúdo exposto é só "este número não bate o dígito
    verificador", não dado de mérito do processo."""
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
    cu: User = Depends(_LEITURA),
):
    """Plano de deduplicação pendente. Nada aqui já foi aplicado à base."""
    q = (
        select(PlanoDedup)
        .where(PlanoDedup.aplicado == aplicado)
        .order_by(PlanoDedup.criado_em.desc())
    )
    q = _filtro_escopo_caso(q, PlanoDedup.numero_cnj, cu)
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

    caso = await _resolver_caso_do_numero(db, plano.numero_cnj)
    if not _pode_agir_no_caso(cu, caso):
        raise HTTPException(status_code=403, detail="Sem acesso ao caso deste número CNJ.")

    if plano.tipo != "duplicata":
        raise HTTPException(
            status_code=422,
            detail=(
                f"tipo='{plano.tipo}' não pode ser fundido por esta rota — "
                "apenas 'duplicata' é colapsável; multi_grau/conexo_sugerido "
                "exigem relacionamento manual, nunca fusão automática."
            ),
        )

    # UPDATE condicionado ao estado (aplicado=False) em vez de checar antes e
    # escrever depois: fecha a corrida entre duas requisições concorrentes
    # decidindo o mesmo plano (achado da auditoria de segurança) — rowcount
    # 0 significa que outra requisição já aplicou entre o SELECT e aqui.
    resultado = await db.execute(
        update(PlanoDedup)
        .where(PlanoDedup.id == plano_id, PlanoDedup.aplicado.is_(False))
        .values(aplicado=True, aplicado_por=cu.id, aplicado_em=datetime.now(timezone.utc))
    )
    if resultado.rowcount == 0:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Este item já foi aplicado.")

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
    cu: User = Depends(_LEITURA),
):
    """Candidatos a encerramento — sinalização automática, nunca decisão."""
    q = select(IndicativoEncerramento).where(IndicativoEncerramento.candidato.is_(True))
    if somente_pendentes:
        q = q.where(IndicativoEncerramento.decisao.is_(None))
    q = _filtro_escopo_caso(q, IndicativoEncerramento.numero_cnj, cu)
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

    caso = await _resolver_caso_do_numero(db, indicativo.numero_cnj)
    if not _pode_agir_no_caso(cu, caso):
        raise HTTPException(status_code=403, detail="Sem acesso ao caso deste número CNJ.")

    agora = datetime.now(timezone.utc)
    # UPDATE condicionado a decisao IS NULL: mesma correção de corrida do
    # aplicar_duplicata — a decisão sobre encerrar um processo é irreversível
    # na prática, então a garantia de "só decide uma vez" tem que vir do
    # próprio UPDATE, não de um SELECT anterior que pode ter ficado obsoleto.
    resultado = await db.execute(
        update(IndicativoEncerramento)
        .where(IndicativoEncerramento.id == indicativo_id, IndicativoEncerramento.decisao.is_(None))
        .values(
            decisao=body.decisao,
            decidido_por=cu.id,
            decidido_em=agora,
            justificativa=body.justificativa,
        )
    )
    if resultado.rowcount == 0:
        await db.rollback()
        await db.refresh(indicativo)
        raise HTTPException(
            status_code=409,
            detail=f"Indicativo já decidido ({indicativo.decisao}) por {indicativo.decidido_por}.",
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
    cu: User = Depends(_LEITURA),
):
    """Painel de divergências base interna × DataJud. Todo item é apontamento
    — nenhuma correção automática é aplicada pela reconciliação.

    `SIGILO` (nivelSigilo>0) é tratamento restrito por definição
    (reconciliacao.py) — fica de fora do relatório amplo para quem não é
    gestão (achado da auditoria de segurança)."""
    q = (
        select(Divergencia)
        .where(Divergencia.tratada == tratada)
        .order_by(Divergencia.criado_em.desc())
    )
    q = _filtro_escopo_caso(q, Divergencia.numero_cnj, cu)
    if not is_gestao(cu):
        q = q.where(Divergencia.tipo != TipoDivergencia.SIGILO.value)
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

    Agregado sobre o catálogo TPU (não há numero_cnj/caso aqui — nada a
    escopar por titularidade). Enquanto a cobertura estiver baixa, o
    indicativo de encerramento opera em modo degradado (menos sinalização,
    nunca sinalização a mais).
    """
    catalogo = await carregar_catalogo(db)
    return catalogo.cobertura
