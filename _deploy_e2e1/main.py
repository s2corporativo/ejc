# ── app/main.py ───────────────────────────────────────────────────────────────
# EJC v3.0 — Ecossistema Jurídico Clovis
# Ponto de entrada FastAPI.
#
# ⚠️ CORREÇÃO P0-1 do v2: AuthMiddleware AGORA É REGISTRADO.
#    No v2 o middleware existia mas nunca era adicionado ao app —
#    37 routers ficavam públicos. Aqui: app.add_middleware(AuthMiddleware).
#
# ⚠️ CORREÇÃO P0-3: scheduler só inicia se ENABLE_SCHEDULER=true
#    (Dockerfile usa --workers 1; nunca aumentar sem desligar o gate).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import check_db
from app.core.auth_middleware import AuthMiddleware
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Routers
from app.routers import (
    evolution_webhook,
    verse,
    auth, users, clients, cases, deadlines, documents,
    legal_docs, fees, environmental, ai, procuracoes,
    dashboard, notifications, audit, rag,
    utils, templates, portal, tasks, timesheet,
    intimacoes, trash, webhooks, calendar_feed, signatures,
    calculadoras, analytics, suspensoes, search, export, ramos,
    teses, prompts_juridicos, atendimentos, jurimetria,
    workflow, jurisprudencia_interna, data_room,
    contratos_societarios, centro_custos, diario_oficial, gestao_societaria,
    checklists, dossie_estrategico,
    case_partes, score_juridico, indice_risco,
    memoria_institucional, mensagens, noticias, movimentos, ia_extra, etiquetas,
)
from app.routers import peca_geracao
from app.routers import processes as processes_router
from app.routers import kanban as kanban_router
from app.routers import whatsapp as whatsapp_router
from app.routers import relatorio as relatorio_router
from app.routers import sala_de_guerra as sdg_router
from app.routers import relatorio_cliente as relcli_router
from app.routers import exito_rateio as exito_router
from app.routers import conversao_caso as conv_router
from app.routers import financeiro_consolidado as fincon_router
from app.routers import documento_ia as docia_router
from app.routers import honorarios_oab as honoab_router
from app.routers import dossie_cliente as dossiecli_router
from app.routers import produtividade as produt_router
from app.routers import jurimetria_extra as juriex_router
from app.routers import agenda_eventos as agenda_router
from app.routers import caso_areas as caso_areas_router
from app.routers import atividades as atividades_router
from app.routers import areas as areas_router
from app.routers import pix as pix_router
from app.routers import analise_bancaria as anbanc_router
from app.routers import extratos as extratos_router
from app.routers import ia_especializada as ia_esp_router
from app.routers import datajud as datajud_router
from app.routers import pending_items as pending_items_router
from app.routers import office_contracts as office_contracts_router
from app.routers import partner_withdrawals as partner_withdrawals_router
from app.routers import despesas as despesas_router
from app.routers import qualidade as qualidade_router
from app.routers import honorarios_calc as honcalc_router
from app.routers import conteudo as conteudo_router
from app.routers import ia_saude as ia_saude_router
from app.routers import wiki as wiki_router
from app.routers import compliance as compliance_router
from app.routers import assistente as assistente_router
from app.routers import ai_tools as ai_tools_router
# Ativa a arquitetura orientada a eventos (P1): importar registra os @on subscribers.
from app.services import event_subscribers as _event_subscribers  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ejc")
settings = get_settings()

# ── Sentry (desabilitado se SENTRY_DSN vazio) ─────────────────────────────────
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,       # 10% das transações para performance
        profiles_sample_rate=0.05,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,       # LGPD: sem PII nos eventos Sentry
    )
    logger.info("[EJC] Sentry inicializado")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_ok = await check_db()
    logger.info(f"[EJC] Banco de dados: {'OK' if db_ok else 'FALHA'}")
    # Carrega feriados municipais/estaduais da tabela `feriados` para o
    # calculador de prazos (caso contrário só os nacionais entram na conta).
    from app.services.deadline_calculator import carregar_feriados_db
    try:
        n_fer = await carregar_feriados_db()
    except Exception as e:
        logger.warning(f"[EJC] Feriados não carregados: {e}")
        n_fer = 0
    logger.info(f"[EJC] Feriados municipais/estaduais carregados: {n_fer}")
    from app.services.deadline_calculator import carregar_suspensoes_db
    try:
        n_susp = await carregar_suspensoes_db()
    except Exception as e:
        logger.warning(f"[EJC] Suspensões não carregadas: {e}")
        n_susp = 0
    logger.info(f"[EJC] Suspensões de tribunal carregadas: {n_susp} dia(s)")
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    logger.info(f"[EJC] v3.0 iniciado — ambiente: {settings.APP_ENV}")
    yield
    # Shutdown
    stop_scheduler()
    logger.info("[EJC] Encerrado.")


app = FastAPI(
    title="EJC — Ecossistema Jurídico Clovis",
    description="Sistema de gestão jurídica — De Paula Teixeira Advogados",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.APP_ENV != "production" else None,
)

# ── Rate limiting (slowapi) — por IP real (respeita X-Forwarded-For) ─────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middlewares (ordem importa: CORS por fora, Auth por dentro) ───────────────
app.add_middleware(AuthMiddleware)          # ← P0-1 CORRIGIDO: registrado!

