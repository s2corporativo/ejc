"""
app/routers/jurisprudencia_externa.py — Busca externa de jurisprudência.

Endpoints:
  GET  /jurisprudencia-externa/buscar   — busca LexML + TJMG
  POST /jurisprudencia-externa/importar — salva resultado na base interna
  GET  /jurisprudencia-externa/fontes   — status das fontes disponíveis
"""
from __future__ import annotations

from datetime import date as _date
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.jurisprudencia_interna import JurisprudenciaInterna
from app.services.jurisprudencia_externa import buscar_todas_fontes, buscar_lexml, buscar_tjmg

router = APIRouter(prefix="/jurisprudencia-externa", tags=["Jurisprudência Externa"])


def _is_staff(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]

def _pode_editar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]


@router.get("/buscar")
async def buscar(
    q: str = Query(..., min_length=3, description="Palavras-chave para busca"),
    fontes: str = Query("lexml,tjmg", description="Fontes: lexml, tjmg (separadas por vírgula)"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=30),
    cu: User = Depends(get_current_user),
):
    """
    Busca em tempo real nas fontes externas (LexML + TJMG).
    Não grava na base — use /importar para salvar.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    lista_fontes = [f.strip().lower() for f in fontes.split(",") if f.strip()]
    resultado = await buscar_todas_fontes(q, fontes=lista_fontes, pagina=pagina, por_pagina=por_pagina)
    return resultado


@router.get("/buscar/lexml")
async def buscar_lexml_endpoint(
    q: str = Query(..., min_length=3),
    tipo: str = Query("jurisprudencia", description="jurisprudencia | legislacao | doutrina"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=30),
    cu: User = Depends(get_current_user),
):
    """Busca exclusiva no LexML.gov.br com suporte a tipos (lei, jurisprudência, doutrina)."""
    if not _is_staff(cu):
        raise HTTPException(403)
    itens = await buscar_lexml(q, tipo=tipo, pagina=pagina, por_pagina=por_pagina)
    return {"total": len(itens), "fonte": "LexML", "itens": itens}


@router.get("/buscar/tjmg")
async def buscar_tjmg_endpoint(
    q: str = Query(..., min_length=3),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=30),
    cu: User = Depends(get_current_user),
):
    """Busca na jurisprudência pública do TJMG."""
    if not _is_staff(cu):
        raise HTTPException(403)
    itens = await buscar_tjmg(q, pagina=pagina, por_pagina=por_pagina)
    return {"total": len(itens), "fonte": "TJMG", "itens": itens}


@router.post("/importar", status_code=201)
async def importar_para_base(
    item: dict = Body(..., description="Item retornado pelo endpoint /buscar"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Salva um resultado de busca externa na base interna de jurisprudências.
    Verifica duplicata por numero_acordao + tribunal antes de inserir.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)

    from sqlalchemy import select
    numero = item.get("numero_acordao") or ""
    tribunal = item.get("tribunal") or ""

    # Verificar duplicata
    if numero and tribunal:
        existing = (await db.execute(
            select(JurisprudenciaInterna).where(
                JurisprudenciaInterna.numero_acordao == numero,
                JurisprudenciaInterna.tribunal == tribunal,
                JurisprudenciaInterna.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing:
            return {
                "importado": False,
                "duplicata": True,
                "id": existing.id,
                "detalhe": f"Já existe na base: {numero} / {tribunal}",
            }

    data_julg = None
    if item.get("data_julgamento"):
        try:
            data_julg = _date.fromisoformat(item["data_julgamento"])
        except ValueError:
            pass

    j = JurisprudenciaInterna(
        id=str(uuid4()),
        created_by=cu.id,
        titulo=item.get("titulo", "")[:300],
        ementa=item.get("ementa", ""),
        fundamentacao=None,
        tribunal=tribunal,
        relator=item.get("relator", ""),
        numero_acordao=numero,
        data_julgamento=data_julg,
        fonte=item.get("fonte", "externo"),
        link_original=item.get("link_original", ""),
        area_juridica=item.get("area_juridica", ""),
        tags=None,
        resultado=None,
        favorito=False,
    )
    db.add(j)
    await db.commit()

    return {
        "importado": True,
        "id": j.id,
        "titulo": j.titulo,
        "tribunal": j.tribunal,
        "fonte": j.fonte,
    }


@router.post("/importar-lote", status_code=201)
async def importar_lote(
    itens: list[dict] = Body(..., description="Lista de itens do /buscar"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Importa múltiplos resultados de uma vez, ignorando duplicatas."""
    if not _pode_editar(cu):
        raise HTTPException(403)

    importados, duplicatas, erros = 0, 0, 0
    for item in itens[:50]:  # máx 50 por vez
        try:
            from sqlalchemy import select
            numero  = item.get("numero_acordao") or ""
            tribunal = item.get("tribunal") or ""
            if numero and tribunal:
                existing = (await db.execute(
                    select(JurisprudenciaInterna).where(
                        JurisprudenciaInterna.numero_acordao == numero,
                        JurisprudenciaInterna.tribunal == tribunal,
                        JurisprudenciaInterna.deleted_at.is_(None),
                    )
                )).scalar_one_or_none()
                if existing:
                    duplicatas += 1
                    continue

            data_julg = None
            if item.get("data_julgamento"):
                try:
                    data_julg = _date.fromisoformat(item["data_julgamento"])
                except ValueError:
                    pass

            j = JurisprudenciaInterna(
                id=str(uuid4()), created_by=cu.id,
                titulo=(item.get("titulo") or "")[:300],
                ementa=item.get("ementa", ""),
                tribunal=tribunal, relator=item.get("relator", ""),
                numero_acordao=numero,
                data_julgamento=data_julg,
                fonte=item.get("fonte", "externo"),
                link_original=item.get("link_original", ""),
                area_juridica=item.get("area_juridica", ""),
                favorito=False,
            )
            db.add(j)
            importados += 1
        except Exception:
            erros += 1

    await db.commit()
    return {"importados": importados, "duplicatas": duplicatas, "erros": erros}


@router.get("/fontes")
async def status_fontes(cu: User = Depends(get_current_user)):
    """Retorna status e informações das fontes externas disponíveis."""
    return {
        "fontes": [
            {
                "id": "lexml",
                "nome": "LexML.gov.br",
                "descricao": "Legislação federal, jurisprudência e doutrina (Senado/Câmara/STF/STJ)",
                "url": "https://www.lexml.gov.br",
                "tipo": "API pública XML",
                "cobertura": "Federal — STF, STJ, TST, TRFs, legislação",
                "gratuita": True,
            },
            {
                "id": "tjmg",
                "nome": "TJMG — Tribunal de Justiça de Minas Gerais",
                "descricao": "Jurisprudência do TJMG via portal público de acórdãos",
                "url": "https://www5.tjmg.jus.br/jurisprudencia/",
                "tipo": "Portal público (scraping HTML)",
                "cobertura": "Estadual MG — câmaras cíveis, criminais, administrativas",
                "gratuita": True,
            },
            {
                "id": "datajud",
                "nome": "DataJud / CNJ",
                "descricao": "Base nacional de dados processuais (CNJ)",
                "url": "https://datajud-wiki.cnj.jus.br",
                "tipo": "API REST (chave necessária)",
                "cobertura": "Nacional — todos os tribunais",
                "gratuita": False,
                "status": "placeholder — integração via /cases/{id}/sincronizar-processo",
            },
        ]
    }
