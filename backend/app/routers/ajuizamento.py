# ── app/routers/ajuizamento.py ───────────────────────────────────────────────
# Núcleo de ajuizamento: capacidades, perfis de tribunal (admin), TPU,
# ajuizamentos (wizard → validação → revisão humana → assinatura → protocolo
# → confirmação → sincronização) e registro de protocolos.
#
# Todas as rotas exigem autenticação (AuthMiddleware + get_current_user) e
# aplicam ownership por caso (verificar_acesso_caso). Atos jurídicos (aprovar,
# assinar, protocolar, confirmar) exigem advogado+ (requer_advogado).
# JUDICIAL_FILING_ENABLED=false → 503 para as rotas de fluxo (perfis e
# capacidades continuam consultáveis para diagnóstico).
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import (
    EQUIPE_JURIDICA, get_current_user, requer_advogado, require_roles, require_roles_exact,
)
from app.models.ajuizamento import JudicialFilingTransicao, JudicialSyncEvent
from app.models.case import Case
from app.models.user import User
from app.schemas.ajuizamento import (
    AprovarReq, AssinarReq, CancelarReq, ConfirmarManualReq, FilingCreate, FilingUpdate,
    PerfilCreate, PerfilIn, TpuImportReq, TpuSyncReq,
)
from app.services.ajuizamento import assinatura as assinatura_mod
from app.services.ajuizamento import auditoria as aud
from app.services.ajuizamento import perfis as perfis_service
from app.services.ajuizamento.conectores.roteador import JudicialConnectorRouter, SistemaNaoSuportado
from app.services.ajuizamento.orquestrador import (
    AjuizamentoError, AjuizamentoNaoEncontrado, JudicialFilingService, filing_para_dict,
)
from app.services.ajuizamento.registro_protocolo import listar_protocolos, protocolo_para_dict
from app.services.ajuizamento.sincronizacao import evento_para_dict
from app.services.ajuizamento.tpu_service import TpuService, TpuTipoInvalido

logger = logging.getLogger("ejc.ajuizamento")

router = APIRouter(prefix="/ajuizamento", tags=["Ajuizamento"])

# Superfície JURÍDICA: allowlist EXATA (EQUIPE_JURIDICA). `require_roles` cairia
# na comparação hierárquica e deixaria `financeiro` (nível 4 > estagiário 3)
# entrar no ajuizamento — ver a nota da Issue #694 em core/security.py.
_OPERACIONAL = require_roles_exact(EQUIPE_JURIDICA)
_ADMIN = require_roles(["superadmin", "admin"])
_roteador = JudicialConnectorRouter()


def _exigir_flag() -> None:
    if not get_settings().JUDICIAL_FILING_ENABLED:
        raise HTTPException(503, "Ajuizamento desabilitado (JUDICIAL_FILING_ENABLED=false)")


def _servico(db: AsyncSession) -> JudicialFilingService:
    return JudicialFilingService(db, get_settings(), _roteador)


async def _carregar(db: AsyncSession, cu: User, filing_id: str, *, lock: bool = False):
    svc = _servico(db)
    try:
        f = await svc.obter(filing_id, lock=lock)
    except AjuizamentoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    await verificar_acesso_caso(db, cu, f.case_id)
    return svc, f


