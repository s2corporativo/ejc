# ── app/routers/saneamento.py ────────────────────────────────────────────────
# Módulo de saneamento de base processual. Todas as rotas exigem autenticação
# + RBAC (nenhuma rota pública — CLAUDE.md, regra 4). Leitura é liberada a
# partir de advogado_auxiliar; escrita de decisão/aplicação de plano exige
# advogado ou superior — regra de negócio inegociável do PROMPT 1 (passo 5):
# o módulo SINALIZA, quem decide é sempre um advogado, nunca um job.
#
# ESCOPO POR TITULARIDADE DE CASO (achado ALTO da auditoria de segurança +
# revisão de código): o resto do EJC trata advogado/advogado_auxiliar como
# papéis NÃO-gestão, restritos aos casos em que atuam. As tabelas de
# saneamento só guardam `numero_cnj` (não `case_id`), então o vínculo é
# resolvido via `Process.numero_cnj` (fonte canônica — 1 Caso : N Processos,
# principal + acessórios) com fallback em `Case.numero_processo` (espelho
# legado, só do processo principal — ver processo_service.py). Resolver só
# por `Case.numero_processo` (versão anterior) deixava processo acessório
# invisível/inacionável para o advogado do caso.
#
# Leitura (`_filtro_escopo_caso`) e visão firm-wide de RELATÓRIO usam
# `pode_ver_todos` (admin+) — o limiar mais alto que `is_gestao` (socio+)
# reservado à ESCRITA em sub-recurso de caso (mesma distinção de
# app/core/ownership.py, usada por rentabilidade.py/case_health.py).
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.database import get_db
from app.core.ownership import is_gestao, pode_ver_todos
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseFase, CaseStatus
from app.models.process import Process
from app.models.fee import CaseReceiptAllocation, Fee, FeePayment
from app.models.saneamento import (
    Divergencia,
    ExcecaoNumero,
    IndicativoEncerramento,
    PlanoDedup,
)
from app.models.user import User
from app.schemas.saneamento import AplicarDedupIn, DecidirIndicativoIn, VarreduraIn
from app.services.saneamento.fusao import fundir_casos
from app.services.saneamento.produtor import executar_varredura_datajud, executar_varredura_dedup
from app.services.saneamento.reconciliacao import TipoDivergencia
from app.services.saneamento.tpu import carregar_catalogo

router = APIRouter(prefix="/saneamento", tags=["Saneamento processual"])

_LEITURA = require_roles(["advogado_auxiliar", "advogado", "socio", "admin", "superadmin"])
_DECISAO = require_roles(["advogado", "socio", "admin", "superadmin"])
# Produtor (achado de revisão de código — Issue #1319): operação de
# infraestrutura do módulo (varredura/ingestão), não decisão sobre um caso
# específico — mesmo limiar de `pode_ver_todos` (admin+) usado para visão
# de relatório firm-wide, não o `is_gestao` (socio+) de escrita por caso.
_ADMIN = require_roles(["admin", "superadmin"])


def _digitos(coluna) -> ColumnElement[str]:
    return func.regexp_replace(coluna, r"\D", "", "g")


def _match_numero_cnj(coluna_numero_cnj: ColumnElement[str]):
    """Casa numero_cnj (já normalizado a 20 dígitos) contra QUALQUER
    Processo do caso (principal ou acessório — fonte canônica) OU, se não
    houver Process cadastrado (dado legado), contra o espelho
    `Case.numero_processo` do processo principal."""
    return or_(
        exists().where(
            Process.case_id == Case.id, _digitos(Process.numero_cnj) == coluna_numero_cnj
        ),
        _digitos(Case.numero_processo) == coluna_numero_cnj,
    )


