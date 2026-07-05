# ── app/services/deadline_calculator.py ──────────────────────────────────────
# Cálculo de prazos processuais e administrativos.
#
# MELHORIA SOBRE v2: feriados móveis calculados (Carnaval, Sexta Santa,
# Corpus Christi) via algoritmo de Gauss para a Páscoa. v2 só tinha fixos.
#
# Regras implementadas:
#  • Prazo processual CPC: dias ÚTEIS (art. 219 CPC)
#  • Prazo CLT: dias úteis (art. 775 CLT, red. Lei 13.467/17)
#  • Prazo administrativo (IBAMA): dias CORRIDOS, prorrogação p/ dia útil
#    se vencer em dia não útil (Lei 9.784/99 art. 66 §1º)
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from datetime import date, timedelta
from functools import lru_cache


# ── Feriados nacionais FIXOS (dia, mês) ───────────────────────────────────────
FERIADOS_FIXOS: set[tuple[int, int]] = {
    (1, 1),    # Confraternização Universal
    (21, 4),   # Tiradentes
    (1, 5),    # Dia do Trabalho
    (7, 9),    # Independência
    (12, 10),  # N. Sra. Aparecida
    (2, 11),   # Finados
    (15, 11),  # Proclamação da República
    (20, 11),  # Consciência Negra (Lei 14.759/2023)
    (25, 12),  # Natal
}

# Feriados forenses adicionais (recesso 20/12 a 06/01 — suspensão CPC art. 220)
RECESSO_FORENSE = [(d, 12) for d in range(20, 32)] + [(d, 1) for d in range(1, 7)]


# ── Feriados municipais/estaduais carregados do BANCO ─────────────────────────
# A tabela `feriados` (ver seeds/seed_all.py) traz feriados MUNICIPAIS de Betim
# e eventuais ESTADUAIS de MG que não são deriváveis em código. São carregados
# uma vez no startup (main.lifespan → carregar_feriados_db) e recarregados
# diariamente pelo scheduler. Conjunto vazio ⇒ comportamento idêntico ao
# anterior (apenas nacionais fixos + móveis + recesso).
#
# ⚠️ LIMITE IMPORTANTE: suspensões processuais por TRIBUNAL (TJMG, TRT3, etc.)
# seguem portarias próprias de cada corte e NÃO estão cobertas aqui — continuam
# a cargo do advogado / integração futura com os calendários dos tribunais.
_FERIADOS_DB: set[date] = set()


def set_feriados_db(datas: set[date]) -> None:
    """Substitui o conjunto de feriados extras (municipais/estaduais) em memória."""
    global _FERIADOS_DB
    _FERIADOS_DB = set(datas)


async def carregar_feriados_db() -> int:
    """
    Carrega da tabela `feriados` os dias municipais/estaduais/forenses.
    Import lazy do banco: mantém este módulo livre de dependência de I/O, então
    as funções de cálculo permanecem síncronas e puras (testáveis sem DB).
    Falha de carga NUNCA derruba a aplicação — apenas mantém o cálculo nacional.
    Retorna a quantidade de datas carregadas.
    """
    try:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.feriado import Feriado
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Feriado.data))).scalars().all()
        set_feriados_db({d for d in rows if d})
        return len(_FERIADOS_DB)
    except Exception:
        return 0


# ── Suspensões de prazo por TRIBUNAL (portarias/feriados forenses locais) ─────
# Cada tribunal suspende prazos por atos próprios. Diferente dos feriados (que
# valem para todos), uma suspensão só afeta prazos do tribunal correspondente.
# Estrutura: {tribunal -> conjunto de datas suspensas}.
_SUSPENSOES_TRIB: dict[str, set[date]] = {}


def set_suspensoes_tribunal(mapping: dict[str, set[date]]) -> None:
    """Substitui o mapa de suspensões por tribunal em memória."""
    global _SUSPENSOES_TRIB
    _SUSPENSOES_TRIB = {k: set(v) for k, v in mapping.items()}


def _suspenso(d: date, tribunal: str | None) -> bool:
    """A data está suspensa para o tribunal informado?"""
    return bool(tribunal) and d in _SUSPENSOES_TRIB.get(tribunal, frozenset())


