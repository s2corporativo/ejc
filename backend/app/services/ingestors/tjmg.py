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
# Sobrescrevível via TJMG_INGEST_TEMAS (.env, CSV). Cobre cível, consumidor,
# imobiliário, família, trabalhista, tributário, administrativo, penal,
# previdenciário, empresarial e ambiental — cada tema vira uma varredura da
# base de acórdãos (teto TJMG_INGEST_MAX_POR_TEMA por tema/execução).
TEMAS_PADRAO = [
    # Cível / responsabilidade / consumidor / bancário
    "dano moral",
    "responsabilidade civil",
    "negativação indevida cadastro de inadimplentes",
    "plano de saúde negativa de cobertura",
    "revisional contrato bancário juros",
    "direito do consumidor inversão do ônus",
    # Imobiliário / registral
    "rescisão contratual imobiliário",
    "usucapião",
    "despejo locação de imóvel",
    # Família / sucessões
    "guarda e alimentos",
    "divórcio partilha de bens",
    "união estável reconhecimento e dissolução",
    "inventário e partilha herança",
    # Trabalhista (câmaras cíveis — relação de trabalho residual)
    "relação de emprego vínculo empregatício",
    # Tributário / administrativo
    "execução fiscal prescrição",
    "certidão de dívida ativa nulidade",
    "improbidade administrativa",
    "servidor público reajuste vantagens",
    # Trânsito
    "acidente de trânsito indenização",
    # Penal
    "tráfico de drogas dosimetria da pena",
    "furto e roubo prescrição da pretensão punitiva",
    "violência doméstica Lei Maria da Penha",
    # Previdenciário / assistencial
    "benefício previdenciário aposentadoria",
    "auxílio-doença restabelecimento INSS",
    # Empresarial
    "recuperação judicial e falência",
    "duplicata título de crédito execução",
    # Ambiental
    "dano ambiental reparação",
    "auto de infração ambiental multa",
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
    # Contagem de itens BRUTOS recebidos, antes de qualquer filtro ou parsing.
    # Sem ela, "nada veio da origem" e "veio e o parser não reconheceu" produzem
    # exatamente o mesmo resultado — zero, sem erro. Esse é o defeito estrutural
    # do parser tolerante: ele nunca falha, então nunca avisa. Com o número
    # bruto no log, um zero passa a ser diagnosticável.
    brutos = 0

    for tema in temas:
        try:
            itens = await buscar_tjmg(
                tema, por_pagina=max_tema,
                data_inicial=data_ini, data_final=data_fim,
            )
        except Exception as e:   # rede/HTML — nunca derruba a execução inteira
            logger.warning("TJMG tema %r: %s: %s", tema, type(e).__name__, e)
            continue

        brutos += len(itens or [])
        n_tema = 0
        for it in itens:
            ementa = it.get("ementa") or ""
            if len(ementa) < 50:
                continue   # sem valor semântico
            chave = _chave(it, tema)
            if chave in vistas:
                continue
            vistas.add(chave)

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
                        "rag_status": "aprovado",
                        "tipo_fonte": "jurisprudencia_oficial",
                    },
                    confianca="alta",   # fonte oficial (portal do TJMG)
                )
                # Commit por item: as métricas (novos/total) só contam o que foi
                # de fato persistido, e um erro isolado dá rollback APENAS do
                # item falho (o volume — ~temas×MAX_POR_TEMA — é pequeno).
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.warning("TJMG upsert %r: %s: %s", chave, type(e).__name__, e)
                continue

            total += 1
            if res in ("novo", "atualizado"):
                novos += 1
                n_tema += 1

        logger.info("TJMG tema %r: %d novos / %d itens", tema, n_tema, len(itens))

    # A linha que torna um zero diagnosticável: brutos=0 é "a origem não
    # devolveu nada"; brutos>0 com total=0 é "veio e o parser descartou tudo" —
    # dois problemas diferentes, com investigações diferentes.
    logger.info(
        "TJMG execução: %d itens brutos recebidos → %d processados → %d novos",
        brutos, total, novos,
    )
    if brutos and not total:
        logger.warning(
            "TJMG: %d itens vieram da origem e NENHUM passou no parsing — "
            "provável mudança de layout na origem, não ausência de julgados.",
            brutos,
        )

    return novos, total
