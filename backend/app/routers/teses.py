# ── app/routers/teses.py ─────────────────────────────────────────────────────
# Banco de Teses Jurídicas — CRUD + ranking + sugestão por IA.
# Acesso: staff (advogado+). Criação: advogado+.
from __future__ import annotations
import logging
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL, EQUIPE_JURIDICA
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.case import Case
from app.models.tese import (
    ELEMENTOS_FONTE, MOTIVOS_OVERRIDE, STATUS_FONTE,
    Tese, TeseCasoLink, TeseTipo, TeseStatus,
)
from app.services import ficha_viva_service as ficha_viva
from app.core.rate_limit import rate_limit
from app.models.diario_oficial import DiarioOficialAlerta
from app.modules.dpt360.access_scope import visible_alerts_query
from app.services.impacto_regulatorio import (
    MAX_PUBLICACOES_VARRIDAS, MAX_TESES_VARRIDAS, ranquear_teses_afetadas,
)
from app.services.tese_caso_matcher import (
    MAX_CASOS_VARRIDOS, PISO_RELEVANCIA_PADRAO, extrair_termos, ranquear_candidatos,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teses", tags=["Banco de Teses"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeseIn(BaseModel):
    titulo:           str = Field(min_length=5, max_length=300)
    descricao:        str = Field(min_length=10)
    fundamentacao:    Optional[str] = None
    jurisprudencia:   Optional[str] = None
    contra_argumento: Optional[str] = None
    area_juridica:    Optional[str] = None
    tribunal:         Optional[str] = None
    magistrado:       Optional[str] = None
    tags:             Optional[str] = None
    observacoes:      Optional[str] = None
    tipo:             TeseTipo     = TeseTipo.escritorio
    status:           TeseStatus   = TeseStatus.ativa
    # QUANDO a ficha se aplica. Aceita lista, JSON em string ou CSV — a
    # normalização vive no service (o campo vem de formulário, import e
    # sugestão de IA, e recusar por formato faria simplesmente não ser
    # preenchido, que é o pior resultado possível para ele).
    gatilhos:         Optional[list[str] | str] = None


class TesePatch(BaseModel):
    titulo:           Optional[str] = None
    descricao:        Optional[str] = None
    fundamentacao:    Optional[str] = None
    jurisprudencia:   Optional[str] = None
    contra_argumento: Optional[str] = None
    area_juridica:    Optional[str] = None
    tribunal:         Optional[str] = None
    magistrado:       Optional[str] = None
    tags:             Optional[str] = None
    observacoes:      Optional[str] = None
    tipo:             Optional[TeseTipo]   = None
    status:           Optional[TeseStatus] = None
    gatilhos:         Optional[list[str] | str] = None
    # O que mudou e por quê — vai para o histórico imutável da ficha.
    resumo_mudanca:   Optional[str] = Field(default=None, max_length=2000)


class LinkIn(BaseModel):
    case_id:    str
    resultado:  Optional[str] = None   # procedente|improcedente|acordo|pendente
    observacao: Optional[str] = None


class SugestaoIARequest(BaseModel):
    descricao_fatos: str = Field(min_length=30)
    area: str
    case_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff(user: User) -> bool:
    # Issue #694: allowlist EXATA — financeiro não acessa o banco de teses
    # jurídicas, mesmo com ROLE_LEVEL acima de estagiario.
    return user.role.value in EQUIPE_JURIDICA

def _pode_editar(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["advogado"]

def _tese_out(t: Tese) -> dict:
    return {
        "id": t.id, "titulo": t.titulo, "descricao": t.descricao,
        "fundamentacao": t.fundamentacao, "jurisprudencia": t.jurisprudencia,
        "contra_argumento": t.contra_argumento,
        "area_juridica": t.area_juridica, "tribunal": t.tribunal,
        "magistrado": t.magistrado, "tags": t.tags, "observacoes": t.observacoes,
        "tipo": t.tipo.value, "status": t.status.value,
        "gatilhos": list(t.gatilhos or []), "versao": t.versao,
        "vezes_usada": t.vezes_usada, "vezes_venceu": t.vezes_venceu,
        "vezes_perdeu": t.vezes_perdeu, "taxa_sucesso": t.taxa_sucesso,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def listar_teses(
    area: Optional[str] = Query(None),
    status: Optional[str] = Query("ativa"),
    tipo: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    order_by: str = Query("taxa_sucesso"),   # taxa_sucesso|vezes_usada|created_at
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito a advogados")

    q = select(Tese).where(Tese.deleted_at.is_(None))
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    if status:
        q = q.where(Tese.status == status)
    if tipo:
        q = q.where(Tese.tipo == tipo)
    if tribunal:
        q = q.where(Tese.tribunal.ilike(f"%{tribunal}%"))
    if busca:
        termo = f"%{busca}%"
        q = q.where(or_(
            Tese.titulo.ilike(termo),
            Tese.descricao.ilike(termo),
            Tese.fundamentacao.ilike(termo),
            Tese.tags.ilike(termo),
        ))

    if order_by == "taxa_sucesso":
        q = q.order_by(Tese.taxa_sucesso.desc().nullslast())
    elif order_by == "vezes_usada":
        q = q.order_by(Tese.vezes_usada.desc())
    else:
        q = q.order_by(Tese.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    teses = (await db.execute(q.offset((page-1)*per_page).limit(per_page))).scalars().all()

    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [_tese_out(t) for t in teses],
    }


@router.post("", status_code=201)
async def criar_tese(
    req: TeseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    dados = req.model_dump()
    dados["gatilhos"] = ficha_viva.normalizar_gatilhos(dados.get("gatilhos"))
    tese = Tese(id=str(uuid4()), created_by=cu.id, **dados)
    db.add(tese)
    # Versão 1 = o estado ORIGINAL da ficha. Sem gravá-la aqui, o histórico
    # começaria na primeira EDIÇÃO e o texto com que a ficha nasceu — o que
    # fundamentou as primeiras peças — se perderia. Mesma transação do INSERT.
    await ficha_viva.registrar_versao(
        db, tese, user_id=cu.id, resumo_mudanca="Criação da ficha.")
    await db.commit()
    return _tese_out(tese)


@router.get("/ranking")
async def ranking_teses(
    area: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Top teses por taxa de sucesso — painel de inteligência do escritório."""
    if not _is_staff(cu):
        raise HTTPException(403)
    q = select(Tese).where(
        Tese.deleted_at.is_(None),
        Tese.status == TeseStatus.ativa,
        Tese.vezes_usada >= 1,
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    q = q.order_by(Tese.taxa_sucesso.desc().nullslast()).limit(limit)
    teses = (await db.execute(q)).scalars().all()
    return [_tese_out(t) for t in teses]


@router.get("/busca-avancada")
async def busca_avancada(
    q: Optional[str] = Query(None, description="Texto livre (título/descrição/fundamentação/tags)"),
    area: Optional[str] = Query(None),
    tribunal: Optional[str] = Query(None),
    status: Optional[str] = Query("ativa"),
    tipo: Optional[str] = Query(None),
    taxa_minima: Optional[float] = Query(None, ge=0, le=1, description="Taxa de sucesso mínima (0–1)"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Busca avançada de teses — consumida por Biblioteca.tsx (era 404).
    Filtros combináveis: texto livre + área + tribunal + taxa mínima + status/tipo.
    Retorna {"total", "teses"} (contrato esperado pelo frontend).
    IMPORTANTE: declarada ANTES de /{tese_id} para não colidir com a rota dinâmica.
    """
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito a advogados")

    stmt = select(Tese).where(Tese.deleted_at.is_(None))
    if area:
        stmt = stmt.where(Tese.area_juridica.ilike(f"%{area}%"))
    if tribunal:
        stmt = stmt.where(Tese.tribunal.ilike(f"%{tribunal}%"))
    if status:
        stmt = stmt.where(Tese.status == status)
    if tipo:
        stmt = stmt.where(Tese.tipo == tipo)
    if taxa_minima is not None:
        stmt = stmt.where(Tese.taxa_sucesso >= taxa_minima)
    if q:
        termo = f"%{q}%"
        stmt = stmt.where(or_(
            Tese.titulo.ilike(termo),
            Tese.descricao.ilike(termo),
            Tese.fundamentacao.ilike(termo),
            Tese.jurisprudencia.ilike(termo),
            Tese.tags.ilike(termo),
        ))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    teses = (await db.execute(
        stmt.order_by(Tese.taxa_sucesso.desc().nullslast(), Tese.created_at.desc())
            .offset(offset).limit(limit)
    )).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "teses": [_tese_out(t) for t in teses],
    }


@router.get("/casos/{case_id}")
async def teses_do_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Teses vinculadas a um caso (via tese_caso_links), com resultado da aplicação."""
    if not _is_staff(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, case_id)  # gate ownership (sigilo EOAB/LGPD)
    rows = (await db.execute(
        select(Tese, TeseCasoLink)
        .join(TeseCasoLink, TeseCasoLink.tese_id == Tese.id)
        .where(TeseCasoLink.case_id == case_id, Tese.deleted_at.is_(None))
        .order_by(TeseCasoLink.created_at.desc())
    )).all()
    out = []
    for t, link in rows:
        item = _tese_out(t)
        item["link_id"] = link.id
        item["resultado"] = link.resultado
        item["observacao"] = link.observacao
        out.append(item)
    return out


@router.get("/impacto-regulatorio")
async def impacto_regulatorio(
    dias: int = Query(7, ge=1, le=90),
    limite: int = Query(20, ge=1, le=100),
    piso: int = Query(PISO_RELEVANCIA_PADRAO, ge=0, le=100,
                      description="score mínimo (0-100) para a tese entrar na lista"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Quais teses do escritório podem ter sido afetadas pelo que saiu no Diário.

    O radar do EJC já respondia "publicação nova → quais EMPRESAS ela atinge"
    (`modules/dpt360/radar_service.py`). Faltava o alvo jurídico, que é o que a
    frente 1 do plano de evolução pede: "esta publicação mexe com a tese X".

    Determinístico, sem IA (`services/impacto_regulatorio.py`), reusando o
    classificador de área e o mapa de equivalências do próprio radar — uma
    taxonomia só, não duas divergindo com o tempo.

    A saída é SUGESTÃO: diz qual tese reler e por quê (os termos que casaram).
    Nada é marcado como superado automaticamente — reavaliar uma tese à luz de
    norma nova é ato jurídico humano.

    Visibilidade: os alertas passam por `visible_alerts_query`, o contrato
    canônico do Diário Oficial (gestão vê tudo; advogado vê os office-wide e os
    dos próprios casos). Esta rota NÃO amplia essa superfície.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    alertas = (await db.execute(
        visible_alerts_query(cu)
        .where(DiarioOficialAlerta.created_at >= desde)
        .order_by(DiarioOficialAlerta.created_at.desc())
        .limit(MAX_PUBLICACOES_VARRIDAS)
    )).scalars().all()

    publicacoes = [{
        "id": a.id,
        "fonte": a.fonte,
        "titulo": a.titulo,
        "resumo": a.resumo,
        "link": a.link,
        "keyword_match": a.keyword_match,
        "data_publicacao": a.data_publicacao.isoformat() if a.data_publicacao else None,
    } for a in alertas]

    teses_rows = (await db.execute(
        select(Tese)
        .where(Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa)
        .order_by(Tese.created_at.desc())
        .limit(MAX_TESES_VARRIDAS)
    )).scalars().all()

    teses = [{
        "id": t.id,
        "titulo": t.titulo,
        "area_juridica": t.area_juridica,
        # Mesmos campos da varredura tese → caso: título, tags e descrição.
        # Fundamentação e jurisprudência ficam de fora de propósito — inflam a
        # lista de termos e o casamento vira ruído.
        "termos": extrair_termos(t.titulo, t.tags, t.descricao),
    } for t in teses_rows]

    afetadas = ranquear_teses_afetadas(teses, publicacoes, piso=piso, limite=limite)

    return {
        "periodo_dias": dias,
        "desde": desde.date().isoformat(),
        "publicacoes_varridas": len(publicacoes),
        "teto_de_varredura_atingido": len(publicacoes) >= MAX_PUBLICACOES_VARRIDAS,
        "teses_varridas": len(teses),
        "total": len(afetadas),
        "teses_afetadas": afetadas,
        "aviso": ("Sugestão determinística por casamento de termos — indica o que "
                  "RELER, não o que está superado. Confira a publicação antes de "
                  "alterar qualquer tese."),
    }


@router.get("/{tese_id}")
async def obter_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tese não encontrada")
    return _tese_out(t)


@router.patch("/{tese_id}")
async def atualizar_tese(
    tese_id: str, req: TesePatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    mudancas = req.model_dump(exclude_none=True)
    # `resumo_mudanca` descreve a edição; não é campo da ficha.
    resumo = mudancas.pop("resumo_mudanca", None)
    if "gatilhos" in mudancas:
        mudancas["gatilhos"] = ficha_viva.normalizar_gatilhos(mudancas["gatilhos"])
    for campo, valor in mudancas.items():
        setattr(t, campo, valor)
    t.updated_at = datetime.now(timezone.utc)
    # DEPOIS de aplicar as alterações e ANTES do commit, na MESMA transação:
    # versão gravada sem a alteração correspondente (ou vice-versa) é a classe
    # de defeito que o CLAUDE.md marca como recorrente. Devolve None quando
    # nada mudou de fato — salvar sem alterar não polui o histórico.
    versao = await ficha_viva.registrar_versao(
        db, t, user_id=cu.id, resumo_mudanca=resumo)
    await db.commit()
    saida = _tese_out(t)
    saida["versao_registrada"] = versao.versao if versao else None
    return saida


@router.delete("/{tese_id}", status_code=204)
async def arquivar_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios podem arquivar teses")
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/{tese_id}/casos-candidatos")
async def casos_candidatos(
    tese_id: str,
    limite: int = Query(20, ge=1, le=100),
    piso: int = Query(PISO_RELEVANCIA_PADRAO, ge=0, le=100,
                      description="score mínimo (0-100) para entrar na lista"),
    incluir_arquivados: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Varredura REVERSA: dada uma tese, onde ela pode caber.

    O caminho caso → teses já existia (`teses_do_caso`, `sugerir_teses_ia`).
    Este é o inverso, e é o que transforma o Banco de Teses de catálogo em
    ferramenta ativa: "a tese X é possivelmente cabível nos processos A, B e C".

    Determinístico, sem IA (ver `services/tese_caso_matcher.py`). A lista é de
    CANDIDATOS — vincular continua sendo ato humano via
    `POST /teses/{tese_id}/vincular-caso`.

    Visibilidade: reusa o mesmo critério de `cases._filtro_visibilidade`
    (advogado/auxiliar vê os próprios casos, socio+ vê todos). Sem isso a
    varredura seria um vazamento: devolveria título e área de casos que o
    usuário não pode abrir.
    """
    if not _is_staff(cu):
        raise HTTPException(403)

    tese = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not tese:
        raise HTTPException(404, "Tese não encontrada")

    termos = extrair_termos(tese.titulo, tese.tags, tese.descricao)
    if not termos:
        return {
            "tese_id": tese_id, "titulo": tese.titulo,
            "area_juridica": tese.area_juridica, "termos": [],
            "total": 0, "candidatos": [],
            "aviso": ("A tese não tem termos aproveitáveis no título, nas tags "
                      "ou na descrição — sem isso não há como procurar casos."),
        }

    # Casos já vinculados saem da lista: o pedido é "onde ela AINDA pode caber".
    ja_vinculados = set((await db.execute(
        select(TeseCasoLink.case_id).where(TeseCasoLink.tese_id == tese_id)
    )).scalars().all())

    q = select(Case).where(Case.deleted_at.is_(None))
    if not incluir_arquivados:
        q = q.where(Case.status != "arquivado")
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id,
        ))
    casos = (await db.execute(q.limit(MAX_CASOS_VARRIDOS))).scalars().all()

    varridos = [
        {
            "id": c.id, "titulo": c.titulo,
            "descricao_fatos": c.descricao_fatos,
            "numero_interno": c.numero_interno,
            "area": c.area.value if hasattr(c.area, "value") else c.area,
            "status": c.status.value if hasattr(c.status, "value") else c.status,
        }
        for c in casos if c.id not in ja_vinculados
    ]

    candidatos = ranquear_candidatos(
        termos, varridos, area_tese=tese.area_juridica, piso=piso, limite=limite,
    )
    return {
        "tese_id": tese_id, "titulo": tese.titulo,
        "area_juridica": tese.area_juridica,
        "termos": termos,
        "casos_varridos": len(varridos),
        "teto_de_varredura_atingido": len(casos) >= MAX_CASOS_VARRIDOS,
        "total": len(candidatos),
        "candidatos": candidatos,
        "aviso": ("Sugestão determinística por casamento de termos — não é "
                  "análise de cabimento. Conferir o caso antes de vincular."),
    }


@router.post("/{tese_id}/vincular-caso")
async def vincular_caso(
    tese_id: str, req: LinkIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vincula tese a um caso e atualiza contadores de desempenho."""
    if not _pode_editar(cu):
        raise HTTPException(403)
    await verificar_acesso_caso(db, cu, req.case_id)  # gate ownership (sigilo EOAB/LGPD)
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404)

    # Write-path único (Classe A, plano-mestre, Issue #1272) — a mesma função
    # que aprovar_tese() usa para materializar o vínculo na aprovação da
    # matriz de teses (services/tese_vinculo_service.py).
    from app.services.tese_vinculo_service import vincular_tese_ao_caso
    link = await vincular_tese_ao_caso(
        db, tese_id=tese_id, case_id=req.case_id,
        resultado=req.resultado, observacao=req.observacao, created_by=cu.id,
    )
    t.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"id": link.id, "taxa_sucesso": t.taxa_sucesso}


@router.post("/sugerir-ia", dependencies=[Depends(rate_limit("teses-sugerir-ia", 15))])
async def sugerir_teses_ia(
    req: SugestaoIARequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    IA analisa os fatos e busca teses existentes no banco + sugere novas.
    Usa AI Gateway — preferência Ollama, fallback Groq.
    Todas as sugestões são RASCUNHO (HITL obrigatório).
    """
    if not _pode_editar(cu):
        raise HTTPException(403)

    from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
    from app.models.ai_log import AITipoUso
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
    from app.core.ownership import verificar_acesso_caso

    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
    escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    texto_limpo, pii = sanitizar_ou_abortar(req.descricao_fatos)

    # Busca teses existentes por área
    teses_existentes = (await db.execute(
        select(Tese).where(
            Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa,
            Tese.area_juridica.ilike(f"%{req.area}%"),
        ).order_by(Tese.taxa_sucesso.desc().nullslast()).limit(5)
    )).scalars().all()

    catalogo = ""
    if teses_existentes:
        linhas = [f"- [{t.titulo}] (sucesso: {t.taxa_sucesso or 'N/A'}) — {t.fundamentacao or t.descricao[:100]}"
                  for t in teses_existentes]
        catalogo = "[TESES DO ESCRITÓRIO DISPONÍVEIS]\n" + "\n".join(linhas) + "\n\n"

    # C4: escopo cliente E caso — intimação/precedente de outro processo do
    # mesmo cliente não entra como contexto desta sugestão.
    fontes = await buscar_contexto_rag(
        db, texto_limpo[:300], limite=5, scope_client_id=escopo_cli,
        scope_case_id=req.case_id,
    )
    rag_txt = ""
    if fontes:
        linhas = [f"- {f['titulo']}: {f['conteudo'][:200]}" for f in fontes]
        rag_txt = "[BASE DE CONHECIMENTO]\n" + "\n".join(linhas) + "\n\n"

    system = """Você é consultor jurídico estratégico. Identifique teses aplicáveis aos fatos apresentados.
Use APENAS as teses do escritório ou fundamentos da base de conhecimento. Não invente julgados ou artigos.

FORMATO OBRIGATÓRIO:
## Teses Recomendadas do Escritório (se aplicáveis)
- [nome] | por que se aplica
## Teses Novas Sugeridas
### [nome da tese] (RASCUNHO — verificar)
Fundamento: [artigo/súmula]
Aplicação: [como usar no caso]
Risco: [principal fragilidade]
⚠️ TODAS as sugestões são RASCUNHOS. Validação pelo advogado é obrigatória."""

    user_msg = f"Área: {req.area}\n\n{catalogo}{rag_txt}FATOS (sanitizados):\n{texto_limpo}"

    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
            task_type="analise_juridica",
            temperature=0.3,
            max_tokens=2000,
        )
        # Auditoria 2026-07-02: este endpoint gerava teses sem deixar NENHUM
        # rastro em ai_logs — quebra de HITL/LGPD. Agora grava sempre.
        log_id = await registrar_ai_log(
            db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=req.case_id,
            prompt_sanitizado=user_msg, pii_removida=pii, resposta=resp.texto,
            modelo=f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo,
            tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
        )
        # S8: vocabulário HITL canônico como último passo; chaves legadas mantidas.
        from app.services.ai.core import hitl_policy
        return hitl_policy.aplicar({
            "ai_log_id": log_id,
            "resposta": resp.texto,
            "modelo_usado": resp.modelo,
            "provedor": resp.provedor,
            "fallback": resp.fallback_ativado,
            "teses_existentes_encontradas": len(teses_existentes),
            "aviso": "⚠️ Sugestões de IA — RASCUNHO. Revisar antes de usar.",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha na chamada de IA (teses)")
        raise HTTPException(502, "IA indisponível no momento")


# ── P2.2 — Motor de Teses estruturado (viabilidade Alta/Média/Baixa) ──────────
from pydantic import BaseModel as _BM, Field as _F


class MotorTesesRequest(_BM):
    area: str
    descricao_fatos: str = _F(min_length=20, max_length=6000)
    case_id: str | None = None
    polo: str | None = "autor"   # autor | reu


def _parse_json_motor(txt: str):
    import json as _j
    import re as _re
    if not txt:
        return None
    try:
        return _j.loads(txt)
    except Exception:
        m = _re.search(r"\{.*\}", txt, _re.DOTALL)
        if m:
            try:
                return _j.loads(m.group(0))
            except Exception:
                return None
    return None


async def _gerar_teses(
    req: MotorTesesRequest,
    db: AsyncSession,
    cu: User,
) -> dict:
    # E04 (auditoria funcional): corpo da geração extraído para função pura de
    # serviço, compartilhada pela rota síncrona (/motor) e pela assíncrona
    # (/motor/async + status) — o frontend agora faz polling em vez de esperar
    # a resposta síncrona, evitando o timeout de 30s do navegador.
    # Motor de teses: recupera jurisprudência + súmulas + precedentes internos +
    # doutrina + teses vencedoras do escritório e gera teses ESTRUTURADAS com
    # viabilidade (alta/media/baixa) + fundamentação + contra-argumento.
    # REGRAS: não inventa julgado/artigo; nunca promete resultado; tudo é RASCUNHO.
    if not _pode_editar(cu):
        raise HTTPException(403)

    from app.services.ai_guard import sanitizar_ou_abortar
    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
    from app.core.ownership import verificar_acesso_caso

    # Bloco 5: se o motor é invocado no contexto de um caso, exige acesso a ele
    # (antes só checava papel) e escopa os PRECEDENTES INTERNOS ao cliente desse
    # caso — precedente de um cliente nunca aparece para outro. Sem case_id, o
    # escopo é None → fail-closed (nenhum precedente interno é recuperado).
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
    escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

    texto, pii = sanitizar_ou_abortar(req.descricao_fatos)
    consulta = f"{req.area} {texto}"[:400]

    # jurisp e doutrina são categorias PÚBLICAS — escopo não as afeta.
    jurisp = await buscar_contexto_rag(
        db, consulta, limite=6,
        categorias=["jurisprudencia", "sumula_stf", "sumula_stj", "sumula_tst"], modo_or=True)
    internos = await buscar_contexto_rag(
        db, consulta, limite=4, categorias=["precedente_interno"], modo_or=True,
        scope_client_id=escopo_cli,
        scope_case_id=req.case_id,  # C4: precedente interno restrito ao caso
    )
    doutrina = await buscar_contexto_rag(db, consulta, limite=3, categorias=["doutrina"], modo_or=True)

    teses_venc = (await db.execute(
        select(Tese).where(
            Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa,
            Tese.area_juridica.ilike(f"%{req.area}%"),
        ).order_by(Tese.taxa_sucesso.desc().nullslast()).limit(5)
    )).scalars().all()

    def _blk(nome, itens):
        if not itens:
            return ""
        return f"[{nome}]\n" + "\n".join(
            f"- {(i.get('titulo') or '')}: {(i.get('conteudo') or '')[:220]}" for i in itens) + "\n\n"

    ctx = _blk("JURISPRUDÊNCIA/SÚMULAS", jurisp) + _blk("PRECEDENTES INTERNOS", internos) + _blk("DOUTRINA", doutrina)
    if teses_venc:
        ctx += "[TESES VENCEDORAS DO ESCRITÓRIO]\n" + "\n".join(
            f"- {t.titulo} (sucesso {t.taxa_sucesso or 'N/A'}, {t.vezes_venceu or 0}V/{t.vezes_perdeu or 0}D): "
            f"{(t.fundamentacao or t.descricao or '')[:160]}" for t in teses_venc) + "\n\n"

    sinal = (f"Histórico interno: {len(teses_venc)} tese(s) da área com taxa registrada."
             if teses_venc else
             "Sem histórico interno nesta área (escritório novo) — avalie viabilidade pela força "
             "da jurisprudência/súmula encontrada no contexto.")

    system = (
        "Você é consultor jurídico estratégico. Gere teses APLICÁVEIS aos fatos, ANCORADAS no contexto "
        "(jurisprudência, súmulas, precedentes internos, doutrina). É PROIBIDO inventar julgado, súmula ou "
        "artigo que não esteja no contexto — se faltar base, marque viabilidade 'baixa' e escreva 'requer pesquisa'. "
        "NUNCA prometa resultado. Classifique a viabilidade: 'alta' = jurisprudência consolidada/súmula a favor; "
        "'media' = há base mas com divergência/condicionantes; 'baixa' = base fraca ou ausente. "
        "Toda saída é RASCUNHO — revisão obrigatória do advogado (OAB)."
    )
    user = (
        f"ÁREA: {req.area} | POLO: {req.polo}\n\nCONTEXTO RECUPERADO:\n{ctx or '(base escassa)'}\n"
        f"SINAL DE VIABILIDADE: {sinal}\n\nFATOS:\n{texto}\n\n"
        'Responda APENAS JSON: {"teses": [{"titulo": "...", "viabilidade": "alta|media|baixa", '
        '"justificativa_viabilidade": "...", "fundamentacao": "...", '
        '"base_legal": "<súmula/artigo presente no contexto, ou \'requer pesquisa\'>", '
        '"aplicacao": "como usar no caso", "contra_argumento": "principal fragilidade"}], '
        '"sintese": "1-2 frases"}'
    )
    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            task_type="analise_juridica", temperature=0.3, max_tokens=2600)
    except Exception:
        logger.exception("Falha na chamada de IA (motor de teses)")
        raise HTTPException(502, "IA indisponível no momento")

    # I9: o motor de teses gerava sem AILog (custo/trilha invisíveis).
    from app.models.ai_log import AITipoUso
    from app.services.ai_gateway import registrar_log_resposta
    # P3-2 (revisão de segurança 03/09/2026): `user` carrega os precedentes
    # internos e a fundamentação das teses, que não passaram por sanitização —
    # só o `texto` do usuário tinha passado. Sanitiza o prompt INTEIRO antes de
    # gravar, senão o registro afirma "sem PII" carregando nome de parte.
    from app.services.sanitizer import sanitizar_pii as _san_log
    _prompt_log, _pii_log = _san_log("[MOTOR_TESES]\n" + user)
    await registrar_log_resposta(
        db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, resp=resp,
        prompt_sanitizado=_prompt_log, pii_removida=(pii or _pii_log),
        case_id=req.case_id,
    )

    data = _parse_json_motor(resp.texto) or {"teses": [], "_bruto": resp.texto[:1500]}
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    if isinstance(data.get("teses"), list):
        data["teses"].sort(key=lambda t: ordem.get((t.get("viabilidade") or "baixa").lower(), 3))
    data["fontes_consultadas"] = {
        "jurisprudencia": len(jurisp), "precedentes_internos": len(internos),
        "doutrina": len(doutrina), "teses_escritorio": len(teses_venc),
    }
    data["modelo"] = f"{resp.provedor}/{resp.modelo}"
    data["_aviso"] = "Teses geradas por IA — RASCUNHO. Verifique cada julgado/artigo e revise antes de usar (OAB)."
    # S8: vocabulário HITL canônico como último passo ("_aviso" legado mantido).
    from app.services.ai.core import hitl_policy
    return hitl_policy.aplicar(data)


# ── E04 (auditoria funcional): geração assíncrona com polling ───────────
# Implementação robusta em P2.2b abaixo (com RBAC, verificação de ownership,
# lock de thread, TTL de 10 min e resposta estruturada). A rota síncrona é
# mantida por compatibilidade.
@router.post("/motor", dependencies=[Depends(rate_limit("teses-motor", 15))])
async def motor_teses(
    req: MotorTesesRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Rota síncrona do Motor de Teses (mantida por compatibilidade — clientes
    antigos e testes dependem dela). Preferir /motor/async para chamadas de UI.
    """
    return await _gerar_teses(req, db, cu)


# ── P2.2b — Geração assíncrona com polling (E04) ────────────────────────────
import secrets as _secrets
import threading as _threading

_motor_tasks: dict[str, dict] = {}
_motor_lock = _threading.Lock()
_MOTOR_TASK_TTL = 600  # 10 minutos — depois o status é descartado


class MotorTesesAsyncResponse(_BM):
    task_id: str
    status: str  # pendente | em_andamento | concluido | erro
    criado_em: str
    estimativa_segundos: int | None = 60


def _expurgar_tarefas_motor() -> None:
    # Descarta tarefas concluídas/erro/estouradas do TTL — evita vazamento de
    # memória em uso intenso (resultado já entregue ao frontend no polling).
    agora = __import__("time").time()
    with _motor_lock:
        expiradas = [tid for tid, t in _motor_tasks.items()
                     if t["status"] in ("concluido", "erro") or agora - t["criado_ts"] > _MOTOR_TASK_TTL]
        for tid in expiradas:
            del _motor_tasks[tid]


async def _executar_tese_task(task_id: str, req: MotorTesesRequest, db: AsyncSession, cu: User) -> None:
    try:
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id]["status"] = "em_andamento"
        data = await _gerar_teses(req, db, cu)
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id].update({"status": "concluido", "resultado": data})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha na geração assíncrona de teses (task %s)", task_id)
        with _motor_lock:
            if task_id in _motor_tasks:
                _motor_tasks[task_id]["status"] = "erro"


@router.post("/motor/async", response_model=MotorTesesAsyncResponse,
             dependencies=[Depends(rate_limit("teses-motor", 15))])
async def motor_teses_async(
    req: MotorTesesRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Geração assíncrona do Motor de Teses: cria uma tarefa e devolve um task_id
    imediatamente (202). O frontend consulta o status por polling em
    GET /motor/async/{task_id} até concluido/erro. O resultado fica em memória
    (com TTL de 10 minutos) — sem dependência de fila externa.
    REGRAS: não inventa julgado/artigo; nunca promete resultado; tudo é RASCUNHO.
    """
    if not _pode_editar(cu):
        raise HTTPException(403)
    # Validação de acesso ANTES de criar a tarefa (mesma regra da rota síncrona).
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso  # noqa: F401
        await verificar_acesso_caso(db, cu, req.case_id)

    task_id = _secrets.token_hex(12)
    criado_em = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    with _motor_lock:
        _motor_tasks[task_id] = {
            "status": "pendente", "criado_ts": __import__("time").time(),
            "criado_em": criado_em.isoformat(),
        }
        _expurgar_tarefas_motor()
    background.add_task(_executar_tese_task, task_id, req, db, cu)
    return MotorTesesAsyncResponse(
        task_id=task_id, status="pendente", criado_em=criado_em.isoformat())


@router.get("/motor/async/{task_id}")
async def motor_teses_async_status(
    task_id: str,
    cu: User = Depends(get_current_user),
):
    """
    Status do motor assíncrono de teses: {task_id, status, resultado?, criado_em}.
    status: pendente | em_andamento | concluido | erro (404 se task_id inexistente).
    """
    with _motor_lock:
        task = _motor_tasks.get(task_id)
    if task is None:
        raise HTTPException(404, "Tarefa não encontrada ou expirada (TTL 10 min)")
    out = {
        "task_id": task_id, "status": task["status"], "criado_em": task["criado_em"],
    }
    if task["status"] == "concluido":
        out["resultado"] = task["resultado"]
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# FICHA VIVA (Legal Drafting 2.0 §5) — histórico, lastro de fontes e recusa.
#
# Superfície da extensão de `teses` descrita em `models/tese.py`. Não é um
# módulo novo: são sub-recursos da ficha canônica, sob o MESMO RBAC do Banco de
# Teses (`_is_staff` para ler, `_pode_editar` para escrever).
# ═══════════════════════════════════════════════════════════════════════════════

class FonteIn(BaseModel):
    elemento:   str = Field(description=f"Um de {list(ELEMENTOS_FONTE)}")
    referencia: str = Field(min_length=2, max_length=300)
    # Obrigatório: uma referência sem o texto que ela diz não é verificável —
    # é exatamente o formato de uma citação alucinada.
    trecho:     str = Field(min_length=10)
    fonte_url:  Optional[str] = Field(default=None, max_length=500)
    knowledge_doc_id:    Optional[str] = Field(default=None, max_length=36)
    authority_record_id: Optional[str] = Field(default=None, max_length=36)
    status_verificacao:  str = Field(
        default="nao_verificada", description=f"Um de {list(STATUS_FONTE)}")


class OverrideIn(BaseModel):
    case_id: str = Field(max_length=36)
    motivo:  str = Field(description=f"Um de {list(MOTIVOS_OVERRIDE)}")
    justificativa: str = Field(
        min_length=ficha_viva.JUSTIFICATIVA_MIN, max_length=4000,
        description="Obrigatória: é ela que transforma a recusa em sinal de revisão.")


async def _ficha_ou_404(db: AsyncSession, tese_id: str) -> Tese:
    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Tese não encontrada")
    return t


@router.get("/{tese_id}/versoes")
async def historico_da_ficha(
    tese_id: str,
    limite: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Histórico IMUTÁVEL da ficha, da versão mais recente para a mais antiga.

    Cada item traz `mudou`: os campos que diferem da versão IMEDIATAMENTE
    anterior, com `de`/`para`. Sem isso o histórico obrigaria a comparar dois
    blocos de texto a olho, e ninguém o usaria."""
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    await _ficha_ou_404(db, tese_id)

    versoes = await ficha_viva.historico(db, tese_id, limite)
    saida = []
    for i, v in enumerate(versoes):
        # A lista vem DESC: a anterior é a próxima da lista. Na última página
        # a comparação fica indisponível em vez de errada — comparar com um
        # "vazio" faria a versão mais antiga da página parecer criação.
        anterior = versoes[i + 1] if i + 1 < len(versoes) else None
        saida.append({
            "id": v.id,
            "versao": v.versao,
            "conteudo": v.conteudo,
            "resumo_mudanca": v.resumo_mudanca,
            "criado_por": v.criado_por,
            "criado_em": v.criado_em.isoformat() if v.criado_em else None,
            "mudou": (ficha_viva.diferenca_entre_versoes(anterior.conteudo, v.conteudo)
                      if anterior else None),
        })
    return {"tese_id": tese_id, "versao_atual": (versoes[0].versao if versoes else None),
            "total": len(saida), "versoes": saida}


@router.get("/{tese_id}/fontes")
async def fontes_da_ficha(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lastro da ficha + cobertura. A cobertura existe para que uma ficha com
    12 fontes NÃO verificadas e outra com 2 verificadas não pareçam igualmente
    sólidas na tela."""
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    await _ficha_ou_404(db, tese_id)

    fontes = await ficha_viva.fontes_da_ficha(db, tese_id)
    return {
        "tese_id": tese_id,
        "cobertura": ficha_viva.cobertura_de_fontes(fontes),
        "fontes": [{
            "id": f.id, "elemento": f.elemento, "referencia": f.referencia,
            "trecho": f.trecho, "fonte_url": f.fonte_url,
            "knowledge_doc_id": f.knowledge_doc_id,
            "authority_record_id": f.authority_record_id,
            "status_verificacao": f.status_verificacao,
            "verificado_em": f.verificado_em.isoformat() if f.verificado_em else None,
            "criado_em": f.criado_em.isoformat() if f.criado_em else None,
        } for f in fontes],
    }


@router.post("/{tese_id}/fontes", status_code=201,
             dependencies=[Depends(rate_limit("teses-fonte", 30))])
async def adicionar_fonte_da_ficha(
    tese_id: str, req: FonteIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Liga um elemento da ficha a uma fonte REAL, com o texto dela.

    As invariantes de domínio (trecho obrigatório; `verificada` exige vínculo
    com a base curada, precedente registrado ou URL oficial) vivem no service e
    chegam aqui como 422 — a regra é uma só, não uma cópia no router."""
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    await _ficha_ou_404(db, tese_id)
    try:
        fonte = await ficha_viva.adicionar_fonte(
            db, tese_id=tese_id, user_id=cu.id, **req.model_dump())
    except ficha_viva.FichaVivaErro as e:
        raise HTTPException(422, str(e))
    await db.commit()
    return {"id": fonte.id, "elemento": fonte.elemento,
            "status_verificacao": fonte.status_verificacao}


@router.get("/{tese_id}/confianca")
async def confianca_da_ficha(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Confiança MEDIDA da ficha, com a amostra declarada junto.

    Não devolve `taxa_sucesso` crua como se fosse confiança: 1 vitória em 1 uso
    viraria "100%" — número verdadeiro, conclusão falsa, e um advogado decide a
    tese da peça por ele. Inclui o sinal determinístico de revisão vindo das
    recusas registradas."""
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    t = await _ficha_ou_404(db, tese_id)
    overrides = await ficha_viva.overrides_da_ficha(db, tese_id)
    return {"tese_id": tese_id, **ficha_viva.confianca(t, overrides)}


@router.get("/{tese_id}/overrides")
async def listar_recusas_da_ficha(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Casos em que a ficha foi AFASTADA, e por quê."""
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    await _ficha_ou_404(db, tese_id)
    overrides = await ficha_viva.overrides_da_ficha(db, tese_id)
    return {
        "tese_id": tese_id,
        "sinal": ficha_viva.sinal_de_revisao(overrides),
        "overrides": [{
            "id": o.id, "case_id": o.case_id, "versao_tese": o.versao_tese,
            "motivo": o.motivo, "justificativa": o.justificativa,
            "criado_por": o.criado_por,
            "criado_em": o.criado_em.isoformat() if o.criado_em else None,
        } for o in overrides],
    }


@router.post("/{tese_id}/overrides", status_code=201,
             dependencies=[Depends(rate_limit("teses-override", 30))])
async def registrar_recusa_da_ficha(
    tese_id: str, req: OverrideIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Registra que a ficha foi afastada NESTE caso, e por quê.

    Fecha o ciclo de aprendizado do catálogo: hoje quem discorda de uma ficha
    simplesmente não a usa, e ela segue parecendo boa porque só é medida quando
    é usada. Não toca em vitórias/derrotas — aquelas medem RESULTADO de
    aplicação; esta mede NÃO-aplicação, e misturar as duas faria uma ficha
    recusada dez vezes parecer uma ficha derrotada dez vezes.

    Ownership do CASO é exigido: o registro vincula a ficha a um caso concreto,
    e escrever em caso alheio seria IDOR."""
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    t = await _ficha_ou_404(db, tese_id)
    await verificar_acesso_caso(db, cu, req.case_id)
    try:
        override = await ficha_viva.registrar_override(
            db, tese=t, case_id=req.case_id, motivo=req.motivo,
            justificativa=req.justificativa, user_id=cu.id)
    except ficha_viva.FichaVivaErro as e:
        raise HTTPException(422, str(e))
    await db.commit()
    return {"id": override.id, "motivo": override.motivo,
            "versao_tese": override.versao_tese}
