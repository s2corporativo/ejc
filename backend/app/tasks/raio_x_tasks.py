# ── app/tasks/raio_x_tasks.py ────────────────────────────────────────────────
# Análise assíncrona do Raio-X do Processo.
#
# Estados observáveis pela UI:
#     fila → em_processamento → aguardando_conferencia | documentos_pendentes
#                             └→ erro
#
# A máquina de estados é concorrente com ações humanas (arquivar/descartar/
# excluir/converter). O worker não mantém row lock durante OCR/IA — isso seria
# um lock longo e degradaria o banco. Em vez disso, ele valida o estado sob
# lock no início e novamente imediatamente antes do commit final. Se uma ação
# humana venceu no intervalo, todo o trabalho pendente da segunda transação é
# revertido e o estado humano prevalece.
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks
from fastapi.encoders import jsonable_encoder

from app.core.celery_app import celery_app

logger = logging.getLogger("ejc.tasks.raio_x")

_ESTADOS_PROCESSAVEIS = {"fila", "em_processamento"}


def _mensagem_erro_segura(exc: BaseException) -> str:
    """Mensagem apta a aparecer na UI sem vazar infraestrutura/PII.

    ValueError carrega a mensagem controlada do extrator/analisador
    (ex.: "OCR vazio (simulado)"), nunca SQL/caminho/URL — por isso o
    texto original é preservado. Exceções de infraestrutura caem no
    ramo genérico, que só revela o nome da classe para correlação.
    """
    if isinstance(exc, ValueError):
        msg = str(exc).strip()
        return msg if msg else "Falha na extração ou validação do documento"
    return f"Erro interno ({type(exc).__name__})"


async def _com_engine_limpo(coro):
    """Executa a corrotina e descarta o pool do engine no MESMO loop."""
    from app.core.database import engine

    try:
        return await coro
    finally:
        await engine.dispose()


async def _marcar_erro(analise_id: str, mensagem: str, session_factory=None) -> None:
    """Melhor esforço sem sobrescrever estado humano mais novo."""
    from sqlalchemy import select

    from app.models.raio_x import RaioXAnalise

    if session_factory is None:
        from app.core.database import AsyncSessionLocal as session_factory
    try:
        async with session_factory() as db:
            analise = (
                await db.execute(
                    select(RaioXAnalise)
                    .where(
                        RaioXAnalise.id == analise_id,
                        RaioXAnalise.deleted_at.is_(None),
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if (
                analise is None
                or analise.status not in _ESTADOS_PROCESSAVEIS
                or analise.convertido_case_id
            ):
                return
            analise.status = "erro"
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
        # Lock curto de admissão. Impede worker atrasado de ressuscitar análise
        # que foi arquivada/descartada/excluída antes de começar.
        analise = (
            await db.execute(
                select(RaioXAnalise)
                .options(selectinload(RaioXAnalise.documentos))
                .where(
                    RaioXAnalise.id == analise_id,
                    RaioXAnalise.deleted_at.is_(None),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if analise is None:
            logger.warning("[raio-x] análise %s não encontrada para processamento", analise_id)
            return "nao_encontrada"
        if analise.convertido_case_id or analise.status == "convertido_em_caso":
            logger.warning("[raio-x] análise %s congelada; processamento ignorado", analise_id)
            return "congelada"
        if analise.status not in _ESTADOS_PROCESSAVEIS:
            logger.info(
                "[raio-x] análise %s em estado %s; worker atrasado ignorado",
                analise_id,
                analise.status,
            )
            return "ignorada_por_estado"

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
                erros.append(
                    {
                        "arquivo": doc.nome_original,
                        "erro": "Arquivo físico indisponível",
                    }
                )
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
                tipo = (
                    intake.get("tipo_documento")
                    if isinstance(intake, dict)
                    else None
                )
                tipo = tipo.get("valor") if isinstance(tipo, dict) else tipo
                doc.tipo_documento = str(tipo)[:100] if tipo else None
                doc.resultado_analise = encoded
                total_tokens += int(
                    encoded.get("tokens_total") or encoded.get("tokens") or 0
                )
                processados.append(doc.id)
            except Exception as exc:  # noqa: BLE001 — erro por documento isolado
                erros.append(
                    {
                        "arquivo": doc.nome_original,
                        "erro": _mensagem_erro_segura(exc),
                    }
                )
                logger.exception(
                    "[raio-x] falha ao processar documento %s da análise %s",
                    doc.id,
                    analise.id,
                )
                if not reprocessar:
                    try:
                        full.unlink(missing_ok=True)
                    except OSError:
                        pass
                    await db.delete(doc)

        # Segundo gate de estado, sob lock. As alterações em documentos acima
        # ainda não foram commitadas. Se uma ação humana mudou o registro após
        # o primeiro commit, rollback desfaz esta fase e preserva o novo estado.
        analise_atual = (
            await db.execute(
                select(RaioXAnalise)
                .where(RaioXAnalise.id == analise_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if (
            analise_atual is None
            or analise_atual.deleted_at is not None
            or analise_atual.convertido_case_id
            or analise_atual.status != "em_processamento"
        ):
            await db.rollback()
            logger.info(
                "[raio-x] finalização da análise %s cancelada por estado concorrente",
                analise_id,
            )
            return "cancelada_por_estado"
        analise = analise_atual

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
            # Visível somente na superfície jurídica autorizada; AuditLog abaixo
            # recebe apenas contagem, não nomes de arquivos.
            relatorio["erros_processamento"] = erros
        analise.relatorio = relatorio
        _aplicar_identificacao(analise)
        preview = await preview_conversao(db, analise)
        analise.alertas_conflito = preview.get("alertas_conflito") or []
        analise.status = (
            "aguardando_conferencia" if current_docs else "documentos_pendentes"
        )
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
                "erros_total": len(erros),
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
    """Processa o Raio-X fora do request e converte falha em estado observável."""
    try:
        return await _processar(
            analise_id,
            user_id,
            user_role,
            documento_ids,
            reprocessar,
            session_factory,
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
    """Task Celery sem retry automático para não duplicar custo de IA."""
    asyncio.run(
        _com_engine_limpo(
            processar_analise(
                analise_id,
                user_id,
                user_role,
                documento_ids,
                reprocessar,
            )
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
    """Agenda Celery quando saudável; caso contrário usa BackgroundTasks."""
    from app.core.config import get_settings
    from app.tasks.dispatcher import _redis_alcancavel

    settings = get_settings()
    if settings.CELERY_ENABLED and await _redis_alcancavel(settings.REDIS_URL):
        try:
            processar_analise_task.delay(
                analise_id,
                user_id,
                user_role,
                documento_ids,
                reprocessar,
            )
            return "celery"
        except Exception as exc:  # noqa: BLE001 — fallback gracioso
            logger.warning(
                "[raio-x] enqueue Celery falhou; exception_type=%s; usando BackgroundTasks",
                type(exc).__name__,
            )
    background_tasks.add_task(
        processar_analise,
        analise_id,
        user_id,
        user_role,
        documento_ids,
        reprocessar,
    )
    return "background"