def _filtro_escopo_caso(query, coluna_numero_cnj: ColumnElement[str], cu: User):
    """Restringe a consulta aos registros cujo numero_cnj está ligado a um
    caso que o usuário pode ver. Visão de RELATÓRIO/firm-wide exige admin+
    (`pode_ver_todos`), não só gestão (`socio+`) — mesma distinção do resto
    do EJC entre escopo de leitura e gate de escrita em sub-recurso. Equipe
    só vê caso em que é responsável/auxiliar, ou caso ÓRFÃO (mesma
    salvaguarda anti-lockout de movimentos.py — sem isso um caso sem dono
    ficaria invisível a todo mundo; a leitura é bem menos arriscada que
    decidir, então mantém o órfão visível aqui). numero_cnj sem NENHUM caso
    correspondente no sistema fica invisível à equipe (nega por padrão)."""
    if pode_ver_todos(cu):
        return query
    vinculo = exists().where(
        _match_numero_cnj(coluna_numero_cnj),
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
            (Case.advogado_responsavel_id.is_(None))
            & (Case.advogado_auxiliar_id.is_(None)),
        ),
    )
    return query.where(vinculo)


async def _resolver_casos_do_numero(db: AsyncSession, numero_cnj: str) -> list[Case]:
    """TODOS os casos vinculados a um numero_cnj — pode haver mais de um
    exatamente no cenário que este módulo existe para tratar: duplicata real
    ainda não fundida, com o mesmo CNJ em mais de um registro interno
    (achado de revisão de código: `.first()` escolhia um caso arbitrário,
    podendo autorizar com base no dono errado quando há mais de um)."""
    return (
        await db.execute(
            select(Case)
            .distinct()
            .where(_match_numero_cnj(numero_cnj), Case.deleted_at.is_(None))
        )
    ).scalars().all()


def _pode_agir_no_numero(cu: User, casos: list[Case]) -> bool:
    """Gate de ESCRITA (decidir/aplicar): mesma regra de
    app/core/ownership.py::verificar_acesso_caso — gestão (socio+) sempre
    passa; equipe só se vinculada a TODOS os casos que casam com o
    numero_cnj (ver _resolver_casos_do_numero — mais de um é o próprio
    cenário de duplicata que o módulo trata; exigir vínculo com todos evita
    que o dono de UM dos registros decida sozinho por um caso alheio).
    Caso ÓRFÃO e numero_cnj sem caso correspondente no sistema são NEGADOS à
    equipe: só gestão decide (escape-hatch legítimo, pode assumir/
    reatribuir o caso) — decidir encerramento de processo é irreversível na
    prática, então aqui a regra é a da escrita, não a do escopo de leitura
    (que mantém caso órfão visível à equipe, ver _filtro_escopo_caso)."""
    if is_gestao(cu):
        return True
    if not casos:
        return False
    return all(
        c.advogado_responsavel_id == cu.id or c.advogado_auxiliar_id == cu.id
        for c in casos
    )


def _escopo_cases_integridade(stmt, cu: User):
    stmt = stmt.where(Case.deleted_at.is_(None))
    if pode_ver_todos(cu):
        return stmt
    return stmt.where(
        or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
            (Case.advogado_responsavel_id.is_(None))
            & (Case.advogado_auxiliar_id.is_(None)),
        )
    )


