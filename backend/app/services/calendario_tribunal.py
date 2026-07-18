# ── app/services/calendario_tribunal.py ──────────────────────────────────────
# Calendário de tribunal VERSIONADO em código/dados (sem migration).
#
# REGRA DA CASA (inviolável): NUNCA inventar feriado, suspensão ou regra.
# Todo registro deste módulo exige `fonte` e `vigencia` — um registro sem
# fonte oficial derruba a importação do módulo (fail-fast, ver _validar()).
#
# Conteúdo incluído (apenas certeza absoluta):
#   • Feriados nacionais OFICIAIS (leis federais) — mesmos dias que o
#     deadline_calculator sempre usou; agora centralizados aqui com fonte.
#   • Recesso forense do CPC art. 220 (20/12 a 20/01, inclusive — suspensão
#     do curso dos prazos processuais). Equivalente trabalhista: CLT art.
#     775-A (Lei 13.467/2017).
#   • Estruturas VAZIAS e documentadas para feriados locais e suspensões por
#     tribunal — curadoria humana futura; nada é inventado aqui.
#
# O deadline_calculator CONSULTA este módulo (nunca o contrário — sem ciclo
# de import). Sem dados locais cadastrados, o comportamento do cálculo é
# IDÊNTICO ao anterior (retrocompatibilidade garantida por teste).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# Versão do calendário (ano.mês.revisão da curadoria). Incrementar a cada
# mudança de DADOS (novo feriado local, suspensão etc.) — permite auditar
# com qual calendário um prazo foi projetado.
CALENDARIO_VERSAO = "2026.07.0"


# ── Feriados nacionais OFICIAIS (leis federais) ──────────────────────────────
# Mesmos (dia, mês) do FERIADOS_FIXOS histórico do deadline_calculator —
# centralizados aqui com fonte e vigência obrigatórias.
FERIADOS_NACIONAIS: list[dict] = [
    {"dia": 1, "mes": 1, "nome": "Confraternização Universal",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 21, "mes": 4, "nome": "Tiradentes",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 1, "mes": 5, "nome": "Dia Mundial do Trabalho",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 7, "mes": 9, "nome": "Independência do Brasil",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 12, "mes": 10, "nome": "Nossa Senhora Aparecida",
     "fonte": "Lei 6.802/1980, art. 1º",
     "vigencia": "desde 30/06/1980"},
    {"dia": 2, "mes": 11, "nome": "Finados",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 15, "mes": 11, "nome": "Proclamação da República",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
    {"dia": 20, "mes": 11, "nome": "Dia Nacional de Zumbi e da Consciência Negra",
     "fonte": "Lei 14.759/2023, art. 1º",
     "vigencia": "desde 22/12/2023"},
    {"dia": 25, "mes": 12, "nome": "Natal",
     "fonte": "Lei 662/1949, art. 1º (red. Lei 10.607/2002)",
     "vigencia": "desde 06/04/1949"},
]

# ── Dias móveis SEM expediente forense (documentação do comportamento) ───────
# As DATAS são calculadas pelo deadline_calculator.feriados_moveis (Gauss) —
# comportamento herdado e preservado. Este bloco só documenta a natureza de
# cada dia (nem todos são feriado nacional por lei federal):
FERIADOS_MOVEIS_INFO: list[dict] = [
    {"nome": "Segunda e Terça de Carnaval",
     "fonte": ("Ponto facultativo federal (decreto anual); expediente forense "
               "suspenso na prática consolidada dos tribunais — comportamento "
               "herdado do deadline_calculator (retrocompatibilidade)"),
     "vigencia": "prática consolidada"},
    {"nome": "Sexta-feira Santa (Paixão de Cristo)",
     "fonte": ("Lei 9.093/1995, art. 2º (feriado religioso conforme lei local); "
               "sem expediente forense na prática consolidada dos tribunais — "
               "comportamento herdado do deadline_calculator"),
     "vigencia": "prática consolidada"},
    {"nome": "Corpus Christi",
     "fonte": ("Ponto facultativo federal (decreto anual); expediente forense "
               "suspenso na prática consolidada dos tribunais — comportamento "
               "herdado do deadline_calculator (retrocompatibilidade)"),
     "vigencia": "prática consolidada"},
]

# ── Recesso forense — CPC art. 220 ───────────────────────────────────────────
# "Suspende-se o curso do prazo processual nos dias compreendidos entre 20 de
#  dezembro e 20 de janeiro, inclusive." Aplica-se a PRAZOS PROCESSUAIS
# (contagem em dias úteis). NÃO se aplica a prazos decadenciais (ex.: MS,
# Lei 12.016/2009 art. 23) nem a prazos administrativos em dias corridos.
# Equivalente trabalhista: CLT, art. 775-A (Lei 13.467/2017).
RECESSO_ART_220: dict = {
    "inicio": (20, 12),   # (dia, mês)
    "fim": (20, 1),       # (dia, mês) — inclusive
    "fonte": "CPC (Lei 13.105/2015), art. 220; CLT, art. 775-A (Lei 13.467/2017)",
    "vigencia": "desde 18/03/2016 (vigência do CPC/2015)",
}


def em_recesso_art220(d: date) -> bool:
    """A data cai na janela de suspensão do CPC art. 220 (20/12–20/01)?"""
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)


