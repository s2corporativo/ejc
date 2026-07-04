# ── app/routers/search.py ─────────────────────────────────────────────────────
# Busca global unificada (clientes, casos, peças) respeitando o escopo do perfil.
# Suporta tipos de busca: tudo (padrão) | parte | cpf | processo.
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.legal_doc import LegalDoc
from app.models.process import Process
from app.routers.clients import _CLIENTES   # papéis com acesso ao CRM de clientes
from app.services.pii_crypto import normalizar_documento, hash_documento

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


def _mascarar_doc(doc: str | None) -> str:
    """Mascara CPF/CNPJ para exibição: só os 4 últimos dígitos (ex.: ***5678)."""
    dig = normalizar_documento(doc) or ""
    return f"***{dig[-4:]}" if dig else ""


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
    tipo=parte    → casos cuja parte processual ATIVA tem o nome buscado.
    tipo=cpf      → clientes (só papéis com acesso ao CRM) e partes por
                    CPF/CNPJ (com ou sem máscara; hash exato quando 11/14
                    dígitos). Documentos são exibidos mascarados (***1234).
    tipo=processo → casos por número de processo/interno e números CNJ
                    dos processos vinculados (tabela `processes`).

    Limites: cada categoria/bloco devolve até `limit` itens (em tipo=processo,
    até `limit` casos via Case.numero_processo/numero_interno + até `limit`
    casos adicionais via Process.numero_cnj, sem duplicar).
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
            .where(Case.deleted_at.is_(None),
                   CaseParte.ativo.is_(True),   # soft-delete de parte = ativo=false
                   CaseParte.nome.ilike(termo))
            .order_by(Case.updated_at.desc()),
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

        # Clientes (cpf ou cnpj) — SÓ para papéis com acesso ao CRM, espelhando
        # a matriz do router de clientes (clients.py:_CLIENTES). Os demais
        # papéis seguem vendo apenas partes→casos (já escopado por caso).
        if cu.role.value in _CLIENTES:
            # Fallback legado: colunas plaintext parciais (podem estar
            # mascaradas no banco → compara só-dígitos dos dois lados).
            conds_cli = [_so_digitos(Client.cpf).like(alvo),
                         _so_digitos(Client.cnpj).like(alvo)]
            # Documento completo (11=CPF, 14=CNPJ) → busca EXATA pelo índice
            # cego (cpf_hash/cnpj_hash), que continua funcionando quando as
            # colunas plaintext forem removidas.
            if len(digitos) in (11, 14):
                try:
                    h = hash_documento(digitos)
                except RuntimeError:
                    h = None   # PII_HASH_KEY ausente — segue só com o fallback
                if h:
                    conds_cli.append(Client.cpf_hash == h if len(digitos) == 11
                                     else Client.cnpj_hash == h)
            qcli = (select(Client)
                    .where(Client.deleted_at.is_(None), or_(*conds_cli))
                    .order_by(Client.updated_at.desc()))
            for c in (await db.execute(qcli.limit(limit))).scalars().all():
                out.append({"tipo": "cliente", "id": c.id,
                            "titulo": c.nome or c.razao_social or "—",
                            "subtitulo": _mascarar_doc(c.cpf or c.cnpj),
                            "link": "/clientes"})

        # Partes processuais ativas → caso dono
        qp = _escopo_casos(
            select(CaseParte, Case)
            .join(Case, Case.id == CaseParte.case_id)
            .where(Case.deleted_at.is_(None),
                   CaseParte.ativo.is_(True),
                   _so_digitos(CaseParte.cpf_cnpj).like(alvo))
            .order_by(Case.updated_at.desc()),
            cu,
        )
        casos_vistos: set[str] = set()
        for parte, caso in (await db.execute(qp.limit(limit * 3))).all():
            if caso.id in casos_vistos:
                continue
            casos_vistos.add(caso.id)
            out.append(_item_caso(
                caso, f"Parte: {parte.nome} · {_mascarar_doc(parte.cpf_cnpj)}"))
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
            select(Case).where(Case.deleted_at.is_(None), or_(*conds))
            .order_by(Case.updated_at.desc()), cu)
        for caso in (await db.execute(qc.limit(limit))).scalars().all():
            casos_vistos.add(caso.id)
            out.append(_item_caso(
                caso, caso.numero_processo or caso.numero_interno or ""))

        # Processos vinculados (model Process, 1 Caso : N Processos) → caso dono.
        conds_p = [Process.numero_cnj.ilike(termo)]
        if digitos:
            conds_p.append(_so_digitos(Process.numero_cnj).like(f"%{digitos}%"))
        qproc = _escopo_casos(
            select(Process, Case)
            .join(Case, Case.id == Process.case_id)
            .where(Process.deleted_at.is_(None), Case.deleted_at.is_(None),
                   or_(*conds_p))
            .order_by(Case.updated_at.desc()),
            cu,
        )
        adicionados = 0   # cap de `limit` casos vindos de Process (além dos acima)
        for proc, caso in (await db.execute(qproc.limit(limit * 3))).all():
            if caso.id in casos_vistos:
                continue   # caso já listado via numero_processo/numero_interno
            casos_vistos.add(caso.id)
            out.append(_item_caso(caso, proc.numero_cnj or ""))
            adicionados += 1
            if adicionados >= limit:
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
