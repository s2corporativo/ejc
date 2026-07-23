# ── app/core/taxonomia.py ─────────────────────────────────────────────────────
# FONTE ÚNICA da taxonomia de áreas do direito do EJC (Fase 0 do Orquestrador
# Jurídico). O vocabulário CANÔNICO é o enum `CaseArea` (app/models/case.py),
# a lista mais completa do sistema e a que está gravada no banco (coluna
# cases.area). Este módulo NÃO cria áreas novas nem remove existentes.
#
# Ele resolve os vocabulários historicamente desalinhados:
#   (a) análise documental  — documento_service.py (9 áreas originais);
#   (b) triagem automática  — case_intel.py (12 áreas + sentinela "outro");
#   (c) gerador de peças    — peca_service.AREAS_DIREITO (17 slugs).
# Cada fluxo restrito passa a DERIVAR seu subconjunto daqui, com mapeamentos
# explícitos e auditáveis do canônico para o vocabulário restrito.
#
# Regra de ouro (jurídica): NUNCA mapear silenciosamente uma área canônica para
# outra juridicamente diversa. Quando não há correspondência segura, o mapa diz
# None (análise/peças) ou "outro" (triagem) — a decisão fica com o humano (HITL).
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional

from app.models.case import CaseArea

# Sentinela usada pelos fluxos de IA quando nenhuma área canônica se aplica com
# segurança. NÃO é uma área: nunca entra em areas_validas().
SENTINELA_OUTRO = "outro"

# ── Canônico ──────────────────────────────────────────────────────────────────

#: Todas as áreas canônicas, na ordem de declaração do enum CaseArea.
AREAS_CANONICAS: tuple[str, ...] = tuple(a.value for a in CaseArea)


def areas_validas() -> list[str]:
    """Lista (cópia) das áreas canônicas válidas — espelho exato de CaseArea."""
    return list(AREAS_CANONICAS)


# ── Normalização ──────────────────────────────────────────────────────────────

