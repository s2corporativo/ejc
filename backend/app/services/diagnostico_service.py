# ── app/services/diagnostico_service.py ──────────────────────────────────────
# Central Eletrônica de Diagnóstico — agrega a saúde de TODOS os subsistemas do
# EJC com diagnóstico acionável (status + detalhe + ação sugerida + latência).
#
# Cada subsistema é medido por um "probe" isolado, todos rodando em paralelo
# (asyncio.gather) com timeout curto e try/except individual: a falha de um
# probe NUNCA derruba o diagnóstico — vira um item status="erro" acionável.
#
# Contrato de cada subsistema:
#   {nome, status, detalhe, acao_sugerida, latencia_ms, [extras...]}
#   status ∈ {"ok", "alerta", "erro", "desligado"}
#
# Segurança: NÃO revela segredos (reusa integration_status, que só expõe flags
# de habilitação/presença de configuração). Somente leitura.
#
# Concorrência: os probes que tocam o banco abrem a PRÓPRIA sessão
# (AsyncSessionLocal) — um AsyncSession não suporta operações concorrentes, então
# compartilhar uma única sessão sob asyncio.gather corromperia o protocolo.
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select, text

from app.core.config import Settings, get_settings

logger = logging.getLogger("ejc.diagnostico")

# Prioridade para o "pior status" (desligado é neutro, não penaliza o geral).
_PESO_STATUS = {"erro": 3, "alerta": 2, "ok": 1, "desligado": 0}
_TIMEOUT_PROBE_S = 5.0


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ms(inicio: float) -> float:
    """Latência em milissegundos desde `inicio` (time.perf_counter())."""
    return round((time.perf_counter() - inicio) * 1000, 2)


def _sub(
    nome: str,
    status: str,
    detalhe: str,
    acao_sugerida: str,
    latencia_ms: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    item = {
        "nome": nome,
        "status": status,
        "detalhe": detalhe,
        "acao_sugerida": acao_sugerida,
        "latencia_ms": latencia_ms,
    }
    item.update(extra)
    return item


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


# ── Probe: Banco de dados ─────────────────────────────────────────────────────
async def _probe_banco(session) -> dict[str, Any]:
    inicio = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return _sub(
            "Banco de dados",
            "erro",
            "Conexão com o PostgreSQL falhou (SELECT 1 não respondeu).",
            "Verifique se o container `db` está no ar e se DATABASE_URL está correta.",
            _ms(inicio),
        )
    latencia = _ms(inicio)

    tem_vetor = False
    try:
        r = await session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname='vector'")
        )
        tem_vetor = r.scalar() is not None
    except Exception:
        tem_vetor = False

    conexoes: int | None = None
    try:
        r = await session.execute(text("SELECT count(*) FROM pg_stat_activity"))
        conexoes = int(r.scalar() or 0)
    except Exception:
        conexoes = None  # sem permissão em alguns ambientes — informativo

    if not tem_vetor:
        return _sub(
            "Banco de dados",
            "alerta",
            "Conexão OK, porém a extensão pgvector NÃO está instalada — busca "
            "vetorial/RAG fica indisponível.",
            "Rode `CREATE EXTENSION vector;` no banco (ou aplique a migration que a cria).",
            latencia,
            pgvector=False,
            conexoes_ativas=conexoes,
        )
    detalhe = "Conexão OK; pgvector presente."
    if conexoes is not None:
        detalhe += f" {conexoes} conexões ativas."
    return _sub(
        "Banco de dados",
        "ok",
        detalhe,
        "Nenhuma ação necessária.",
        latencia,
        pgvector=True,
        conexoes_ativas=conexoes,
    )


