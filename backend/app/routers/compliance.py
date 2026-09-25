"""
compliance.py — Compliance/LGPD (#88 Termo de consentimento de uso de IA).
Gera o termo (template, SEM IA) preenchido com cliente/caso, para assinatura e
arquivamento. Não substitui orientação jurídica — é documento operacional.
"""
from __future__ import annotations
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.models.user import User
from app.models.case import Case, CaseFase, CaseStatus
from app.models.client import Client
from app.models.diario_oficial import DiarioOficialAlerta
from app.models.environmental import EnvironmentalCase, StatusDefesa

log = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Compliance / LGPD"])

# ── Radar de compliance — vocabulário de risco (mesmo de indice_risco._nivel) ──
_ORDEM_RISCO = {"critico": 0, "alto": 1, "medio": 2, "baixo": 3}


def _subir(nivel: str) -> str:
    """Eleva um degrau de risco (baixo→medio→alto→critico)."""
    escala = ["baixo", "medio", "alto", "critico"]
    i = escala.index(nivel) if nivel in escala else 1
    return escala[min(i + 1, len(escala) - 1)]


def _nivel_diario(a: DiarioOficialAlerta) -> str:
    """Diário Oficial não tem nível nativo → deriva por keyword/título + status
    de leitura. Termos críticos (constrição patrimonial) > termos de prazo/sanção
    > demais; publicação NÃO lida eleva um degrau (exige atenção da equipe)."""
    txt = f"{a.keyword_match or ''} {a.titulo or ''}".lower()
    CRIT = ("penhora", "leilão", "leilao", "bloqueio", "sequestro", "prazo fatal", "arrematação")
    ALTO = ("intimação", "intimacao", "citação", "citacao", "prazo", "multa",
            "sanção", "sancao", "embargo", "condenação", "condenacao", "liminar")
    if any(t in txt for t in CRIT):
        base = "critico"
    elif any(t in txt for t in ALTO):
        base = "alto"
    else:
        base = "medio"
    if not a.lido:
        base = _subir(base)
    return base


def _nivel_regulatorio(qtd: int) -> str:
    """Tópico regulatório em alta: risco derivado do VOLUME de publicações no
    período (mais publicações recorrentes = maior pressão regulatória)."""
    if qtd >= 10:
        return "critico"
    if qtd >= 5:
        return "alto"
    if qtd >= 2:
        return "medio"
    return "baixo"


def _nivel_ambiental(env: EnvironmentalCase, hoje: date) -> str:
    """Ambiental deriva risco de status_defesa + proximidade do prazo de defesa.
    Prazo correndo e vencendo = crítico; ciência ainda não registrada = alto
    (risco de perder o marco); casos encerrados/protocolados = baixo."""
    st = env.status_defesa
    if st in (StatusDefesa.protocolada, StatusDefesa.julgada, StatusDefesa.encerrado):
        return "baixo"
    if st == StatusDefesa.aguardando_ciencia:
        return "alto"
    if st in (StatusDefesa.prazo_correndo, StatusDefesa.elaborando):
        if env.data_prazo_defesa:
            dias = (env.data_prazo_defesa - hoje).days
            if dias <= 5:
                return "critico"
            if dias <= 15:
                return "alto"
        return "alto"
    return "medio"


def _pode_ver_radar(u: User) -> bool:
    """Mesma visibilidade dos endpoints de Diário Oficial (advogado+)."""
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]


def _acessa_caso(cu: User, case: Optional[Case]) -> bool:
    """Regra de ownership espelhada de core.ownership.verificar_acesso_caso,
    porém sem lançar (para FILTRAR o feed). Gestão vê tudo; equipe vê os próprios;
    caso órfão (sem responsável nem auxiliar) liberado (legado/triagem)."""
    if is_gestao(cu):
        return True
    if case is None:
        return True  # item sem caso vinculado não é per-caso → não filtra
    if cu.id in (case.advogado_responsavel_id, case.advogado_auxiliar_id):
        return True
    if case.advogado_responsavel_id is None and case.advogado_auxiliar_id is None:
        return True
    return False

