"""Governança de cálculo e conferência de prazos — recorte da #717.

O serviço não decide ownership nem persiste sozinho. Ele produz/atualiza a
prova técnica sem conteúdo processual ou PII e aplica as invariantes de dupla
validação aos prazos classificados com prioridade ``critica``.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services import calendario_tribunal as calendario
from app.services.deadline_calculator import eh_feriado

ENGINE_VERSION = "deadline_calculator/2026-09-01.v1"


def _valor(value: Any) -> Any:
    return getattr(value, "value", value)


def _iso(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return _valor(value)


def prazo_critico(prazo_or_prioridade: Any) -> bool:
    prioridade = getattr(prazo_or_prioridade, "prioridade", prazo_or_prioridade)
    return _valor(prioridade) == "critica"


def _excecoes_calendario(
    inicio: date,
    fim: date,
    *,
    tribunal: str | None,
    regime: str | None,
) -> list[dict[str, Any]]:
    """Materializa os dias excepcionais usados para reprodução/conferência.

    O registro é deliberadamente factual: não contém partes, número de processo
    ou texto de intimação. Para CPP, fins de semana/feriados intermediários são
    identificados como observados, não automaticamente excluídos da contagem.
    """
    if fim < inicio:
        return []
    locais = calendario.datas_feriados_locais(tribunal) if tribunal else frozenset()
    suspensoes = (
        calendario.datas_suspensoes_tribunal(tribunal) if tribunal else frozenset()
    )
    itens: list[dict[str, Any]] = []
    atual = inicio + timedelta(days=1)
    limite = 4000
    while atual <= fim and len(itens) < limite:
        motivos: list[str] = []
        if atual.weekday() >= 5:
            motivos.append("fim_de_semana")
        if eh_feriado(atual, incluir_recesso=False):
            motivos.append("feriado_nacional_ou_cadastrado")
        if atual in locais:
            motivos.append("feriado_local_tribunal")
        if atual in suspensoes:
            motivos.append("suspensao_tribunal")
        if calendario.em_recesso_art220(atual):
            motivos.append("recesso_20_12_a_20_01")
        if motivos:
            itens.append(
                {
                    "data": atual.isoformat(),
                    "motivos": sorted(set(motivos)),
                    "regime": regime,
                }
            )
        atual += timedelta(days=1)
    return itens


def construir_prova_calculo(
    *,
    actor_id: str,
    data_ciencia: date | None,
    termo_inicial: date | None,
    termo_final: date,
    regime: str | None,
    tribunal: str | None,
    dias: int | None,
    dobro: bool,
    excecao_recesso_penal: bool,
    base_legal: str | None,
    resultado: dict[str, Any] | None,
    modo_origem: str,
) -> dict[str, Any]:
    """Cria snapshot suficiente para reexecutar e comparar o cálculo.

    ``resultado`` é a saída do motor canônico quando houve cálculo automático.
    Em prazo informado manualmente, os campos desconhecidos permanecem nulos e
    o snapshot registra isso explicitamente, sem inventar regra/calendário.
    """
    inicio = termo_inicial or data_ciencia
    excecoes = (
        _excecoes_calendario(
            inicio,
            termo_final,
            tribunal=tribunal,
            regime=regime,
        )
        if inicio
        else []
    )
    serial = json.dumps(excecoes, ensure_ascii=False, sort_keys=True).encode("utf-8")
    prova = {
        "versao_prova": 1,
        "engine_version": ENGINE_VERSION if resultado else None,
        "modo_origem": modo_origem,
        "data_ciencia": _iso(data_ciencia),
        "termo_inicial": _iso(termo_inicial or data_ciencia),
        "termo_final": termo_final.isoformat(),
        "regime_calculo": regime,
        "tribunal": tribunal,
        "dias": dias,
        "dobro": bool(dobro),
        "excecao_recesso_penal": bool(excecao_recesso_penal),
        "regra_juridica": base_legal,
        "calendario_status": (resultado or {}).get("calendario_status"),
        "resultado_preliminar": bool((resultado or {}).get("resultado_preliminar")),
        "revisao_obrigatoria_motor": bool((resultado or {}).get("revisao_obrigatoria")),
        "calendario_excecoes": excecoes,
        "calendario_fingerprint_sha256": hashlib.sha256(serial).hexdigest(),
        "calculado_por": actor_id,
        "calculado_em": datetime.now(timezone.utc).isoformat(),
        "historico_recalculo": [],
        "ultima_conferencia": None,
    }
    return prova


def invalidar_conferencia(
    prazo: Any,
    *,
    actor_id: str,
    motivo: str,
    antes: dict[str, Any],
    depois: dict[str, Any],
) -> bool:
    """Invalida conferência anterior e preserva histórico de recálculo.

    Retorna ``True`` quando havia estado de conferência a ser reaberto. A nova
    alteração passa a ter o ator atual como calculista, impedindo que ele mesmo
    faça a conferência subsequente quando o prazo é crítico.
    """
    metadata = deepcopy(getattr(prazo, "calculo_metadata", None) or {})
    historico = list(metadata.get("historico_recalculo") or [])
    havia_conferencia = bool(
        getattr(prazo, "confirmado", False)
        or getattr(prazo, "conferido_por", None)
        or metadata.get("ultima_conferencia")
    )
    historico.append(
        {
            "em": datetime.now(timezone.utc).isoformat(),
            "por": actor_id,
            "motivo": motivo,
            "antes": {k: _iso(v) for k, v in antes.items()},
            "depois": {k: _iso(v) for k, v in depois.items()},
            "conferencia_anterior": {
                "por": getattr(prazo, "conferido_por", None),
                "em": _iso(getattr(prazo, "conferido_em", None)),
            },
        }
    )
    metadata["historico_recalculo"] = historico
    metadata["ultima_conferencia"] = None
    metadata["estado_validacao"] = "aguardando_conferencia"
    prazo.calculo_metadata = metadata
    prazo.calculado_por = actor_id
    prazo.conferido_por = None
    prazo.conferido_em = None
    prazo.confirmado = False
    return havia_conferencia


def validar_conferente(prazo: Any, actor_id: str) -> None:
    """Aplica a regra de usuários distintos somente a prioridade crítica."""
    if not prazo_critico(prazo):
        return
    calculista = getattr(prazo, "calculado_por", None)
    if not calculista:
        raise ValueError(
            "Prazo crítico legado sem calculista identificado: revise/recalcule antes da conferência."
        )
    if calculista == actor_id:
        raise ValueError(
            "Prazo crítico exige dupla validação: o conferente deve ser diferente do calculista."
        )


def registrar_conferencia(prazo: Any, actor_id: str) -> None:
    validar_conferente(prazo, actor_id)
    agora = datetime.now(timezone.utc)
    prazo.confirmado = True
    prazo.conferido_por = actor_id
    prazo.conferido_em = agora
    metadata = deepcopy(getattr(prazo, "calculo_metadata", None) or {})
    metadata["ultima_conferencia"] = {
        "por": actor_id,
        "em": agora.isoformat(),
        "calculado_por": getattr(prazo, "calculado_por", None),
    }
    metadata["estado_validacao"] = "conferido"
    prazo.calculo_metadata = metadata


def preparar_estado_inicial(
    *,
    prioridade: Any,
    actor_id: str,
    confirmado_motor: bool,
) -> tuple[bool, str | None]:
    """Prazo crítico sempre nasce pendente de um segundo usuário."""
    if prazo_critico(prioridade):
        return False, actor_id
    return confirmado_motor, actor_id
