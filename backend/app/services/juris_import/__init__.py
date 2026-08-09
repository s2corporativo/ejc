# ── app/services/juris_import/ ───────────────────────────────────────────────
# Importação on-demand de jurisprudência REAL de fontes públicas OFICIAIS,
# alimentando (1) a base de conhecimento RAG e (2) a base de citações
# validadas do gate anti-alucinação. Ver base.py (contrato) e ingest.py.
#
# Fontes implementadas (contrato confirmado — referências nos módulos):
#   • lexml — LexML Brasil/Senado, serviço SRU (legislação + jurisprudência).
#   • stj   — STJ Dados Abertos (CKAN), espelhos de acórdãos com ementa.
#   • tjmg  — Busca pública de acórdãos do TJMG (formulário HTML; parser
#             tolerante fail-safe — sem API oficial de dados abertos).
#   • tcu   — TCU Dados Abertos, acórdãos com título/sumário e URL oficial.
#
# DataJud/CNJ permanece fora deste pacote porque entrega capa/movimentos, não
# ementa. A taxonomia TPU/SGT é consumida no gateway de integrações para
# normalização processual, não como jurisprudência.
from __future__ import annotations

import os

from app.services.juris_import import lexml, stj, tcu, tjmg

_TRUE = frozenset({"1", "true", "yes", "on", "sim"})


def _env_true(nome: str) -> bool:
    """Feature flag externa: ausente/valor desconhecido = OFF."""
    return os.getenv(nome, "").strip().casefold() in _TRUE


def _configurar_fontes_ativas(raw: str, *, tcu_enabled: bool) -> set[str]:
    """Combina o CSV legado com flags novas sem exigir edição do valor antigo.

    Produção preserva `.env` entre deploys. Portanto um ambiente que já tenha
    `JURIS_IMPORT_FONTES=lexml,stj` passa a habilitar TCU ao ligar apenas
    `TCU_OPEN_DATA_ENABLED=true`; não é necessário reescrever o CSV legado.
    Inversamente, a presença de `tcu` no CSV não contorna a feature flag: OFF
    remove a fonte e garante rollback imediato conforme CLAUDE.md/ADR.
    """
    fontes = {f.strip().lower() for f in (raw or "").split(",") if f.strip()}
    if tcu_enabled:
        fontes.add("tcu")
    else:
        fontes.discard("tcu")
    return fontes


# Config por env var DE PROPÓSITO: não toca core/config.py (arquivo estrutural
# sob governança reforçada). TCU é integração NOVA e nasce opt-in/default OFF.
_FONTES_ATIVAS = _configurar_fontes_ativas(
    os.getenv("JURIS_IMPORT_FONTES", "lexml,stj"),
    tcu_enabled=_env_true("TCU_OPEN_DATA_ENABLED"),
)

FONTES: dict[str, dict] = {
    "lexml": {
        "slug": "lexml",
        "nome": "LexML Brasil (SRU)",
        "descricao": "Rede de Informação Legislativa e Jurídica — Senado Federal. "
                     "Jurisprudência com URN persistente (lexml.gov.br).",
        "tribunais": "STF, STJ, TST e demais órgãos indexados",
        "enabled": "lexml" in _FONTES_ATIVAS,
        "buscar": lexml.buscar,
    },
    "stj": {
        "slug": "stj",
        "nome": "STJ — Dados Abertos (espelhos de acórdãos)",
        "descricao": "Portal de Dados Abertos do STJ (CKAN): ementas, teses e "
                     "referências legislativas dos acórdãos por órgão julgador.",
        "tribunais": "STJ",
        "enabled": "stj" in _FONTES_ATIVAS,
        "buscar": stj.buscar,
    },
    "tjmg": {
        "slug": "tjmg",
        "nome": "TJMG — Busca de acórdãos (espelho)",
        "descricao": "Base pública de acórdãos de 2º grau do TJMG "
                     "(formulário oficial; parser tolerante fail-safe — o "
                     "TJMG não publica API de dados abertos). Dedup "
                     "compartilhado com o crawler agendado do TJMG.",
        "tribunais": "TJMG (acórdãos de 2º grau, incl. IRDR/IAC)",
        "enabled": "tjmg" in _FONTES_ATIVAS,
        "buscar": tjmg.buscar,
    },
    "tcu": {
        "slug": "tcu",
        "nome": "TCU — Dados Abertos (acórdãos)",
        "descricao": "Acórdãos do Tribunal de Contas da União via API oficial de "
                     "Dados Abertos; busca temática limitada e sem download "
                     "automático de PDFs.",
        "tribunais": "TCU",
        "enabled": "tcu" in _FONTES_ATIVAS,
        "buscar": tcu.buscar,
    },
}


def fontes_disponiveis() -> list[dict]:
    """Metadados públicos das fontes (sem o callable `buscar`)."""
    return [
        {k: v for k, v in f.items() if k != "buscar"}
        for f in FONTES.values()
    ]