_TERMO = """TERMO DE CONSENTIMENTO PARA USO DE INTELIGÊNCIA ARTIFICIAL

Escritório: De Paula Teixeira Advogados Associados (Betim/MG).
Cliente: {cliente}
Caso (ref. interna): {numero} — {titulo}
Data: {data}

Pelo presente, o(a) Cliente declara estar ciente e CONSENTIR que o escritório
utilize ferramentas de Inteligência Artificial como APOIO ao trabalho jurídico
(triagem, organização de informações, pesquisa e elaboração de minutas), nos
seguintes termos:

1. Todo conteúdo produzido por IA é RASCUNHO e passa por revisão obrigatória do
   advogado responsável (Provimento OAB) antes de qualquer uso.
2. Dados pessoais são tratados conforme a LGPD (Lei 13.709/2018); antes de
   qualquer processamento externo, informações identificáveis são anonimizadas.
3. A IA NÃO substitui o julgamento profissional do advogado nem garante resultado.
4. O Cliente pode, a qualquer tempo, revogar este consentimento por escrito.

_________________________________      _________________________________
Cliente                                 Advogado(a) responsável (OAB)
"""


@router.get("/cases/{case_id}/termo-consentimento-ia")
async def termo_consentimento_ia(case_id: str, db: AsyncSession = Depends(get_db),
                                 cu: User = Depends(get_current_user)):
    # Gate de ownership: sem isso o termo vaza o NOME do cliente de qualquer caso.
    case = await verificar_acesso_caso(db, cu, case_id)
    client = (await db.execute(
        select(Client).where(Client.id == case.client_id))).scalar_one_or_none()
    nome = "[NOME DO CLIENTE]"
    if client:
        nome = client.nome or client.razao_social or nome
    texto = _TERMO.format(
        cliente=nome,
        numero=case.numero_interno or "—",
        titulo=case.titulo or "—",
        data=date.today().strftime("%d/%m/%Y"),
    )
    return {
        "case_id": case_id,
        "cliente": nome,
        "termo": texto,
        "instrucao": "Imprimir, colher assinaturas (cliente + advogado) e arquivar no caso (Documentos).",
    }


# ── Radar de compliance consolidado priorizado por risco ──────────────────────
# Feed único que agrega Diário Oficial + regulatório + ambiental, ordenado por
# risco (crítico→baixo) e recência. Cada fonte é isolada em try/except: se uma
# falhar/estiver vazia, o radar retorna as demais (fail-safe, não quebra tudo).

async def _itens_diario(db: AsyncSession, cu: User, desde: Optional[date], limit: int) -> list[dict]:
    """Fonte 'diario_oficial' — item-level (DiarioOficialAlerta).

    #10(b): aplica ownership como _itens_ambiental (antes retornava TODOS os
    alertas sem filtro). Gestão vê tudo; equipe vê os itens office-wide (sem
    caso) OU dos casos em que é responsável/auxiliar — via _acessa_caso. Faz JOIN
    com Case e busca margem extra (limit*3), pois parte é filtrada por ownership."""
    q = (
        select(DiarioOficialAlerta, Case)
        .join(Case, Case.id == DiarioOficialAlerta.case_id, isouter=True)
    )
    if desde:
        q = q.where(DiarioOficialAlerta.data_publicacao >= desde)
    q = q.order_by(DiarioOficialAlerta.data_publicacao.desc()).limit(limit * 3)
    rows = (await db.execute(q)).all()
    itens = []
    for a, case in rows:
        if not _acessa_caso(cu, case):
            continue
        if len(itens) >= limit:
            break
        itens.append({
            "fonte": "diario_oficial",
            "id": a.id,
            "titulo": a.titulo or (a.keyword_match or "Publicação em Diário Oficial"),
            "resumo": a.resumo,
            "data": a.data_publicacao.isoformat() if a.data_publicacao else None,
            "nivel_risco": _nivel_diario(a),
            "link": a.link,
            "case_id": a.case_id,
            "_dt": a.data_publicacao or date.min,
        })
    return itens