def _slug(texto: str) -> str:
    """minúsculas, sem acento, não-alfanumérico vira '_' ("Direito Cível"→"direito_civel")."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9]+", "_", t.strip().lower()).strip("_")
    return t


# Aliases/grafias → área canônica. SOMENTE sinônimos juridicamente evidentes.
# Acentuação já é resolvida por _slug ("família"→"familia", "tributário"→
# "tributario"), então aqui entram apenas variações de NOME.
# Na dúvida jurídica, o termo NÃO entra (normalizar_area devolve None).
_ALIASES: dict[str, str] = {
    # grafias/sinônimos diretos
    "civel": "civil",                    # "cível" é o nome forense do civil
    "penal": "criminal",                 # direito penal == criminal
    "consumerista": "consumidor",
    "trabalho": "trabalhista",           # "direito do trabalho"
    "do_trabalho": "trabalhista",
    "de_familia": "familia",             # "direito de família"
    "familiar": "familia",
    "previdencia": "previdenciario",
    "fiscal": "tributario",              # direito fiscal == tributário
    "comercial": "empresarial",          # direito comercial → empresarial (CC/2002)
    "sucessao": "sucessoes",
    "das_sucessoes": "sucessoes",
    "licitacao": "licitacoes",
    # direito digital / proteção de dados
    "lgpd": "digital_lgpd",
    "digital": "digital_lgpd",
    "digital_lgpd": "digital_lgpd",
    "protecao_de_dados": "digital_lgpd",
    "seguranca_lgpd": "digital_lgpd",    # chave legada de prompt (peca_service)
    # NÃO mapeados de propósito (juridicamente ambíguos — ficam None):
    #   "juizados"           → rito (pode ser civil, consumidor, fazenda pública)
    #   "bancario vs consumidor/empresarial" → já são áreas canônicas distintas
    #   "publico", "privado" → gêneros, não áreas
}


def normalizar_area(texto: Optional[str]) -> Optional[str]:
    """Normaliza texto livre para uma área CANÔNICA (valor de CaseArea) ou None.

    Aceita: valores canônicos (inclusive os já gravados no banco), variações de
    caixa/acento ("Cível", "Família", "Direito Tributário") e sinônimos
    evidentes ("penal"→"criminal"). Mudança ADITIVA: todo valor legado de
    CaseArea normaliza para si mesmo.

    Devolve None quando não há correspondência juridicamente segura — o
    chamador decide o fallback (ex.: SENTINELA_OUTRO, campo vazio, HITL).
    """
    if not texto or not isinstance(texto, str):
        return None
    s = _slug(texto)
    if not s:
        return None
    # "direito_civil", "direito_do_trabalho" → remove o prefixo genérico
    if s.startswith("direito_"):
        s = s[len("direito_"):]
    if s in AREAS_CANONICAS:
        return s
    return _ALIASES.get(s)


def areas_para_prompt(
    subconjunto: Optional[Iterable[str]] = None,
    separador: str = ", ",
) -> str:
    """Lista formatada de áreas para prompts de IA (fonte única de vocabulário).

    ``subconjunto`` restringe às áreas informadas (validadas contra o canônico;
    valor fora do canônico levanta ValueError — nada de vocabulário fantasma em
    prompt). Sem subconjunto, usa todas as áreas canônicas.
    """
    areas = list(subconjunto) if subconjunto is not None else list(AREAS_CANONICAS)
    invalidas = [a for a in areas if a not in AREAS_CANONICAS]
    if invalidas:
        raise ValueError(f"áreas fora do canônico (CaseArea): {invalidas}")
    return separador.join(areas)


# ── (a) Análise documental — documento_service.py ────────────────────────────
# O extrator estruturado só classifica nas 9 áreas ORIGINAIS (migration 001);
# ampliar o vocabulário do prompt é decisão de produto fora da Fase 0.

AREAS_ANALISE_DOCUMENTAL: tuple[str, ...] = (
    "civil", "trabalhista", "consumidor", "familia", "ambiental",
    "criminal", "previdenciario", "empresarial", "tributario",
)

# Canônico → uma das 9 áreas da análise documental, ou None quando o
# enquadramento seria juridicamente incerto (fica para o revisor humano).
MAPA_CANONICO_PARA_ANALISE: dict[str, Optional[str]] = {
    # identidade (as 9 originais)
    "civil": "civil",
    "trabalhista": "trabalhista",
    "consumidor": "consumidor",
    "familia": "familia",
    "ambiental": "ambiental",
    "criminal": "criminal",
    "previdenciario": "previdenciario",
    "empresarial": "empresarial",
    "tributario": "tributario",
    # sub-ramos com correspondência SEGURA
    "imobiliario": "civil",        # direito imobiliário integra o direito civil
    "sucessoes": "civil",          # Livro V do Código Civil
    "contratual": "civil",         # obrigações/contratos — direito civil
    "societario": "empresarial",   # sub-ramo do direito empresarial
    # SEM correspondência segura nas 9 → None (nunca chutar área diversa)
    "administrativo": None,        # não é civil; as 9 não têm público
    "bancario": None,              # pode ser consumidor OU empresarial
    "constitucional": None,
    "digital_lgpd": None,          # pode ser consumidor, civil ou regulatório
    "transito": None,              # administrativo, civil ou criminal conforme o caso
    "saude": None,                 # consumidor, civil ou administrativo (SUS)
    "medico": None,                # o bug histórico era "médico vira civil" — não repetir
    "agrario": None,               # ramo autônomo
    "agronegocio": None,
    "eleitoral": None,
    "internacional": None,
    "licitacoes": None,              # desativado no EJC; preservado no enum por compat de DB
}

# ── (b) Triagem automática — case_intel.py ───────────────────────────────────
# Subconjunto canônico do vocabulário da triagem (ordem preservada do prompt
# histórico; "civel"→civil e "penal"→criminal foram canonizados — os valores
# antigos seguem aceitos por normalizar_area). O prompt acrescenta a sentinela
# "outro" no fim (SENTINELA_OUTRO), que não é área.

AREAS_TRIAGEM: tuple[str, ...] = (
    "trabalhista", "civil", "empresarial", "administrativo", "tributario",
    "previdenciario", "consumidor", "familia", "sucessoes", "criminal",
    "ambiental", "bancario",
)

# Canônico → vocabulário da triagem; sem correspondência segura → "outro".
MAPA_CANONICO_PARA_TRIAGEM: dict[str, str] = {
    # identidade (as 12 do vocabulário da triagem)
    **{a: a for a in AREAS_TRIAGEM},
    # sub-ramos com correspondência SEGURA
    "imobiliario": "civil",
    "contratual": "civil",
    "societario": "empresarial",
    # juridicamente ambíguos → sentinela (decisão fica com o advogado)
    "constitucional": SENTINELA_OUTRO,
    "digital_lgpd": SENTINELA_OUTRO,
    "transito": SENTINELA_OUTRO,
    "saude": SENTINELA_OUTRO,
    "medico": SENTINELA_OUTRO,
    "agrario": SENTINELA_OUTRO,
    "agronegocio": SENTINELA_OUTRO,
    "eleitoral": SENTINELA_OUTRO,
    "internacional": SENTINELA_OUTRO,
    "licitacoes": "administrativo",
}

# ── (c) Gerador de peças — peca_service.AREAS_DIREITO ────────────────────────
# Vocabulário do pipeline de peças (17 slugs, ordem histórica preservada — o
# endpoint /pecas/meta e testes de invariantes dependem da ordem). Exceção
# documentada: "juizados" é um RITO do pipeline (prompt próprio), não uma área
# canônica de CaseArea — permanece aqui por compatibilidade, mas não existe no
# canônico e normalizar_area("juizados") devolve None.

AREA_PECA_EXTRA_RITO = "juizados"

AREAS_PECA: tuple[str, ...] = (
    "trabalhista", "civil", "previdenciario", "tributario",
    "criminal", "consumidor", "administrativo", "familia",
    "empresarial", "ambiental", "bancario", "imobiliario",
    "sucessoes", "constitucional", AREA_PECA_EXTRA_RITO, "digital_lgpd",
    "transito",
)

# Canônico → slug do pipeline de peças; sem correspondência segura → None.
MAPA_CANONICO_PARA_PECA: dict[str, Optional[str]] = {
    # identidade (todas as canônicas que o pipeline já cobre)
    **{a: a for a in AREAS_PECA if a in AREAS_CANONICAS},
    # sub-ramos com correspondência SEGURA
    "contratual": "civil",
    "societario": "empresarial",
    # juridicamente ambíguos → None (pipeline exige escolha humana da área)
    "saude": None,
    "medico": None,
    "agrario": None,
    "agronegocio": None,
    "eleitoral": None,
    "internacional": None,
    "licitacoes": "administrativo",
}

# ── Sanidade (falha no import — nunca em runtime silencioso) ─────────────────
assert set(AREAS_ANALISE_DOCUMENTAL) <= set(AREAS_CANONICAS)
assert set(AREAS_TRIAGEM) <= set(AREAS_CANONICAS)
assert set(AREAS_PECA) - {AREA_PECA_EXTRA_RITO} <= set(AREAS_CANONICAS)
assert set(MAPA_CANONICO_PARA_ANALISE) == set(AREAS_CANONICAS)
assert set(MAPA_CANONICO_PARA_TRIAGEM) == set(AREAS_CANONICAS)
assert set(MAPA_CANONICO_PARA_PECA) == set(AREAS_CANONICAS)
assert all(v is None or v in AREAS_ANALISE_DOCUMENTAL
           for v in MAPA_CANONICO_PARA_ANALISE.values())
assert all(v == SENTINELA_OUTRO or v in AREAS_TRIAGEM
           for v in MAPA_CANONICO_PARA_TRIAGEM.values())
assert all(v is None or v in AREAS_PECA for v in MAPA_CANONICO_PARA_PECA.values())
