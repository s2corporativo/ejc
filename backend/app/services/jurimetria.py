# ── app/services/jurimetria.py ───────────────────────────────────────────────
# Jurimetria (Bloco D) — métricas de desfecho sobre casos ENCERRADOS, agregadas
# por área, comarca ou advogado. Honestidade estatística: o tamanho da amostra
# (n) é SEMPRE exposto e grupos com n < MIN_AMOSTRA são sinalizados como
# estatisticamente insuficientes. Nenhuma taxa é "arredondada para impressionar":
# a distribuição bruta acompanha cada taxa, permitindo recálculo/auditoria.
from __future__ import annotations

from math import sqrt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.case import Case, CaseStatus

# Vocabulário canônico de Case.resultado. O write-path atual grava
# exito|exito_parcial|acordo|derrota|desistencia|arquivado; aliases antigos
# (exito_total/improcedente) continuam reconhecidos sem reescrever o histórico.
RESULTADOS_FAVORAVEIS = frozenset({"exito", "exito_total", "exito_parcial"})
RESULTADOS_DESFAVORAVEIS = frozenset({"derrota", "improcedente"})
RESULTADOS_ACORDO = frozenset({"acordo"})
RESULTADOS_NAO_DECIDIDOS = frozenset({"desistencia", "arquivado"})
_ALIAS_BUCKET = {
    "exito": "exito_total",
    "exito_total": "exito_total",
    "exito_parcial": "exito_parcial",
    "acordo": "acordo",
    "derrota": "improcedente",
    "improcedente": "improcedente",
    "desistencia": "outro",
    "arquivado": "outro",
}
FAVORAVEIS = {"exito_total", "exito_parcial"}
CONSENSUAL = {"acordo"}
DESFAVORAVEIS = {"improcedente"}
CATEGORIAS = ["exito_total", "exito_parcial", "acordo", "improcedente", "outro"]

FECHADOS = [CaseStatus.encerrado, CaseStatus.arquivado]
MIN_AMOSTRA = 5   # piso operacional; IC95% continua visível quando houver decisão


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


def normalizar_resultado(resultado: str | None) -> str:
    """Normaliza Case.resultado preservando aliases históricos."""
    return _ALIAS_BUCKET.get((resultado or "").strip().lower(), "outro")


def classificar_resultado(resultado: str | None) -> str:
    """Classificação semântica única usada por jurimetria e consumidores."""
    r = (resultado or "").strip().lower()
    if r in RESULTADOS_FAVORAVEIS:
        return "favoravel"
    if r in RESULTADOS_DESFAVORAVEIS:
        return "desfavoravel"
    if r in RESULTADOS_ACORDO:
        return "acordo"
    if r in RESULTADOS_NAO_DECIDIDOS:
        return "nao_decidido"
    return "outro"


def intervalo_wilson(sucessos: int, total: int, z: float = 1.959963984540054) -> dict | None:
    """Intervalo de confiança de Wilson para uma proporção."""
    if total <= 0:
        return None
    p = sucessos / total
    z2 = z * z
    den = 1 + z2 / total
    centro = (p + z2 / (2 * total)) / den
    margem = z * sqrt((p * (1 - p) + z2 / (4 * total)) / total) / den
    return {
        "inferior": round(max(0.0, centro - margem) * 100, 1),
        "superior": round(min(1.0, centro + margem) * 100, 1),
        "nivel": 0.95,
        "metodo": "wilson",
    }


def _bucket(resultado: str | None) -> str:
    return normalizar_resultado(resultado)


def _resumo(amostra: list[str]) -> dict:
    """Distribuição e taxas judiciais sobre decisões classificáveis."""
    n = len(amostra)
    dist = {c: 0 for c in CATEGORIAS}
    for r in amostra:
        dist[r] += 1
    favor = dist["exito_total"] + dist["exito_parcial"]
    desfavor = dist["improcedente"]
    acordo = dist["acordo"]
    decididos = favor + desfavor
    base_com_acordo = decididos + acordo
    return {
        "n": n,
        "n_decididos": decididos,
        "n_nao_decididos": n - decididos - acordo,
        "distribuicao": dist,
        "taxa_exito": round(favor / decididos * 100, 1) if decididos else None,
        "taxa_exito_com_acordo": (
            round((favor + acordo) / base_com_acordo * 100, 1)
            if base_com_acordo else None
        ),
        "taxa_improcedencia": round(desfavor / decididos * 100, 1) if decididos else None,
        "intervalo_confianca_95": intervalo_wilson(favor, decididos),
        "amostra_suficiente": decididos >= MIN_AMOSTRA,
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
            "taxa_exito": "(êxito total + êxito parcial) / decisões classificáveis",
            "taxa_exito_com_acordo": "(êxito + acordo) / (decisões classificáveis + acordo) — legado",
            "intervalo_confianca": "Wilson 95% sobre decisões classificáveis",
            "min_amostra": MIN_AMOSTRA,
            "min_amostra_decidida": MIN_AMOSTRA,
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

    if resultado["global"]["n_decididos"] < MIN_AMOSTRA:
        resultado["aviso"] = (
            f"Amostra decidida global de {resultado['global']['n_decididos']} caso(s) — "
            f"abaixo de {MIN_AMOSTRA}. A taxa judicial não deve orientar decisão isoladamente."
        )
    return resultado
