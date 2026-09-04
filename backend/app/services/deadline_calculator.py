# ── app/services/deadline_calculator.py ──────────────────────────────────────
# Cálculo de prazos processuais e administrativos.
#
# Regras centrais:
#  • CPC: dias úteis (art. 219) + suspensão 20/12–20/01 (art. 220)
#  • CLT: dias úteis (art. 775) + suspensão 20/12–20/01 (art. 775-A)
#  • CPP: contagem contínua (art. 798), com prorrogação do termo final quando
#    não útil; suspensão 20/12–20/01 pelo art. 798-A, salvo exceções legais
#    explicitamente indicadas pelo operador.
#  • Administrativo federal: dias corridos quando aplicável, com prorrogação do
#    termo final (Lei 9.784/99, art. 66, §1º).
#
# Regime penal nunca herda automaticamente o algoritmo civil em dias úteis.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

from app.services import calendario_tribunal as _cal

RegimeProcessual = Literal["civel", "trabalhista", "penal"]


# ── Saúde do calendário carregado em runtime ──────────────────────────────────
# None = ainda não carregado neste processo; True = carga concluída; False =
# carga falhou. Em produção o lifespan carrega ambos. O estado é consultável
# pela calculadora para que falha de fonte local não vire prazo definitivo sem
# aviso/revisão.
_CALENDARIO_RUNTIME: dict[str, bool | str | None] = {
    "feriados_ok": None,
    "suspensoes_ok": None,
    "feriados_erro_tipo": None,
    "suspensoes_erro_tipo": None,
}


def marcar_calendario_falho(alvo: str, erro_tipo: str) -> None:
    """Marca `feriados`/`suspensoes` como FALHO (carga não concluída).

    Existe porque a falha nem sempre chega como exceção ao loader: o teto de
    tempo do boot (`asyncio.timeout` em main.py) CANCELA a corrotina, e
    `CancelledError` herda de BaseException — sem marcação explícita o estado
    ficaria `None` ("nao_inicializado") e o cálculo sairia sem o aviso de
    degradação. Idempotente e nunca levanta.
    """
    if alvo not in ("feriados", "suspensoes"):
        return
    _CALENDARIO_RUNTIME[f"{alvo}_ok"] = False
    _CALENDARIO_RUNTIME[f"{alvo}_erro_tipo"] = erro_tipo


def calendario_runtime_status() -> dict[str, bool | str | None]:
    status = dict(_CALENDARIO_RUNTIME)
    if status["feriados_ok"] is False or status["suspensoes_ok"] is False:
        status["status"] = "degradado"
    elif status["feriados_ok"] is True and status["suspensoes_ok"] is True:
        status["status"] = "validado"
    else:
        status["status"] = "nao_inicializado"
    return status


# ── Feriados nacionais FIXOS (dia, mês) ───────────────────────────────────────
FERIADOS_FIXOS: set[tuple[int, int]] = _cal.feriados_fixos_nacionais()

# Recesso forense parcial legado 20/12–06/01. A suspensão PROCESSUAL integral
# 20/12–20/01 é aplicada separadamente por `aplicar_recesso=True`.
RECESSO_FORENSE = [(d, 12) for d in range(20, 32)] + [(d, 1) for d in range(1, 7)]


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
        _CALENDARIO_RUNTIME["feriados_ok"] = True
        _CALENDARIO_RUNTIME["feriados_erro_tipo"] = None
        return len(_FERIADOS_DB)
    except asyncio.CancelledError as exc:
        # Teto de tempo do boot: `asyncio.timeout` injeta CancelledError AQUI
        # (BaseException — o `except Exception` abaixo não pega). Sem esta
        # marcação a carga ficaria "nao_inicializado" e o prazo sairia sem
        # feriados locais e SEM aviso de degradação. Marca e re-levanta: o
        # cancelamento tem de seguir sua propagação.
        marcar_calendario_falho("feriados", type(exc).__name__)
        raise
    except Exception as exc:
        marcar_calendario_falho("feriados", type(exc).__name__)
        return 0


# ── Suspensões de prazo por TRIBUNAL ──────────────────────────────────────────
_SUSPENSOES_TRIB: dict[str, set[date]] = {}


def set_suspensoes_tribunal(mapping: dict[str, set[date]]) -> None:
    global _SUSPENSOES_TRIB
    _SUSPENSOES_TRIB = {k: set(v) for k, v in mapping.items()}


def _suspenso(d: date, tribunal: str | None) -> bool:
    return bool(tribunal) and d in _SUSPENSOES_TRIB.get(tribunal, frozenset())


