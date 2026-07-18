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
CALENDARIO_VERSAO = "2026.07.1"


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


# ── Feriados LOCAIS por tribunal (curadoria humana) ──────────────────────────
# Estrutura: {"TJMG": [{"data": date(...), "nome": ..., "fonte": ...,
#                       "vigencia": ...}], ...}
# `fonte` deve citar o ato oficial (lei estadual/municipal, portaria do
# tribunal); `vigencia` o período de validade. NUNCA preencher sem fonte —
# a validação de import derruba o módulo. Feriados municipais dinâmicos
# continuam vindo da tabela `feriados` (deadline_calculator._FERIADOS_DB).
#
# CURADORIA 2026-07-18 (foro do escritório: Belo Horizonte/MG — TJMG e TRT-3).
# Processo: cada registro abaixo foi confirmado em conteúdo de DOMÍNIO OFICIAL
# (tjmg.jus.br, trt3.jus.br, cmbh.mg.gov.br, prefeitura.pbh.gov.br) acessado
# nesta sessão via busca restrita por domínio (fetch direto bloqueado pelo
# proxy do ambiente); a fonte de cada registro cita a norma (número/ano) e a
# página oficial. Completar ANUALMENTE: as portarias/resoluções de calendário
# (TJMG: Portaria Conjunta anual; TRT-3: Resolução Administrativa anual +
# Portaria SEGP de feriados locais) valem só para o ano de referência.
# Nada além do confirmado foi incluído (regra da casa: nunca inventar).
#
# NOTA: a data magna de MG (21/04, Constituição Estadual art. 256, red. EC
# 22/1997) coincide com o feriado nacional de Tiradentes — não precisa de
# registro local. Os feriados aqui referem-se ao MUNICÍPIO-SEDE Belo
# Horizonte (comarca de BH / varas de BH); comarcas do interior têm feriados
# próprios NÃO curados aqui.
_FONTE_LEI_BH = (
    "Lei municipal de Belo Horizonte 1.327, de 08/02/1967 (feriados "
    "religiosos municipais: Sexta-feira da Paixão, Corpus Christi, Assunção "
    "de Nossa Senhora 15/08 e Imaculada Conceição 08/12) — "
    "cmbh.mg.gov.br/atividade-legislativa/pesquisar-legislacao/lei/1327/1967; "
    "confirmada tb. em prefeitura.pbh.gov.br (notícias de funcionamento nos "
    "feriados de Assunção e Imaculada Conceição)"
)
_FONTE_PC_TJMG_2026 = (
    "TJMG, Portaria Conjunta 1798/PR/2026 (DJe 13/04/2026) — calendário de "
    "feriados e suspensões de expediente forense de 2026 — "
    "www8.tjmg.jus.br/institucional/at/pdf/pc17982026.pdf; portal: "
    "tjmg.jus.br/portal-tjmg/informes/calendario-de-feriados-em-2026-"
    "suspensoes-de-expediente.htm"
)
_FONTE_RA_TRT3_2026 = (
    "TRT-3, Resolução Administrativa 109, de 12/08/2025 (Órgão Especial) — "
    "calendário de feriados da JT/MG em 2026 — portal.trt3.jus.br/internet/"
    "conheca-o-trt/comunicacao/noticias-institucionais/aprovado-calendario-"
    "de-feriados-da-jt-minas-em-2026; Portaria TRT3/SEGP 991, de 03/11/2025 "
    "(divulga os feriados locais de 2026, Anexo Único)"
)