@router.get("/integridade")
async def painel_integridade_processual(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_LEITURA),
):
    """Fila operacional de inconsistências sem corrigir nada automaticamente."""
    tem_processo = exists().where(
        Process.case_id == Case.id,
        Process.deleted_at.is_(None),
    )
    tem_cnj = or_(
        func.length(func.trim(func.coalesce(Case.numero_processo, ""))) > 0,
        exists().where(
            Process.case_id == Case.id,
            Process.deleted_at.is_(None),
            func.length(func.trim(func.coalesce(Process.numero_cnj, ""))) > 0,
        ),
    )
    tem_principal = exists().where(
        Process.case_id == Case.id,
        Process.deleted_at.is_(None),
        Process.is_principal.is_(True),
    )

    filtros = {
        "sem_responsavel": and_(
            Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
            Case.advogado_responsavel_id.is_(None),
        ),
        "pre_processual_com_cnj": and_(
            Case.fase == CaseFase.pre_processual,
            tem_cnj,
        ),
        "protocolado_sem_processo": and_(
            Case.status == CaseStatus.protocolado,
            ~tem_processo,
            func.length(func.trim(func.coalesce(Case.numero_processo, ""))) == 0,
        ),
        "processo_sem_principal": and_(
            tem_processo,
            ~tem_principal,
        ),
    }

    contagens: dict[str, int | None] = {}
    itens: list[dict] = []
    mensagens = {
        "sem_responsavel": "Caso ativo sem advogado responsável.",
        "pre_processual_com_cnj": "Caso ainda pré-processual apesar de já possuir número processual.",
        "protocolado_sem_processo": "Caso protocolado sem entidade Processo vinculada.",
        "processo_sem_principal": "Caso possui Processo ativo, mas nenhum está marcado como principal.",
    }
    for tipo, filtro in filtros.items():
        count_stmt = _escopo_cases_integridade(
            select(func.count()).select_from(Case).where(filtro), cu
        )
        contagens[tipo] = int((await db.execute(count_stmt)).scalar_one())
        rows_stmt = _escopo_cases_integridade(
            select(Case).where(filtro).order_by(Case.updated_at.desc()).limit(8), cu
        )
        rows = (await db.execute(rows_stmt)).scalars().all()
        for caso in rows:
            itens.append({
                "tipo": tipo,
                "case_id": caso.id,
                "numero_interno": caso.numero_interno,
                "titulo": caso.titulo,
                "mensagem": mensagens[tipo],
            })

    q_div = _filtro_escopo_caso(
        select(func.count()).select_from(Divergencia).where(Divergencia.tratada.is_(False)),
        Divergencia.numero_cnj,
        cu,
    )
    q_dup = _filtro_escopo_caso(
        select(func.count()).select_from(PlanoDedup).where(
            PlanoDedup.aplicado.is_(False),
            PlanoDedup.tipo == "duplicata",
        ),
        PlanoDedup.numero_cnj,
        cu,
    )
    contagens["divergencias_datajud"] = int((await db.execute(q_div)).scalar_one())

    # Somente pagamentos identificados como "Honorários recebidos" e já
    # vinculados a caso entram nesta checagem. Pagamentos legados genéricos não
    # são tratados como erro, evitando falso positivo em dados anteriores ao
    # ledger de rateio por caso.
    filtros_recebimento = (
        Fee.deleted_at.is_(None),
        Fee.case_id.is_not(None),
        Fee.descricao.ilike("Honorários recebidos%"),
        CaseReceiptAllocation.id.is_(None),
    )
    q_recebimentos_count = (
        select(func.count())
        .select_from(FeePayment)
        .join(Fee, Fee.id == FeePayment.fee_id)
        .join(Case, Case.id == Fee.case_id)
        .outerjoin(
            CaseReceiptAllocation,
            CaseReceiptAllocation.fee_payment_id == FeePayment.id,
        )
        .where(*filtros_recebimento)
    )
    q_recebimentos_count = _escopo_cases_integridade(q_recebimentos_count, cu)
    contagens["recebimentos_sem_rateio"] = int(
        (await db.execute(q_recebimentos_count)).scalar_one()
    )
    q_recebimentos = (
        select(FeePayment, Fee, Case)
        .join(Fee, Fee.id == FeePayment.fee_id)
        .join(Case, Case.id == Fee.case_id)
        .outerjoin(
            CaseReceiptAllocation,
            CaseReceiptAllocation.fee_payment_id == FeePayment.id,
        )
        .where(*filtros_recebimento)
        .order_by(FeePayment.created_at.desc())
    )
    q_recebimentos = _escopo_cases_integridade(q_recebimentos, cu)
    recebimentos = (await db.execute(q_recebimentos.limit(20))).all()
    for _pagamento, _fee, caso in recebimentos:
        itens.append({
            "tipo": "recebimentos_sem_rateio",
            "case_id": caso.id,
            "numero_interno": caso.numero_interno,
            "titulo": caso.titulo,
            "mensagem": "Honorários recebidos vinculados ao caso ainda sem rateio econômico.",
        })
    contagens["duplicatas_cnj"] = int((await db.execute(q_dup)).scalar_one())
    contagens["numeros_invalidos"] = None
    if is_gestao(cu):
        contagens["numeros_invalidos"] = int(
            (
                await db.execute(
                    select(func.count()).select_from(ExcecaoNumero).where(
                        ExcecaoNumero.resolvido.is_(False)
                    )
                )
            ).scalar_one()
        )

    return {
        "contagens": contagens,
        "total_casos_pendentes": sum(
            int(contagens[chave] or 0)
            for chave in (
                "sem_responsavel",
                "pre_processual_com_cnj",
                "protocolado_sem_processo",
                "processo_sem_principal",
                "recebimentos_sem_rateio",
            )
        ),
        "itens": itens[:20],
        "somente_sinalizacao": True,
    }


