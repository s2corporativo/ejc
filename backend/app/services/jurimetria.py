# ── app/services/jurimetria.py ───────────────────────────────────────────────
# Jurimetria (Bloco D) — métricas de desfecho sobre casos ENCERRADOS, agregadas
# por área, comarca ou advogado. Honestidade estatística: o tamanho da amostra
# (n) é SEMPRE exposto e grupos com n < MIN_AMOSTRA são sinalizados como
# estatisticamente insuficientes. Nenhuma taxa é "arredondada para impressionar":
# a distribuição bruta acompanha cada taxa, permitindo recálculo/auditoria.
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.case import Case, CaseStatus

# Resultados conhecidos (Case.resultado). Valores fora desta lista entram em "outro".
FAVORAVEIS = {"exito_total", "exito_parcial"}
CONSENSUAL = {"acordo"}
DESFAVORAVEIS = {"improcedente"}
CATEGORIAS = ["exito_total", "exito_parcial", "acordo", "improcedente", "outro"]

FECHADOS = [CaseStatus.encerrado, CaseStatus.arquivado]
MIN_AMOSTRA = 5   # abaixo disto, taxa é apenas indicativa


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


def _bucket(resultado: str | None) -> str:
    r = (resultado or "").strip().lower()
    return r if r in (FAVORAVEIS | CONSENSUAL | DESFAVORAVEIS) else "outro"


def _resumo(amostra: list[str]) -> dict:
    """Recebe lista de resultados (já em bucket) e devolve distribuição + taxas."""
    n = len(amostra)
    dist = {c: 0 for c in CATEGORIAS}
    for r in amostra:
        dist[r] += 1
    favor = dist["exito_total"] + dist["exito_parcial"]
    acordo = dist["acordo"]
    return {
        "n": n,
        "distribuicao": dist,
        # taxa de êxito SEM contar acordo, e taxa COM acordo — ambas explícitas
        "taxa_exito": round(favor / n * 100, 1) if n else None,
        "taxa_exito_com_acordo": round((favor + acordo) / n * 100, 1) if n else None,
        "taxa_improcedencia": round(dist["improcedente"] / n * 100, 1) if n else None,
        "amostra_suficiente": n >= MIN_AMOSTRA,
    }


async def jurimetria(db: AsyncSession, user: User, dimensao: str | None = None) -> dict:
    """Métricas de desfecho. dimensao ∈ {None, 'area', 'comarca', 'advogado'}.

    None → resumo global. Com dimensão → quebra por grupo, ordenada por n desc.
    Considera apenas casos encerrados/arquivados com `resultado` preenchido.
    """
    if dimensao not in (None, "area", "comarca", "advogado"):
        raise ValueError("dimensao deve ser: area, comarca, advogado ou vazio")

    q = select(
        Case.area, Case.comarca, Case.advogado_responsavel_id, Case.resultado
    ).where(
        Case.deleted_at.is_(None),
        Case.status.in_(FECHADOS),
        Case.resultado.isnot(None),
    )
    if not pode_ver_todos(user):
        q = q.where(
            (Case.advogado_responsavel_id == user.id) |
            (Case.advogado_auxiliar_id == user.id)
        )
    linhas = (await db.execute(q)).all()

    global_amostra = [_bucket(r.resultado) for r in linhas]
    resultado = {
        "escopo": "todos os casos" if pode_ver_todos(user) else "casos do usuário",
        "criterio": "casos encerrados/arquivados com resultado registrado",
        "definicoes": {
            "taxa_exito": "(êxito total + êxito parcial) / n",
            "taxa_exito_com_acordo": "(êxito total + êxito parcial + acordo) / n",
            "min_amostra": MIN_AMOSTRA,
        },
        "global": _resumo(global_amostra),
    }

    if dimensao:
        # resolve nomes de advogados quando necessário
        nomes: dict[str, str] = {}
        if dimensao == "advogado":
            ids = {r.advogado_responsavel_id for r in linhas if r.advogado_responsavel_id}
            if ids:
                for uid, nome in (await db.execute(
                    select(User.id, User.full_name).where(User.id.in_(ids))
                )).all():
                    nomes[uid] = nome

        grupos: dict[str, list[str]] = {}
        for r in linhas:
            if dimensao == "area":
                chave = r.area.value if r.area else "(sem área)"
            elif dimensao == "comarca":
                chave = (r.comarca or "(sem comarca)").strip()
            else:
                chave = nomes.get(r.advogado_responsavel_id, "(sem responsável)")
            grupos.setdefault(chave, []).append(_bucket(r.resultado))

        detalhado = [{"grupo": k, **_resumo(v)} for k, v in grupos.items()]
        detalhado.sort(key=lambda g: g["n"], reverse=True)
        resultado["dimensao"] = dimensao
        resultado["grupos"] = detalhado

    if resultado["global"]["n"] < MIN_AMOSTRA:
        resultado["aviso"] = (
            f"Amostra global de {resultado['global']['n']} caso(s) — abaixo de "
            f"{MIN_AMOSTRA}. Taxas são meramente indicativas, sem valor estatístico."
        )
    return resultado
