# ── app/services/juris_import/ ───────────────────────────────────────────────
# Importação on-demand de jurisprudência REAL de fontes públicas OFICIAIS,
# alimentando (1) a base de conhecimento RAG e (2) a base de citações
# validadas do gate anti-alucinação. Ver base.py (contrato) e ingest.py.
#
# Fontes implementadas (contrato confirmado — referências nos módulos):
#   • lexml — LexML Brasil/Senado, serviço SRU (legislação + jurisprudência).
#   • stj   — STJ Dados Abertos (CKAN), espelhos de acórdãos com ementa.
#   • tjmg  — Busca pública de acórdãos do TJMG (formulário HTML; parser
#             tolerante fail-safe — sem API oficial de dados abertos). Mesmo
#             keyspace de dedup do crawler agendado (ingestors/tjmg.py).
#
# Candidatas avaliadas e NÃO implementadas nesta passada (sem contrato de
# ementa/inteiro teor confirmado): API Pública DataJud/CNJ retorna apenas
# CAPA e MOVIMENTOS (sem ementa) — já usada como VALIDADOR de nº CNJ pelo
# verificador_jurisprudencia; dados abertos STF/TST — sem endpoint estável
# de acórdãos confirmado nesta pesquisa.
from __future__ import annotations

import os

from app.services.juris_import import lexml, stj, tjmg

# Config por env var (os.getenv) DE PROPÓSITO: a migração destas chaves para
# core/config.Settings fica para depois — outro fluxo é dono de config.py e
# .env.example neste PR. CSV de fontes habilitadas; default: todas.
_FONTES_ATIVAS = {
    f.strip().lower()
    for f in os.getenv("JURIS_IMPORT_FONTES", "lexml,stj,tjmg").split(",")
    if f.strip()
}

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
}


def fontes_disponiveis() -> list[dict]:
    """Metadados públicos das fontes (sem o callable `buscar`)."""
    return [
        {k: v for k, v in f.items() if k != "buscar"}
        for f in FONTES.values()
    ]