@router.get("/excecoes")
async def listar_excecoes(
    resolvido: bool = Query(False, description="False = fila pendente (default)."),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _cu: User = Depends(require_roles(["socio", "admin", "superadmin"])),
):
    """Fila de números que falharam na validação do dígito verificador —
    ERRO DE DIGITAÇÃO, nunca duplicata (regra de negócio inegociável).

    Restrita à gestão (achado de revisão de código): `numero_bruto` e
    `numero_corrigido` (quando já resolvido) identificam processo mesmo
    antes de validados, e a coluna `numero_corrigido` não dá para escopar
    por caso com segurança (nula na maior parte das linhas pendentes,
    exatamente o caso comum) — restringir o endpoint é mais simples e mais
    seguro do que um filtro parcial que só cobriria parte das linhas."""
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
    """Aplica o plano de deduplicação: funde de verdade os casos absorvidos
    no principal (app/services/saneamento/fusao.py — Issue #1319) e marca
    o plano como aplicado, na MESMA transação (erro na fusão desfaz o
    aplicado=true também). `tipo='multi_grau'` ou `'conexo_sugerido'`
    NUNCA devem ser fundidos (regra de negócio inegociável), só
    relacionados/sugeridos — únicos que passam daqui são `'duplicata'`.
    """
    if not body.confirmar:
        raise HTTPException(status_code=422, detail="Confirmação explícita exigida (confirmar=true).")

    plano = (
        await db.execute(select(PlanoDedup).where(PlanoDedup.id == plano_id))
    ).scalar_one_or_none()
    if plano is None:
        raise HTTPException(status_code=404, detail="Plano de deduplicação não encontrado.")

    casos = await _resolver_casos_do_numero(db, plano.numero_cnj)
    if not _pode_agir_no_numero(cu, casos):
        raise HTTPException(status_code=403, detail="Sem acesso a todos os casos deste número CNJ.")

    if plano.tipo != "duplicata":
        raise HTTPException(
            status_code=422,
            detail=(
                f"tipo='{plano.tipo}' não pode ser fundido por esta rota — "
                "apenas 'duplicata' é colapsável; multi_grau/conexo_sugerido "
                "exigem relacionamento manual, nunca fusão automática."
            ),
        )

    # Hardening da auditoria de segurança: os ids gravados no plano (criados
    # pela varredura, num momento anterior) precisam ainda pertencer ao
    # conjunto de casos resolvido AGORA por numero_cnj — a autorização acima
    # (_pode_agir_no_numero) só vale para ESSE conjunto. Hoje os dois sempre
    # deveriam coincidir (mesmo critério de casamento em ambos os lados),
    # mas nada no código reforçava isso; sem esta checagem, uma divergência
    # de dados entre a varredura e a aplicação (ex.: caso reatribuído entre
    # os dois momentos) fundiria um id fora do que foi autorizado.
    ids_do_plano = {plano.id_interno_principal, *plano.ids_absorvidos}
    ids_autorizados = {c.id for c in casos}
    if not ids_do_plano.issubset(ids_autorizados):
        raise HTTPException(
            status_code=409,
            detail="Plano desatualizado: os casos registrados não batem mais com os "
                   "casos vinculados a este número CNJ. Rode a varredura de novo.",
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

    relatorios_fusao = {}
    for absorvido_id in plano.ids_absorvidos:
        relatorio = await fundir_casos(
            db, principal_id=plano.id_interno_principal, absorvido_id=absorvido_id,
            numero_cnj_gatilho=plano.numero_cnj, ator_id=cu.id,
        )
        relatorios_fusao[absorvido_id] = {
            "reatribuidas": relatorio.reatribuidas, "descartadas": relatorio.descartadas,
            "processos_colapsados": relatorio.processos_colapsados,
            "ja_arquivado": relatorio.absorvido_ja_arquivado,
        }

    await criar_audit_log(
        db, cu.id, cu.role.value,
        "APLICAR", "saneamento.plano_dedup", str(plano_id),
        dados_depois={"numero_cnj": plano.numero_cnj, "tipo": plano.tipo, "fusao": relatorios_fusao},
    )
    await db.commit()
    return {"id": plano_id, "aplicado": True, "fusao": relatorios_fusao}


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

    casos = await _resolver_casos_do_numero(db, indicativo.numero_cnj)
    if not _pode_agir_no_numero(cu, casos):
        raise HTTPException(status_code=403, detail="Sem acesso a todos os casos deste número CNJ.")

    # Achado de revisão de código: sem esta checagem, quem soubesse o ID
    # podia registrar "encerrar" mesmo quando o avaliador NÃO sinalizou o
    # processo como candidato (ex.: reativador posterior, suspensivo
    # vigente, silêncio insuficiente) — exatamente os casos em que
    # avaliar_encerramento() deliberadamente NÃO recomenda encerramento.
    # Checada DEPOIS do acesso: 403 (autorização) nunca vaza atrás de um
    # 422 (regra de negócio) para quem não tem acesso ao caso.
    if body.decisao == "encerrar" and not indicativo.candidato:
        raise HTTPException(
            status_code=422,
            detail="Este indicativo não é candidato a encerramento — a avaliação automática não recomenda 'encerrar'.",
        )

    agora = datetime.now(timezone.utc)
    # UPDATE condicionado a decisao IS NULL: mesma correção de corrida do
    # aplicar_duplicata — a decisão sobre encerrar um processo é irreversível
    # na prática, então a garantia de "só decide uma vez" tem que vir do
    # próprio UPDATE, não de um SELECT anterior que pode ter ficado obsoleto.
    # A checagem de `candidato` acima também entra no WHERE — corrida não
    # pode contornar a regra de negócio.
    resultado = await db.execute(
        update(IndicativoEncerramento)
        .where(
            IndicativoEncerramento.id == indicativo_id,
            IndicativoEncerramento.decisao.is_(None),
            or_(body.decisao != "encerrar", IndicativoEncerramento.candidato.is_(True)),
        )
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
    (reconciliacao.py — que também para de gerar QUALQUER outra divergência
    para o mesmo documento sigiloso) — fica de fora do relatório amplo para
    quem não tem visão de relatório firm-wide."""
    q = (
        select(Divergencia)
        .where(Divergencia.tratada == tratada)
        .order_by(Divergencia.criado_em.desc())
    )
    q = _filtro_escopo_caso(q, Divergencia.numero_cnj, cu)
    if not pode_ver_todos(cu):
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


@router.post("/varredura")
async def acionar_varredura(
    body: VarreduraIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADMIN),
):
    """Produtor do módulo (Issue #1319): aciona deduplicar()/
    avaliar_encerramento()/reconciliar() sobre a base real e persiste os
    resultados nas filas que as rotas GET acima leem. Sem chamar esta rota
    (ou um job agendado que a substitua), o módulo fica permanentemente
    vazio. `tipo=dedup` não depende de rede; `datajud`/`completa` fazem
    chamadas externas (rate-limited, com `limite_datajud` por execução) e
    são no-op gracioso se DATAJUD_ENABLED/DATAJUD_API_KEY não estiverem
    configurados."""
    execucoes = []
    if body.tipo in ("dedup", "completa"):
        execucoes.append(await executar_varredura_dedup(db))
    if body.tipo in ("datajud", "completa"):
        execucoes.append(await executar_varredura_datajud(db, limite=body.limite_datajud))

    await criar_audit_log(
        db, cu.id, cu.role.value,
        "VARREDURA", "saneamento.execucao", ",".join(str(e.id) for e in execucoes),
        dados_depois={"tipo": body.tipo, "resultados": [
            {"id": e.id, "tipo": e.tipo, "status": e.status, "processados": e.processados, "falhas": e.falhas}
            for e in execucoes
        ]},
    )
    await db.commit()
    return {
        "execucoes": [
            {
                "id": e.id, "tipo": e.tipo, "status": e.status,
                "processados": e.processados, "falhas": e.falhas,
                "iniciado_em": e.iniciado_em, "finalizado_em": e.finalizado_em,
                "detalhe": e.detalhe,
            }
            for e in execucoes
        ],
    }
