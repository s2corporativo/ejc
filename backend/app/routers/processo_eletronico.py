# ── app/routers/processo_eletronico.py ───────────────────────────────────────
# Integração de processo eletrônico via MNI 2.2.2 — Issue #762, Fase A
# (SOMENTE LEITURA). Router fino: dispara a task Celery de sincronização,
# expõe o status e o CRUD de credenciais (nunca ecoando o segredo).
#
# `entregarManifestacaoProcessual` (peticionamento) está FORA de escopo desta
# fase — nenhuma rota aqui dá suporte a isso.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.processo_eletronico import (
    CredencialProcessoEletronico, SincronizacaoProcessoEletronico, Tribunal,
)
from app.schemas.processo_eletronico import (
    CredencialCreateReq, CredencialMetaResp, SincronizarProcessoReq,
    SincronizarProcessoResp, StatusSincronizacaoResp, TestarCredencialResp,
)
from app.services import processo_eletronico_credential_service as cred_service
from app.services.security_service import obter_ip_real

logger = logging.getLogger("ejc.processo_eletronico")

router = APIRouter(prefix="/processo-eletronico", tags=["Processo Eletrônico (MNI)"])

ENTIDADE_AUDIT = "credenciais_processo_eletronico"

# Consulta/sincronização: qualquer papel operacional (advogado ou acima).
_OPERACIONAL = require_roles(
    ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]
)
# Gestão de credenciais: admin ou superior (segredo de acesso ao tribunal).
_GESTAO_CREDENCIAL = require_roles(["superadmin", "admin", "socio"])
# Leitura de credenciais: qualquer papel operacional — a restrição "só a
# própria ou admin" é aplicada dentro do handler (RBAC por linha, não por rota).
_LEITURA_CREDENCIAL = require_roles(
    ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]
)


@router.post(
    "/sincronizar", response_model=SincronizarProcessoResp, status_code=202,
    dependencies=[Depends(rate_limit("processo-eletronico-sync", 10))],
    summary="Enfileira a sincronização de um caso via MNI (Celery, assíncrono)",
)
async def sincronizar(
    req: SincronizarProcessoReq, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_OPERACIONAL),
):
    """Nunca chama o MNI na própria request — só enfileira a task Celery
    (sincronizar_processo_task) e devolve o job_id. O status real é
    consultado em GET /status/{case_id}.

    Ownership: `verificar_acesso_caso` (mesmo gate dos demais sub-recursos
    de caso) — só a equipe vinculada ao caso ou a gestão (sócio+) pode
    disparar sincronização MNI, evitando IDOR sobre credencial/caso alheio."""
    await verificar_acesso_caso(db, cu, req.case_id)

    from app.tasks.processo_eletronico_tasks import sincronizar_processo_task

    async_result = sincronizar_processo_task.delay(req.case_id, req.numero_cnj)

    await criar_audit_log(
        db, cu.id, cu.role.value, "PROCESSO_ELETRONICO_SYNC_ENFILEIRADO",
        "cases", req.case_id,
        detalhes=f"numero_cnj={req.numero_cnj} job_id={async_result.id}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    return SincronizarProcessoResp(job_id=async_result.id, status="enfileirado")


@router.get(
    "/status/{case_id}", response_model=StatusSincronizacaoResp,
    summary="Estado da última sincronização MNI de um caso",
)
async def status_sincronizacao(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_OPERACIONAL),
):
    """Ownership: `verificar_acesso_caso` — sem o gate, `numero_cnj`,
    contagem de documentos e `mensagem_erro` de qualquer caso vazariam para
    qualquer papel operacional, inclusive casos em segredo de justiça."""
    await verificar_acesso_caso(db, cu, case_id)

    sync = (await db.execute(
        select(SincronizacaoProcessoEletronico).where(
            SincronizacaoProcessoEletronico.case_id == case_id,
        )
    )).scalar_one_or_none()
    if sync is None:
        return StatusSincronizacaoResp(case_id=case_id, status=None)
    return StatusSincronizacaoResp(
        case_id=case_id,
        status=sync.status.value if sync.status else None,
        last_synced_at=sync.last_synced_at,
        docs_novos=sync.docs_novos,
        mensagem_erro=sync.mensagem_erro,
    )