# ── Feriados LOCAIS por tribunal (curadoria humana — VAZIO por padrão) ───────
# Estrutura: {"TJMG": [{"data": date(...), "nome": ..., "fonte": ...,
#                       "vigencia": ...}], ...}
# `fonte` deve citar o ato oficial (lei estadual/municipal, portaria do
# tribunal); `vigencia` o período de validade. NUNCA preencher sem fonte —
# a validação de import derruba o módulo. Feriados municipais dinâmicos
# continuam vindo da tabela `feriados` (deadline_calculator._FERIADOS_DB).
FERIADOS_LOCAIS: dict[str, list[dict]] = {}

# ── Suspensões de prazo por tribunal (curadoria humana — VAZIO por padrão) ───
# Estrutura: {"TJMG": [{"data_inicio": date(...), "data_fim": date(...),
#                       "nome": ..., "fonte": ..., "vigencia": ...}], ...}
# `fonte` = portaria/resolução do tribunal que suspendeu os prazos.
# Suspensões dinâmicas continuam vindo da tabela `suspensoes_tribunal`
# (deadline_calculator._SUSPENSOES_TRIB) — este bloco é para curadoria
# versionada em código.
SUSPENSOES_TRIBUNAL: dict[str, list[dict]] = {}


# ── Validação fail-fast: registro sem fonte/vigencia derruba o import ────────
def _validar() -> None:
    for reg in FERIADOS_NACIONAIS + FERIADOS_MOVEIS_INFO:
        if not (reg.get("fonte") and reg.get("vigencia")):
            raise ValueError(f"Registro de calendário sem fonte/vigencia: {reg}")
    if not (RECESSO_ART_220.get("fonte") and RECESSO_ART_220.get("vigencia")):
        raise ValueError("RECESSO_ART_220 sem fonte/vigencia")
    for trib, regs in list(FERIADOS_LOCAIS.items()) + list(SUSPENSOES_TRIBUNAL.items()):
        for reg in regs:
            if not (reg.get("fonte") and reg.get("vigencia")):
                raise ValueError(
                    f"Registro do tribunal {trib} sem fonte/vigencia: {reg}")


_validar()


# ── Acessores consumidos pelo deadline_calculator ────────────────────────────

def feriados_fixos_nacionais() -> set[tuple[int, int]]:
    """Conjunto {(dia, mês)} dos feriados nacionais oficiais."""
    return {(f["dia"], f["mes"]) for f in FERIADOS_NACIONAIS}


@lru_cache(maxsize=64)
def datas_feriados_locais(tribunal: str) -> frozenset[date]:
    """Datas de feriados locais curados para o tribunal (vazio por padrão)."""
    return frozenset(r["data"] for r in FERIADOS_LOCAIS.get(tribunal, ()))


@lru_cache(maxsize=64)
def datas_suspensoes_tribunal(tribunal: str) -> frozenset[date]:
    """Datas suspensas por atos do tribunal curados em código (vazio por padrão)."""
    dias: set[date] = set()
    for r in SUSPENSOES_TRIBUNAL.get(tribunal, ()):
        atual = r["data_inicio"]
        while atual <= r["data_fim"]:
            dias.add(atual)
            atual += timedelta(days=1)
    return frozenset(dias)


def versao_calendario() -> dict:
    """Metadados do calendário vigente (para auditoria/resposta de API)."""
    return {
        "versao": CALENDARIO_VERSAO,
        "feriados_nacionais": len(FERIADOS_NACIONAIS),
        "tribunais_com_feriados_locais": sorted(FERIADOS_LOCAIS.keys()),
        "tribunais_com_suspensoes": sorted(SUSPENSOES_TRIBUNAL.keys()),
        "recesso_art_220": RECESSO_ART_220["fonte"],
    }
