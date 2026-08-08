# ── app/tasks/raio_x_tasks.py ────────────────────────────────────────────────
# Análise assíncrona do Raio-X do Processo (Onda 1 da Refatoração Total).
#
# A extração (OCR) + interpretação por IA dos documentos preliminares roda
# AQUI, nunca dentro do ciclo request/response — o endpoint de upload chegava
# a 71–87s em produção com a IA inline. Estados observáveis pela UI via
# GET /raio-x/{id}:
#
#     fila → em_processamento → aguardando_conferencia | documentos_pendentes
#                             └→ erro (mensagem legível, string, em
#                                      relatorio["erro_processamento"])
#
# Despacho segue o padrão do dispatcher RAG (app/tasks/dispatcher.py):
# Celery quando CELERY_ENABLED=True E o Redis responde ao ping; caso contrário
# BackgroundTasks in-process — a infraestrutura ausente nunca quebra a request
# e o estado continua observável do mesmo jeito.
#
# Sessão de banco: mesmo padrão dos demais tasks (rag_tasks /
# processo_eletronico_tasks) — worker Celery é síncrono, cada task cria o
# próprio event loop com asyncio.run e uma AsyncSessionLocal própria, e
# descarta o pool do engine ao final (engine.dispose()).
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks
from fastapi.encoders import jsonable_encoder

from app.core.celery_app import celery_app

logger = logging.getLogger("ejc.tasks.raio_x")


def _mensagem_erro_segura(exc: BaseException) -> str:
    """Mensagem de erro apta a aparecer na UI sem vazar detalhe interno.

    `str(exc)` de exceção de infraestrutura carrega statement SQL com
    parâmetros, caminho absoluto do servidor ou URL de provedor (achado da
    auditoria de segurança desta branch). Só `ValueError` — levantado pelo
    próprio fluxo com texto controlado ("Falha na extração", erro do
    intake) — passa literal; o resto vira o nome da exceção, e o detalhe
    fica no `logger.exception` do chamador.
    """
    if isinstance(exc, ValueError):
        return str(exc)[:300]
    return f"Erro interno ({type(exc).__name__})"


async def _com_engine_limpo(coro):
    """Executa a corrotina e descarta o pool do engine no MESMO loop."""
    from app.core.database import engine
    try:
        return await coro
    finally:
        await engine.dispose()


async def _marcar_erro(analise_id: str, mensagem: str, session_factory=None) -> None:
    """Melhor esforço: marca a análise como `erro` com mensagem legível p/ UI."""
    from sqlalchemy import select

    from app.models.raio_x import RaioXAnalise

    if session_factory is None:
        from app.core.database import AsyncSessionLocal as session_factory
    try:
        async with session_factory() as db:
            analise = (
                await db.execute(select(RaioXAnalise).where(RaioXAnalise.id == analise_id))
            ).scalar_one_or_none()
            if analise is None:
                return
            analise.status = "erro"
            # `erro_processamento` é STRING legível — contrato com a UI
            # (RaioXProcesso.tsx faz String(relatorio.erro_processamento)).
            analise.relatorio = {
                **(analise.relatorio or {}),
                "erro_processamento": mensagem[:500],
                "erro_processamento_em": datetime.now(timezone.utc).isoformat(),
            }
            await db.commit()
    except Exception:  # noqa: BLE001 — melhor esforço, nunca propaga
        logger.exception("[raio-x] falha ao marcar erro na análise %s", analise_id)