# ── Probe: Migrations Alembic ─────────────────────────────────────────────────
def _heads_esperadas() -> list[str]:
    """Heads declaradas no diretório de migrations (fonte da verdade do código)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return list(ScriptDirectory.from_config(cfg).get_heads())


async def _probe_migrations(session, heads: list[str] | None = None) -> dict[str, Any]:
    inicio = time.perf_counter()
    esperadas = list(heads) if heads is not None else _heads_esperadas()

    try:
        r = await session.execute(text("SELECT version_num FROM alembic_version"))
        atuais = [str(v) for v in r.scalars().all()]
    except Exception:
        return _sub(
            "Migrations (Alembic)",
            "alerta",
            "Tabela alembic_version ausente — o banco não tem controle de versão aplicado.",
            "Rode `alembic upgrade head` para inicializar o schema versionado.",
            _ms(inicio),
            heads_esperadas=esperadas,
            revisoes_aplicadas=[],
        )

    if set(atuais) == set(esperadas):
        return _sub(
            "Migrations (Alembic)",
            "ok",
            f"Schema na head esperada ({', '.join(esperadas) or '—'}).",
            "Nenhuma ação necessária.",
            _ms(inicio),
            heads_esperadas=esperadas,
            revisoes_aplicadas=atuais,
        )
    return _sub(
        "Migrations (Alembic)",
        "alerta",
        f"Divergência de schema — aplicadas {atuais or '[]'} ≠ esperadas {esperadas}. "
        "Há migrations pendentes ou o código está atrás do banco.",
        "Rode `alembic upgrade head` (ou revise migrations não aplicadas).",
        _ms(inicio),
        heads_esperadas=esperadas,
        revisoes_aplicadas=atuais,
    )


# ── Probe: IA / provedores ────────────────────────────────────────────────────
async def _probe_ia(settings: Settings) -> dict[str, Any]:
    inicio = time.perf_counter()
    if not settings.AI_ENABLED:
        return _sub(
            "IA / Provedores",
            "desligado",
            "Núcleo de IA desabilitado (AI_ENABLED=false).",
            "Defina AI_ENABLED=true para habilitar geração e RAG assistido.",
            _ms(inicio),
            provedores=[],
        )

    provedores: list[str] = []
    if settings.ANTHROPIC_ENABLED and settings.ANTHROPIC_API_KEY:
        provedores.append("anthropic")
    if settings.GROQ_API_KEY:
        provedores.append("groq")
    if settings.OLLAMA_ENABLED and settings.OLLAMA_BASE_URL:
        provedores.append("ollama")

    if not provedores:
        return _sub(
            "IA / Provedores",
            "alerta",
            "AI_ENABLED=true, mas NENHUM provedor está configurado — nenhuma "
            "chamada de IA pode ser atendida.",
            "Configure ao menos um provedor (Anthropic/Groq/Ollama) ou desative AI_ENABLED.",
            _ms(inicio),
            provedores=[],
        )
    return _sub(
        "IA / Provedores",
        "ok",
        f"{len(provedores)} provedor(es) configurado(s): {', '.join(provedores)}. "
        "(Verificação apenas de configuração — sem gasto de tokens.)",
        "Nenhuma ação necessária.",
        _ms(inicio),
        provedores=provedores,
    )


# ── Probe: Integrações externas ───────────────────────────────────────────────
def _item_integracao(
    chave: str, label: str, grupo: str, enabled: bool, configured: bool
) -> dict[str, Any]:
    if not enabled:
        return {
            "chave": chave, "label": label, "grupo": grupo, "status": "desligado",
            "detalhe": "Integração desligada por configuração.",
            "acao_sugerida": "",
        }
    if not configured:
        return {
            "chave": chave, "label": label, "grupo": grupo, "status": "alerta",
            "detalhe": "Ligada, porém sem credencial/configuração obrigatória.",
            "acao_sugerida": "Preencha a credencial exigida no ambiente ou desligue a flag.",
        }
    return {
        "chave": chave, "label": label, "grupo": grupo, "status": "ok",
        "detalhe": "Habilitada com configuração presente.",
        "acao_sugerida": "",
    }


async def _probe_integracoes(settings: Settings) -> dict[str, Any]:
    inicio = time.perf_counter()
    from app.services.integration_status import build_integration_status

    _map = {"ready": "ok", "attention": "alerta", "disabled": "desligado"}
    itens: list[dict[str, Any]] = []

    # Reusa o painel existente (não duplica); grupo "Inteligência" é coberto pelos
    # probes de IA e RAG, então fica de fora daqui.
    painel = build_integration_status(settings)
    for it in painel["items"]:
        if it.get("group") == "Inteligência":
            continue
        itens.append({
            "chave": it["key"], "label": it["label"], "grupo": it["group"],
            "status": _map.get(it["status"], "alerta"),
            "detalhe": it["detail"],
            "acao_sugerida": (
                "Preencha a credencial exigida no ambiente ou desligue a flag."
                if it["status"] == "attention" else ""
            ),
        })

    # Integrações não cobertas pelo painel (lidas só via flags — sem tocar nos
    # serviços): Infosimples, Google Drive (base de conhecimento) e índices BCB.
    itens.append(_item_integracao(
        "infosimples", "Infosimples (consultas pagas)", "Jurídico",
        settings.INFOSIMPLES_ENABLED, bool(settings.INFOSIMPLES_TOKEN),
    ))
    itens.append(_item_integracao(
        "google_drive", "Google Drive (base de conhecimento)", "Conhecimento",
        os.getenv("GOOGLE_DRIVE_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
        bool(os.getenv("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID", "").strip()),
    ))
    itens.append(_item_integracao(
        "indices_bcb", "Índices oficiais BCB", "Jurídico",
        settings.INDICES_BCB_ENABLED, True,  # API pública, sem credencial
    ))

    total = len(itens)
    n_ok = sum(i["status"] == "ok" for i in itens)
    n_alerta = sum(i["status"] == "alerta" for i in itens)
    n_desligado = sum(i["status"] == "desligado" for i in itens)

    if n_alerta:
        status, detalhe, acao = (
            "alerta",
            f"{n_alerta} integração(ões) ligada(s) sem credencial completa.",
            "Revise as integrações em alerta (credencial ausente).",
        )
    elif n_ok:
        status, detalhe, acao = (
            "ok",
            f"{n_ok} integração(ões) prontas; {n_desligado} desligada(s).",
            "Nenhuma ação necessária.",
        )
    else:
        status, detalhe, acao = (
            "desligado",
            "Todas as integrações externas estão desligadas.",
            "Ative e configure as integrações desejadas no ambiente.",
        )

    return _sub(
        "Integrações externas", status, detalhe, acao, _ms(inicio),
        itens=itens,
        resumo={"total": total, "ok": n_ok, "alerta": n_alerta, "desligado": n_desligado},
    )


# ── Probe: Embeddings / RAG ───────────────────────────────────────────────────
async def _probe_rag(
    settings: Settings, disponivel_fn: Callable[[], bool] | None = None
) -> dict[str, Any]:
    inicio = time.perf_counter()
    if not settings.EMBEDDINGS_ENABLED:
        return _sub(
            "Embeddings / RAG",
            "desligado",
            "Embeddings desabilitados (EMBEDDINGS_ENABLED=false) — busca cai para o "
            "fallback textual.",
            "Defina EMBEDDINGS_ENABLED=true para habilitar busca semântica.",
            _ms(inicio),
            provider=settings.EMBEDDINGS_PROVIDER,
            busca="fallback_textual",
        )

    from app.services import embedding_service

    disp_fn = disponivel_fn or embedding_service.disponivel
    if disp_fn():
        modo = "modelo local (fastembed)" if settings.EMBEDDINGS_PROVIDER == "local" \
            else "serviço http de embeddings"
        return _sub(
            "Embeddings / RAG",
            "ok",
            f"Busca semântica ativa via {modo}.",
            "Nenhuma ação necessária.",
            _ms(inicio),
            provider=settings.EMBEDDINGS_PROVIDER,
            busca="semantica",
        )
    return _sub(
        "Embeddings / RAG",
        "alerta",
        "EMBEDDINGS_ENABLED=true, mas o provedor não está disponível (ex.: fastembed "
        "ausente ou EMBEDDINGS_API_URL vazio) — busca em fallback textual.",
        "Instale o fastembed (provider local) ou configure EMBEDDINGS_API_URL (provider http).",
        _ms(inicio),
        provider=settings.EMBEDDINGS_PROVIDER,
        busca="fallback_textual",
    )


# ── Probe: Scheduler / jobs ───────────────────────────────────────────────────
async def _probe_scheduler(
    session, settings: Settings, scheduler: Any | None = None
) -> dict[str, Any]:
    inicio = time.perf_counter()
    if not settings.ENABLE_SCHEDULER:
        return _sub(
            "Scheduler / jobs",
            "desligado",
            "Scheduler desabilitado (ENABLE_SCHEDULER=false).",
            "Em produção com --workers 1, mantenha ENABLE_SCHEDULER=true.",
            _ms(inicio),
            rodando=False, jobs=[], fontes_com_erro=[],
        )

    if scheduler is None:
        from app.services.scheduler import get_scheduler
        scheduler = get_scheduler()
    rodando = bool(getattr(scheduler, "running", False))

    jobs: list[dict[str, Any]] = []
    try:
        for j in scheduler.get_jobs():
            jobs.append({
                "id": getattr(j, "id", None),
                "proxima_execucao": _iso(getattr(j, "next_run_time", None)),
            })
    except Exception:
        jobs = []

    # Última execução das fontes de ingestão (auditoria de jobs que rodam).
    fontes: list[dict[str, Any]] = []
    com_erro: list[str] = []
    try:
        from app.models.rag import FonteIngestao

        r = await session.execute(select(FonteIngestao))
        for f in r.scalars().all():
            fontes.append({
                "slug": f.slug,
                "ultima_execucao": _iso(f.ultima_execucao),
                "ultimo_status": f.ultimo_status,
                "registros_novos": f.registros_novos,
            })
            if (f.ultimo_status or "").lower() == "erro":
                com_erro.append(f.slug)
    except Exception:
        fontes = []

    if not rodando:
        return _sub(
            "Scheduler / jobs",
            "alerta",
            "ENABLE_SCHEDULER=true, mas o scheduler NÃO está rodando neste processo.",
            "Verifique o boot do backend (lifespan/start_scheduler) e os logs.",
            _ms(inicio),
            rodando=False, jobs=jobs, fontes=fontes, fontes_com_erro=com_erro,
        )
    if com_erro:
        return _sub(
            "Scheduler / jobs",
            "alerta",
            f"Scheduler ativo ({len(jobs)} jobs), mas {len(com_erro)} fonte(s) "
            f"falharam na última execução: {', '.join(com_erro)}.",
            "Investigue o último erro das fontes de ingestão sinalizadas.",
            _ms(inicio),
            rodando=True, jobs=jobs, fontes=fontes, fontes_com_erro=com_erro,
        )
    return _sub(
        "Scheduler / jobs",
        "ok",
        f"Scheduler ativo com {len(jobs)} jobs agendados; nenhuma fonte de "
        "ingestão com erro na última execução.",
        "Nenhuma ação necessária.",
        _ms(inicio),
        rodando=True, jobs=jobs, fontes=fontes, fontes_com_erro=com_erro,
    )


# ── Probe: Jobs monitorados (heartbeat) ───────────────────────────────────────
async def _probe_heartbeat_jobs(session, settings: Settings) -> dict[str, Any]:
    """Detecta parada SILENCIOSA dos jobs críticos do scheduler (achado nº 1 da
    auditoria): lê `scheduler_heartbeat` (última EXECUÇÃO real de cada job) e
    classifica cada job em ok / defasado / nunca_executou / erro conforme a
    cadência esperada — em vez de derivar saúde da última linha de DADOS."""
    inicio = time.perf_counter()
    from app.services import heartbeat_service as hb

    if not settings.ENABLE_SCHEDULER:
        return _sub(
            "Jobs monitorados (heartbeat)",
            "desligado",
            "Scheduler desabilitado (ENABLE_SCHEDULER=false) — nenhum heartbeat "
            "de job é esperado.",
            "Em produção com --workers 1, mantenha ENABLE_SCHEDULER=true.",
            _ms(inicio),
            jobs=[],
        )

    from app.models.scheduler_heartbeat import SchedulerHeartbeat

    heartbeats: dict[str, dict[str, Any]] = {}
    try:
        r = await session.execute(select(SchedulerHeartbeat))
        for h in r.scalars().all():
            heartbeats[h.job_name] = {
                "last_run_at": h.last_run_at,
                "last_status": h.last_status,
                "detail": h.detail,
            }
    except Exception:
        return _sub(
            "Jobs monitorados (heartbeat)",
            "alerta",
            "Tabela scheduler_heartbeat ausente — heartbeat dos jobs indisponível "
            "(migration pendente?).",
            "Rode `alembic upgrade head` para criar a tabela de heartbeat.",
            _ms(inicio),
            jobs=[],
        )

    # Cruzamento execução × RESULTADO (armadilha da auditoria: "captura DJEN
    # reporta ok há meses sem nunca ter capturado nada"): para jobs de captura
    # com fonte mapeada (hb.FONTE_POR_JOB), consulta a saúde da fonte em
    # fontes_ingestao — job em dia com fonte `nunca_produziu`/
    # `parou_de_produzir` vira "sem_resultado" (alerta), não "ok".
    # Best-effort: sem a tabela/linhas, avaliação por execução preservada.
    saudes_fontes = None
    try:
        from app.models.rag import FonteIngestao
        from app.services.ingestao_saude import avaliar_fontes

        rf = await session.execute(
            select(FonteIngestao).where(
                FonteIngestao.slug.in_(sorted(set(hb.FONTE_POR_JOB.values())))
            )
        )
        saudes_fontes = avaliar_fontes(rf.scalars().all())
    except Exception:
        saudes_fontes = None

    jobs = hb.avaliar_jobs(heartbeats, saudes_fontes=saudes_fontes)
    for j in jobs:
        j["last_run_at"] = _iso(j["last_run_at"])  # serializa datetime p/ JSON

    n_erro = sum(j["status"] == "erro" for j in jobs)
    n_defasado = sum(j["status"] == "defasado" for j in jobs)
    n_nunca = sum(j["status"] == "nunca_executou" for j in jobs)
    n_sem_resultado = sum(j["status"] == "sem_resultado" for j in jobs)
    problemas = [
        j["label"] for j in jobs
        if j["status"] in ("erro", "defasado", "nunca_executou", "sem_resultado")
    ]
    resumo = {
        "total": len(jobs),
        "ok": sum(j["status"] == "ok" for j in jobs),
        "defasado": n_defasado,
        "nunca_executou": n_nunca,
        "erro": n_erro,
        "sem_resultado": n_sem_resultado,
    }

    if n_erro:
        return _sub(
            "Jobs monitorados (heartbeat)",
            "erro",
            f"{n_erro} job(s) falharam na última execução: {', '.join(problemas)}.",
            "Investigue os logs do backend dos jobs sinalizados.",
            _ms(inicio),
            jobs=jobs, resumo=resumo,
        )
    if n_defasado or n_nunca:
        return _sub(
            "Jobs monitorados (heartbeat)",
            "alerta",
            f"{n_defasado} job(s) defasado(s) e {n_nunca} sem execução registrada "
            f"(possível parada silenciosa do scheduler): {', '.join(problemas)}.",
            "Confirme que o scheduler está de pé e que os jobs rodam "
            "(lifespan/start_scheduler e logs).",
            _ms(inicio),
            jobs=jobs, resumo=resumo,
        )
    if n_sem_resultado:
        motivos = "; ".join(
            f"{j['label']}: {j['motivo']}" for j in jobs
            if j["status"] == "sem_resultado" and j.get("motivo")
        )
        return _sub(
            "Jobs monitorados (heartbeat)",
            "alerta",
            f"{n_sem_resultado} job(s) executam em dia mas a fonte "
            f"correspondente não produz resultado — {motivos}",
            "Job que roda sem entregar não é saudável: verifique o ingestor da "
            "fonte sinalizada (GET /ia-governanca/fontes traz o veredito).",
            _ms(inicio),
            jobs=jobs, resumo=resumo,
        )
    return _sub(
        "Jobs monitorados (heartbeat)",
        "ok",
        f"Todos os {len(jobs)} jobs monitorados executaram dentro da cadência esperada.",
        "Nenhuma ação necessária.",
        _ms(inicio),
        jobs=jobs, resumo=resumo,
    )


# ── Probe: Backup offsite ─────────────────────────────────────────────────────
async def _probe_backup(settings: Settings) -> dict[str, Any]:
    """Sinaliza produção rodando SEM backup offsite (achado da auditoria): o
    backup cifrado é o único mitigante do ponto único de falha do banco. Só
    leitura de config — NÃO liga o backup."""
    inicio = time.perf_counter()
    producao = (settings.APP_ENV or "").strip().lower() == "production"
    habilitado = bool(settings.BACKUP_ENABLED)

    if producao and not habilitado:
        return _sub(
            "Backup offsite",
            "alerta",
            "Ambiente de PRODUÇÃO com BACKUP_ENABLED=false — o backup cifrado "
            "offsite (único mitigante do ponto único de falha do banco) está "
            "DESLIGADO.",
            "Defina BACKUP_ENABLED=true (e BACKUP_ENCRYPTION_KEY) para proteger "
            "os dados contra perda total.",
            _ms(inicio),
            app_env=settings.APP_ENV, backup_enabled=habilitado,
        )
    if habilitado:
        return _sub(
            "Backup offsite",
            "ok",
            "Backup cifrado offsite habilitado (BACKUP_ENABLED=true).",
            "Nenhuma ação necessária.",
            _ms(inicio),
            app_env=settings.APP_ENV, backup_enabled=True,
        )
    return _sub(
        "Backup offsite",
        "desligado",
        "Backup offsite desabilitado (BACKUP_ENABLED=false) fora de produção.",
        "Em produção, habilite BACKUP_ENABLED=true para proteção contra perda total.",
        _ms(inicio),
        app_env=settings.APP_ENV, backup_enabled=False,
    )


# ── Probe: Disco / uploads ────────────────────────────────────────────────────
def _path_existente(p: str) -> str:
    cand = Path(p)
    while not cand.exists() and cand != cand.parent:
        cand = cand.parent
    return str(cand)


def _rotulo_mount(p: str) -> str:
    """Rótulo do ponto de MONTAGEM do caminho — NUNCA o path absoluto do host.
    Expor o caminho absoluto (ex.: /srv/ejc/uploads) no diagnóstico vaza layout
    interno de disco. Sobe até o mount e devolve seu nome (ou '/')."""
    try:
        cand = Path(p).resolve()
        while not os.path.ismount(cand) and cand != cand.parent:
            cand = cand.parent
        return cand.name or "/"
    except Exception:
        return "uploads"


async def _probe_disco(
    settings: Settings,
    disk_usage_fn: Callable[[str], Any] | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    inicio = time.perf_counter()
    alvo = _path_existente(path or settings.UPLOAD_DIR)
    du = disk_usage_fn or shutil.disk_usage
    try:
        uso = du(alvo)
        total, _usado, livre = uso.total, uso.used, uso.free
    except Exception:
        return _sub(
            "Disco / uploads",
            "erro",
            f"Não foi possível ler o uso de disco do volume {_rotulo_mount(alvo)}.",
            "Verifique se o volume de uploads está montado e acessível.",
            _ms(inicio),
        )

    pct_livre = round((livre / total * 100), 1) if total else 0.0
    livre_gb = round(livre / (1024 ** 3), 2)
    total_gb = round(total / (1024 ** 3), 2)
    rotulo = _rotulo_mount(alvo)   # só o mount/rótulo — nunca o path absoluto
    extras = {
        "caminho": rotulo,
        "livre_gb": livre_gb,
        "total_gb": total_gb,
        "percentual_livre": pct_livre,
    }
    if pct_livre < 10:
        return _sub(
            "Disco / uploads",
            "alerta",
            f"Espaço livre baixo: {pct_livre}% ({livre_gb} GB de {total_gb} GB) no volume {rotulo}.",
            "Libere espaço, expanda o volume ou mova/rotacione uploads e backups antigos.",
            _ms(inicio),
            **extras,
        )
    return _sub(
        "Disco / uploads",
        "ok",
        f"Espaço livre saudável: {pct_livre}% ({livre_gb} GB de {total_gb} GB) no volume {rotulo}.",
        "Nenhuma ação necessária.",
        _ms(inicio),
        **extras,
    )


# ── Probe: Erros recentes ─────────────────────────────────────────────────────
async def _probe_erros(settings: Settings) -> dict[str, Any]:
    inicio = time.perf_counter()
    if settings.SENTRY_DSN:
        return _sub(
            "Erros recentes",
            "ok",
            "Rastreamento externo de erros ativo (Sentry configurado).",
            "Consulte o painel do Sentry para as falhas mais recentes.",
            _ms(inicio),
            coletor="sentry",
        )
    return _sub(
        "Erros recentes",
        "ok",
        "Sem coletor de erros persistido no banco (falhas ficam nos logs do container).",
        "Considere habilitar Sentry (SENTRY_DSN) para rastreamento de erros centralizado.",
        _ms(inicio),
        coletor=None,
    )


# ── Orquestração ──────────────────────────────────────────────────────────────
async def _rodar(nome: str, coro, timeout: float = _TIMEOUT_PROBE_S) -> dict[str, Any]:
    """Executa um probe com timeout curto; qualquer falha vira item 'erro'."""
    inicio = time.perf_counter()
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return _sub(
            nome, "erro",
            f"O probe excedeu o tempo limite ({timeout:.0f}s).",
            "Investigue lentidão ou travamento neste subsistema.",
            _ms(inicio),
        )
    except Exception as e:  # noqa: BLE001 — probe nunca pode derrubar o diagnóstico
        logger.warning("[diagnostico] probe %s falhou: %s", nome, e)
        return _sub(
            nome, "erro",
            f"Falha inesperada ao coletar o diagnóstico ({type(e).__name__}).",
            "Verifique os logs do backend para o stack trace.",
            _ms(inicio),
        )


async def _com_sessao(fn, *args):
    """Abre uma sessão dedicada (parallel-safe) e executa o probe."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        return await fn(s, *args)


