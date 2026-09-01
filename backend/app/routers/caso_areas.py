"""Multi-área por caso — área principal + áreas relacionadas (N:N).
   Um mesmo caso pode tocar vários ramos (ex.: multa ambiental = ambiental + administrativo + tributário).
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User

router = APIRouter(prefix="/cases/{case_id}/areas", tags=["Áreas do Caso"])


@router.get("")
async def listar_areas(case_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    await verificar_acesso_caso(db, cu, case_id)
    rows = (await db.execute(text("""
        SELECT area, principal FROM caso_areas WHERE case_id = :cid ORDER BY principal DESC, area
    """), {"cid": case_id})).mappings().all()
    return {"areas": [dict(r) for r in rows]}


@router.post("")
async def adicionar_area(case_id: str, body: dict = Body(...),
                         db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    # Normalização (padronização): a área é gravada SEMPRE em minúsculas e sem
    # espaços nas bordas. Antes, este endpoint gravava o texto cru enquanto
    # cases.py::aplicar_extracao já normalizava — o mesmo ramo entrava duas
    # vezes na tabela ("Ambiental" e "ambiental") e escapava do índice único
    # (case_id, area).
    area = (body.get("area") or "").strip().lower()
    if not area:
        raise HTTPException(422, "Campo obrigatório: area")
    if len(area) > 40:
        raise HTTPException(422, "Área inválida: máximo de 40 caracteres")
    principal = bool(body.get("principal", False))
    # verificar_acesso_caso já devolve 404 p/ caso inexistente/excluído e 403
    # sem permissão — a consulta anterior a `cases` duplicava esse SELECT.
    await verificar_acesso_caso(db, cu, case_id)
    # Validação contra a taxonomia canônica (routers/areas.py → tabela `areas`).
    # Só rejeita quando o catálogo está populado: em base sem seed de áreas o
    # endpoint continua aceitando, para não travar ambiente novo.
    catalogo = (await db.execute(text(
        "SELECT count(*) FROM areas WHERE ativo = true"
    ))).scalar() or 0
    if catalogo:
        conhecida = (await db.execute(text(
            "SELECT 1 FROM areas WHERE slug = :a AND ativo = true LIMIT 1"
        ), {"a": area})).scalar()
        if not conhecida:
            raise HTTPException(
                422,
                f"Área inválida: {area!r}. Consulte GET /areas para a lista de áreas ativas.",
            )
    if principal:
        await db.execute(text("UPDATE caso_areas SET principal = false WHERE case_id = :cid"), {"cid": case_id})
    await db.execute(text("""
        INSERT INTO caso_areas (case_id, area, principal) VALUES (:cid, :a, :p)
        ON CONFLICT (case_id, area) DO UPDATE SET principal = EXCLUDED.principal
    """), {"cid": case_id, "a": area, "p": principal})
    await db.commit()
    return {"ok": True}


@router.delete("/{area}")
async def remover_area(case_id: str, area: str,
                       db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    """Remove uma área SECUNDÁRIA do caso.

    A área principal é protegida de propósito (o caso não pode ficar sem ramo).
    Antes, o DELETE devolvia sempre `{"ok": true}` mesmo quando nada era
    removido: a tela dava sucesso, recarregava e a área continuava lá, sem
    qualquer explicação ao usuário. Agora o resultado reflete o que aconteceu.
    """
    await verificar_acesso_caso(db, cu, case_id)
    linha = (await db.execute(text("""
        SELECT principal FROM caso_areas WHERE case_id = :cid AND area = :a LIMIT 1
    """), {"cid": case_id, "a": area})).scalar()
    if linha is None:
        raise HTTPException(404, "Área não vinculada a este caso")
    if linha:
        raise HTTPException(
            409,
            "Área principal não pode ser removida — defina outra área como "
            "principal antes de removê-la.",
        )
    await db.execute(text("""
        DELETE FROM caso_areas WHERE case_id = :cid AND area = :a AND principal = false
    """), {"cid": case_id, "a": area})
    await db.commit()
    return {"ok": True}
