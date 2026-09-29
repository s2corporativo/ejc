#!/usr/bin/env python3
"""Jornada jurídica fictícia ponta a ponta do EJC.

Esta é a jornada funcional canônica do escritório. Ela reaproveita login,
dados fictícios, redação de PII, relatório e cleanup de
`run_fictitious_smoke.py`, mas cria o CASO pela mesma Entrada Única usada no
dashboard:

    Entrada Única (IA) -> confirmação humana -> caso canônico
      -> documento -> peça -> prazo -> tarefa -> financeiro

A análise da IA cria somente um rascunho. Os campos que viram registro oficial
são enviados explicitamente no passo de confirmação, reproduzindo o HITL real
do produto. Nenhuma inferência da IA é persistida automaticamente pelo teste.

Nunca execute contra produção sem a proteção explícita já exigida pelo runner
canônico (`EJC_ALLOW_PRODUCTION_E2E=true`) e autorização operacional.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

import run_fictitious_smoke as core

DPT_ROLES = {"superadmin", "admin", "socio", "advogado"}
FINANCEIRO_MUTACAO_ROLES = {"superadmin", "admin", "socio", "financeiro"}


def _criar_caso_via_entrada(
    client: httpx.Client,
    state: core.SuiteState,
    matrix: dict,
) -> None:
    """Prova IA -> rascunho -> confirmação HITL -> Case no mesmo fluxo da UI."""
    if not state.client_id:
        core._afirmar(
            state,
            "jornada.entrada.precondicao_cliente",
            False,
            "cliente fictício não foi criado/localizado",
        )
        return

    user_id = str(state.user.get("user_id") or "")
    if not user_id:
        core._afirmar(
            state,
            "jornada.entrada.precondicao_usuario",
            False,
            "login não devolveu user_id para advogado_responsavel_id",
        )
        return

    caso = matrix["fictional_data"]["caso_consumidor"]
    relato = (
        f"{core.MARKER_RUN}. {caso['descricao_fatos']} "
        f"Processo {caso['numero_processo']}, tribunal {caso['tribunal']}, "
        f"comarca {caso['comarca']}, vara {caso['vara']}. "
        "Analise este atendimento apenas para criar um rascunho de homologação; "
        "os dados oficiais serão confirmados explicitamente pelo usuário."
    )
    analise = core._request(
        client,
        state,
        name="jornada.entrada.analisar",
        method="POST",
        path="/api/entrada/analisar",
        expected=[200],
        data={"texto": relato},
        timeout=300,
    )
    if analise is None or analise.status_code != 200:
        return

    proposta = analise.json()
    rascunho_id = proposta.get("rascunho_id")
    core._afirmar(
        state,
        "jornada.entrada.rascunho_persistido",
        isinstance(rascunho_id, str) and bool(rascunho_id),
        "POST /entrada/analisar não devolveu rascunho_id",
    )
    if not rascunho_id:
        return

    # HITL: a IA propõe; estes valores controlados/fictícios são os dados
    # efetivamente confirmados para persistência oficial.
    payload = {
        "cliente": {"client_id": state.client_id},
        "area": str(caso.get("area") or "consumidor"),
        "titulo": str(caso["titulo"]),
        "fatos": str(caso["descricao_fatos"]),
        "parte_contraria": caso.get("parte_contraria"),
        "documentos_ids": [],
        "assunto": "Homologação da Entrada Única",
        "natureza_demanda": "contencioso",
        "prioridade": str(caso.get("prioridade") or "media"),
        "documentos_faltantes": [],
        "provas_necessarias": [],
        "proximos_passos": [
            "Validar o dossiê fictício",
            "Preparar peça jurídica de homologação",
        ],
        "proxima_acao": str(caso.get("proxima_acao") or "Revisar o caso fictício"),
        "advogado_responsavel_id": user_id,
        "confirmo_dados_revisados": True,
        "conflict_confirmed": False,
        "duplicate_confirmed": False,
        "processo_novo_confirmado": True,
        "processo_confirmado": {
            "numero_cnj": caso["numero_processo"],
            "tribunal": caso["tribunal"],
            "comarca": caso["comarca"],
            "vara": caso["vara"],
        },
    }
    criado = core._request(
        client,
        state,
        name="jornada.entrada.confirmar_criar_caso",
        method="POST",
        path=f"/api/entrada/{rascunho_id}/criar-caso",
        expected=[200],
        json_body=payload,
        timeout=120,
    )
    if criado is None or criado.status_code != 200:
        return

    corpo = criado.json()
    state.case_id = corpo.get("case_id")
    process_id = corpo.get("process_id")
    core._afirmar(
        state,
        "jornada.entrada.processo_canonico",
        bool(process_id),
        "Entrada Única recebeu CNJ válido, mas não criou/vinculou Process canônico",
    )
    if state.case_id:
        state.criados_nesta_execucao.add(str(state.case_id))

    core._afirmar(
        state,
        "jornada.entrada.case_id",
        bool(state.case_id),
        "confirmação da Entrada Única não devolveu case_id",
    )
    if not state.case_id:
        return

    # O lote convertido é parte da trilha auditável da Entrada Única. Hoje não
    # existe rota segura para apagá-lo e o expurgo LGPD só remove lotes sem
    # case_id. Declaramos o resíduo explicitamente em vez de fingir cleanup.
    state.nao_coberto.append({
        "module_key": "entrada_unica.audit_trail",
        "method": "DELETE",
        "path": f"document_intake_batches/{rascunho_id}",
        "motivo": (
            "lote convertido é trilha auditável vinculada ao caso; não há "
            "endpoint de cleanup seguro e o expurgo canônico não remove case_id preenchido"
        ),
    })

    relido = core._request(
        client,
        state,
        name="jornada.entrada.reler_caso",
        method="GET",
        path=f"/api/cases/{state.case_id}",
        expected=[200],
    )
    if relido is not None and relido.status_code == 200:
        oficial = relido.json()
        core._afirmar(
            state,
            "jornada.entrada.vinculo_cliente",
            str(oficial.get("client_id") or "") == str(state.client_id),
            (
                f"caso criado pela Entrada Única ficou em client_id="
                f"{oficial.get('client_id')!r}, esperado {state.client_id!r}"
            ),
        )
        core._afirmar(
            state,
            "jornada.entrada.titulo_confirmado",
            str(oficial.get("titulo") or "") == str(caso["titulo"]),
            "o caso oficial não preservou o título confirmado no HITL",
        )

    processos = core._request(
        client,
        state,
        name="jornada.entrada.reler_processo",
        method="GET",
        path=f"/api/cases/{state.case_id}/processes",
        expected=[200],
    )
    if processos is not None and processos.status_code == 200 and process_id:
        try:
            itens = processos.json().get("data") or []
        except Exception as exc:
            core._afirmar(
                state,
                "jornada.entrada.processo_contrato",
                False,
                f"resposta de processos não é JSON objeto válido: {exc}",
            )
        else:
            processo = next(
                (item for item in itens if str(item.get("id")) == str(process_id)),
                None,
            )
            cnj_esperado = "".join(
                ch for ch in str(caso["numero_processo"]) if ch.isdigit()
            )
            core._afirmar(
                state,
                "jornada.entrada.metadados_processuais_confirmados",
                bool(processo)
                and "".join(
                    ch for ch in str(processo.get("numero_cnj") or "") if ch.isdigit()
                )
                == cnj_esperado
                and str(processo.get("tribunal") or "") == str(caso["tribunal"])
                and str(processo.get("comarca") or "") == str(caso["comarca"])
                and str(processo.get("vara") or "") == str(caso["vara"]),
                "Process canônico não preservou CNJ/tribunal/comarca/vara confirmados",
            )


def _criar_e_validar_peca(
    client: httpx.Client,
    state: core.SuiteState,
) -> str | None:
    if not state.case_id:
        return None
    payload = {
        "titulo": f"{core.MARKER_RUN} Peça de homologação",
        "tipo_peca": "peticao_inicial",
        "conteudo": (
            f"{core.MARKER_RUN}\n"
            "Rascunho exclusivamente fictício para validar persistência, vínculo "
            "ao caso e cleanup da jornada E2E. Não possui uso jurídico externo."
        ),
        "case_id": state.case_id,
        "ai_generated": False,
    }
    resposta = core._request(
        client,
        state,
        name="jornada.peca.criar",
        method="POST",
        path="/api/legal-docs/",
        expected=[201],
        json_body=payload,
    )
    if resposta is None or resposta.status_code != 201:
        return None
    doc_id = resposta.json().get("id")
    if not doc_id:
        core._afirmar(state, "jornada.peca.id", False, "peça criada sem id")
        return None

    relida = core._request(
        client,
        state,
        name="jornada.peca.reler",
        method="GET",
        path=f"/api/legal-docs/{doc_id}",
        expected=[200],
    )
    if relida is not None and relida.status_code == 200:
        corpo = relida.json()
        core._afirmar(
            state,
            "jornada.peca.vinculo_caso",
            corpo.get("case_id") == state.case_id,
            f"peça {doc_id} não permaneceu vinculada ao caso",
        )
    return str(doc_id)


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


def _criar_e_validar_tarefa(
    client: httpx.Client,
    state: core.SuiteState,
) -> str | None:
    if not state.case_id:
        return None
    payload = {
        "titulo": f"{core.MARKER_RUN} Revisar documentos do caso",
        "descricao": "Tarefa fictícia da jornada E2E.",
        "prioridade": "media",
        "data_limite": (date.today() + timedelta(days=5)).isoformat(),
        "case_id": state.case_id,
    }
    resposta = core._request(
        client,
        state,
        name="jornada.tarefa.criar",
        method="POST",
        path="/api/tasks/",
        expected=[201],
        json_body=payload,
    )
    if resposta is None or resposta.status_code != 201:
        return None
    task_id = resposta.json().get("id")
    if not task_id:
        core._afirmar(state, "jornada.tarefa.id", False, "tarefa criada sem id")
        return None
    relida = core._request(
        client,
        state,
        name="jornada.tarefa.reler_por_caso",
        method="GET",
        path=f"/api/tasks/?case_id={state.case_id}",
        expected=[200],
    )
    if relida is not None and relida.status_code == 200:
        itens = relida.json().get("data") or []
        core._afirmar(
            state,
            "jornada.tarefa.persistida",
            any(item.get("id") == task_id for item in itens),
            f"tarefa {task_id} não apareceu na lista do caso",
        )
    return str(task_id)


def _criar_e_validar_honorario(
    client: httpx.Client,
    state: core.SuiteState,
) -> str | None:
    role = str(state.user.get("role") or "")
    if role not in FINANCEIRO_MUTACAO_ROLES:
        state.nao_coberto.append(
            {
                "module_key": "jornada.financeiro",
                "method": "POST",
                "path": "/api/fees/",
                "motivo": (
                    f"papel {role!r} não possui mutação financeira por desenho; "
                    "use conta fictícia admin/sócio/financeiro para cobrir esta etapa"
                ),
            }
        )
        return None
    if not state.case_id or not state.client_id:
        return None

    payload = {
        "tipo": "fixo",
        "descricao": f"{core.MARKER_RUN} Honorário fictício da jornada E2E",
        "valor": "100.00",
        "data_vencimento": (date.today() + timedelta(days=20)).isoformat(),
        "client_id": state.client_id,
        "case_id": state.case_id,
        "observacoes": "Registro fictício; não representa cobrança real.",
    }
    resposta = core._request(
        client,
        state,
        name="jornada.financeiro.criar_honorario",
        method="POST",
        path="/api/fees/",
        expected=[201],
        json_body=payload,
    )
    if resposta is None or resposta.status_code != 201:
        return None
    fee_id = resposta.json().get("id")
    if not fee_id:
        core._afirmar(
            state, "jornada.financeiro.id", False, "honorário criado sem id"
        )
        return None

    relida = core._request(
        client,
        state,
        name="jornada.financeiro.reler_por_caso",
        method="GET",
        path=f"/api/fees/?case_id={state.case_id}&page_size=100",
        expected=[200],
    )
    if relida is not None and relida.status_code == 200:
        itens = relida.json().get("data") or []
        core._afirmar(
            state,
            "jornada.financeiro.persistido",
            any(item.get("id") == fee_id for item in itens),
            f"honorário {fee_id} não apareceu na carteira financeira do caso",
        )
    return str(fee_id)


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


def _cleanup_recurso(
    client: httpx.Client,
    state: core.SuiteState,
    *,
    nome: str,
    resource_id: str | None,
    delete_path: str,
) -> None:
    if not resource_id:
        return
    core._request(
        client,
        state,
        name=f"jornada.{nome}.cleanup",
        method="DELETE",
        path=delete_path,
        expected=[200, 204, 404],
        degradado_ok=True,
    )


def _cleanup_peca(
    client: httpx.Client, state: core.SuiteState, doc_id: str | None
) -> None:
    if not doc_id:
        return
    _cleanup_recurso(
        client,
        state,
        nome="peca",
        resource_id=doc_id,
        delete_path=f"/api/legal-docs/{doc_id}",
    )
    core._request(
        client,
        state,
        name="jornada.peca.cleanup_confirmado",
        method="GET",
        path=f"/api/legal-docs/{doc_id}",
        expected=[404],
        degradado_ok=True,
    )


def _cleanup_tarefa(
    client: httpx.Client, state: core.SuiteState, task_id: str | None
) -> None:
    if not task_id:
        return
    _cleanup_recurso(
        client,
        state,
        nome="tarefa",
        resource_id=task_id,
        delete_path=f"/api/tasks/{task_id}",
    )
    if state.case_id:
        relida = core._request(
            client,
            state,
            name="jornada.tarefa.cleanup_confirmado",
            method="GET",
            path=f"/api/tasks/?case_id={state.case_id}",
            expected=[200],
        )
        if relida is not None and relida.status_code == 200:
            itens = relida.json().get("data") or []
            core._afirmar(
                state,
                "jornada.tarefa.removida",
                not any(item.get("id") == task_id for item in itens),
                f"tarefa {task_id} ainda aparece após cleanup",
            )


def _cleanup_honorario(
    client: httpx.Client, state: core.SuiteState, fee_id: str | None
) -> None:
    if not fee_id:
        return
    _cleanup_recurso(
        client,
        state,
        nome="financeiro",
        resource_id=fee_id,
        delete_path=f"/api/fees/{fee_id}",
    )
    if state.case_id:
        relida = core._request(
            client,
            state,
            name="jornada.financeiro.cleanup_confirmado",
            method="GET",
            path=f"/api/fees/?case_id={state.case_id}&page_size=100",
            expected=[200],
        )
        if relida is not None and relida.status_code == 200:
            itens = relida.json().get("data") or []
            core._afirmar(
                state,
                "jornada.financeiro.removido",
                not any(item.get("id") == fee_id for item in itens),
                f"honorário {fee_id} ainda aparece após cleanup",
            )


def _cancelar_prazo(
    client: httpx.Client,
    state: core.SuiteState,
    deadline_id: str | None,
) -> None:
    if not deadline_id:
        return
    _cleanup_recurso(
        client,
        state,
        nome="prazo",
        resource_id=deadline_id,
        delete_path=f"/api/deadlines/{deadline_id}",
    )


def _cleanup_seguro(
    state: core.SuiteState,
    nome: str,
    func,
    *args,
) -> None:
    """Cleanup nunca interrompe os próximos alvos nem a gravação do relatório."""
    try:
        func(*args)
    except Exception as exc:
        core._afirmar(
            state,
            f"jornada.cleanup.{nome}.execucao",
            False,
            f"cleanup levantou exceção e foi isolado: {type(exc).__name__}: {exc}",
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
    peca_id: str | None = None
    deadline_id: str | None = None
    task_id: str | None = None
    fee_id: str | None = None

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
            core._matrix_smoke(
                client,
                state,
                matrix,
                covered_posts=core._POST_COBERTO_POR_FLUXO - {"/api/cases/"},
                skipped_posts={
                    "/api/cases/": (
                        "não coberto nesta jornada: a origem canônica do caso é "
                        "POST /api/entrada/{rascunho_id}/criar-caso; o endpoint "
                        "direto permanece coberto por run_fictitious_smoke.py"
                    )
                },
            )
            core._create_client(client, state, matrix)

            # DIFERENÇA CENTRAL desta jornada: o caso não é criado diretamente
            # por /api/cases/. Ele nasce pela Entrada Única e pela confirmação
            # HITL, igual ao fluxo padrão do dashboard.
            _criar_caso_via_entrada(client, state, matrix)

            core._upload_document(client, state, matrix)
            core._case_followups(client, state, matrix)
            core._document_followups(client, state)

            peca_id = _criar_e_validar_peca(client, state)
            deadline_id = _criar_e_validar_prazo(client, state)
            task_id = _criar_e_validar_tarefa(client, state)
            fee_id = _criar_e_validar_honorario(client, state)
            _validar_inteligencia_do_caso(client, state)
            _validar_dpt360(client, state)
        finally:
            # Dependências FK: satélites primeiro, depois documento/caso/cliente
            # no cleanup canônico. Cada remoção usa apenas IDs desta execução.
            if os.getenv("EJC_E2E_CLEANUP", "true").strip().lower() != "false":
                _cleanup_seguro(
                    state, "financeiro", _cleanup_honorario, client, state, fee_id
                )
                _cleanup_seguro(
                    state, "tarefa", _cleanup_tarefa, client, state, task_id
                )
                _cleanup_seguro(
                    state, "prazo", _cancelar_prazo, client, state, deadline_id
                )
                _cleanup_seguro(
                    state, "peca", _cleanup_peca, client, state, peca_id
                )
                _cleanup_seguro(
                    state, "core", core._cleanup, client, state
                )
            core._write_report(state, matrix)


if __name__ == "__main__":
    main()