async def carregar_suspensoes_db() -> int:
    """
    Carrega da tabela `suspensoes_tribunal` os intervalos vigentes (não
    deletados) e expande em datas por tribunal. Import lazy; falha nunca
    derruba a app. Retorna o total de dias suspensos carregados.
    """
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
        return sum(len(v) for v in _SUSPENSOES_TRIB.values())
    except Exception:
        return 0


@lru_cache(maxsize=32)
def calcular_pascoa(ano: int) -> date:
    """
    Algoritmo de Gauss (computus) — data da Páscoa para qualquer ano.
    Base dos feriados móveis brasileiros.
    """
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
    """Feriados móveis derivados da Páscoa."""
    pascoa = calcular_pascoa(ano)
    return {
        pascoa - timedelta(days=48),  # Segunda de Carnaval
        pascoa - timedelta(days=47),  # Terça de Carnaval
        pascoa - timedelta(days=2),   # Sexta-feira Santa
        pascoa + timedelta(days=60),  # Corpus Christi
    }


def eh_feriado(d: date, incluir_recesso: bool = False) -> bool:
    """Feriado nacional (fixo/móvel) OU municipal/estadual carregado do banco."""
    if (d.day, d.month) in FERIADOS_FIXOS:
        return True
    if d in feriados_moveis(d.year):
        return True
    if d in _FERIADOS_DB:                       # municipais/estaduais (banco)
        return True
    if incluir_recesso and (d.day, d.month) in RECESSO_FORENSE:
        return True
    return False


def eh_dia_util(d: date, forense: bool = True, tribunal: str | None = None) -> bool:
    """Dia útil = não é fim de semana, feriado nem dia suspenso pelo tribunal."""
    if d.weekday() >= 5:        # 5=sábado, 6=domingo
        return False
    if _suspenso(d, tribunal):  # suspensão específica do tribunal (portaria)
        return False
    return not eh_feriado(d, incluir_recesso=forense)


def proximo_dia_util(d: date, forense: bool = True, tribunal: str | None = None) -> date:
    """Retorna a própria data se útil; senão, o próximo dia útil."""
    while not eh_dia_util(d, forense, tribunal):
        d += timedelta(days=1)
    return d


def dia_util_anterior(d: date, forense: bool = True, tribunal: str | None = None) -> date:
    """Retorna a própria data se útil; senão, o dia útil anterior."""
    while not eh_dia_util(d, forense, tribunal):
        d -= timedelta(days=1)
    return d


# ── Cálculo de prazos ─────────────────────────────────────────────────────────

def prazo_dias_uteis(data_inicio: date, dias: int, tribunal: str | None = None,
                     em_dobro: bool = False) -> date:
    """
    Prazo processual em dias ÚTEIS (CPC art. 219 / CLT art. 775).
    Exclui o dia do início; conta apenas dias úteis forenses.
    Se `tribunal` for informado, desconsidera também os dias suspensos por ele.

    em_dobro=True DOBRA a quantidade de dias — prazo em dobro do CPC:
      • art. 180 — Ministério Público;
      • art. 183 — Fazenda Pública (União, Estados, DF, Municípios e autarquias/
        fundações);
      • art. 186 — Defensoria Pública / escritórios de prática jurídica;
      • art. 229 — litisconsortes com procuradores distintos, de escritórios
        diferentes, APENAS em autos FÍSICOS (não se aplica ao processo
        eletrônico, art. 229 §2º).
    O dobro incide sobre a CONTAGEM (nº de dias úteis), não sobre a data.
    """
    if em_dobro:
        dias *= 2
    atual = data_inicio
    contados = 0
    while contados < dias:
        atual += timedelta(days=1)
        if eh_dia_util(atual, forense=True, tribunal=tribunal):
            contados += 1
    return atual


def prazo_dias_corridos(data_inicio: date, dias: int,
                        prorrogar_fim: bool = True,
                        tribunal: str | None = None) -> date:
    """
    Prazo administrativo em dias CORRIDOS (ex: defesa IBAMA, 20 dias).
    Lei 9.784/99 art. 66 §1º: se o vencimento cair em dia não útil,
    prorroga para o primeiro dia útil seguinte (considerando o tribunal).
    """
    vencimento = data_inicio + timedelta(days=dias)
    if prorrogar_fim:
        vencimento = proximo_dia_util(vencimento, forense=False, tribunal=tribunal)
    return vencimento


