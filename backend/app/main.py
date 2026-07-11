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
from app.core.log_sanitizer import safe_exception_log, sanitize_log_value
from app.core.database import check_db
from app.core.auth_middleware import AuthMiddleware
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Routers
from app.routers import agenda_eventos
from app.routers import ai
from app.routers import ai_core
from app.routers import anexos
from app.routers import ai_skills
from app.routers import ai_tools
from app.routers import analise_bancaria
from app.routers import analytics
from app.routers import andamentos
from app.routers import areas
from app.routers import atendimentos
from app.routers import atividades
from app.routers import audit
from app.routers import auth
from app.routers import backup_admin
from app.routers import bank_analysis
from app.routers import calculadoras
from app.routers import calendar_feed
from app.routers import case_partes
from app.routers import cases
from app.routers import caso_areas
from app.routers import centro_custos
from app.routers import cerebro
from app.routers import checklists
from app.routers import clients
from app.routers import compliance
from app.routers import consumidor_monitor
from app.routers import conteudo
from app.routers import contratos_societarios
from app.routers import conversao_caso
from app.routers import curadoria_renomada
from app.routers import dashboard
from app.routers import data_room
from app.routers import data_room_v4
from app.routers import datajud
from app.routers import deadlines
from app.routers import despesas
from app.routers import diario_oficial
from app.routers import diplomacia_v3
from app.routers import documento_ia
from app.routers import documents
from app.routers import dossie_cliente
from app.routers import dossie_estrategico
from app.routers import environmental
from app.routers import etiquetas
from app.routers import evolution_webhook
from app.routers import exito_rateio
from app.routers import export
from app.routers import extratos
from app.routers import fees
from app.routers import financeiro_consolidado
from app.routers import gestao_societaria
from app.routers import honorarios_calc
from app.routers import ia_adversarial
from app.routers import ia_citacoes
from app.routers import ia_defensiva
from app.routers import ia_especializada
from app.routers import ia_extra
from app.routers import ia_governanca
from app.routers import ia_saude
from app.routers import indice_risco
from app.routers import intelligence_v3
from app.routers import intimacoes
from app.routers import jurimetria
from app.routers import jurimetria_extra
from app.routers import juris_import
from app.routers import jurisprudencia_externa
from app.routers import honorarios_oab
from app.routers import intake
from app.routers import triagem_entrevista
from app.routers import jurisprudencia_interna
from app.routers import kanban
from app.routers import legal_docs
from app.routers import memoria_institucional
from app.routers import mensagens
from app.routers import module_help
from app.routers import movimentos
from app.routers import noticias
from app.routers import notifications
from app.routers import novos_modulos
from app.routers import observabilidade
from app.routers import office_contracts
from app.routers import partner_withdrawals
from app.routers import peca_geracao
from app.routers import peca_geracao_router
from app.routers import pending_items
from app.routers import pix
from app.routers import portal
from app.routers import processes
from app.routers import procuracoes
from app.routers import produtividade
from app.routers import prompts
from app.routers import prompts_juridicos
from app.routers import qualidade
from app.routers import rag
from app.routers import rag_public
from app.routers import api_keys as api_keys_router
from app.routers import regulatorio
from app.routers import ramos
from app.routers import previdenciario_beneficio
from app.routers import relatorio
from app.routers import relatorio_cliente
from app.routers import sala_de_guerra
from app.routers import sala_de_guerra_v3
from app.routers import lgpd_registros
from app.routers import score_juridico
from app.routers import search
from app.routers import signatures
from app.routers import sociedades_cliente
from app.routers import provas
from app.routers import jornada_caso
from app.routers import sumulas
from app.routers import suspensoes
from app.routers import system_modules
from app.routers import module_settings
from app.routers import tributario_fiscal
from app.routers import trabalhista_liquidacao
from app.routers import ambiental_estrategia
from app.routers import tasks
from app.routers import templates
from app.routers import teses
from app.routers import teses_v4
from app.routers import timesheet
from app.routers import trash
from app.routers import users
from app.routers import utils
from app.routers import validador_juridico
from app.routers import veredito_ia_router
from app.routers import verse
from app.routers import victory_vault_router
from app.routers import visual_law
from app.routers import webhooks
from app.routers import whatsapp
from app.routers import wiki
from app.routers import workflow


