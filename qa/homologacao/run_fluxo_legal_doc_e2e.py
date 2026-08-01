#!/usr/bin/env python3
"""Homologação ponta a ponta do fluxo validação → HITL → aprovação → PDF.

Usa somente massa fictícia marcada. Exige ambiente de homologação/produção
controlada com credenciais QA e provedor de IA funcional.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pyotp

OUT = Path(os.getenv("EJC_QA_OUT", "qa/homologacao/reports"))
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "legal_doc_flow_e2e.json"


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def request(client: httpx.Client, method: str, path: str, expected: set[int], **kwargs) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.status_code not in expected:
        raise RuntimeError(
            f"{method} {path}: esperado {sorted(expected)}, recebido "
            f"{response.status_code}: {(response.text or '')[:1200]}"
        )
    return response


def cpf_valido(base: int) -> str:
    digits = [int(x) for x in f"{base % 1_000_000_000:09d}"]
    if len(set(digits)) == 1:
        digits = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    first = (sum(v * p for v, p in zip(digits, range(10, 1, -1))) * 10 % 11) % 10
    digits.append(first)
    second = (sum(v * p for v, p in zip(digits, range(11, 1, -1))) * 10 % 11) % 10
    digits.append(second)
    return "".join(map(str, digits))


def main() -> None:
    marker = f"HOMOLOG-LEGALDOC-{time.time_ns()}"
    report: dict[str, Any] = {
        "marker": marker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
        "ids": {},
        "result": "INCOMPLETE",
    }
    base_url = env("EJC_BASE_URL").rstrip("/")
    with httpx.Client(base_url=base_url, timeout=300, follow_redirects=True) as client:
        login = request(
            client,
            "POST",
            "/api/auth/login",
            {200},
            json={
                "email": env("EJC_TEST_EMAIL"),
                "password": env("EJC_TEST_PASSWORD"),
                "totp_code": pyotp.TOTP(env("EJC_TEST_TOTP_SECRET")).now(),
            },
        )
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        report["steps"].append("login")

        suffix = int(str(time.time_ns())[-9:])
        client_resp = request(
            client,
            "POST",
            "/api/clients/",
            {201},
            json={
                "tipo": "PF",
                "nome": f"{marker} Cliente Fictício",
                "cpf": cpf_valido(suffix),
                "email": f"qa.{suffix}@example.invalid",
                "telefone": f"319{suffix:08d}"[-11:],
                "cidade": "Betim",
                "estado": "MG",
                "observacoes": "Massa fictícia e descartável de homologação.",
            },
        )
        client_id = client_resp.json()["id"]
        report["ids"]["client_id"] = client_id

        fatos = (
            f"{marker}. Caso integralmente fictício. O consumidor quitou obrigação "
            "contratual, apresentou comprovante, solicitou correção administrativa e "
            "permaneceu com cobrança indevida. O contrato, o comprovante de pagamento, "
            "os protocolos e a resposta do fornecedor estão indicados como provas. "
            "A pretensão é declaratória e indenizatória, com pedido de tutela, inversão "
            "do ônus da prova e demais providências cabíveis. "
        ) * 8
        case_resp = request(
            client,
            "POST",
            "/api/cases/",
            {201},
            json={
                "titulo": f"{marker} Caso fictício",
                "area": "consumidor",
                "prioridade": "alta",
                "descricao_fatos": fatos,
                "client_id": client_id,
            },
        )
        case_id = case_resp.json()["id"]
        report["ids"]["case_id"] = case_id

        conteudo = (
            "AO JUÍZO DO JUIZADO ESPECIAL CÍVEL DE BETIM/MG\n\n"
            "DOS FATOS\n" + fatos + "\n\n"
            "DO DIREITO\nA relação é regida pelos arts. 6º e 14 da Lei 8.078/1990. "
            "A documentação indicada comprova a contratação, o pagamento e os protocolos.\n\n"
            "DOS PEDIDOS\nRequer tutela adequada, declaração de inexistência da cobrança, "
            "inversão do ônus da prova, citação e procedência dos pedidos.\n\n"
            "DAS PROVAS\nContrato, comprovante de pagamento, protocolos e resposta do fornecedor.\n\n"
            "DO VALOR DA CAUSA\nDá-se à causa o valor de R$ 10.000,00.\n\n"
            "Termos em que, pede deferimento."
        )
        doc_resp = request(
            client,
            "POST",
            "/api/legal-docs/",
            {201},
            json={
                "titulo": f"{marker} Petição fictícia",
                "tipo_peca": "peticao_inicial",
                "conteudo": conteudo,
                "case_id": case_id,
                "ai_generated": True,
            },
        )
        doc_id = doc_resp.json()["id"]
        report["ids"]["legal_doc_id"] = doc_id

        def validar_aprovar_exportar(cycle: int) -> None:
            validation = request(client, "POST", f"/api/legal-docs/{doc_id}/validar", {200}).json()
            if validation.get("score_confianca", 0) < 75:
                raise RuntimeError(f"Ciclo {cycle}: score abaixo do gate: {validation}")
            log_id = validation["ai_log_id"]
            request(
                client,
                "PATCH",
                f"/api/ai/logs/{log_id}/hitl",
                {200},
                json={"status": "revisado"},
            )
            request(
                client,
                "PATCH",
                f"/api/legal-docs/{doc_id}/aprovar",
                {200},
                json={"observacoes": f"Revisão humana fictícia de homologação — ciclo {cycle}."},
            )
            pdf = request(client, "GET", f"/api/legal-docs/{doc_id}/pdf", {200})
            if not pdf.content.startswith(b"%PDF"):
                raise RuntimeError(f"Ciclo {cycle}: exportação não retornou PDF válido")
            pacote = request(
                client,
                "GET",
                f"/api/legal-docs/{doc_id}/documento-unico-impressao",
                {200},
            )
            if not pacote.content.startswith(b"%PDF"):
                raise RuntimeError(f"Ciclo {cycle}: documento único não retornou PDF válido")
            report["steps"].append(f"cycle_{cycle}_approved_and_exported")
            report.setdefault("validation_log_ids", []).append(log_id)

        validar_aprovar_exportar(1)

        edited = request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {200},
            json={"conteudo": conteudo + "\n\nALTERAÇÃO CONTROLADA PARA INVALIDAR A VALIDAÇÃO."},
        ).json()
        if edited.get("human_reviewed") is not False or edited.get("status") != "em_revisao":
            raise RuntimeError(f"Edição não retornou ao fluxo de revisão: {edited}")
        validation_state = request(client, "GET", f"/api/legal-docs/{doc_id}/validacao", {200}).json()
        if validation_state.get("apto_fluxo") is not False:
            raise RuntimeError(f"Validação antiga permaneceu apta: {validation_state}")
        request(client, "GET", f"/api/legal-docs/{doc_id}/pdf", {422})
        request(client, "GET", f"/api/legal-docs/{doc_id}/documento-unico-impressao", {422})
        report["steps"].append("edit_invalidated_review_validation_and_pdfs")

        validar_aprovar_exportar(2)

        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}/protocolo",
            {200},
            json={
                "numero_protocolo": f"{marker}-PROTOCOLO-FICTICIO",
                "protocolo_tribunal": "TJMG-HOMOLOGACAO",
                "protocolado_em": datetime.now(timezone.utc).isoformat(),
            },
        )
        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {200},
            json={"status": "protocolada"},
        )
        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {422},
            json={"status": "em_revisao"},
        )
        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {422},
            json={"conteudo": conteudo + "\nTentativa proibida após protocolo."},
        )
        report["steps"].append("protocolled_document_is_immutable")
        report["result"] = "PASS"

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"result": report["result"], "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        REPORT.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "result": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise
