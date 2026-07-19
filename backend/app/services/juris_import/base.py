# ── app/services/juris_import/base.py ────────────────────────────────────────
# Contrato comum dos conectores de importação de jurisprudência (APIs oficiais).
#
# Cada módulo de fonte (lexml.py, stj.py, tjmg.py, ...) expõe:
#     async def buscar(consulta: str, tribunal: str | None = None,
#                      limite: int = 20, ano: int | None = None,
#                      ) -> list[JulgadoNormalizado]
# `ano` é filtro CLIENT-SIDE pela data do julgado (ver no_ano) — fontes que
# suportam janela de data server-side (ex.: TJMG) também a aplicam, mas o
# filtro client-side é sempre a garantia final.
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
    # Chave PRINCIPAL de gravação (knowledge_docs.chave_origem) quando o
    # conector compartilha keyspace com um ingestor agendado (ex.: STJ usa a
    # MESMA chave "stj:<numeroRegistro>" do job diário — assim o job de amanhã
    # não reimporta o que o advogado importou hoje). None = usa a canônica.
    chave_principal: str | None = None
    # Chaves extras de dedup — evita duplicar doc já ingerido por outro caminho.
    chaves_extras: list[str] = Field(default_factory=list)

    def numero_digitos(self) -> str:
        return re.sub(r"\D", "", self.numero or "")

    def chave_canonica(self) -> str:
        """Chave canônica por tribunal+número (julgado:<TRIB>:<dígitos>)."""
        num = self.numero_digitos() or re.sub(r"\s+", "", (self.numero or "").lower())
        return f"julgado:{(self.tribunal or '').upper()}:{num}"

    def chave_dedup(self) -> str:
        """Chave usada como knowledge_docs.chave_origem na gravação."""
        return self.chave_principal or self.chave_canonica()

    def chaves_dedup(self) -> list[str]:
        """Todas as chaves consultadas no dedup (principal + canônica + extras)."""
        return list(dict.fromkeys(
            [self.chave_dedup(), self.chave_canonica(), *self.chaves_extras]
        ))


def no_ano(data: str | None, ano: int | None) -> bool:
    """True se a data (ISO AAAA-MM-DD, ou qualquer string iniciada pelo ano)
    cair no `ano`. Regras: ano=None → sempre True (sem filtro); ano definido e
    data ausente/ilegível → False (sem data comprovada, o julgado NÃO entra em
    uma importação filtrada por ano — filtro client-side conservador)."""
    if ano is None:
        return True
    m = re.match(r"\s*(\d{4})", data or "")
    return bool(m) and int(m.group(1)) == ano


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
