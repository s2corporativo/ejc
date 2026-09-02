"""Governança de cálculo e conferência de prazos — recorte da #717.

O serviço não decide ownership nem executa commit. Ele produz/atualiza a prova
técnica sem conteúdo processual ou PII, aplica as invariantes de dupla validação
aos prazos classificados como críticos e pode adicionar uma notificação à
MESMA transação do prazo.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.models.notification import Notification
from app.services import calendario_tribunal as calendario
from app.services.deadline_calculator import eh_feriado

ENGINE_VERSION = "deadline_calculator/2026-09-01.v1"


class PrazoAuditError(ValueError):
    """Erro de invariável de auditoria/conferência."""


class DuplaValidacaoError(PrazoAuditError):
    """O mesmo usuário tentou calcular e conferir prazo crítico."""


class ProvaIncompletaError(PrazoAuditError):
    """Faltam elementos mínimos para conferir prazo crítico."""


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
    """Materializa dias excepcionais observados para reprodução/conferência.

    O registro é factual: não contém partes, número de processo ou teor de
    intimação. Para CPP, finais de semana e feriados intermediários são apenas
    observados; o snapshot não afirma que foram excluídos da contagem.
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


def validar_marcos_prazo(
    *,
    data_publicacao: date | None,
    termo_inicial: date | None,
    termo_final: date,
) -> None:
    if data_publicacao and termo_inicial and termo_inicial < data_publicacao:
        raise ProvaIncompletaError(
            "termo_inicial não pode ser anterior à data_publicacao"
        )
    if termo_inicial and termo_final < termo_inicial:
        raise ProvaIncompletaError(
            "data_prazo não pode ser anterior ao termo_inicial"
        )


def construir_prova_calculo(
    *,
    actor_id: str,
    data_ciencia: date | None,
    data_publicacao: date | None,
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
    """Cria snapshot suficiente para reexecutar ou identificar lacunas.

    ``data_ciencia`` jamais é renomeada silenciosamente para termo inicial. Se o
    chamador ainda usa o campo legado como base do motor, isso aparece em
    ``data_base_calculo``; ``termo_inicial`` permanece nulo até ser conhecido.
    """
    validar_marcos_prazo(
        data_publicacao=data_publicacao,
        termo_inicial=termo_inicial,
        termo_final=termo_final,
    )
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
    return {
        "versao_prova": 1,
        "engine_version": ENGINE_VERSION if resultado else None,
        "modo_origem": modo_origem,
        "data_ciencia": _iso(data_ciencia),
        "data_publicacao": _iso(data_publicacao),
        "termo_inicial": _iso(termo_inicial),
        "data_base_calculo": _iso(inicio),
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
        "estado_validacao": "aguardando_conferencia",
    }


def _atualizar_snapshot_material(
    metadata: dict[str, Any],
    depois: dict[str, Any],
    actor_id: str,
) -> None:
    mapa = {
        "data_publicacao": "data_publicacao",
        "termo_inicial": "termo_inicial",
        "data_prazo": "termo_final",
        "regime_calculo": "regime_calculo",
        "base_legal": "regra_juridica",
    }
    for origem, destino in mapa.items():
        if origem in depois:
            metadata[destino] = _iso(depois[origem])
    metadata["calculado_por"] = actor_id
    metadata["calculado_em"] = datetime.now(timezone.utc).isoformat()


def invalidar_conferencia(
    prazo: Any,
    *,
    actor_id: str,
    motivo: str,
    antes: dict[str, Any],
    depois: dict[str, Any],
) -> bool:
    """Invalida conferência e preserva histórico da mudança material."""
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
    _atualizar_snapshot_material(metadata, depois, actor_id)
    prazo.calculo_metadata = metadata
    prazo.calculado_por = actor_id
    prazo.conferido_por = None
    prazo.conferido_em = None
    prazo.confirmado = False
    return havia_conferencia


def validar_prova_para_conferencia(prazo: Any) -> None:
    if not prazo_critico(prazo):
        return
    metadata = getattr(prazo, "calculo_metadata", None) or {}
    if not metadata or not metadata.get("termo_final"):
        raise ProvaIncompletaError(
            "Prazo crítico sem snapshot reproduzível: revise os marcos antes de conferir."
        )
    tipo = _valor(getattr(prazo, "tipo", None))
    if tipo == "processual":
        if not getattr(prazo, "regime_calculo", None):
            raise ProvaIncompletaError(
                "Prazo processual crítico exige regime_calculo antes da conferência."
            )
        if not getattr(prazo, "termo_inicial", None):
            raise ProvaIncompletaError(
                "Prazo processual crítico exige termo_inicial antes da conferência."
            )


def validar_conferente(prazo: Any, actor_id: str) -> None:
    """Aplica usuários distintos somente a prazo de prioridade crítica."""
    if not prazo_critico(prazo):
        return
    calculista = getattr(prazo, "calculado_por", None)
    if not calculista:
        raise ProvaIncompletaError(
            "Prazo crítico legado sem calculista identificado: revise/recalcule antes da conferência."
        )
    if calculista == actor_id:
        raise DuplaValidacaoError(
            "Prazo crítico exige dupla validação: o conferente deve ser diferente do calculista."
        )


def registrar_conferencia(prazo: Any, actor_id: str) -> None:
    validar_prova_para_conferencia(prazo)
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
) -> tuple[bool, str]:
    """Prazo crítico sempre nasce pendente de um segundo usuário."""
    if prazo_critico(prioridade):
        return False, actor_id
    return confirmado_motor, actor_id


def adicionar_notificacao_reconferencia(db: Any, user_id: str | None) -> None:
    """Adiciona aviso interno sem commit antecipado e sem PII/caso no texto."""
    if not user_id:
        return
    db.add(
        Notification(
            id=str(uuid4()),
            user_id=user_id,
            titulo="Prazo requer nova conferência",
            mensagem=(
                "Um prazo sob sua responsabilidade teve alteração material e "
                "a conferência anterior foi reaberta. Revise-o na Central de Atividades."
            ),
            tipo="prazo",
            link="/atividades",
        )
    )