def _422(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


# ── Capacidades / assinatura ─────────────────────────────────────────────────

@router.get("/capacidades", summary="Matriz de capacidades por conector × perfil de tribunal")
async def capacidades(db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    s = get_settings()
    return {
        "habilitado": s.JUDICIAL_FILING_ENABLED,
        "flags": {
            "JUDICIAL_FILING_ENABLED": s.JUDICIAL_FILING_ENABLED,
            "PDPJ_INTEGRATION_ENABLED": s.PDPJ_INTEGRATION_ENABLED,
            "PJE_MNI_ENABLED": s.PJE_MNI_ENABLED,
            "EPROC_INTEGRATION_ENABLED": s.EPROC_INTEGRATION_ENABLED,
            "DATAJUD_ENABLED": s.DATAJUD_ENABLED,
            "DATAJUD_SYNC_ENABLED": s.DATAJUD_SYNC_ENABLED,
        },
        "conectores": await _roteador.matriz_completa(db, s),
        "assinatura": assinatura_mod.matriz_assinatura(),
        "tpu": await TpuService(db).resumo(),
    }


# ── Perfis de tribunal (admin) ───────────────────────────────────────────────

@router.get("/perfis", summary="Perfis de integração por tribunal/sistema/ambiente")
async def listar_perfis(db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    return [perfis_service.perfil_para_dict(p) for p in await perfis_service.listar_perfis(db)]


@router.post("/perfis", status_code=201, summary="Cadastra perfil de tribunal (admin)")
async def criar_perfil(payload: PerfilCreate, db: AsyncSession = Depends(get_db), cu: User = Depends(_ADMIN)):
    try:
        p = await perfis_service.criar_perfil(db, payload.model_dump(exclude_none=True), created_by=cu.id)
        await db.flush()
    except (ValueError, perfis_service.BaseUrlInvalida) as exc:
        raise _422(exc)
    dados = perfis_service.perfil_para_dict(p)
    await aud.auditar(db, cu, aud.ACAO_PERFIL, p.id, detalhes="perfil criado", dados_depois=dados,
                      entidade=aud.ENTIDADE_PERFIL)
    await db.commit()
    return dados


@router.patch("/perfis/{perfil_id}", summary="Atualiza perfil/checklist de homologação (admin)")
async def atualizar_perfil(perfil_id: str, payload: PerfilIn, db: AsyncSession = Depends(get_db),
                           cu: User = Depends(_ADMIN)):
    dados_in = payload.model_dump(exclude_unset=True)
    try:
        p = await perfis_service.atualizar_perfil(db, perfil_id, dados_in)
    except (ValueError, perfis_service.BaseUrlInvalida) as exc:
        raise _422(exc)
    if p is None:
        raise HTTPException(404, "Perfil não encontrado")
    dados = perfis_service.perfil_para_dict(p)
    await aud.auditar(db, cu, aud.ACAO_PERFIL, p.id, detalhes=f"campos: {sorted(dados_in)}",
                      dados_depois=dados, entidade=aud.ENTIDADE_PERFIL)
    await db.commit()
    return dados


# ── TPU ──────────────────────────────────────────────────────────────────────

@router.get("/tpu/{tipo}", summary="Lista/pesquisa a TPU no cache local")
async def listar_tpu(tipo: str, busca: Optional[str] = Query(None, max_length=200),
                     limite: int = Query(50, ge=1, le=200),
                     db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    try:
        return {"itens": await TpuService(db).listar(tipo, busca, limite)}
    except TpuTipoInvalido as exc:
        raise _422(exc)


@router.post("/tpu/sincronizar", summary="Sincroniza itens da TPU a partir do SGT/CNJ (admin; CONDITIONAL)",
             dependencies=[Depends(rate_limit("ajuizamento-tpu-sync", 10))])
async def sincronizar_tpu(payload: TpuSyncReq, db: AsyncSession = Depends(get_db), cu: User = Depends(_ADMIN)):
    try:
        r = await TpuService(db).sincronizar_por_termo(payload.tipo, payload.termo, payload.tipo_pesquisa)
    except Exception as exc:  # noqa: BLE001 — falha upstream vira 502 controlado
        logger.warning("[TPU] sync falhou (%s)", type(exc).__name__)
        raise HTTPException(502, "SGT/CNJ indisponível para sincronização") from exc
    await db.commit()
    return r


@router.post("/tpu/importar", summary="Carga administrativa de itens TPU normalizados (admin)")
async def importar_tpu(payload: TpuImportReq, db: AsyncSession = Depends(get_db), cu: User = Depends(_ADMIN)):
    n = await TpuService(db).importar_itens(payload.tipo, payload.itens, origem=payload.origem)
    await aud.auditar(db, cu, aud.ACAO_PERFIL, payload.tipo, detalhes=f"tpu importar {n} itens ({payload.origem})",
                      entidade="judicial_tpu_itens")
    await db.commit()
    return {"importados": n}


# ── Ajuizamentos ─────────────────────────────────────────────────────────────

@router.get("/filings", summary="Lista ajuizamentos (por caso ou visíveis ao usuário)")
async def listar_filings(case_id: Optional[str] = Query(None, max_length=36),
                         db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    svc = _servico(db)
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)
        itens = await svc.listar(case_id=case_id)
    elif is_gestao(cu):
        itens = await svc.listar()
    else:
        visiveis = (await db.execute(select(Case.id).where(
            Case.deleted_at.is_(None),
            (Case.advogado_responsavel_id == cu.id) | (Case.advogado_auxiliar_id == cu.id),
        ))).scalars().all()
        itens = await svc.listar(casos_visiveis=list(visiveis))
    return [filing_para_dict(f, incluir_canonico=False) for f in itens]


@router.post("/filings", status_code=201, summary="Cria ajuizamento (DRAFT) a partir de um caso")
async def criar_filing(payload: FilingCreate, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    case = await verificar_acesso_caso(db, cu, payload.case_id)
    svc = _servico(db)
    try:
        f = await svc.criar(case=case, cu=cu, dados=payload.model_dump(exclude={"case_id"}, exclude_unset=True))
    except AjuizamentoError as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_CRIAR, f.id, detalhes=f"caso {case.id}",
                      dados_depois={"tribunal": f.tribunal_code, "system": f.system})
    await db.commit()
    return filing_para_dict(f)


@router.get("/filings/{filing_id}", summary="Detalhe do ajuizamento (canônico mascarado + preflight)")
async def obter_filing(filing_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _, f = await _carregar(db, cu, filing_id)
    return filing_para_dict(f)


@router.patch("/filings/{filing_id}", summary="Edita o ajuizamento (volta a DRAFT)")
async def atualizar_filing(filing_id: str, payload: FilingUpdate, db: AsyncSession = Depends(get_db),
                           cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    dados = payload.model_dump(exclude_unset=True)
    try:
        await svc.atualizar(f, cu=cu, dados=dados)
    except AjuizamentoError as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_ATUALIZAR, f.id, detalhes=f"campos: {sorted(dados)}")
    await db.commit()
    return filing_para_dict(f)


@router.post("/filings/{filing_id}/validar", summary="Preflight: monta o canônico e valida contra o destino",
             dependencies=[Depends(rate_limit("ajuizamento-validar", 30))])
async def validar_filing(filing_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        resultado = await svc.validar(f, cu=cu)
    except AjuizamentoError as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_VALIDAR, f.id,
                      detalhes=f"ready={resultado['ready']} erros={len(resultado['errors'])} hash={f.canonico_hash}")
    await db.commit()
    return {"filing": filing_para_dict(f), "preflight": resultado}


@router.post("/filings/{filing_id}/aprovar", summary='Revisão humana final ("REVISAR E PROTOCOLAR")')
async def aprovar_filing(filing_id: str, payload: AprovarReq, db: AsyncSession = Depends(get_db),
                         cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    requer_advogado(cu, detail="Aprovação do ajuizamento é restrita a advogados")
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        await svc.aprovar(f, cu=cu, confirmacao=payload.confirmacao, observacoes=payload.observacoes)
    except AjuizamentoError as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_APROVAR, f.id, detalhes=f"hash={f.canonico_hash}; obs={payload.observacoes or ''}",
                      dados_depois={"tribunal": f.tribunal_code, "system": f.system, "classe": f.classe_codigo,
                                    "assuntos": [a.get("codigo") for a in (f.assuntos or [])]})
    await db.commit()
    return filing_para_dict(f)


@router.post("/filings/{filing_id}/assinar", summary="Registra a assinatura (SigningProvider)")
async def assinar_filing(filing_id: str, payload: AssinarReq, db: AsyncSession = Depends(get_db),
                         cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    requer_advogado(cu, detail="Assinatura é restrita a advogados")
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    dados = payload.model_dump(exclude_none=True)
    try:
        r = await svc.assinar(f, cu=cu, provider=payload.provider, dados=dados)
    except AjuizamentoError as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_ASSINAR, f.id, detalhes=f"provider={payload.provider}; estado={r['estado']}",
                      dados_depois=r.get("evidencia"))
    await db.commit()
    return r


@router.post("/filings/{filing_id}/protocolar", summary="Envia ao conector (idempotente)",
             dependencies=[Depends(rate_limit("ajuizamento-protocolar", 10))])
async def protocolar_filing(filing_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    requer_advogado(cu, detail="Protocolo é restrito a advogados")
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        r = await svc.protocolar(f, cu=cu)
    except AjuizamentoError as exc:
        await db.commit()   # transições de falha já registradas ficam persistidas
        raise _422(exc)
    except SistemaNaoSuportado as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_PROTOCOLAR, f.id,
                      detalhes=f"estado={f.estado}; tribunal={f.tribunal_code}; system={f.system}; hash={f.canonico_hash}",
                      dados_depois={k: v for k, v in r.items() if k != "recibo"})
    await db.commit()
    return r


@router.post("/filings/{filing_id}/confirmar-manual", summary="Registra protocolo feito no portal do tribunal")
async def confirmar_manual(filing_id: str, payload: ConfirmarManualReq, db: AsyncSession = Depends(get_db),
                           cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    requer_advogado(cu, detail="Registro de protocolo é restrito a advogados")
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        r = await svc.confirmar_manual(f, cu=cu, dados=payload.model_dump())
    except (AjuizamentoError, ValueError) as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_CONFIRMAR, f.id, detalhes=f"cnj={r.get('cnj_number')}", dados_depois=r)
    await db.commit()
    return r


@router.post("/filings/{filing_id}/sincronizar", summary="Sincroniza o caso pelo número CNJ (MNI/DataJud)",
             dependencies=[Depends(rate_limit("ajuizamento-sync", 10))])
async def sincronizar_filing(filing_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _exigir_flag()
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        r = await svc.sincronizar(f, cu=cu)
    except AjuizamentoError as exc:
        raise _422(exc)
    except Exception as exc:  # noqa: BLE001
        await db.commit()
        raise HTTPException(502, f"Sincronização falhou ({type(exc).__name__})") from exc
    await aud.auditar(db, cu, aud.ACAO_SINCRONIZAR, f.id, detalhes=f"novos={r.get('movimentos_novos')}")
    await db.commit()
    return r


@router.post("/filings/{filing_id}/cancelar", summary="Cancela o ajuizamento (antes do protocolo)")
async def cancelar_filing(filing_id: str, payload: CancelarReq, db: AsyncSession = Depends(get_db),
                          cu: User = Depends(_OPERACIONAL)):
    svc, f = await _carregar(db, cu, filing_id, lock=True)
    try:
        await svc.cancelar(f, cu=cu, motivo=payload.motivo)
    except (AjuizamentoError, ValueError) as exc:
        raise _422(exc)
    await aud.auditar(db, cu, aud.ACAO_CANCELAR, f.id, detalhes=payload.motivo)
    await db.commit()
    return filing_para_dict(f, incluir_canonico=False)


@router.get("/filings/{filing_id}/transicoes", summary="Histórico da máquina de estados")
async def transicoes_filing(filing_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(_OPERACIONAL)):
    _, f = await _carregar(db, cu, filing_id)
    linhas = (await db.execute(
        select(JudicialFilingTransicao).where(JudicialFilingTransicao.filing_id == f.id)
        .order_by(JudicialFilingTransicao.created_at)
    )).scalars().all()
    eventos = (await db.execute(
        select(JudicialSyncEvent).where(JudicialSyncEvent.filing_id == f.id).order_by(JudicialSyncEvent.created_at)
    )).scalars().all()
    return {
        "transicoes": [
            {"id": t.id, "de": t.de_estado, "para": t.para_estado, "ator_id": t.ator_id, "motivo": t.motivo,
             "created_at": t.created_at.isoformat() if t.created_at else None}
            for t in linhas
        ],
        "sync_eventos": [evento_para_dict(e) for e in eventos],
    }


@router.get("/protocolos", summary="Registro de protocolos (ProtocolRegistry)")
async def protocolos(case_id: str = Query(..., max_length=36), db: AsyncSession = Depends(get_db),
                     cu: User = Depends(_OPERACIONAL)):
    await verificar_acesso_caso(db, cu, case_id)
    return [protocolo_para_dict(p) for p in await listar_protocolos(db, case_id=case_id)]
