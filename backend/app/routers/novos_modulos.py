"""
routers/novos_modulos.py
Endpoints para os módulos da Etapa B:
  - /precificacao   — Motor de precificação OAB
  - /inadimplencia  — Alertas de inadimplência
  - /ambiental      — Módulo ambiental por caso
  - /due-diligence  — Templates de due diligence
  - /cofre          — Log de acesso a documentos + sensibilidade
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.core.request_context import get_client_ip
from app.models.user import User

router = APIRouter(tags=["Novos Módulos — Etapa B"])

# Ações válidas da trilha de acesso ao cofre — espelha o CHECK da coluna
# document_access_log.action (migration 050). Valor fora da lista → 422.
_COFRE_ACOES = ("view", "download", "print", "share", "delete")
# Confidencialidade a partir da qual só gestão (socio+) pode acessar/registrar.
_CONF_RESTRITA = ("restrito", "confidencial", "segredo_justica")


# ════════════════════════════════════════════════════════════
# PRECIFICAÇÃO
# ════════════════════════════════════════════════════════════

@router.get("/precificacao/tabela")
async def precificacao_tabela(
    area: Optional[str] = None,
    complexity: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.services.precificacao_service import listar_tabela
    return await listar_tabela(db, area=area, complexity=complexity)


@router.get("/precificacao/calcular/{rule_id}")
async def precificacao_calcular(
    rule_id: str,
    causa_valor: Optional[float] = Query(None, description="Valor da causa em R$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    from app.services.precificacao_service import calcular_honorario
    result = await calcular_honorario(db, rule_id, causa_valor)
    if "erro" in result:
        raise HTTPException(404, result["erro"])
    return result


class PrecificacaoCreate(BaseModel):
    area: str
    case_type: str
    complexity: str = "media"
    fee_type: str = "fixo"
    base_amount: Optional[float] = None
    percentage_of_value: Optional[float] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    exit_percentage: Optional[float] = None
    oab_reference: Optional[str] = None
    notes: Optional[str] = None


@router.post("/precificacao/regras", status_code=201)
async def criar_regra(
    body: PrecificacaoCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role not in ("admin", "superadmin", "socio"):
        raise HTTPException(403, "Acesso restrito a sócios e administradores")
    from app.services.precificacao_service import criar_regra
    return await criar_regra(db, body.model_dump(), cu.id)


# ════════════════════════════════════════════════════════════
# INADIMPLÊNCIA
# ════════════════════════════════════════════════════════════

@router.get("/inadimplencia/alertas")
async def inadimplencia_alertas(
    resolved: bool = False,
    nivel: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # IDOR/sigilo (auditoria 2026-06-30): inadimplência exposta só a gestão/financeiro.
    if cu.role not in ("admin", "superadmin", "socio", "financeiro"):
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    from app.services.inadimplencia_service import listar_alertas
    return await listar_alertas(db, resolved=resolved, nivel=nivel, limit=limit)


@router.post("/inadimplencia/varrer")
async def inadimplencia_varrer(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role not in ("admin", "superadmin"):
        raise HTTPException(403, "Acesso restrito a administradores")
    from app.services.inadimplencia_service import varrer_inadimplencia
    return await varrer_inadimplencia(db)


class ResolverAlerta(BaseModel):
    action_taken: str


@router.patch("/inadimplencia/alertas/{alert_id}/resolver")
async def resolver_alerta(
    alert_id: str,
    body: ResolverAlerta,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # IDOR/sigilo: resolver inadimplência é ação de gestão/financeiro (espelha o GET irmão).
    if cu.role not in ("admin", "superadmin", "socio", "financeiro"):
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    from app.services.inadimplencia_service import resolver_alerta
    return await resolver_alerta(db, alert_id, body.action_taken)


# ════════════════════════════════════════════════════════════
# AMBIENTAL
# ════════════════════════════════════════════════════════════

class AmbientalCreate(BaseModel):
    subtype: Optional[str] = None
    numero_auto: Optional[str] = None
    orgao_autuador: Optional[str] = None
    data_auto: Optional[str] = None
    prazo_defesa: Optional[str] = None
    valor_multa: Optional[float] = None
    infracoes: list = []
    licenca_tipo: Optional[str] = None
    licenca_numero: Optional[str] = None
    licenca_validade: Optional[str] = None
    licenca_orgao: Optional[str] = None
    car_numero: Optional[str] = None
    reserva_legal_ha: Optional[float] = None
    app_area_ha: Optional[float] = None
    tcfa_cnpj: Optional[str] = None
    tcfa_atividade: Optional[str] = None
    tcfa_vencimento: Optional[str] = None
    tcfa_valor: Optional[float] = None
    credito_carbono_ton: Optional[float] = None
    observacoes: Optional[str] = None


@router.get("/casos/{case_id}/ambiental")
async def get_ambiental(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    r = await db.execute(
        text("SELECT * FROM case_ambiental WHERE case_id = :cid"),
        {"cid": case_id},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(404, "Dados ambientais não encontrados para este caso")
    return dict(row._mapping)


@router.post("/casos/{case_id}/ambiental")
async def upsert_ambiental(
    case_id: str,
    body: AmbientalCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    import json
    await verificar_acesso_caso(db, cu, case_id)
    existing = await db.execute(
        text("SELECT id FROM case_ambiental WHERE case_id = :cid"), {"cid": case_id}
    )
    row = existing.fetchone()

    if row:
        await db.execute(text("""
            UPDATE case_ambiental SET
                subtype=:subtype, numero_auto=:numero_auto, orgao_autuador=:orgao,
                data_auto=:data_auto, prazo_defesa=:prazo_defesa, valor_multa=:valor_multa,
                infracoes=:infracoes::jsonb, licenca_tipo=:lic_tipo, licenca_numero=:lic_num,
                licenca_validade=:lic_val, licenca_orgao=:lic_orgao,
                car_numero=:car_num, reserva_legal_ha=:rl_ha, app_area_ha=:app_ha,
                tcfa_cnpj=:tcfa_cnpj, tcfa_atividade=:tcfa_at, tcfa_vencimento=:tcfa_ven,
                tcfa_valor=:tcfa_val, credito_carbono_ton=:carbono,
                observacoes=:obs, updated_at=NOW()
            WHERE case_id = :cid
        """), {**_ambiental_params(body), "cid": case_id})
    else:
        await db.execute(text("""
            INSERT INTO case_ambiental
                (id, case_id, subtype, numero_auto, orgao_autuador, data_auto,
                 prazo_defesa, valor_multa, infracoes, licenca_tipo, licenca_numero,
                 licenca_validade, licenca_orgao, car_numero, reserva_legal_ha,
                 app_area_ha, tcfa_cnpj, tcfa_atividade, tcfa_vencimento, tcfa_valor,
                 credito_carbono_ton, observacoes)
            VALUES
                (gen_random_uuid()::text, :cid, :subtype, :numero_auto, :orgao,
                 :data_auto, :prazo_defesa, :valor_multa, :infracoes::jsonb, :lic_tipo,
                 :lic_num, :lic_val, :lic_orgao, :car_num, :rl_ha, :app_ha,
                 :tcfa_cnpj, :tcfa_at, :tcfa_ven, :tcfa_val, :carbono, :obs)
        """), {**_ambiental_params(body), "cid": case_id})

    await db.commit()
    return {"case_id": case_id, "saved": True}


def _ambiental_params(body: AmbientalCreate) -> dict:
    import json
    return {
        "subtype":     body.subtype,
        "numero_auto": body.numero_auto,
        "orgao":       body.orgao_autuador,
        "data_auto":   body.data_auto,
        "prazo_defesa": body.prazo_defesa,
        "valor_multa": body.valor_multa,
        "infracoes":   json.dumps(body.infracoes, ensure_ascii=False),
        "lic_tipo":    body.licenca_tipo,
        "lic_num":     body.licenca_numero,
        "lic_val":     body.licenca_validade,
        "lic_orgao":   body.licenca_orgao,
        "car_num":     body.car_numero,
        "rl_ha":       body.reserva_legal_ha,
        "app_ha":      body.app_area_ha,
        "tcfa_cnpj":   body.tcfa_cnpj,
        "tcfa_at":     body.tcfa_atividade,
        "tcfa_ven":    body.tcfa_vencimento,
        "tcfa_val":    body.tcfa_valor,
        "carbono":     body.credito_carbono_ton,
        "obs":         body.observacoes,
    }


# ════════════════════════════════════════════════════════════
# DUE DILIGENCE TEMPLATES
# ════════════════════════════════════════════════════════════

@router.get("/due-diligence/templates")
async def listar_templates(
    dd_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    filters = ["is_active = TRUE"]
    params: dict = {}
    if dd_type:
        filters.append("LOWER(dd_type) = LOWER(:dd_type)")
        params["dd_type"] = dd_type
    where = " AND ".join(filters)
    r = await db.execute(text(
        f"SELECT id, name, dd_type, items, created_at FROM due_diligence_templates "
        f"WHERE {where} ORDER BY name"
    ), params)
    return [dict(row._mapping) for row in r.fetchall()]


class DDTemplateCreate(BaseModel):
    name: str
    dd_type: str
    items: list


@router.post("/due-diligence/templates", status_code=201)
async def criar_template(
    body: DDTemplateCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    import json
    r = await db.execute(text("""
        INSERT INTO due_diligence_templates (id, name, dd_type, items, created_by)
        VALUES (gen_random_uuid()::text, :name, :dd_type, :items::jsonb, :uid)
        RETURNING id
    """), {
        "name": body.name, "dd_type": body.dd_type,
        "items": json.dumps(body.items, ensure_ascii=False), "uid": cu.id,
    })
    await db.commit()
    return {"id": r.scalar(), "created": True}


# ════════════════════════════════════════════════════════════
# COFRE — LOG DE ACESSO + SENSIBILIDADE
# ════════════════════════════════════════════════════════════

@router.get("/cofre/documentos/{document_id}/logs")
async def cofre_logs(
    document_id: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Logs de acesso ao cofre = trilha de auditoria sensível: só gestão consulta.
    if cu.role not in ("admin", "superadmin", "socio"):
        raise HTTPException(403, "Acesso restrito a sócios e administradores")
    r = await db.execute(text("""
        SELECT l.id, l.action, l.ip_address, l.created_at,
               u.full_name AS user_nome, u.email AS user_email
        FROM document_access_log l
        JOIN users u ON u.id = l.user_id
        WHERE l.document_id = :did
        ORDER BY l.created_at DESC
        LIMIT :lim
    """), {"did": document_id, "lim": limit})
    return [dict(row._mapping) for row in r.fetchall()]


def _pode_registrar_acesso(cu: User, confidencialidade: str) -> bool:
    """Mesmo limiar do download (documents._pode_acessar_confidencial):
    restrito+ exige socio ou superior."""
    if confidencialidade in _CONF_RESTRITA:
        return ROLE_LEVEL.get(cu.role.value, 0) >= ROLE_LEVEL["socio"]
    return True


@router.post("/cofre/documentos/{document_id}/registrar-acesso")
async def cofre_registrar_acesso(
    document_id: str,
    action: str = "view",
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Este endpoint ALIMENTA a trilha de auditoria do cofre (consumida por
    # cofre_logs/cofre_relatorio, restritos a sócios). Sem o MESMO gate do
    # download, qualquer usuário autenticado forjava acessos — com IP falso — em
    # documentos que sequer pode ver, e inflava download_count arbitrário. O IP
    # vem SEMPRE do servidor (request_context), nunca de um parâmetro do cliente.
    if action not in _COFRE_ACOES:
        raise HTTPException(
            422, f"Ação inválida: {action}. Use uma de: {', '.join(_COFRE_ACOES)}"
        )

    doc = (await db.execute(text("""
        SELECT case_id, confidencialidade FROM documents
        WHERE id = :did AND deleted_at IS NULL
    """), {"did": document_id})).first()
    if doc is None:
        raise HTTPException(404, "Documento não encontrado")

    if doc.case_id:
        await verificar_acesso_caso(db, cu, doc.case_id)
    conf = getattr(doc.confidencialidade, "value", doc.confidencialidade)
    if not _pode_registrar_acesso(cu, conf):
        raise HTTPException(403, "Documento restrito — acesso negado")

    await db.execute(text("""
        INSERT INTO document_access_log (id, document_id, user_id, action, ip_address)
        VALUES (gen_random_uuid()::text, :did, :uid, :action, :ip)
    """), {"did": document_id, "uid": cu.id, "action": action, "ip": get_client_ip()})

    if action == "download":
        await db.execute(text("""
            UPDATE documents
            SET download_count = download_count + 1,
                last_accessed_at = NOW()
            WHERE id = :did
        """), {"did": document_id})

    await db.commit()
    return {"registered": True}


class SensibilidadeUpdate(BaseModel):
    sensitivity_level: str
    access_users: list = []
    watermark: Optional[str] = None


@router.patch("/cofre/documentos/{document_id}/sensibilidade")
async def cofre_sensibilidade(
    document_id: str,
    body: SensibilidadeUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role not in ("admin", "superadmin", "socio"):
        raise HTTPException(403, "Acesso restrito a sócios e administradores")
    import json
    res = await db.execute(text("""
        UPDATE documents
        SET sensitivity_level = :sl,
            access_users = :au::jsonb,
            watermark = :wm,
            updated_at = NOW()
        WHERE id = :did AND deleted_at IS NULL
    """), {
        "sl": body.sensitivity_level,
        "au": json.dumps(body.access_users),
        "wm": body.watermark,
        "did": document_id,
    })
    # #30: sem checar rowcount o endpoint devolvia sucesso mesmo para um
    # document_id inexistente (no-op silencioso).
    if res.rowcount == 0:
        raise HTTPException(404, "Documento não encontrado")
    await db.commit()
    return {"updated": True, "document_id": document_id}


@router.get("/cofre/relatorio")
async def cofre_relatorio(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role not in ("admin", "superadmin", "socio"):
        raise HTTPException(403, "Acesso restrito a sócios e administradores")
    r = await db.execute(text("""
        SELECT d.id, d.title, d.sensitivity_level, d.download_count,
               d.last_accessed_at,
               COUNT(l.id) AS total_acessos
        FROM documents d
        LEFT JOIN document_access_log l ON l.document_id = d.id
        WHERE d.deleted_at IS NULL
        GROUP BY d.id, d.title, d.sensitivity_level, d.download_count, d.last_accessed_at
        ORDER BY d.last_accessed_at DESC NULLS LAST
        LIMIT :lim
    """), {"lim": limit})
    return [dict(row._mapping) for row in r.fetchall()]
