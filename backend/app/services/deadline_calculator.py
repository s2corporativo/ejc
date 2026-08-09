# ── app/services/deadline_calculator.py ──────────────────────────────────────
# Cálculo de prazos processuais e administrativos.
#
# Princípios:
#  • CPC: dias úteis (art. 219) + suspensão 20/12–20/01 (art. 220)
#  • CLT: dias úteis (art. 775) + suspensão 20/12–20/01 (art. 775-A)
#  • CPP: prazo contínuo (art. 798), com prorrogação do termo final quando
#    recair em dia não útil; suspensão 20/12–20/01 conforme art. 798-A, salvo
#    as exceções legais que DEVEM ser declaradas pelo operador.
#  • DJEN: disponibilização != publicação != termo inicial. A publicação é o
#    primeiro dia útil seguinte à disponibilização e o prazo começa no primeiro
#    dia útil seguinte à publicação (Lei 11.419/2006, art. 4º, §§ 3º e 4º).
#  • Administrativo: dias corridos, com prorrogação do termo final quando a lei
#    aplicável assim determinar (ex.: Lei 9.784/99, art. 66, §1º).
#
# O motor é deliberadamente fail-safe: regime desconhecido não é inferido como
# civil. Quem chama deve informar/derivar o regime por dado objetivo do caso.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

from app.services import calendario_tribunal as _cal

RegimeProcessual = Literal["civel", "trabalhista", "penal"]


# ── Feriados nacionais FIXOS (dia, mês) ───────────────────────────────────────
FERIADOS_FIXOS: set[tuple[int, int]] = _cal.feriados_fixos_nacionais()

# Compatibilidade histórica: alguns fluxos não processuais usavam o recesso
# forense reduzido 20/12–06/01 como feriado. Não ampliar este alias globalmente:
# prazos processuais usam `aplicar_recesso=True` de forma explícita.
RECESSO_FORENSE = [(d, 12) for d in range(20, 32)] + [
    (d, 1) for d in range(1, 7)
]


# ── Feriados municipais/estaduais carregados do BANCO ─────────────────────────
_FERIADOS_DB: set[date] = set()


def set_feriados_db(datas: set[date]) -> None:
    global _FERIADOS_DB
    _FERIADOS_DB = set(datas)


async def carregar_feriados_db() -> int:
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.feriado import Feriado

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Feriado.data))).scalars().all()
        set_feriados_db({d for d in rows if d})
        return len(_FERIADOS_DB)
    except Exception:
        # O carregamento do calendário nunca derruba a aplicação. A ausência
        # dele deve aparecer na Central de Diagnóstico e manter o cálculo
        # nacional, sem inventar feriado local.
        return 0


# ── Suspensões por TRIBUNAL ────────────────────────────────────────────────────
_SUSPENSOES_TRIB: dict[str, set[date]] = {}


def set_suspensoes_tribunal(mapping: dict[str, set[date]]) -> None:
    global _SUSPENSOES_TRIB
    _SUSPENSOES_TRIB = {k: set(v) for k, v in mapping.items()}


def _suspenso(d: date, tribunal: str | None) -> bool:
    return bool(tribunal) and d in _SUSPENSOES_TRIB.get(tribunal, frozenset())


def eh_suspensao_processual(
    d: date,
    tribunal: str | None = None,
    *,
    aplicar_recesso: bool = True,
) -> bool:
    """Somente suspensão do CURSO do prazo, não mero feriado.

    Esta distinção é essencial para o CPP: sábados, domingos e feriados podem
    integrar a contagem contínua; suspensões processuais efetivamente congelam
    o curso do prazo.
    """
    if aplicar_recesso and _cal.em_recesso_art220(d):
        return True
    if _suspenso(d, tribunal):
        return True
    if tribunal and d in _cal.datas_suspensoes_tribunal(tribunal):
        return True
    return False


