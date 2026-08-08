# ── app/services/conhecimento_ingest/ ────────────────────────────────────────
# Bloco 3 — Ingestão contínua de conhecimento (fontes oficiais → RAG).
#
# Fontes deste pacote:
#   • anpd        — regulamentações + guias orientativos da ANPD (LGPD),
#                   raspagem leve das páginas gov.br (teto 30 docs/execução).
#   • normas_rfb  — atos tributários (IN/ADI/Soluções de Consulta) via
#                   querystring do sijut2consulta (teto 20 docs/execução).
#
# DECISÃO — STJ CKAN (Entrega 3 do Bloco 3): fonte NÃO adicionada aqui, de
# propósito. O portal CKAN do STJ (dadosabertos.web.stj.jus.br, 20 datasets)
# já é consumido pelo ingestor agendado `services/ingestors/stj.py` (job
# semanal sáb 03h, id="ing_stj"), que baixa o lote mensal mais recente dos 10
# datasets "espelhos de acórdãos" (Corte Especial + 3 Seções + 6 Turmas) —
# ementa + tese jurídica + referências legislativas, ou seja, exatamente o
# conteúdo citável de decisões. Os demais datasets do catálogo são
# estatísticos/administrativos (processos distribuídos, sessões etc.) e não
# oferecem inteiro teor estruturado melhor que os espelhos. Um stj_ckan.py
# aqui duplicaria a mesma fonte com outro keyspace de dedup ("stj:<registro>"
# já é compartilhado entre o job e o importador on-demand juris_import/stj.py).
#
# Orquestração: executar_ingest_conhecimento() roda cada fonte com sessão
# própria e try/except POR FONTE (uma fonte quebrada nunca derruba as outras),
# registra métricas em fontes_ingestao (registrar_fonte/marcar_execucao — o
# mesmo painel dos demais ingestores) e devolve o resumo
# {fonte: {novos, atualizados, inalterados, erros, status}}.
#
# Estado/dedup: a própria chave_origem do upsert_documento (idempotente e
# versionado — migration 068) resolve; reexecução não duplica nada.
#
# ROADMAP — fontes ainda ausentes (auditoria RAG, item "conectores"): STF,
# TST (jurisprudência — súmulas já cobertas em sumulas_ingestion.py), TCU,
# CARF. Não implementadas nesta rodada porque exigem raspagem de páginas de
# busca (não APIs estáveis como STJ CKAN/Câmara/Senado) que não puderam ser
# verificadas ponta a ponta contra o site real nesta sessão — implementar
# sem essa verificação arriscaria produzir conector silenciosamente quebrado
# ou, pior, extrair conteúdo incorreto (exatamente a classe de erro que esta
# auditoria corrigiu nas súmulas). A expansão de cobertura feita nesta rodada
# foi no DataJud/CNJ (app/services/datajud_service.py — de 3 TJs/1 TRT para
# todos os 27 TJs e 24 TRTs), que é uma API documentada e já testada no
# projeto — mas o DataJud só devolve METADADOS de movimentação processual,
# não texto integral de acórdão/ementa, então não fecha o gap de ingestão de
# JURISPRUDÊNCIA de STF/TST/TCU/CARF apontado na auditoria. Próximo passo
# recomendado: verificar (com acesso de rede real) se cada tribunal tem API
# documentada equivalente à do STJ CKAN antes de escrever o scraper.
#
# Agendamento: job semanal DOMINGO 03h00 UTC (scheduler.job_ingestao_conhecimento),
# gate CONHECIMENTO_INGEST_ENABLED (default True — autorizado pelo dono).
# Disparo manual: POST /rag/ingest-fontes-oficiais (socio+, audit log,
# background).
from __future__ import annotations

import logging

from app.services.ingestion_service import marcar_execucao, registrar_fonte

logger = logging.getLogger("ejc.conhecimento_ingest")