# Compressão GZip (>500 bytes): reduz payload JSON em 70-85%. Fica entre
# CORS (externo) e Auth (interno) — não altera a lógica de autorização.
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,   # via .env — nunca "*" em prod
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Routers (todos sob /api) ──────────────────────────────────────────────────
API = "/api"
app.include_router(auth.router,          prefix=API)
app.include_router(users.router,         prefix=API)
app.include_router(clients.router,       prefix=API)
app.include_router(cases.router,         prefix=API)
app.include_router(deadlines.router,     prefix=API)
app.include_router(documents.router,     prefix=API)
app.include_router(legal_docs.router,    prefix=API)
app.include_router(fees.router,          prefix=API)
app.include_router(environmental.router, prefix=API)
app.include_router(ai.router,            prefix=API)
app.include_router(procuracoes.router,   prefix=API)
app.include_router(dashboard.router,     prefix=API)
app.include_router(notifications.router, prefix=API)
app.include_router(audit.router,         prefix=API)
app.include_router(rag.router,           prefix=API)
app.include_router(utils.router,         prefix=API)
app.include_router(templates.router,     prefix=API)
app.include_router(portal.router,        prefix=API)
app.include_router(tasks.router,         prefix=API)
app.include_router(timesheet.router,     prefix=API)
app.include_router(intimacoes.router,    prefix=API)
app.include_router(trash.router,         prefix=API)
app.include_router(webhooks.router,      prefix=API)
app.include_router(calendar_feed.router, prefix=API)
app.include_router(signatures.router,    prefix=API)
app.include_router(calculadoras.router,  prefix=API)
app.include_router(analytics.router,     prefix=API)
app.include_router(suspensoes.router,    prefix=API)
app.include_router(search.router,        prefix=API)
app.include_router(export.router,        prefix=API)
app.include_router(ramos.router,         prefix=API)
app.include_router(teses.router,            prefix=API)
app.include_router(prompts_juridicos.router, prefix=API)
app.include_router(atendimentos.router,     prefix=API)
app.include_router(jurimetria.router,           prefix=API)
app.include_router(jurisprudencia_interna.router, prefix=API)
app.include_router(data_room.router,            prefix=API)
app.include_router(contratos_societarios.router, prefix=API)
app.include_router(centro_custos.router,        prefix=API)
app.include_router(diario_oficial.router,       prefix=API)
app.include_router(gestao_societaria.router,    prefix=API)
app.include_router(checklists.router,           prefix=API)
app.include_router(dossie_estrategico.router,   prefix=API)
app.include_router(case_partes.router,         prefix=API)
app.include_router(score_juridico.router,      prefix=API)
app.include_router(indice_risco.router,        prefix=API)
app.include_router(memoria_institucional.router, prefix=API)
app.include_router(mensagens.router,           prefix=API)
app.include_router(noticias.router,            prefix=API)
app.include_router(qualidade_router.router,    prefix=API)
app.include_router(honcalc_router.router,      prefix=API)
app.include_router(conteudo_router.router,     prefix=API)
app.include_router(ia_saude_router.router,     prefix=API)
app.include_router(wiki_router.router,         prefix=API)
app.include_router(compliance_router.router,   prefix=API)
app.include_router(assistente_router.router,   prefix=API)
app.include_router(docia_router.router,        prefix=API)
app.include_router(honoab_router.router,       prefix=API)
app.include_router(movimentos.router,          prefix=API)
app.include_router(evolution_webhook.router, prefix=API)
app.include_router(verse.router,           prefix=API)
app.include_router(ia_extra.router,            prefix=API)
app.include_router(etiquetas.router,           prefix=API)
app.include_router(peca_geracao.router,        prefix=API)
app.include_router(processes_router.router,    prefix=API)
app.include_router(ai_tools_router.router,     prefix="/api/v1")
app.include_router(datajud_router.router)
app.include_router(kanban_router.router)
app.include_router(whatsapp_router.router)
app.include_router(relatorio_router.router, prefix="/api/v1")
app.include_router(sdg_router.router, prefix="/api")
app.include_router(relcli_router.router, prefix="/api")
app.include_router(exito_router.router, prefix="/api/v1")
app.include_router(conv_router.router, prefix="/api")
app.include_router(fincon_router.router, prefix="/api/v1")
app.include_router(dossiecli_router.router, prefix="/api")
app.include_router(produt_router.router, prefix="/api")
app.include_router(juriex_router.router, prefix="/api")
app.include_router(agenda_router.router, prefix="/api")
app.include_router(caso_areas_router.router, prefix="/api")
app.include_router(atividades_router.router, prefix="/api")
app.include_router(areas_router.router, prefix="/api")
app.include_router(pix_router.router, prefix="/api")
app.include_router(anbanc_router.router, prefix="/api")
app.include_router(extratos_router.router, prefix="/api")
app.include_router(ia_esp_router.router, prefix="/api")
app.include_router(pending_items_router.router)
app.include_router(office_contracts_router.router)
app.include_router(partner_withdrawals_router.router)
app.include_router(despesas_router.router)


# ── Health check (público — usado pelo Docker healthcheck) ────────────────────
@app.get("/api/health")
async def health():
    db_ok = await check_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "3.0.0",
        "database": db_ok,
    }


# ── Exception handler global (nunca vazar stack trace) ────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erro não tratado em {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno. A equipe foi notificada."},
    )
