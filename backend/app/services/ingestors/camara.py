# ── app/services/ingestors/camara.py ─────────────────────────────────────────
# Monitor legislativo — Câmara dos Deputados (API REST v2, sem auth).
# Ingere a EMENTA de proposições recentes dos tipos mais relevantes, permitindo
# que a IA responda "há projetos tramitando sobre X?" e alimentando vigilância
# legislativa. Não é lei consolidada (essa vem do Planalto) — é acompanhamento.
#
# Incremental: filtra por data de apresentação nos últimos N dias. Dedup por id
# da proposição evita reingestão de itens já vistos.
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.ingestao.camara")

API = "https://dadosabertos.camara.leg.br/api/v2"

# Tipos de maior relevância jurídica (evita ruído de requerimentos internos).
TIPOS = ["PL", "PEC", "PLP", "MPV", "PDL"]

DIAS_JANELA = 30        # apresentadas nos últimos 30 dias
MAX_POR_TIPO = 100      # teto por tipo/execução


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere ementas de proposições recentes. Retorna (novos, total)."""
    novos = total = 0
    inicio = (date.today() - timedelta(days=DIAS_JANELA)).isoformat()

    for tipo in TIPOS:
        try:
            r = await fetch(
                f"{API}/proposicoes",
                params={
                    "siglaTipo": tipo,
                    "dataApresentacaoInicio": inicio,
                    "itens": MAX_POR_TIPO,
                    "ordem": "DESC",
                    "ordenarPor": "id",
                },
                timeout=30,
            )
            dados = r.json().get("dados", [])
            for p in dados:
                ementa = (p.get("ementa") or "").strip()
                if len(ementa) < 50:
                    continue
                pid = p.get("id")
                titulo = f"{p.get('siglaTipo')} {p.get('numero')}/{p.get('ano')}"
                conteudo = (
                    f"{titulo} (Câmara dos Deputados)\n"
                    "ATENÇÃO: proposição em tramitação — não é norma vigente.\n"
                    f"Apresentada em: {p.get('dataApresentacao','')[:10]}\n\n"
                    f"Ementa: {ementa}"
                )
                total += 1
                res = await upsert_documento(
                    db, titulo=titulo, categoria="proposicao_legislativa",
                    conteudo=conteudo, chave_origem=f"camara:{pid}",
                    fonte=p.get("uri") or f"{API}/proposicoes/{pid}",
                    extra={
                        "tipo": tipo,
                        "ano": p.get("ano"),
                        "numero": p.get("numero"),
                        "casa": "camara",
                        "rag_status": "aprovado",
                        "tipo_fonte": "proposicao_oficial",
                        "source_official": True,
                        "authority_level": "oficial_informativa",
                        "proposicao_nao_vigente": True,
                        "aviso_governanca": "Projeto em tramitação — não é norma vigente.",
                    },
                    # Fonte é oficial, mas o conteúdo é proposição em tramitação,
                    # não direito vigente; confiança jurídica não pode ser "alta".
                    confianca="media",
                )
                if res in ("novo", "atualizado"):
                    novos += 1
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"Câmara {tipo}: {type(e).__name__}: {e}")
    return novos, total