async def _itens_regulatorio(db: AsyncSession, desde: Optional[date], hoje: date) -> list[dict]:
    """Fonte 'regulatorio' — reusa o serviço regulatorio.digest_semanal (que
    agrega diario_oficial_alertas por keyword). Cada 'top keyword' vira um item
    de radar (tópico regulatório em alta), sem duplicar as linhas do diário."""
    from app.routers.regulatorio import digest_semanal
    dias = 7
    if desde:
        dias = max(1, min(30, (hoje - desde).days))
    digest = await digest_semanal(dias=dias, db=db)
    itens = []
    for tk in digest.get("top_keywords", []):
        kw, qtd = tk.get("keyword"), int(tk.get("qtd", 0))
        if not kw:
            continue
        itens.append({
            "fonte": "regulatorio",
            "id": f"regulatorio:{kw}",
            "titulo": f"Tópico regulatório em alta: {kw}",
            "resumo": f"{qtd} publicação(ões) em Diário Oficial nos últimos {dias} dias "
                      f"casaram com a palavra-chave monitorada '{kw}'.",
            "data": digest.get("desde"),
            "nivel_risco": _nivel_regulatorio(qtd),
            "link": None,
            "case_id": None,
            "_dt": hoje,  # sinal agregado do período → recência = hoje
        })
    return itens


async def _itens_processual(
    db: AsyncSession,
    cu: User,
    desde: Optional[date],
    limit: int,
) -> list[dict]:
    """Casos com CNJ preenchido e estado operacional incompatível.

    É um alerta determinístico de saneamento. Não consulta nem grava processo,
    não infere andamento e respeita o mesmo ownership das demais fontes.
    """
    q = (
        select(Case)
        .where(
            Case.deleted_at.is_(None),
            Case.numero_processo.is_not(None),
            Case.numero_processo != "",
            or_(
                Case.has_judicial_process.is_(False),
                Case.case_type.is_(None),
                Case.case_type != "judicial",
                Case.status == CaseStatus.aberto,
                Case.fase == CaseFase.pre_processual,
            ),
        )
        .order_by(Case.updated_at.desc())
        .limit(limit * 3)
    )
    casos = (await db.execute(q)).scalars().all()
    itens: list[dict] = []
    from app.services.validators_service import normalizar_cnj, validar_cnj

    for caso in casos:
        numero = (caso.numero_processo or "").strip()
        if len(normalizar_cnj(numero)) != 20 or not validar_cnj(numero):
            continue
        if not _acessa_caso(cu, caso):
            continue
        dt = caso.updated_at.date() if caso.updated_at else None
        if desde and dt and dt < desde:
            continue
        inconsistencias: list[str] = []
        if not caso.has_judicial_process:
            inconsistencias.append("marcado como sem processo judicial")
        if caso.case_type != "judicial":
            inconsistencias.append(f"tipo atual: {caso.case_type or 'não informado'}")
        if caso.status == CaseStatus.aberto:
            inconsistencias.append("status ainda aberto")
        if caso.fase == CaseFase.pre_processual:
            inconsistencias.append("fase ainda pré-processual")
        itens.append(
            {
                "fonte": "processual",
                "id": caso.id,
                "titulo": (
                    f"Inconsistência processual: "
                    f"{caso.numero_interno or caso.titulo or caso.numero_processo}"
                ),
                "resumo": (
                    f"CNJ {caso.numero_processo} já está registrado, porém "
                    + "; ".join(inconsistencias)
                    + ". Revise a reconciliação do caso."
                ),
                "data": dt.isoformat() if dt else None,
                "nivel_risco": (
                    "alto"
                    if (
                        not caso.has_judicial_process
                        or caso.case_type != "judicial"
                        or caso.fase == CaseFase.pre_processual
                    )
                    else "medio"
                ),
                "link": None,
                "case_id": caso.id,
                "_dt": dt or date.min,
            }
        )
        if len(itens) >= limit:
            break
    return itens