async def _processar(
    analise_id: str,
    user_id: str,
    user_role: str,
    documento_ids: list[str] | None,
    reprocessar: bool,
    session_factory=None,
) -> str:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.core.config import get_settings
    from app.models.audit_log import criar_audit_log
    from app.models.raio_x import RaioXAnalise, RaioXDocumento
    from app.routers.raio_x import _aplicar_identificacao
    from app.services import documento_service
    from app.services.raio_x_service import consolidar_relatorio, preview_conversao

    if session_factory is None:
        from app.core.database import AsyncSessionLocal as session_factory

    settings = get_settings()
    async with session_factory() as db:
        analise = (
            await db.execute(
                select(RaioXAnalise)
                .options(selectinload(RaioXAnalise.documentos))
                .where(RaioXAnalise.id == analise_id, RaioXAnalise.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if analise is None:
            logger.warning("[raio-x] análise %s não encontrada para processamento", analise_id)
            return "nao_encontrada"
        if analise.status == "convertido_em_caso":
            logger.warning("[raio-x] análise %s congelada (convertida); processamento ignorado", analise_id)
            return "congelada"

        # Estado observável imediatamente pela UI (fila → em_processamento).
        analise.status = "em_processamento"
        await db.commit()

        pendentes = list(analise.documentos)
        if documento_ids is not None:
            alvo = set(documento_ids)
            pendentes = [doc for doc in pendentes if doc.id in alvo]

        erros: list[dict[str, str]] = []
        total_tokens = 0
        processados: list[str] = []
        for doc in pendentes:
            full = Path(settings.UPLOAD_DIR) / doc.filepath
            if not full.exists():
                erros.append({"arquivo": doc.nome_original, "erro": "Arquivo físico indisponível"})
                if not reprocessar:
                    await db.delete(doc)
                continue
            try:
                result = await documento_service.extrair_e_analisar(
                    str(full),
                    doc.mimetype,
                    db=db,
                    enriquecer_rag=True,
                    user_id=user_id,
                )
                if not result.get("ok"):
                    raise ValueError(result.get("erro") or "Falha na extração")
                result.pop("_texto_sanitizado", None)
                encoded = jsonable_encoder(result)
                intake = encoded.get("intake_result") or encoded
                tipo = intake.get("tipo_documento") if isinstance(intake, dict) else None
                tipo = tipo.get("valor") if isinstance(tipo, dict) else tipo
                doc.tipo_documento = str(tipo)[:100] if tipo else None
                doc.resultado_analise = encoded
                total_tokens += int(encoded.get("tokens_total") or encoded.get("tokens") or 0)
                processados.append(doc.id)
            except Exception as exc:  # noqa: BLE001 — erro por documento é isolado
                erros.append(
                    {"arquivo": doc.nome_original, "erro": _mensagem_erro_segura(exc)}
                )
                logger.exception(
                    "[raio-x] falha ao processar documento %s da análise %s",
                    doc.id,
                    analise.id,
                )
                if not reprocessar:
                    # Lote novo: mesma semântica do fluxo inline anterior —
                    # documento que falhou não permanece na análise.
                    try:
                        full.unlink(missing_ok=True)
                    except OSError:
                        pass
                    await db.delete(doc)
        await db.flush()

        current_docs = list(
            (
                await db.execute(
                    select(RaioXDocumento)
                    .where(RaioXDocumento.analise_id == analise.id)
                    .order_by(RaioXDocumento.created_at.asc())
                )
            ).scalars().all()
        )
        relatorio = consolidar_relatorio(current_docs)
        if erros:
            # Erros por documento ficam visíveis à UI no GET da análise.
            relatorio["erros_processamento"] = erros
        analise.relatorio = relatorio
        _aplicar_identificacao(analise)
        preview = await preview_conversao(db, analise)
        analise.alertas_conflito = preview.get("alertas_conflito") or []
        analise.status = "aguardando_conferencia" if current_docs else "documentos_pendentes"
        analise.custo_ia = {
            **(analise.custo_ia or {}),
            "tokens_ultimo_lote": total_tokens,
            "arquivos_ultimo_lote": len(processados),
            "documentos_totais": len(current_docs),
        }
        await criar_audit_log(
            db,
            user_id,
            user_role,
            "AI_USE",
            "raio_x_analises",
            analise.id,
            detalhes=(
                f"Análise assíncrona ({'reprocessamento' if reprocessar else 'lote novo'}): "
                f"{len(processados)} documento(s) analisado(s); {len(erros)} erro(s)"
            ),
            dados_depois={
                "documentos": processados,
                "erros": erros,
                "risco": analise.risco_nivel,
                "urgente": analise.prazo_urgente,
                "alertas_conflito": len(analise.alertas_conflito or []),
            },
        )
        await db.commit()
        return "ok"


async def processar_analise(
    analise_id: str,
    user_id: str,
    user_role: str,
    documento_ids: list[str] | None = None,
    reprocessar: bool = False,
    session_factory=None,
) -> str:
    """Processa a análise Raio-X fora do request (extração + IA + consolidação).

    Falha inesperada NUNCA propaga: a análise é marcada como `erro` com
    mensagem legível — o estado permanece observável pela UI em qualquer
    desfecho. `session_factory` existe para testes (default: AsyncSessionLocal).
    """
    try:
        return await _processar(
            analise_id, user_id, user_role, documento_ids, reprocessar, session_factory
        )
    except Exception as exc:  # noqa: BLE001 — desfecho vira estado observável
        logger.exception("[raio-x] processamento da análise %s falhou", analise_id)
        await _marcar_erro(
            analise_id,
            "Falha no processamento da análise — tente reprocessar. "
            f"Detalhes no log do servidor (referência: {analise_id}). "
            f"Motivo: {_mensagem_erro_segura(exc)}",
            session_factory,
        )
        return "erro"


@celery_app.task(name="app.tasks.raio_x_processar", bind=True, max_retries=0)
def processar_analise_task(
    self,
    analise_id: str,
    user_id: str,
    user_role: str,
    documento_ids: list[str] | None = None,
    reprocessar: bool = False,
) -> str:
    """Task Celery da análise Raio-X. Sem retry automático: `processar_analise`
    já converte falha em status `erro` (retry repetiria custo de IA); o usuário
    reprocessa pela UI quando quiser."""
    asyncio.run(
        _com_engine_limpo(
            processar_analise(analise_id, user_id, user_role, documento_ids, reprocessar)
        )
    )
    return analise_id


async def agendar_analise(
    analise_id: str,
    user_id: str,
    user_role: str,
    documento_ids: list[str] | None,
    reprocessar: bool,
    background_tasks: BackgroundTasks,
) -> str:
    """Agenda o processamento da análise. Retorna o mecanismo usado
    ("celery" | "background") — útil em testes/observabilidade.

    Mesmo contrato do dispatcher RAG: Celery só quando CELERY_ENABLED=True e o
    Redis responde; qualquer falha ao enfileirar cai para BackgroundTasks."""
    from app.core.config import get_settings
    from app.tasks.dispatcher import _redis_alcancavel

    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            processar_analise_task.delay(
                analise_id, user_id, user_role, documento_ids, reprocessar
            )
            return "celery"
        except Exception as e:  # noqa: BLE001 — fallback gracioso
            logger.warning(
                "[raio-x] enfileirar no Celery falhou (%s: %s) — caindo para "
                "BackgroundTasks", type(e).__name__, str(e)[:200],
            )
    background_tasks.add_task(
        processar_analise, analise_id, user_id, user_role, documento_ids, reprocessar
    )
    return "background"