# Ativa a arquitetura orientada a eventos (P1): importar registra os @on subscribers.
from app.services import event_subscribers as _event_subscribers  # noqa: F401

settings = get_settings()

# Logging estruturado opcional (LOG_JSON): substitui o basicConfig antigo.
from app.core.logging_config import setup_logging
setup_logging(json_logs=settings.LOG_JSON, level=settings.LOG_LEVEL)
logger = logging.getLogger("ejc")

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
        logger.warning("[EJC] Feriados não carregados", extra=safe_exception_log(e))
        n_fer = 0
    logger.info(f"[EJC] Feriados municipais/estaduais carregados: {n_fer}")
    from app.services.deadline_calculator import carregar_suspensoes_db
    try:
        n_susp = await carregar_suspensoes_db()
    except Exception as e:
        logger.warning("[EJC] Suspensões não carregadas", extra=safe_exception_log(e))
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

# Item 1.1 — captura o IP real por requisição num ContextVar para que TODO
# evento de auditoria (não só LOGIN) grave o IP de origem. Puro-ASGI (roda na
# mesma task do endpoint → ContextVar propaga com segurança).
from app.core.request_context import ClientIPMiddleware
app.add_middleware(ClientIPMiddleware)

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
app.include_router(agenda_eventos.router, prefix=API)
app.include_router(ai.router, prefix=API)
app.include_router(ai_core.router, prefix=API)
app.include_router(anexos.router, prefix=API)
app.include_router(ai_skills.router, prefix=API)
app.include_router(ai_tools.router, prefix=API)
app.include_router(analise_bancaria.router, prefix=API)
app.include_router(analytics.router, prefix=API)
app.include_router(andamentos.router, prefix=API)
app.include_router(areas.router, prefix=API)
app.include_router(atendimentos.router, prefix=API)
app.include_router(atividades.router, prefix=API)
app.include_router(audit.router, prefix=API)
app.include_router(auth.router, prefix=API)
app.include_router(backup_admin.router, prefix=API)
app.include_router(bank_analysis.router, prefix=API)
app.include_router(calculadoras.router, prefix=API)
app.include_router(calendar_feed.router, prefix=API)
app.include_router(case_partes.router, prefix=API)
app.include_router(cases.router, prefix=API)
app.include_router(caso_areas.router, prefix=API)
app.include_router(centro_custos.router, prefix=API)
app.include_router(cerebro.router, prefix=API)
app.include_router(checklists.router, prefix=API)
app.include_router(clients.router, prefix=API)
app.include_router(compliance.router, prefix=API)
app.include_router(consumidor_monitor.router, prefix=API)
app.include_router(conteudo.router, prefix=API)
app.include_router(contratos_societarios.router, prefix=API)
app.include_router(conversao_caso.router, prefix=API)
app.include_router(curadoria_renomada.router, prefix=API)
app.include_router(dashboard.router, prefix=API)
app.include_router(data_room.router, prefix=API)
app.include_router(data_room_v4.router, prefix=API)
app.include_router(datajud.router, prefix=API)
app.include_router(deadlines.router, prefix=API)
app.include_router(despesas.router, prefix=API)
app.include_router(diario_oficial.router, prefix=API)
app.include_router(diplomacia_v3.router, prefix=API)
app.include_router(documento_ia.router, prefix=API)
app.include_router(documents.router, prefix=API)
app.include_router(dossie_cliente.router, prefix=API)
app.include_router(dossie_estrategico.router, prefix=API)
app.include_router(environmental.router, prefix=API)
app.include_router(etiquetas.router, prefix=API)
app.include_router(evolution_webhook.router, prefix=API)
app.include_router(exito_rateio.router, prefix=API)
app.include_router(export.router, prefix=API)
app.include_router(extratos.router, prefix=API)
app.include_router(fees.router, prefix=API)
app.include_router(financeiro_consolidado.router, prefix=API)
app.include_router(gestao_societaria.router, prefix=API)
app.include_router(honorarios_calc.router, prefix=API)
app.include_router(ia_adversarial.router, prefix=API)
app.include_router(ia_citacoes.router, prefix=API)
app.include_router(ia_defensiva.router, prefix=API)
app.include_router(ia_especializada.router, prefix=API)
app.include_router(ia_extra.router, prefix=API)  # Bloco 1 (Etapa 4): router antes não montado → 8 chamadas frontend em 404
app.include_router(ia_governanca.router, prefix=API)
app.include_router(ia_saude.router, prefix=API)
app.include_router(indice_risco.router, prefix=API)
app.include_router(intelligence_v3.router, prefix=API)
app.include_router(intimacoes.router, prefix=API)
app.include_router(jurimetria.router, prefix=API)
app.include_router(jurimetria_extra.router, prefix=API)  # A5: router antes órfão (404 silencioso)
app.include_router(juris_import.router, prefix=API)
app.include_router(jurisprudencia_externa.router, prefix=API)
app.include_router(jurisprudencia_interna.router, prefix=API)
app.include_router(kanban.router, prefix=API)
app.include_router(legal_docs.router, prefix=API)
app.include_router(memoria_institucional.router, prefix=API)
app.include_router(honorarios_oab.router, prefix=API)  # frontend: /api/honorarios-oab/estimar (EstimadorHonorarios)
app.include_router(intake.router, prefix=API)  # frontend: /api/intake/casos/{id}/analise-completa (IntakeAnalise)
app.include_router(triagem_entrevista.router, prefix=API)  # frontend: /api/triagem/entrevista (EntrevistaInteligente — Jornada etapa 2)
app.include_router(mensagens.router, prefix=API)
app.include_router(module_help.router, prefix=API)  # frontend: /api/module-help/* (HelpButton)
app.include_router(movimentos.router, prefix=API)
app.include_router(noticias.router, prefix=API)
app.include_router(notifications.router, prefix=API)
app.include_router(novos_modulos.router, prefix=API)
app.include_router(observabilidade.router, prefix=API)
app.include_router(office_contracts.router, prefix=API)
app.include_router(partner_withdrawals.router, prefix=API)
app.include_router(peca_geracao.router, prefix=API)
app.include_router(peca_geracao_router.router, prefix=API)
app.include_router(pending_items.router, prefix=API)
app.include_router(pix.router, prefix=API)
app.include_router(portal.router, prefix=API)
app.include_router(processes.router, prefix=API)
app.include_router(procuracoes.router, prefix=API)
app.include_router(produtividade.router, prefix=API)
app.include_router(prompts.router, prefix=API)
app.include_router(prompts_juridicos.router, prefix=API)
app.include_router(qualidade.router, prefix=API)
app.include_router(rag.router, prefix=API)
app.include_router(rag_public.router, prefix=API)      # API pública (X-API-Key)
app.include_router(api_keys_router.router, prefix=API) # admin de chaves (JWT admin)
app.include_router(regulatorio.router, prefix=API)
app.include_router(ramos.router, prefix=API)
app.include_router(previdenciario_beneficio.router, prefix=API)  # vertical Previdenciário — regras de transição EC 103/2019 + RMI
app.include_router(relatorio.router, prefix=API)
app.include_router(relatorio_cliente.router, prefix=API)
app.include_router(sala_de_guerra.router, prefix=API)
app.include_router(sala_de_guerra_v3.router, prefix=API)
app.include_router(score_juridico.router, prefix=API)
app.include_router(search.router, prefix=API)
app.include_router(signatures.router, prefix=API)
app.include_router(sociedades_cliente.router, prefix=API)  # gestão societária de CLIENTES (vertical Empresarial)
app.include_router(provas.router, prefix=API)  # Gestão de Provas por caso + Documento Único de Anexos (Visual Law)
app.include_router(jornada_caso.router, prefix=API)  # Jornada do Caso — estado determinístico das 9 etapas (sem IA)
app.include_router(lgpd_registros.router, prefix=API)  # vertical LGPD — ROPA (art. 37) por cliente + RIPD (art. 38)
app.include_router(sumulas.router, prefix=API)
app.include_router(suspensoes.router, prefix=API)
app.include_router(system_modules.router, prefix=API)  # Mapa de Módulos — governança modular
app.include_router(module_settings.router, prefix=API)  # Lifecycle auditável dos módulos
app.include_router(tributario_fiscal.router, prefix=API)  # vertical Tributário — XML fiscal + recuperação de créditos
app.include_router(trabalhista_liquidacao.router, prefix=API)  # vertical Trabalhista — liquidação de sentença (ADC 58 / Selic real BCB)
app.include_router(ambiental_estrategia.router, prefix=API)  # vertical Ambiental — simulador de estratégia do auto de infração
app.include_router(tasks.router, prefix=API)
app.include_router(templates.router, prefix=API)
app.include_router(teses.router, prefix=API)
app.include_router(teses_v4.router, prefix=API)
app.include_router(timesheet.router, prefix=API)
app.include_router(trash.router, prefix=API)
app.include_router(users.router, prefix=API)
app.include_router(utils.router, prefix=API)
app.include_router(validador_juridico.router, prefix=API)
app.include_router(veredito_ia_router.router, prefix=API)
app.include_router(verse.router, prefix=API)
app.include_router(victory_vault_router.router, prefix=API)
app.include_router(visual_law.router, prefix=API)
app.include_router(webhooks.router, prefix=API)
app.include_router(whatsapp.router, prefix=API)
app.include_router(wiki.router, prefix=API)
app.include_router(workflow.router, prefix=API)