async def _itens_ambiental(db: AsyncSession, cu: User, desde: Optional[date],
                           hoje: date, limit: int) -> list[dict]:
    """Fonte 'ambiental' — reusa o mesmo select de environmental.listar
    (EnvironmentalCase). Fonte por-caso: aplica ownership (filtra casos fora
    do escopo do usuário)."""
    q = (
        select(EnvironmentalCase, Case)
        .join(Case, Case.id == EnvironmentalCase.case_id, isouter=True)
        .where(EnvironmentalCase.deleted_at.is_(None))
        .order_by(EnvironmentalCase.data_prazo_defesa.asc().nullslast())
        .limit(limit * 3)  # margem: parte pode ser filtrada por ownership/desde
    )
    rows = (await db.execute(q)).all()
    itens = []
    for env, case in rows:
        if not _acessa_caso(cu, case):
            continue
        dt = env.data_prazo_defesa or env.data_ciencia
        if desde and dt and dt < desde:
            continue
        multa = f" | Multa: R$ {env.valor_multa}" if env.valor_multa is not None else ""
        prazo = (f" | Prazo defesa: {env.data_prazo_defesa.strftime('%d/%m/%Y')}"
                 if env.data_prazo_defesa else "")
        itens.append({
            "fonte": "ambiental",
            "id": env.id,
            "titulo": f"Auto de infração {env.numero_auto} ({env.orgao_autuador.value})",
            "resumo": (env.especie_infracao or "Auto de infração ambiental")
                      + f" | Status: {env.status_defesa.value}{prazo}{multa}",
            "data": dt.isoformat() if dt else None,
            "nivel_risco": _nivel_ambiental(env, hoje),
            "link": None,
            "case_id": env.case_id,
            "_dt": dt or date.min,
        })
    return itens


@router.get("/radar", dependencies=[Depends(rate_limit("compliance-radar", 15))])
async def radar_compliance(
    fonte: Optional[str] = Query(
        None, description="diario_oficial|regulatorio|ambiental|processual"
    ),
    desde: Optional[date] = Query(None, description="Só itens a partir desta data (YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Radar de compliance consolidado priorizado por risco.

    Agrega Diário Oficial + regulatório + ambiental + saneamento processual num
    feed unificado, ordenado
    por risco (crítico→baixo) e recência. Fail-safe: se uma fonte falhar, as
    demais ainda são retornadas.
    """
    if not _pode_ver_radar(cu):
        raise HTTPException(403, "Sem permissão para o radar de compliance")

    hoje = date.today()
    itens: list[dict] = []
    erros: list[str] = []
    # margem por-fonte antes do corte final por risco
    fetch = min(200, limit * 2)

    if fonte in (None, "diario_oficial"):
        try:
            itens += await _itens_diario(db, cu, desde, fetch)
        except Exception as e:  # noqa: BLE001 — fail-safe por fonte
            log.warning("radar: fonte diario_oficial falhou: %s", e)
            erros.append("diario_oficial")

    if fonte in (None, "regulatorio"):
        try:
            itens += await _itens_regulatorio(db, desde, hoje)
        except Exception as e:  # noqa: BLE001
            log.warning("radar: fonte regulatorio falhou: %s", e)
            erros.append("regulatorio")

    if fonte in (None, "ambiental"):
        try:
            itens += await _itens_ambiental(db, cu, desde, hoje, fetch)
        except Exception as e:  # noqa: BLE001
            log.warning("radar: fonte ambiental falhou: %s", e)
            erros.append("ambiental")

    if fonte in (None, "processual"):
        try:
            itens += await _itens_processual(db, cu, desde, fetch)
        except Exception as e:  # noqa: BLE001
            log.warning("radar: fonte processual falhou: %s", e)
            erros.append("processual")

    # Ordena por risco (crítico→baixo) e depois recência (mais novo primeiro).
    itens.sort(key=lambda it: (
        _ORDEM_RISCO.get(it["nivel_risco"], 9),
        -(it["_dt"].toordinal() if isinstance(it.get("_dt"), date) else 0),
    ))
    itens = itens[:limit]
    for it in itens:
        it.pop("_dt", None)

    return {
        "total": len(itens),
        "fontes_com_erro": erros,
        "filtros": {"fonte": fonte, "desde": desde.isoformat() if desde else None, "limit": limit},
        "itens": itens,
    }