@router.get(
    "/credenciais", response_model=list[CredencialMetaResp],
    summary="Lista credenciais MNI (sem segredo) — próprio advogado ou admin",
)
async def listar_credenciais(
    advogado_id: str,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_LEITURA_CREDENCIAL),
):
    """Leitura de credenciais restrita ao próprio advogado ou admin/superadmin
    (nunca um advogado vê a credencial de outro)."""
    from app.core.security import ROLE_LEVEL
    eh_admin = ROLE_LEVEL.get(cu.role, 0) >= ROLE_LEVEL.get("admin", 0)
    if not eh_admin and advogado_id != cu.id:
        raise HTTPException(
            status_code=403,
            detail="Só é possível listar as próprias credenciais MNI.",
        )
    linhas = (await db.execute(
        select(CredencialProcessoEletronico).where(
            CredencialProcessoEletronico.advogado_id == advogado_id,
        )
    )).scalars().all()
    return [CredencialMetaResp.model_validate(c) for c in linhas]


@router.post(
    "/credenciais", response_model=CredencialMetaResp, status_code=201,
    dependencies=[Depends(rate_limit("processo-eletronico-credenciais", 5))],
    summary="Cadastra credencial MNI de um advogado num tribunal (segredo cifrado)",
)
async def criar_credencial(
    req: CredencialCreateReq, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_GESTAO_CREDENCIAL),
):
    """A senha/id_consultante vão direto para o cifrador (pii_crypto/Fernet)
    — o valor em claro nunca é persistido nem ecoado na resposta."""
    from uuid import uuid4

    tribunal = (await db.execute(
        select(Tribunal).where(Tribunal.id == req.tribunal_id)
    )).scalar_one_or_none()
    if tribunal is None:
        raise HTTPException(status_code=404, detail="Tribunal não encontrado.")

    credencial = CredencialProcessoEletronico(
        id=str(uuid4()), tribunal_id=req.tribunal_id, advogado_id=req.advogado_id,
        tipo=req.tipo,
        id_consultante_cifrado=cred_service.cifrar_id_consultante(req.id_consultante),
        senha_consultante_ref=cred_service.cifrar_senha(req.senha_consultante),
        certificado_ref=req.certificado_ref,
        escopo=req.escopo, ativo=True,
    )
    db.add(credencial)
    await db.flush()

    await criar_audit_log(
        db, cu.id, cu.role.value, "PROCESSO_ELETRONICO_CREDENCIAL_CRIADA",
        ENTIDADE_AUDIT, credencial.id,
        detalhes=f"tribunal={req.tribunal_id} advogado={req.advogado_id} tipo={req.tipo}",
        ip=obter_ip_real(request),
    )
    await db.commit()
    await db.refresh(credencial)
    return CredencialMetaResp.model_validate(credencial)


@router.post(
    "/credenciais/{credencial_id}/testar", response_model=TestarCredencialResp,
    dependencies=[Depends(rate_limit("processo-eletronico-credenciais-teste", 10))],
    summary="Healthcheck da credencial (consultarProcesso de teste)",
)
async def testar_credencial(
    credencial_id: str, request: Request,
    db: AsyncSession = Depends(get_db),
    cu=Depends(_GESTAO_CREDENCIAL),
):
    """Dispara o teste em Celery (nunca síncrono na request) e devolve
    'enfileirado' — a chamada SOAP pode levar segundos e não pode bloquear
    o event loop do worker uvicorn (premissa de worker único). O resultado
    atualiza `ultima_verificacao` na credencial; consulte /credenciais para
    ver o novo valor.

    Fase A: se o SOAP falhar (tribunal indisponível, credencial inválida),
    a falha é tratada graciosamente dentro da task — não derruba a rota."""
    credencial = (await db.execute(
        select(CredencialProcessoEletronico).where(
            CredencialProcessoEletronico.id == credencial_id,
        )
    )).scalar_one_or_none()
    if credencial is None:
        raise HTTPException(status_code=404, detail="Credencial não encontrada.")

    from app.tasks.processo_eletronico_tasks import testar_credencial_task

    testar_credencial_task.delay(credencial_id)

    await criar_audit_log(
        db, cu.id, cu.role.value, "PROCESSO_ELETRONICO_CREDENCIAL_TESTADA",
        ENTIDADE_AUDIT, credencial_id, ip=obter_ip_real(request),
    )
    await db.commit()
    return TestarCredencialResp(estado="enfileirado", detalhe="Teste de credencial enfileirado.")