FERIADOS_LOCAIS: dict[str, list[dict]] = {
    "TJMG": [
        # Comarca de Belo Horizonte — feriados municipais por lei permanente.
        {"data": date(2026, 8, 15), "nome": "Assunção de Nossa Senhora (BH)",
         "fonte": _FONTE_LEI_BH + "; constante tb. da " + _FONTE_PC_TJMG_2026,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2026"},
        {"data": date(2026, 12, 8), "nome": "Imaculada Conceição (BH)",
         "fonte": _FONTE_LEI_BH,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2026"},
        {"data": date(2027, 8, 15), "nome": "Assunção de Nossa Senhora (BH)",
         "fonte": _FONTE_LEI_BH,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2027"},
        {"data": date(2027, 12, 8), "nome": "Imaculada Conceição (BH)",
         "fonte": _FONTE_LEI_BH,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2027"},
    ],
    "TRT3": [
        # Varas de Belo Horizonte — feriados municipais (lei permanente) +
        # calendário JT/MG 2026 (RA 109/2025; Portaria SEGP 991/2025).
        {"data": date(2026, 8, 15), "nome": "Assunção de Nossa Senhora (BH)",
         "fonte": _FONTE_LEI_BH + "; constante tb. da " + _FONTE_RA_TRT3_2026,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2026"},
        {"data": date(2026, 12, 8),
         "nome": "Dia da Justiça e Imaculada Conceição (BH)",
         "fonte": _FONTE_RA_TRT3_2026 + "; " + _FONTE_LEI_BH,
         "vigencia": "ano de 2026 (RA 109/2025); Imaculada Conceição em BH "
                     "desde 08/02/1967 (lei em vigor)"},
        {"data": date(2027, 8, 15), "nome": "Assunção de Nossa Senhora (BH)",
         "fonte": _FONTE_LEI_BH,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2027"},
        {"data": date(2027, 12, 8), "nome": "Imaculada Conceição (BH)",
         "fonte": _FONTE_LEI_BH,
         "vigencia": "desde 08/02/1967 (lei em vigor); data de 2027"},
    ],
}

# ── Suspensões de prazo por tribunal (curadoria humana) ──────────────────────
# Estrutura: {"TJMG": [{"data_inicio": date(...), "data_fim": date(...),
#                       "nome": ..., "fonte": ..., "vigencia": ...}], ...}
# `fonte` = portaria/resolução do tribunal que suspendeu os prazos.
# Suspensões dinâmicas continuam vindo da tabela `suspensoes_tribunal`
# (deadline_calculator._SUSPENSOES_TRIB) — este bloco é para curadoria
# versionada em código.
#
# CURADORIA 2026-07-18 — mesmo processo e fontes da seção FERIADOS_LOCAIS
# acima (conteúdo de domínio oficial acessado nesta sessão; completar
# anualmente quando o tribunal publicar o calendário do ano seguinte).
# Recesso 20/12–20/01 NÃO entra aqui: já coberto por RECESSO_ART_220
# (CPC art. 220 / CLT art. 775-A) via aplicar_recesso.
SUSPENSOES_TRIBUNAL: dict[str, list[dict]] = {
    "TJMG": [
        {"data_inicio": date(2026, 2, 18), "data_fim": date(2026, 2, 18),
         "nome": "Quarta-feira de Cinzas (sem expediente forense)",
         "fonte": "TJMG, Resolução 458/2004 (Carnaval: expediente suspenso "
                  "de segunda a Quarta-feira de Cinzas, 16 a 18/02/2026); "
                  + _FONTE_PC_TJMG_2026,
         "vigencia": "datas de 2026 (16 e 17/02 já cobertos como feriados "
                     "móveis de Carnaval)"},
        {"data_inicio": date(2026, 4, 1), "data_fim": date(2026, 4, 2),
         "nome": "Semana Santa — quarta e quinta-feira santas "
                 "(sem expediente; sexta 03/04 já é feriado móvel)",
         "fonte": _FONTE_PC_TJMG_2026,
         "vigencia": "ano de 2026"},
        {"data_inicio": date(2026, 4, 20), "data_fim": date(2026, 4, 20),
         "nome": "Suspensão de expediente — segunda-feira anterior a "
                 "Tiradentes (21/04)",
         "fonte": _FONTE_PC_TJMG_2026,
         "vigencia": "ano de 2026"},
        {"data_inicio": date(2026, 10, 30), "data_fim": date(2026, 10, 30),
         "nome": "Comemoração do Dia do Servidor Público "
                 "(expediente forense suspenso)",
         "fonte": _FONTE_PC_TJMG_2026,
         "vigencia": "ano de 2026"},
        {"data_inicio": date(2026, 12, 7), "data_fim": date(2026, 12, 7),
         "nome": "Suspensão de expediente — segunda-feira anterior a "
                 "08/12 (Imaculada Conceição em BH)",
         "fonte": _FONTE_PC_TJMG_2026,
         "vigencia": "ano de 2026"},
    ],
    "TRT3": [
        {"data_inicio": date(2026, 4, 1), "data_fim": date(2026, 4, 2),
         "nome": "Semana Santa — quarta e quinta-feira santas "
                 "(calendário JT/MG: Semana Santa de 01 a 05/04/2026; "
                 "sexta 03/04 já é feriado móvel)",
         "fonte": _FONTE_RA_TRT3_2026,
         "vigencia": "ano de 2026"},
    ],
}


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