async def carregar_suspensoes_db() -> int:
    try:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.suspensao import SuspensaoTribunal

        out: dict[str, set[date]] = {}
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SuspensaoTribunal).where(SuspensaoTribunal.deleted_at.is_(None))
            )).scalars().all()
        for s in rows:
            dias = out.setdefault(s.tribunal, set())
            atual = s.data_inicio
            while atual <= s.data_fim:
                dias.add(atual)
                atual += timedelta(days=1)
        set_suspensoes_tribunal(out)
        _CALENDARIO_RUNTIME["suspensoes_ok"] = True
        _CALENDARIO_RUNTIME["suspensoes_erro_tipo"] = None
        return sum(len(v) for v in _SUSPENSOES_TRIB.values())
    except asyncio.CancelledError as exc:
        # Ver carregar_feriados_db: cancelamento por teto de boot precisa
        # marcar o estado ANTES de re-levantar.
        marcar_calendario_falho("suspensoes", type(exc).__name__)
        raise
    except Exception as exc:
        marcar_calendario_falho("suspensoes", type(exc).__name__)
        return 0


@lru_cache(maxsize=32)
def calcular_pascoa(ano: int) -> date:
    """Algoritmo de Gauss (computus) para a Páscoa."""
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


def eh_suspensao_processual(
    d: date,
    tribunal: str | None = None,
    *,
    aplicar_recesso: bool = True,
) -> bool:
    """Indica suspensão do CURSO do prazo, distinta de mero dia não útil.

    Essa distinção é necessária no processo penal: sábado/domingo/feriado
    intermediário integra a contagem contínua; suspensão processual efetiva
    congela a contagem.
    """
    if aplicar_recesso and _cal.em_recesso_art220(d):
        return True
    if _suspenso(d, tribunal):
        return True
    if tribunal and d in _cal.datas_suspensoes_tribunal(tribunal):
        return True
    return False


def eh_dia_util(d: date, forense: bool = True, tribunal: str | None = None,
                aplicar_recesso: bool = False) -> bool:
    if d.weekday() >= 5:
        return False
    if _suspenso(d, tribunal):
        return False
    if aplicar_recesso and _cal.em_recesso_art220(d):
        return False
    if tribunal and (d in _cal.datas_feriados_locais(tribunal)
                     or d in _cal.datas_suspensoes_tribunal(tribunal)):
        return False
    return not eh_feriado(d, incluir_recesso=forense)


def proximo_dia_util(d: date, forense: bool = True, tribunal: str | None = None,
                     aplicar_recesso: bool = False) -> date:
    while not eh_dia_util(d, forense, tribunal, aplicar_recesso):
        d += timedelta(days=1)
    return d


def dia_util_anterior(d: date, forense: bool = True, tribunal: str | None = None,
                      aplicar_recesso: bool = False) -> date:
    while not eh_dia_util(d, forense, tribunal, aplicar_recesso):
        d -= timedelta(days=1)
    return d


# ── Cálculo de prazos ─────────────────────────────────────────────────────────
def prazo_dias_uteis(data_inicio: date, dias: int, tribunal: str | None = None,
                     em_dobro: bool = False, aplicar_recesso: bool = False,
                     forense: bool = True) -> date:
    """Conta prazo em dias úteis excluindo o dia de início."""
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")
    if em_dobro:
        dias *= 2
    atual = data_inicio
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if eh_dia_util(atual, forense=forense, tribunal=tribunal,
                       aplicar_recesso=aplicar_recesso):
            contados += 1
    return atual


def prazo_dias_corridos(data_inicio: date, dias: int,
                        prorrogar_fim: bool = True,
                        tribunal: str | None = None) -> date:
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")
    vencimento = data_inicio + timedelta(days=dias)
    if prorrogar_fim:
        vencimento = proximo_dia_util(vencimento, forense=False, tribunal=tribunal)
    return vencimento


def prazo_processual_penal(
    data_inicio: date,
    dias: int,
    tribunal: str | None = None,
    *,
    excecao_recesso: bool = False,
) -> date:
    """Prazo processual penal pelo regime próprio do CPP.

    Exclui o dia inicial e inclui o vencimento; a contagem intermediária é
    contínua. O recesso suspende o curso salvo quando o operador marca uma das
    exceções legais do art. 798-A. O termo final em dia não útil é prorrogado.
    """
    if dias < 1:
        raise ValueError("dias deve ser maior que zero")

    aplicar_recesso = not excecao_recesso
    atual = data_inicio
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if eh_suspensao_processual(
            atual, tribunal, aplicar_recesso=aplicar_recesso
        ):
            continue
        contados += 1

    return proximo_dia_util(
        atual,
        forense=False,
        tribunal=tribunal,
        aplicar_recesso=aplicar_recesso,
    )


