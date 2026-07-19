from __future__ import annotations

import functools
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import uuid4

from app.services.ai_cost import estimar_custo_brl

logger = logging.getLogger("ejc.ai.provider_metrics")
_INSTALADO = False
_DB_RETRY_AFTER = 0.0


@dataclass
class _TraceContext:
    request_id: str
    task_type: str
    attempt_number: int = 0
    providers_attempted: set[str] = field(default_factory=set)
    failures: list[str] = field(default_factory=list)


_TRACE: ContextVar[_TraceContext | None] = ContextVar(
    "ejc_ai_provider_trace", default=None
)


def normalizar_erro(exc: Exception) -> tuple[str, int | None, str]:
    """Retorna somente metadados seguros; nunca persiste a mensagem da exceção."""
    http_status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    error_type = type(exc).__name__[:100]
    if error_type == "_ProviderPulado":
        return "bloqueado_lgpd", http_status, "Bloqueio preventivo de PII (LGPD)"
    reason = error_type + (f" (HTTP {http_status})" if http_status else "")
    return "erro", http_status, reason


async def _persistir(**dados) -> None:
    """Grava telemetria em sessão isolada e fail-open.

    A indisponibilidade da tabela ou do banco nunca pode derrubar uma chamada de
    IA. Um pequeno circuit breaker evita repetir o mesmo erro em todos os requests
    durante deploys em que a migration ainda esteja sendo aplicada.
    """
    global _DB_RETRY_AFTER
    agora = time.monotonic()
    if agora < _DB_RETRY_AFTER:
        return
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.ai_provider_metric import AIProviderMetric

        async with AsyncSessionLocal() as db:
            db.add(AIProviderMetric(**dados))
            await db.commit()
    except Exception as exc:  # observabilidade nunca quebra o fluxo principal
        _DB_RETRY_AFTER = time.monotonic() + 60
        logger.warning(
            "Métrica de provedor não persistida (%s); nova tentativa em 60s",
            type(exc).__name__,
        )


def _novo_contexto(task_type: str) -> _TraceContext:
    return _TraceContext(
        request_id=str(uuid4()),
        task_type=(task_type or "nao_informado")[:80],
    )


def _contexto_para_tentativa(provider: str) -> _TraceContext:
    ctx = _TRACE.get()
    # Uma cadeia normal não repete provider. Se ele reapareceu, trata-se de nova
    # execução feita no mesmo asyncio Task após uma cadeia anterior sem sucesso.
    if ctx is None or provider in ctx.providers_attempted:
        ctx = _novo_contexto("tarefa_profissional")
        _TRACE.set(ctx)
    ctx.attempt_number += 1
    ctx.providers_attempted.add(provider)
    return ctx


def _instalar_instrumentacao(ai_gateway) -> None:
    if getattr(ai_gateway, "_ejc_provider_metrics_installed", False):
        return

    resolver_original = ai_gateway._resolver_cadeia

    @functools.wraps(resolver_original)
    def resolver_instrumentado(*args, **kwargs):
        task_type = str(args[0] if args else kwargs.get("task_type") or "nao_informado")
        _TRACE.set(_novo_contexto(task_type))
        return resolver_original(*args, **kwargs)

    chamar_original = ai_gateway._chamar_com_barreira

    @functools.wraps(chamar_original)
    async def chamar_instrumentado(
        provider,
        model,
        messages,
        modo_sanitizacao,
        entidades,
        temperature,
        max_tokens,
    ):
        ctx = _contexto_para_tentativa(str(provider))
        inicio = time.monotonic()
        try:
            resultado = await chamar_original(
                provider,
                model,
                messages,
                modo_sanitizacao,
                entidades,
                temperature,
                max_tokens,
            )
            usage = resultado[2] or {}
            modelo_real = str(usage.get("model") or model or "")[:160] or None
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            custo = float(
                estimar_custo_brl(
                    str(provider),
                    int(input_tokens or 0),
                    int(output_tokens or 0),
                    modelo_real or "",
                )
            )
            fallback = ctx.attempt_number > 1
            await _persistir(
                request_id=ctx.request_id,
                attempt_number=ctx.attempt_number,
                provider=str(provider)[:30],
                model=modelo_real,
                task_type=ctx.task_type[:80],
                status="sucesso",
                duration_ms=max(0, int((time.monotonic() - inicio) * 1000)),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_brl=custo,
                fallback_triggered=fallback,
                fallback_reason="; ".join(ctx.failures[-3:])[:2000] if fallback else None,
                error_type=None,
                http_status=None,
            )
            _TRACE.set(None)
            return resultado
        except Exception as exc:
            status, http_status, motivo = normalizar_erro(exc)
            ctx.failures.append(f"{provider}: {motivo}")
            await _persistir(
                request_id=ctx.request_id,
                attempt_number=ctx.attempt_number,
                provider=str(provider)[:30],
                model=str(model or "")[:160] or None,
                task_type=ctx.task_type[:80],
                status=status,
                duration_ms=max(0, int((time.monotonic() - inicio) * 1000)),
                input_tokens=None,
                output_tokens=None,
                estimated_cost_brl=0.0,
                # Uma falha é justamente o evento que aciona a tentativa seguinte;
                # o painel distingue isso de um sucesso obtido via fallback.
                fallback_triggered=True,
                fallback_reason=motivo[:2000],
                error_type=type(exc).__name__[:100],
                http_status=http_status,
            )
            raise

    # O caminho profissional não chama `_resolver_cadeia`; delimitamos sua
    # execução para atribuir o tipo jurídico correto e impedir que um contexto de
    # uma cadeia totalmente falha contamine a requisição seguinte no mesmo Task.
    tarefa_original = ai_gateway.executar_tarefa_ia

    @functools.wraps(tarefa_original)
    async def tarefa_instrumentada(*args, **kwargs):
        tarefa = args[0] if args else kwargs.get("tarefa")
        tarefa_label = str(getattr(tarefa, "value", tarefa) or "tarefa_profissional")
        token = _TRACE.set(_novo_contexto(tarefa_label))
        try:
            return await tarefa_original(*args, **kwargs)
        finally:
            _TRACE.reset(token)

    ai_gateway._resolver_cadeia = resolver_instrumentado
    ai_gateway._chamar_com_barreira = chamar_instrumentado
    ai_gateway.executar_tarefa_ia = tarefa_instrumentada
    ai_gateway._ejc_provider_metrics_installed = True
    logger.info("Telemetria técnica dos provedores conectada ao AI Gateway")


def _instalar_router() -> None:
    """Acopla o painel ao router de governança existente, sem novo menu paralelo."""
    from app.routers import ia_governanca, ia_provider_metrics

    existing = {
        (getattr(route, "path", None), tuple(sorted(getattr(route, "methods", []) or [])))
        for route in ia_governanca.router.routes
    }
    added = 0
    for route in ia_provider_metrics.router.routes:
        key = (
            getattr(route, "path", None),
            tuple(sorted(getattr(route, "methods", []) or [])),
        )
        if key not in existing:
            ia_governanca.router.routes.append(route)
            existing.add(key)
            added += 1
    logger.info("Painel de provedores registrado (%d rota(s))", added)


def instalar(ai_gateway=None) -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    if ai_gateway is None:
        from app.services import ai_gateway as gateway
    else:
        gateway = ai_gateway
    _instalar_instrumentacao(gateway)
    _instalar_router()
    _INSTALADO = True