# Slugs públicos (painel fontes_ingestao / resposta do endpoint manual)
FONTES_SLUGS = ["anpd", "normas_rfb"]


def _fontes() -> list[tuple]:
    """(slug, descricao, categoria_rag, coro ingerir(db)->dict). Import tardio
    para não pagar o custo dos módulos no boot (padrão dos jobs do repo)."""
    from app.services.conhecimento_ingest import anpd, normas_rfb
    return [
        ("anpd", "ANPD — regulamentações e guias orientativos (LGPD)",
         "legislacao", anpd.ingerir),
        ("normas_rfb", "Normas RFB — sijut2consulta (atos tributários)",
         "legislacao_tributaria", normas_rfb.ingerir),
    ]


def _sessao():
    """Fábrica de sessão isolada (monkeypatch-ável em teste)."""
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal()


async def executar_ingest_conhecimento() -> dict:
    """Executa todas as fontes de conhecimento, isolando falhas por fonte.

    Retorna {slug: {"novos", "atualizados", "inalterados", "erros", "status"
    [, "erro"]}}. NUNCA levanta — apto a rodar em scheduler/BackgroundTasks.

    Diagnóstico (mesmo contrato do wrapper ingestion_service.executar_ingestao):
    status "erro" NUNCA grava `ultimo_erro` vazio no painel — usa a amostra da
    última exceção que o ingestor engoliu ("ultimo_erro_amostra" no resumo) ou
    um texto que aponte para os logs. E "zero_brutos" (a origem não rendeu
    NENHUM link/ato — layout provavelmente mudou) não vira "sucesso": vira erro
    com mensagem explícita, que o painel de saúde (services/ingestao_saude.py)
    trata como crítico.
    """
    resumo_geral: dict[str, dict] = {}
    for slug, descricao, categoria, ingerir in _fontes():
        parcial = {"novos": 0, "atualizados": 0, "inalterados": 0, "erros": 0}
        erro: str | None = None
        try:
            async with _sessao() as db:
                await registrar_fonte(db, slug, descricao, categoria)
                await db.commit()
            async with _sessao() as db:
                parcial = await ingerir(db)
                await db.commit()
        except Exception as e:   # fonte quebrada não derruba as demais
            erro = f"{type(e).__name__}: {e}"[:300]
            parcial["erros"] = parcial.get("erros", 0) + 1
            logger.error("[conhecimento:%s] %s", slug, erro)

        efetivos = parcial.get("novos", 0) + parcial.get("atualizados", 0)
        total = efetivos + parcial.get("inalterados", 0)
        houve_erro = (bool(erro) or parcial.get("erros", 0) > 0
                      or bool(parcial.get("zero_brutos")))
        status = ("sucesso" if not houve_erro
                  else ("parcial" if total else "erro"))
        # Erros engolidos dentro do ingestor (contados em "erros"/"zero_brutos",
        # sem exceção propagada) chegavam aqui com erro=None e o painel exibia
        # "erro" sem mensagem — o estado `erro_sem_diagnostico`. A amostra que o
        # ingestor capturou preenche a lacuna; sem amostra, ao menos o caminho
        # de investigação fica registrado.
        if houve_erro and not erro:
            erro = parcial.get("ultimo_erro_amostra")
        if status == "erro" and not (erro or "").strip():
            erro = (
                f"{parcial.get('erros', 0)} falha(s) sem mensagem capturada; "
                f"investigue o ingestor '{slug}' pelos logs do container."
            )
        try:
            async with _sessao() as db:
                await marcar_execucao(db, slug, status=status,
                                      novos=efetivos, total=total, erro=erro)
                await db.commit()
        except Exception as e:
            logger.error("[conhecimento:%s] falha ao marcar execução: %s", slug, e)

        resumo_geral[slug] = {**parcial, "status": status,
                              **({"erro": erro} if erro else {})}
        logger.info("[conhecimento:%s] %s — %s", slug, status, parcial)
    return resumo_geral