def calcular_prazo_processual(
    data_inicio: date,
    dias: int,
    regime: RegimeProcessual,
    tribunal: str | None = None,
    *,
    em_dobro: bool = False,
    excecao_recesso_penal: bool = False,
) -> dict:
    """Calcula prazo processual por regime explícito e devolve trilha explicável."""
    if regime == "penal":
        if em_dobro:
            raise ValueError("prazo em dobro do CPC não se aplica ao regime penal")
        vencimento = prazo_processual_penal(
            data_inicio,
            dias,
            tribunal,
            excecao_recesso=excecao_recesso_penal,
        )
        modo = "CPP art. 798 (contagem contínua) + art. 798-A (recesso)"
        if excecao_recesso_penal:
            modo += " · exceção ao recesso declarada pelo operador"
    elif regime == "trabalhista":
        vencimento = prazo_dias_uteis(
            data_inicio,
            dias,
            tribunal=tribunal,
            em_dobro=em_dobro,
            aplicar_recesso=True,
            forense=True,
        )
        modo = "CLT arts. 775 e 775-A (dias úteis + suspensão do recesso)"
        if em_dobro:
            modo += " · hipótese de prazo em dobro deve ser conferida"
    elif regime == "civel":
        vencimento = prazo_dias_uteis(
            data_inicio,
            dias,
            tribunal=tribunal,
            em_dobro=em_dobro,
            aplicar_recesso=True,
            forense=True,
        )
        modo = "CPC arts. 219 e 220 (dias úteis + suspensão do recesso)"
        if em_dobro:
            modo += " · CPC arts. 180/183/186/229 conforme hipótese aplicável"
    else:
        raise ValueError("regime processual não suportado")

    calendario = calendario_runtime_status()
    # Feriado municipal/estadual entra em `eh_dia_util` SEM depender de
    # tribunal informado (_FERIADOS_DB é global): falha na carga dos feriados
    # degrada QUALQUER cálculo. Suspensão é por tribunal — só degrada quando há
    # tribunal na conta.
    degradado = bool(
        calendario.get("feriados_ok") is False
        or (tribunal and calendario.get("suspensoes_ok") is False)
    )
    return {
        "data_vencimento": vencimento,
        "regime_calculo": regime,
        "modo": modo,
        "calendario_status": calendario["status"],
        "resultado_preliminar": degradado,
        "revisao_obrigatoria": degradado,
        "aviso": (
            "Calendário local/suspensões indisponível: resultado preliminar, "
            "exige conferência humana antes de confirmação."
            if degradado else None
        ),
    }


def prazo_defesa_ambiental(data_ciencia: date) -> dict:
    """Prazo de defesa contra auto de infração ambiental federal."""
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


def dias_uteis_restantes(vencimento: date) -> int:
    """Dias úteis entre hoje e o vencimento (indicador operacional do painel)."""
    hoje = date.today()
    if vencimento <= hoje:
        return 0
    atual, contados = hoje, 0
    while atual < vencimento:
        atual += timedelta(days=1)
        if eh_dia_util(atual):
            contados += 1
    return contados


# ── Tabela de prescrição por tipo de ação ─────────────────────────────────────
PRESCRICAO_TABELA: dict[str, dict] = {
    "reparacao_civil":      {"anos": 3,  "base": "CC art. 206, §3º, V"},
    "cobranca_divida":      {"anos": 5,  "base": "CC art. 206, §5º, I"},
    "anulacao_negocio":     {"anos": 4,  "base": "CC art. 178"},
    "pretensao_geral":      {"anos": 10, "base": "CC art. 205"},
    "responsabilidade_medica": {"anos": 3, "base": "CC art. 206, §3º, V c/c STJ Súm. 278"},
    "negativacao_indevida":    {"anos": 5, "base": "CDC art. 43, §5º"},
    "acao_trabalhista":        {"anos": 2, "base": "CF art. 7º, XXIX (bienal — pós-extinção)"},
    "creditos_trabalhistas":   {"anos": 5, "base": "CF art. 7º, XXIX (quinquenal — na vigência)"},
    "vicio_consumidor":        {"anos": 5, "base": "CDC art. 27"},
    "prescricao_penal_2anos":  {"anos": 2,  "base": "CP art. 109, VI (pena máx ≤ 1 ano / multa)"},
    "prescricao_penal_4anos":  {"anos": 4,  "base": "CP art. 109, V (pena máx 1-2 anos)"},
    "prescricao_penal_8anos":  {"anos": 8,  "base": "CP art. 109, IV (pena máx 2-4 anos)"},
    "prescricao_penal_12anos": {"anos": 12, "base": "CP art. 109, III (pena máx 4-8 anos)"},
    "prescricao_penal_16anos": {"anos": 16, "base": "CP art. 109, II (pena máx 8-12 anos)"},
    "acao_rescisoria":         {"anos": 2, "base": "CPC art. 975 (do trânsito em julgado)"},
    "execucao_fiscal":         {"anos": 5, "base": "CTN art. 174"},
    "multa_ambiental_adm":     {"anos": 5, "base": "Lei 9.873/99 art. 1º"},
}


def calcular_prescricao(tipo_acao: str, data_fato: date) -> dict | None:
    regra = PRESCRICAO_TABELA.get(tipo_acao)
    if not regra:
        return None
    from app.utils.datas import data_segura

    limite = data_segura(data_fato.year + regra["anos"], data_fato.month, data_fato.day)
    return {
        "data_limite": limite,
        "base_legal": regra["base"],
        "dias_restantes": max((limite - date.today()).days, 0),
        "aviso_causas": (
            "⚠️ Verifique causas suspensivas (CC arts. 197-201) e interruptivas "
            "(CC art. 202) — podem alterar esta data. Cálculo assume prazo contínuo."
        ),
    }
