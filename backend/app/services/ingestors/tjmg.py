# ── app/services/ingestors/tjmg.py ────────────────────────────────────────────
# Ingestor de jurisprudência do TJMG → RAG (crawler agendado por temas/datas).
#
# Por que crawler (≠ STJ): o TJMG NÃO tem API de dados abertos. A jurisprudência
# fica atrás de um formulário HTML (pesquisaPalavrasEspelhoAcordao.do). Este
# ingestor dirige aquela busca por uma lista curada de temas do escritório,
# dentro de uma janela de datas, e ingere as EMENTAS no RAG com dedup idempotente
# por `chave_origem = tjmg:<registro>`. Reaproveita o parser tolerante de
# `jurisprudencia_externa.buscar_tjmg` (regex, degrada para lista vazia).
#
# COBERTURA (honesta): a base de acórdãos do TJMG cobre julgados de 2º grau —
# acórdãos e, como CLASSES dessa base, precedentes qualificados (IRDR, IAC e
# demais incidentes). Decisões MONOCRÁTICAS e SENTENÇAS de 1º grau NÃO estão
# nesta base (ficam na Consulta Processual, um sistema distinto do TJMG) —
# conector dedicado fica como follow-up documentado. Súmulas do TJMG são um
# conjunto finito publicado à parte (follow-up). Não se inventa endpoint aqui:
# o que este ingestor coleta é exatamente o que a base de acórdãos retorna.
#
# GOVERNANÇA: jurisprudência é conteúdo PÚBLICO/global (categoria
# "jurisprudencia", client_id/case_id = NULL) — não passa pelo isolamento por
# cliente e não carrega PII de cliente. A busca e a geração controlada (citation
# gate, HITL) que consomem esta base já estão implementadas no EJC.
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ingestion_service import upsert_documento
from app.services.jurisprudencia_externa import buscar_tjmg

logger = logging.getLogger("ejc.ingestao.tjmg")

# Temas de busca padrão — áreas de atuação do escritório (Betim/MG).
# Sobrescrevível via TJMG_INGEST_TEMAS (.env, CSV).
TEMAS_PADRAO = [
    "dano moral",
    "responsabilidade civil",
    "plano de saúde negativa de cobertura",
    "revisional contrato bancário juros",
    "direito do consumidor inversão do ônus",
    "rescisão contratual imobiliário",
    "usucapião",
    "guarda e alimentos",
    "improbidade administrativa",
    "execução fiscal prescrição",
    "acidente de trânsito indenização",
    "relação de emprego vínculo empregatício",
]


def _temas(cfg) -> list[str]:
    csv = (getattr(cfg, "TJMG_INGEST_TEMAS", "") or "").strip()
    if csv:
        return [t.strip() for t in csv.split(",") if t.strip()]
    return TEMAS_PADRAO


def _janela(cfg) -> tuple[str, str]:
    """Retorna (data_inicial, data_final) em dd/mm/aaaa para o formulário do
    TJMG. Janela <= 0 → sem filtro de data (strings vazias)."""
    dias = int(getattr(cfg, "TJMG_INGEST_JANELA_DIAS", 0) or 0)
    if dias <= 0:
        return "", ""
    hoje = date.today()
    ini = hoje - timedelta(days=dias)
    return ini.strftime("%d/%m/%Y"), hoje.strftime("%d/%m/%Y")


def _chave(item: dict, tema: str) -> str:
    """Chave de dedup idempotente. Prefere o número do acórdão; sem ele, usa um
    hash estável da ementa (mesmo julgado não duplica entre execuções)."""
    reg = (item.get("numero_acordao") or "").strip()
    if reg:
        return f"tjmg:{reg}"
    base = (item.get("ementa") or "")[:500]
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"tjmg:ementa:{h}"


def _monta_conteudo(item: dict) -> str:
    """Concatena as partes juridicamente citáveis de um acórdão do TJMG
    (mesma estratégia do ingestor STJ: ementa + metadados, não inteiro teor)."""
    partes: list[str] = []
    if item.get("classe"):
        partes.append(f"Classe: {item['classe']}")
    if item.get("orgao_julgador"):
        partes.append(f"Órgão julgador: {item['orgao_julgador']}")
    if item.get("relator"):
        partes.append(f"Relator(a): {item['relator']}")
    if item.get("data_julgamento"):
        partes.append(f"Julgamento: {item['data_julgamento']}")
    if item.get("area_juridica"):
        partes.append(f"Área: {item['area_juridica']}")
    if item.get("ementa"):
        partes.append(f"\nEMENTA:\n{item['ementa']}")
    return "\n".join(partes)


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Varre o TJMG por temas curados (dentro da janela de datas) e ingere as
    ementas no RAG. Retorna (novos, total_processados) — assinatura exigida por
    `ingestion_service.executar_ingestao`.
    """
    cfg = get_settings()
    temas = _temas(cfg)
    data_ini, data_fim = _janela(cfg)
    max_tema = int(getattr(cfg, "TJMG_INGEST_MAX_POR_TEMA", 50) or 50)

    novos = total = 0
    vistas: set[str] = set()   # dedup intra-execução (mesmo julgado em 2 temas)

    for tema in temas:
        try:
            itens = await buscar_tjmg(
                tema, por_pagina=max_tema,
                data_inicial=data_ini, data_final=data_fim,
            )
        except Exception as e:   # rede/HTML — nunca derruba a execução inteira
            logger.warning("TJMG tema %r: %s: %s", tema, type(e).__name__, e)
            continue

        n_tema = 0
        for it in itens:
            ementa = it.get("ementa") or ""
            if len(ementa) < 50:
                continue   # sem valor semântico
            chave = _chave(it, tema)
            if chave in vistas:
                continue
            vistas.add(chave)

            total += 1
            try:
                res = await upsert_documento(
                    db,
                    titulo=(it.get("titulo") or "Acórdão TJMG")[:500],
                    categoria="jurisprudencia",
                    conteudo=_monta_conteudo(it),
                    chave_origem=chave,
                    fonte="TJMG — Jurisprudência (espelho de acórdão)",
                    tribunal="TJMG",
                    extra={
                        "orgao": it.get("orgao_julgador"),
                        "relator": it.get("relator"),
                        "classe": it.get("classe"),
                        "data_julgamento": it.get("data_julgamento"),
                        "area_juridica": it.get("area_juridica"),
                        "link": it.get("link_original"),
                        "tema_busca": tema,
                    },
                    confianca="alta",   # fonte oficial (portal do TJMG)
                )
            except Exception as e:
                await db.rollback()
                logger.warning("TJMG upsert %r: %s: %s", chave, type(e).__name__, e)
                continue

            if res in ("novo", "atualizado"):
                novos += 1
                n_tema += 1
            if total % 50 == 0:
                await db.commit()   # commit em lotes (não segura tudo em memória)

        await db.commit()
        logger.info("TJMG tema %r: %d novos / %d itens", tema, n_tema, len(itens))

    return novos, total
