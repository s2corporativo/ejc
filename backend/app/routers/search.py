# ── app/routers/search.py ─────────────────────────────────────────────────────
# Busca global unificada (clientes, casos, peças) respeitando o escopo do perfil.
# Suporta tipos de busca: tudo (padrão) | parte | cpf | processo.
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.legal_doc import LegalDoc
from app.services.pii_crypto import normalizar_documento

router = APIRouter(prefix="/search", tags=["Busca global"])


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _escopo_casos(stmt, cu: User):
    """Aplica o escopo por perfil sobre um select que envolve Case."""
    if not _ve_todos(cu):
        stmt = stmt.where(or_(Case.advogado_responsavel_id == cu.id,
                              Case.advogado_auxiliar_id == cu.id))
    return stmt


def _so_digitos(coluna):
    """Coluna normalizada para apenas dígitos (compara CPF/CNPJ/CNJ com ou sem máscara)."""
    return func.regexp_replace(func.coalesce(coluna, ""), "[^0-9]", "", "g")


def _item_caso(caso: Case, subtitulo: str) -> dict:
    return {"tipo": "caso", "id": caso.id, "titulo": caso.titulo,
            "subtitulo": subtitulo, "link": f"/casos/{caso.id}"}


@router.get("")
@router.get("/")
@limiter.limit("30/minute")
async def busca_global(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    tipo: str = Query("tudo", pattern="^(tudo|parte|cpf|processo)$"),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Busca unificada em clientes, casos e peças (escopo por perfil).

    tipo=tudo     → comportamento clássico (clientes + casos + peças).
    tipo=parte    → casos cuja parte processual tem o nome buscado.
    tipo=cpf      → clientes e partes por CPF/CNPJ (com ou sem máscara).
    tipo=processo → casos por número de processo/interno e números CNJ
                    dos processos vinculados (tabela `processes`).
    """
    if cu.role.value == "cliente_externo":
        return {"q": q, "tipo": tipo, "resultados": []}   # o portal do cliente tem visão própria

    termo = f"%{q.strip()}%"
    out = []

    # ── Busca por PARTE ──
    if tipo == "parte":
        qp = _escopo_casos(
            select(CaseParte, Case)
            .join(Case, Case.id == CaseParte.case_id)
            .where(Case.deleted_at.is_(None), CaseParte.nome.ilike(termo)),
            cu,
        )
        casos_vistos: set[str] = set()
        for parte, caso in (await db.execute(qp.limit(limit * 3))).all():
            if caso.id in casos_vistos:
                continue   # evita duplicar o mesmo caso (várias partes batendo)
            casos_vistos.add(caso.id)
            out.append(_item_caso(caso, f"Parte: {parte.nome}"))
            if len(out) >= limit:
                break
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    # ── Busca por CPF/CNPJ ──
    if tipo == "cpf":
        digitos = normalizar_documento(q)   # mesma normalização de clients.py/pii_crypto
        if not digitos:
            return {"q": q, "tipo": tipo, "total": 0, "resultados": []}
        alvo = f"%{digitos}%"

        # Clientes (cpf ou cnpj, valores no banco podem estar mascarados)
        qcli = select(Client).where(
            Client.deleted_at.is_(None),
            or_(_so_digitos(Client.cpf).like(alvo),
                _so_digitos(Client.cnpj).like(alvo)),
        )
        for c in (await db.execute(qcli.limit(limit))).scalars().all():
            out.append({"tipo": "cliente", "id": c.id,
                        "titulo": c.nome or c.razao_social or "—",
                        "subtitulo": c.cpf or c.cnpj or "", "link": "/clientes"})

        # Partes processuais → caso dono
        qp = _escopo_casos(
            select(CaseParte, Case)
            .join(Case, Case.id == CaseParte.case_id)
            .where(Case.deleted_at.is_(None),
                   _so_digitos(CaseParte.cpf_cnpj).like(alvo)),
            cu,
        )
        casos_vistos: set[str] = set()
        for parte, caso in (await db.execute(qp.limit(limit * 3))).all():
            if caso.id in casos_vistos:
                continue
            casos_vistos.add(caso.id)
            out.append(_item_caso(caso, f"Parte: {parte.nome} · {parte.cpf_cnpj}"))
            if len(casos_vistos) >= limit:
                break
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    # ── Busca por NÚMERO DE PROCESSO ──
    if tipo == "processo":
        digitos = normalizar_documento(q)   # número CNJ digitado com ou sem máscara
        casos_vistos: set[str] = set()

        # Case.numero_processo / Case.numero_interno (bruto e só-dígitos)
        conds = [Case.numero_processo.ilike(termo), Case.numero_interno.ilike(termo)]
        if digitos:
            alvo = f"%{digitos}%"
            conds += [_so_digitos(Case.numero_processo).like(alvo),
                      _so_digitos(Case.numero_interno).like(alvo)]
        qc = _escopo_casos(
            select(Case).where(Case.deleted_at.is_(None), or_(*conds)), cu)
        for caso in (await db.execute(qc.limit(limit))).scalars().all():
            casos_vistos.add(caso.id)
            out.append(_item_caso(
                caso, caso.numero_processo or caso.numero_interno or ""))

        # Processos vinculados (tabela `processes`, 1 Caso : N Processos — SQL cru,
        # padrão do router processes.py; não há model ORM para essa entidade).
        sql = """
            SELECT p.numero_cnj, c.id AS case_id, c.titulo
            FROM processes p
            JOIN cases c ON c.id = p.case_id
            WHERE p.deleted_at IS NULL AND c.deleted_at IS NULL
              AND (p.numero_cnj ILIKE :termo {cond_digitos})
              {cond_escopo}
            LIMIT :lim
        """
        params = {"termo": termo, "lim": limit * 3}
        cond_digitos = ""
        if digitos:
            cond_digitos = ("OR regexp_replace(coalesce(p.numero_cnj, ''), "
                            "'[^0-9]', '', 'g') LIKE :alvo")
            params["alvo"] = f"%{digitos}%"
        cond_escopo = ""
        if not _ve_todos(cu):
            cond_escopo = ("AND (c.advogado_responsavel_id = :uid "
                           "OR c.advogado_auxiliar_id = :uid)")
            params["uid"] = cu.id
        rows = (await db.execute(
            text(sql.format(cond_digitos=cond_digitos, cond_escopo=cond_escopo)),
            params,
        )).mappings().all()
        for r in rows:
            if r["case_id"] in casos_vistos:
                continue   # caso já listado via numero_processo/numero_interno
            casos_vistos.add(r["case_id"])
            out.append({"tipo": "caso", "id": r["case_id"], "titulo": r["titulo"],
                        "subtitulo": r["numero_cnj"] or "",
                        "link": f"/casos/{r['case_id']}"})
            if len(out) >= limit * 2:
                break
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    # ── tipo=tudo (comportamento clássico) ──
    # ── Clientes ──
    cli = (await db.execute(
        select(Client).where(
            Client.deleted_at.is_(None),
            or_(Client.nome.ilike(termo), Client.razao_social.ilike(termo),
                Client.cpf.ilike(termo), Client.cnpj.ilike(termo)),
        ).limit(limit)
    )).scalars().all()
    for c in cli:
        out.append({"tipo": "cliente", "id": c.id,
                    "titulo": c.nome or c.razao_social or "—",
                    "subtitulo": c.cpf or c.cnpj or "", "link": "/clientes"})

    # ── Casos (escopo) ──
    qc = select(Case).where(
        Case.deleted_at.is_(None),
        or_(Case.titulo.ilike(termo), Case.numero_interno.ilike(termo),
            Case.numero_processo.ilike(termo)),
    )
    if not _ve_todos(cu):
        qc = qc.where(or_(Case.advogado_responsavel_id == cu.id,
                          Case.advogado_auxiliar_id == cu.id))
    casos = (await db.execute(qc.limit(limit))).scalars().all()
    for c in casos:
        out.append({"tipo": "caso", "id": c.id, "titulo": c.titulo,
                    "subtitulo": c.numero_interno or c.numero_processo or "",
                    "link": f"/casos/{c.id}"})

    # ── Peças (escopo via caso) ──
    qp = select(LegalDoc).where(
        LegalDoc.deleted_at.is_(None), LegalDoc.titulo.ilike(termo),
    )
    if not _ve_todos(cu):
        sub = select(Case.id).where(or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id))
        qp = qp.where(LegalDoc.case_id.in_(sub))
    pecas = (await db.execute(qp.limit(limit))).scalars().all()
    for p in pecas:
        out.append({"tipo": "peca", "id": p.id, "titulo": p.titulo,
                    "subtitulo": str(p.status.value), "link": "/pecas"})

    return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}