async def carregar_suspensoes_db() -> int:
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.suspensao import SuspensaoTribunal

        out: dict[str, set[date]] = {}
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(SuspensaoTribunal).where(
                        SuspensaoTribunal.deleted_at.is_(None)
                    )
                )
            ).scalars().all()
        for suspensao in rows:
            dias = out.setdefault(suspensao.tribunal, set())
            atual = suspensao.data_inicio
            while atual <= suspensao.data_fim:
                dias.add(atual)
                atual += timedelta(days=1)
        set_suspensoes_tribunal(out)
        return sum(len(v) for v in _SUSPENSOES_TRIB.values())
    except Exception:
        return 0


@lru_cache(maxsize=32)
def calcular_pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=32)
def feriados_moveis(ano: int) -> set[date]:
    pascoa = calcular_pascoa(ano)
    return {
        pascoa - timedelta(days=48),
        pascoa - timedelta(days=47),
        pascoa - timedelta(days=2),
        pascoa + timedelta(days=60),
    }


def eh_feriado(d: date, incluir_recesso: bool = False) -> bool:
    if (d.day, d.month) in FERIADOS_FIXOS:
        return True
    if d in feriados_moveis(d.year):
        return True
    if d in _FERIADOS_DB:
        return True
    if incluir_recesso and (d.day, d.month) in RECESSO_FORENSE:
        return True
    return False


def eh_dia_util(
    d: date,
    forense: bool = True,
    tribunal: str | None = None,
    aplicar_recesso: bool = False,
) -> bool:
    if d.weekday() >= 5:
        return False
    if _suspenso(d, tribunal):
        return False
    if aplicar_recesso and _cal.em_recesso_art220(d):
        return False
    if tribunal and (
        d in _cal.datas_feriados_locais(tribunal)
        or d in _cal.datas_suspensoes_tribunal(tribunal)
    ):
        return False
    return not eh_feriado(d, incluir_recesso=forense)


def proximo_dia_util(
    d: date,
    forense: bool = True,
    tribunal: str | None = None,
    aplicar_recesso: bool = False,
) -> date:
    while not eh_dia_util(d, forense, tribunal, aplicar_recesso):
        d += timedelta(days=1)
    return d


def dia_util_anterior(
    d: date,
    forense: bool = True,
    tribunal: str | None = None,
    aplicar_recesso: bool = False,
) -> date:
    while not eh_dia_util(d, forense, tribunal, aplicar_recesso):
        d -= timedelta(days=1)
    return d


# ── Cálculo de prazos ─────────────────────────────────────────────────────────
def prazo_dias_uteis(
    data_inicio: date,
    dias: int,
    tribunal: str | None = None,
    em_dobro: bool = False,
    aplicar_recesso: bool = False,
) -> date:
    """Conta dias úteis excluindo a data de referência.

    `aplicar_recesso` permanece opt-in para não modificar SLAs internos e
    prazos administrativos que historicamente reutilizam esta função. Todo
    prazo PROCESSUAL cível/trabalhista deve chamá-la com True.
    """
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")
    if em_dobro:
        dias *= 2
    atual = data_inicio
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if eh_dia_util(
            atual,
            forense=True,
            tribunal=tribunal,
            aplicar_recesso=aplicar_recesso,
        ):
            contados += 1
    return atual


def prazo_dias_corridos(
    data_inicio: date,
    dias: int,
    prorrogar_fim: bool = True,
    tribunal: str | None = None,
) -> date:
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")
    vencimento = data_inicio + timedelta(days=dias)
    if prorrogar_fim:
        vencimento = proximo_dia_util(
            vencimento, forense=False, tribunal=tribunal
        )
    return vencimento


def regime_processual_por_area(area: str | None) -> RegimeProcessual | None:
    """Deriva regime somente quando a área fornece resposta objetiva.

    Eleitoral e demais ritos especiais NÃO são convertidos silenciosamente para
    CPC; nesses casos o chamador deve exigir conferência/data manual.
    """
    if not area:
        return None
    valor = getattr(area, "value", area)
    valor = str(valor).strip().lower()
    if valor == "criminal":
        return "penal"
    if valor == "trabalhista":
        return "trabalhista"
    if valor in {
        "civil",
        "consumidor",
        "familia",
        "previdenciario",
        "empresarial",
        "tributario",
        "administrativo",
        "bancario",
        "imobiliario",
        "sucessoes",
        "constitucional",
        "digital_lgpd",
        "transito",
        "saude",
        "medico",
        "agrario",
        "agronegocio",
        "internacional",
        "contratual",
        "societario",
        "licitacoes",
        "ambiental",
    }:
        return "civel"
    return None


