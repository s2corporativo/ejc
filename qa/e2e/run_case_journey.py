#!/usr/bin/env python3
"""Jornada jurídica fictícia ponta a ponta do EJC.

Complementa `run_fictitious_smoke.py` reutilizando integralmente login, criação
de cliente/caso/documento, RBAC, redação de PII, relatório e cleanup. Acrescenta
apenas as etapas que dependem de IDs reais criados na própria execução:

- prazo vinculado ao caso → releitura → ciência → cancelamento;
- leitura da Inteligência do Caso;
- DPT Empresarial 360 conforme o mesmo piso advogado+ do backend.

Nunca execute contra produção sem a proteção explícita já exigida pelo runner
canônico (`EJC_ALLOW_PRODUCTION_E2E=true`) e autorização operacional.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

import run_fictitious_smoke as core

DPT_ROLES = {"superadmin", "admin", "socio", "advogado"}


def _criar_e_validar_prazo(
    client: httpx.Client,
    state: core.SuiteState,
) -> str | None:
    if not state.case_id:
        core._afirmar(
            state,
            "jornada.prazo.precondicao",
            False,
            "caso fictício não foi criado/localizado",
        )
        return None

    vencimento = date.today() + timedelta(days=12)
    payload = {
        "titulo": f"{core.MARKER_RUN} Prazo processual fictício",
        "tipo": "processual",
        "prioridade": "media",
        "descricao": "Prazo sintético criado exclusivamente pela homologação EJC.",
        "data_prazo": vencimento.isoformat(),
        "base_legal": "DADO FICTÍCIO — sem fundamento jurídico operacional",
        "case_id": state.case_id,
    }
    resposta = core._request(
        client,
        state,
        name="jornada.prazo.criar",
        method="POST",
        path="/api/deadlines/",
        expected=[201],
        json_body=payload,
    )
    if resposta is None or resposta.status_code != 201:
        return None

    prazo = resposta.json()
    deadline_id = prazo.get("id")
    core._afirmar(
        state,
        "jornada.prazo.vinculo_caso",
        bool(deadline_id) and prazo.get("case_id") == state.case_id,
        f"deadline_id={deadline_id!r}, case_id={prazo.get('case_id')!r}",
    )

    releitura = core._request(
        client,
        state,
        name="jornada.prazo.reler_por_caso",
        method="GET",
        path=f"/api/deadlines/?case_id={state.case_id}&status=pendente",
        expected=[200],
    )
    if releitura is not None and releitura.status_code == 200 and deadline_id:
        itens = releitura.json().get("data") or []
        core._afirmar(
            state,
            "jornada.prazo.persistido",
            any(item.get("id") == deadline_id for item in itens),
            f"prazo {deadline_id} não apareceu na lista filtrada do caso",
        )

    if deadline_id:
        ciencia = core._request(
            client,
            state,
            name="jornada.prazo.ciencia",
            method="POST",
            path=f"/api/deadlines/{deadline_id}/ciencia",
            expected=[200],
        )
        core._afirmar(
            state,
            "jornada.prazo.ciencia_confirmada",
            ciencia is not None and ciencia.status_code == 200,
            "endpoint de ciência não confirmou o prazo fictício",
        )
    return str(deadline_id) if deadline_id else None


def _validar_inteligencia_do_caso(
    client: httpx.Client,
    state: core.SuiteState,
) -> None:
    if not state.case_id:
        return
    resposta = core._request(
        client,
        state,
        name="jornada.inteligencia.ler",
        method="GET",
        path=f"/api/cases/{state.case_id}/inteligencia",
        expected=[200],
    )
    if resposta is None or resposta.status_code != 200:
        return
    corpo = resposta.json()
    core._afirmar(
        state,
        "jornada.inteligencia.escopo_caso",
        corpo.get("case_id") == state.case_id,
        f"inteligência respondeu case_id={corpo.get('case_id')!r}",
    )
    core._afirmar(
        state,
        "jornada.inteligencia.contrato",
        isinstance(corpo.get("total"), int)
        and isinstance(corpo.get("historico"), list),
        "resposta não contém total inteiro + histórico em lista",
    )


def _validar_dpt360(client: httpx.Client, state: core.SuiteState) -> None:
    role = str(state.user.get("role") or "")
    esperado = [200] if role in DPT_ROLES else [403]
    resposta = core._request(
        client,
        state,
        name="jornada.dpt360.dashboard",
        method="GET",
        path="/api/dpt360/dashboard",
        expected=esperado,
        degradado_ok=False,
    )
    if role in DPT_ROLES and resposta is not None and resposta.status_code == 200:
        corpo = resposta.json()
        core._afirmar(
            state,
            "jornada.dpt360.contrato",
            isinstance(corpo, dict) and "metrics" in corpo,
            "dashboard DPT360 não devolveu o contrato esperado",
        )


def _cancelar_prazo(
    client: httpx.Client,
    state: core.SuiteState,
    deadline_id: str | None,
) -> None:
    if not deadline_id:
        return
    core._request(
        client,
        state,
        name="jornada.prazo.cleanup",
        method="DELETE",
        path=f"/api/deadlines/{deadline_id}",
        expected=[200, 404],
        degradado_ok=True,
    )


def main() -> None:
    base_url = core._env("EJC_BASE_URL").rstrip("/")
    if (
        os.getenv("EJC_ALLOW_PRODUCTION_E2E") != "true"
        and "staging" not in base_url
        and "homolog" not in base_url
        and "localhost" not in base_url
    ):
        raise SystemExit(
            "Proteção ativa: use staging/homologação/localhost ou defina "
            "EJC_ALLOW_PRODUCTION_E2E=true com autorização explícita."
        )

    matrix = core._load_matrix()
    state = core.SuiteState(base_url=base_url)
    deadline_id: str | None = None

    with httpx.Client(base_url=base_url, follow_redirects=True) as client:
        try:
            core._request(
                client,
                state,
                name="health.live",
                method="GET",
                path="/api/health",
                expected=[200],
            )
            core._login(client, state)
            core._negativas_de_autorizacao(client, state)
            core._matrix_smoke(client, state, matrix)
            core._create_client(client, state, matrix)
            core._create_case(client, state, matrix)
            core._upload_document(client, state, matrix)
            core._case_followups(client, state, matrix)
            core._document_followups(client, state)

            deadline_id = _criar_e_validar_prazo(client, state)
            _validar_inteligencia_do_caso(client, state)
            _validar_dpt360(client, state)
        finally:
            # Dependência FK: prazo primeiro; depois o cleanup canônico remove
            # documento, caso e cliente criados por esta execução.
            _cancelar_prazo(client, state, deadline_id)
            if os.getenv("EJC_E2E_CLEANUP", "true").strip().lower() != "false":
                core._cleanup(client, state)
            core._write_report(state, matrix)


if __name__ == "__main__":
    main()
