# ── app/services/juris_import/base.py ────────────────────────────────────────
# Contrato comum dos conectores de importação de jurisprudência (APIs oficiais).
#
# Cada módulo de fonte (lexml.py, stj.py, ...) expõe:
#     async def buscar(consulta: str, tribunal: str | None = None,
#                      limite: int = 20) -> list[JulgadoNormalizado]
#
# Regras do pacote:
#   • Somente APIs/serviços PÚBLICOS e DOCUMENTADOS (sem scraping de HTML).
#   • httpx async com timeout/retry — reusa ingestion_service.fetch.
#   • Paginação LIMITADA (teto de páginas por busca) — nunca varre o acervo.
#   • LGPD: julgados são dados públicos oficiais; a importação é 100%
#     DETERMINÍSTICA (parse + normalização locais). NENHUM conteúdo é enviado
#     a provedores externos de IA — os embeddings do RAG são gerados pelo
#     modelo LOCAL (embedding_service, multilingual-e5).
from __future__ import annotations

import re

from pydantic import BaseModel, Field


class JulgadoNormalizado(BaseModel):
    """Julgado normalizado — formato único de saída de todos os conectores."""
    tribunal: str                      # sigla (STJ, STF, TJMG, ...)
    numero: str                        # nº do processo/acórdão como veio da fonte
    data: str | None = None            # ISO (AAAA-MM-DD) quando disponível
    ementa: str                        # texto citável (ementa/espelho)
    inteiro_teor: str | None = None    # raramente disponível via API
    url_fonte: str                     # URL oficial/persistente do registro
    orgao_julgador: str | None = None
    relator: str | None = None
    classe: str | None = None
    # Chaves extras de dedup (ex.: chave legada do ingestor agendado do STJ,
    # "stj:<registro>") — evita duplicar doc já ingerido por outro caminho.
    chaves_extras: list[str] = Field(default_factory=list)

    def numero_digitos(self) -> str:
        return re.sub(r"\D", "", self.numero or "")

    def chave_dedup(self) -> str:
        """Chave canônica de dedup por tribunal+número (knowledge_docs.chave_origem)."""
        num = self.numero_digitos() or re.sub(r"\s+", "", (self.numero or "").lower())
        return f"julgado:{(self.tribunal or '').upper()}:{num}"

    def chaves_dedup(self) -> list[str]:
        return [self.chave_dedup(), *self.chaves_extras]


def normalizar_termos(consulta: str) -> list[str]:
    """Termos de busca minúsculos e sem acento (comparação tolerante)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", (consulta or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 3]


def texto_normalizado(texto: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))