def agregar(subsistemas: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    """Status geral (pior status, desligado é neutro) + contagens por status."""
    resumo = {"ok": 0, "alerta": 0, "erro": 0, "desligado": 0}
    for s in subsistemas:
        st = s.get("status", "ok")
        resumo[st] = resumo.get(st, 0) + 1
    if resumo["erro"]:
        geral = "erro"
    elif resumo["alerta"]:
        geral = "alerta"
    elif resumo["ok"]:
        geral = "ok"
    else:
        geral = "desligado"
    return geral, resumo


async def diagnostico_completo(db=None) -> dict[str, Any]:
    """Roda todos os probes em paralelo e agrega o estado de saúde do sistema.

    `db` é aceito por compatibilidade de assinatura, mas os probes que tocam o
    banco abrem a própria sessão (AsyncSession não é concurrency-safe sob gather).
    """
    settings = get_settings()

    tarefas = [
        _rodar("Banco de dados", _com_sessao(_probe_banco)),
        _rodar("Migrations (Alembic)", _com_sessao(_probe_migrations)),
        _rodar("IA / Provedores", _probe_ia(settings)),
        _rodar("Integrações externas", _probe_integracoes(settings)),
        _rodar("Embeddings / RAG", _probe_rag(settings)),
        _rodar("Scheduler / jobs", _com_sessao(_probe_scheduler, settings)),
        _rodar("Jobs monitorados (heartbeat)", _com_sessao(_probe_heartbeat_jobs, settings)),
        _rodar("Backup offsite", _probe_backup(settings)),
        _rodar("Disco / uploads", _probe_disco(settings)),
        _rodar("Erros recentes", _probe_erros(settings)),
    ]
    subsistemas = await asyncio.gather(*tarefas)
    geral, resumo = agregar(subsistemas)

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "status_geral": geral,
        "resumo": resumo,
        "subsistemas": subsistemas,
        "aviso": (
            "Diagnóstico somente-leitura. Verifica configuração e conectividade "
            "básica; não revela segredos nem executa chamadas pagas."
        ),
    }