# ── Health check (público — usado pelo Docker healthcheck) ────────────────────
@app.get("/api/health")
async def health():
    db_ok = await check_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "3.0.0",
        "database": db_ok,
    }


# ── Readiness (público — para monitores externos: UptimeRobot, etc.) ──────────
# Diferente do /api/health (liveness, sempre 200 se o processo respira e usado
# pelo Docker healthcheck): aqui o STATUS HTTP reflete a prontidão. DB fora do ar
# → 503, para o monitor externo efetivamente detectar a queda (200 "degraded"
# passava despercebido). Redis/embeddings são informativos (não derrubam o 200).
@app.get("/api/health/ready")
async def readiness():
    settings = get_settings()
    db_ok = await check_db()

    # Redis só é checado quando alguma feature depende dele; senão, "não usado".
    redis_ok = None
    if settings.CELERY_ENABLED or settings.RATE_LIMIT_REDIS_ENABLED:
        from app.tasks.dispatcher import _redis_alcancavel
        redis_ok = await _redis_alcancavel(settings.REDIS_URL)

    from app.services.embedding_service import disponivel as _emb_disponivel
    checks = {
        "database": db_ok,          # crítico
        "redis": redis_ok,          # informativo (None = não utilizado)
        "embeddings": _emb_disponivel(),  # informativo
    }
    pronto = db_ok                  # só o DB é bloqueante para "ready"
    return JSONResponse(
        status_code=200 if pronto else 503,
        content={"status": "ready" if pronto else "not_ready", "checks": checks},
    )


# ── Exception handler global (nunca vazar stack trace) ────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Erro não tratado em rota",
        extra={
            "path": sanitize_log_value(request.url.path, max_len=240),
            **safe_exception_log(exc),
        },
        # Em produção, não registrar stack trace em logs de container/agregador.
        # Em dev/staging, mantém stack para diagnóstico técnico.
        exc_info=settings.APP_ENV != "production",
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno. A equipe foi notificada."},
    )