def prazo_defesa_ambiental(data_ciencia: date) -> dict:
    """
    Prazo de defesa contra auto de infração ambiental federal.
    Base: Decreto 6.514/2008 art. 113 — 20 dias da ciência da autuação.

    Retorna:
      data_legal    → vencimento legal (com prorrogação Lei 9.784)
      data_interna  → margem de segurança do escritório (2 dias úteis antes)
      dias_restantes → corridos a partir de hoje
    """
    data_legal = prazo_dias_corridos(data_ciencia, 20, prorrogar_fim=True)

    # Margem interna: protocolar 2 dias úteis antes do prazo legal
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
    """Dias úteis entre hoje e o vencimento (para painel de urgência)."""
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
    # ── Cível ─────────────────────────────────────────────────────────────────
    "reparacao_civil":      {"anos": 3,  "base": "CC art. 206, §3º, V"},
    "cobranca_divida":      {"anos": 5,  "base": "CC art. 206, §5º, I"},
    "anulacao_negocio":     {"anos": 4,  "base": "CC art. 178"},
    "pretensao_geral":      {"anos": 10, "base": "CC art. 205"},
    # ── Responsabilidade civil ────────────────────────────────────────────────
    "responsabilidade_medica": {"anos": 3, "base": "CC art. 206, §3º, V c/c STJ Súm. 278"},
    "negativacao_indevida":    {"anos": 5, "base": "CDC art. 43, §5º"},
    # ── Trabalhista ───────────────────────────────────────────────────────────
    "acao_trabalhista":        {"anos": 2, "base": "CF art. 7º, XXIX (bienal — pós-extinção)"},
    "creditos_trabalhistas":   {"anos": 5, "base": "CF art. 7º, XXIX (quinquenal — na vigência)"},
    # ── Consumidor ────────────────────────────────────────────────────────────
    "vicio_consumidor":        {"anos": 5, "base": "CDC art. 27"},
    # ── Penal ─────────────────────────────────────────────────────────────────
    # Prazo calculado sobre pena MÁXIMA em abstracto (CP art. 109)
    "prescricao_penal_2anos":  {"anos": 2,  "base": "CP art. 109, VI (pena máx ≤ 1 ano / multa)"},
    "prescricao_penal_4anos":  {"anos": 4,  "base": "CP art. 109, V (pena máx 1-2 anos)"},
    "prescricao_penal_8anos":  {"anos": 8,  "base": "CP art. 109, IV (pena máx 2-4 anos)"},
    "prescricao_penal_12anos": {"anos": 12, "base": "CP art. 109, III (pena máx 4-8 anos)"},
    "prescricao_penal_16anos": {"anos": 16, "base": "CP art. 109, II (pena máx 8-12 anos)"},
    # ── Processual ────────────────────────────────────────────────────────────
    "acao_rescisoria":         {"anos": 2, "base": "CPC art. 975 (do trânsito em julgado)"},
    # ── Tributário / Administrativo ───────────────────────────────────────────
    "execucao_fiscal":         {"anos": 5, "base": "CTN art. 174"},
    "multa_ambiental_adm":     {"anos": 5, "base": "Lei 9.873/99 art. 1º"},
}


def calcular_prescricao(tipo_acao: str, data_fato: date) -> dict | None:
    """
    Data-limite prescricional para um tipo de ação a partir do fato gerador.

    IMPORTANTE — causas que suspendem ou interrompem o prazo NÃO são aplicadas
    automaticamente; o advogado deve verificá-las caso a caso:
      • Suspensivas (CC arts. 197-201): entre cônjuges, filhos, incapazes,
        ausentes do País a serviço público, pendência de ação de guarda, etc.
        → prazo PARA enquanto a causa durar, retomando do ponto em que parou.
      • Interruptivas (CC art. 202): protesto, despacho citatório, ato judicial
        que constitua em mora, apresentação de título em inventário/concurso.
        → prazo RECOMEÇA do zero após a interrupção.
    A data_limite retornada assume início contínuo; ajuste conforme as causas.
    """
    regra = PRESCRICAO_TABELA.get(tipo_acao)
    if not regra:
        return None
    limite = date(
        data_fato.year + regra["anos"], data_fato.month,
        min(data_fato.day, 28)  # segurança p/ fevereiro
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