def data_publicacao_djen(
    data_disponibilizacao: date,
    tribunal: str | None = None,
) -> date:
    """Lei 11.419/2006, art. 4º, §3º: publicação no primeiro dia útil seguinte."""
    return proximo_dia_util(
        data_disponibilizacao + timedelta(days=1),
        forense=False,
        tribunal=tribunal,
        aplicar_recesso=False,
    )


def termo_inicial_djen(
    data_publicacao: date,
    tribunal: str | None = None,
    *,
    aplicar_recesso: bool = True,
) -> date:
    """Lei 11.419/2006, art. 4º, §4º: início no primeiro útil após publicação."""
    return proximo_dia_util(
        data_publicacao + timedelta(days=1),
        forense=False,
        tribunal=tribunal,
        aplicar_recesso=aplicar_recesso,
    )


def prazo_processual_penal_djen(
    data_publicacao: date,
    dias: int,
    tribunal: str | None = None,
    *,
    excecao_recesso: bool = False,
) -> tuple[date, date]:
    """Prazo penal originado em publicação eletrônica.

    O PRIMEIRO dia contado é o primeiro dia útil após a publicação (Lei
    11.419/2006). A partir daí a contagem é contínua (CPP art. 798), mas o curso
    fica suspenso no recesso do art. 798-A, salvo exceção legal explicitamente
    informada. Feriados/fins de semana intermediários contam; apenas o termo
    final é prorrogado se não útil.
    """
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")

    aplicar_recesso = not excecao_recesso
    termo = termo_inicial_djen(
        data_publicacao,
        tribunal,
        aplicar_recesso=aplicar_recesso,
    )
    atual = termo
    contados = 1
    while contados < dias:
        atual += timedelta(days=1)
        if eh_suspensao_processual(
            atual,
            tribunal,
            aplicar_recesso=aplicar_recesso,
        ):
            continue
        contados += 1

    # CPP art. 798, §3º: termo final em domingo/feriado é prorrogado. Também
    # respeitamos suspensão específica cadastrada do tribunal.
    atual = proximo_dia_util(
        atual,
        forense=False,
        tribunal=tribunal,
        aplicar_recesso=aplicar_recesso,
    )
    return termo, atual


def calcular_prazo_djen(
    data_disponibilizacao: date,
    dias: int,
    regime: RegimeProcessual,
    tribunal: str | None = None,
    *,
    em_dobro: bool = False,
    excecao_recesso_penal: bool = False,
) -> dict:
    """Calcula e EXPLICA um prazo originado no DJEN.

    Retorna as três datas separadas para que UI, audit log e usuário consigam
    reconstruir o raciocínio: disponibilização → publicação → termo inicial →
    vencimento.
    """
    if regime not in ("civel", "trabalhista", "penal"):
        raise ValueError("regime processual não suportado para cálculo automático")

    publicacao = data_publicacao_djen(data_disponibilizacao, tribunal)

    if regime == "penal":
        if em_dobro:
            raise ValueError("prazo em dobro do CPC não se aplica ao regime penal")
        termo, vencimento = prazo_processual_penal_djen(
            publicacao,
            dias,
            tribunal,
            excecao_recesso=excecao_recesso_penal,
        )
        modo = "CPP art. 798 (contínuo) + art. 798-A (recesso), com termo inicial da Lei 11.419/2006"
    else:
        termo = termo_inicial_djen(publicacao, tribunal, aplicar_recesso=True)
        vencimento = prazo_dias_uteis(
            publicacao,
            dias,
            tribunal=tribunal,
            em_dobro=em_dobro,
            aplicar_recesso=True,
        )
        if regime == "trabalhista":
            modo = "CLT arts. 775 e 775-A + termo inicial da Lei 11.419/2006"
        else:
            modo = "CPC arts. 219 e 220 + termo inicial da Lei 11.419/2006"
        if em_dobro:
            modo += " · quantidade de dias dobrada (hipótese deve ser conferida)"

    return {
        "data_disponibilizacao": data_disponibilizacao,
        "data_publicacao": publicacao,
        "termo_inicial": termo,
        "data_vencimento": vencimento,
        "dias": dias,
        "regime": regime,
        "modo": modo,
        "excecao_recesso_penal": bool(excecao_recesso_penal),
    }


def prazo_defesa_ambiental(data_ciencia: date) -> dict:
    data_legal = prazo_dias_corridos(data_ciencia, 20, prorrogar_fim=True)
    interna = data_legal
    for _ in range(2):
        interna -= timedelta(days=1)
        interna = dia_util_anterior(interna, forense=False)
    hoje = date.today()
    return {
        "data_legal": data_legal,
        "data_interna": interna,
        "dias_restantes": max((data_legal - hoje).days, 0),
        "base_legal": "Decreto 6.514/2008, art. 113 c/c Lei 9.784/99, art. 66, §1º",
    }


def dias_uteis_restantes(
    vencimento: date,
    *,
    aplicar_recesso: bool = False,
    tribunal: str | None = None,
) -> int:
    hoje = date.today()
    if vencimento <= hoje:
        return 0
    atual, contados = hoje, 0
    while atual < vencimento:
        atual += timedelta(days=1)
        if eh_dia_util(
            atual,
            tribunal=tribunal,
            aplicar_recesso=aplicar_recesso,
        ):
            contados += 1
    return contados


# ── Tabela de prescrição por tipo de ação ─────────────────────────────────────
PRESCRICAO_TABELA: dict[str, dict] = {
    "reparacao_civil": {"anos": 3, "base": "CC art. 206, §3º, V"},
    "cobranca_divida": {"anos": 5, "base": "CC art. 206, §5º, I"},
    "anulacao_negocio": {"anos": 4, "base": "CC art. 178"},
    "pretensao_geral": {"anos": 10, "base": "CC art. 205"},
    "responsabilidade_medica": {
        "anos": 3,
        "base": "CC art. 206, §3º, V c/c STJ Súm. 278",
    },
    "negativacao_indevida": {"anos": 5, "base": "CDC art. 43, §5º"},
    "acao_trabalhista": {
        "anos": 2,
        "base": "CF art. 7º, XXIX (bienal — pós-extinção)",
    },
    "creditos_trabalhistas": {
        "anos": 5,
        "base": "CF art. 7º, XXIX (quinquenal — na vigência)",
    },
    "vicio_consumidor": {"anos": 5, "base": "CDC art. 27"},
    "prescricao_penal_2anos": {
        "anos": 2,
        "base": "CP art. 109, VI (pena máx ≤ 1 ano / multa)",
    },
    "prescricao_penal_4anos": {
        "anos": 4,
        "base": "CP art. 109, V (pena máx 1-2 anos)",
    },
    "prescricao_penal_8anos": {
        "anos": 8,
        "base": "CP art. 109, IV (pena máx 2-4 anos)",
    },
    "prescricao_penal_12anos": {
        "anos": 12,
        "base": "CP art. 109, III (pena máx 4-8 anos)",
    },
    "prescricao_penal_16anos": {
        "anos": 16,
        "base": "CP art. 109, II (pena máx 8-12 anos)",
    },
    "acao_rescisoria": {
        "anos": 2,
        "base": "CPC art. 975 (do trânsito em julgado)",
    },
    "execucao_fiscal": {"anos": 5, "base": "CTN art. 174"},
    "multa_ambiental_adm": {"anos": 5, "base": "Lei 9.873/99 art. 1º"},
}


def calcular_prescricao(tipo_acao: str, data_fato: date) -> dict | None:
    regra = PRESCRICAO_TABELA.get(tipo_acao)
    if not regra:
        return None
    from app.utils.datas import data_segura

    limite = data_segura(
        data_fato.year + regra["anos"], data_fato.month, data_fato.day
    )
    return {
        "data_limite": limite,
        "base_legal": regra["base"],
        "dias_restantes": max((limite - date.today()).days, 0),
        "aviso_causas": (
            "⚠️ Verifique causas suspensivas (CC arts. 197-201) e interruptivas "
            "(CC art. 202) — podem alterar esta data. Cálculo assume prazo contínuo."
        ),
    }
