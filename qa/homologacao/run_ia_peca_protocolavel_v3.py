#!/usr/bin/env python3
"""Homologação da IA com documento fictício explicitamente autorizado.

Preserva as rodadas anteriores como evidência dos gates encontrados. Esta versão
intercepta somente a criação do caso e a chamada de geração para anexar um arquivo
textual fictício ao caso e incluí-lo em `documentos_considerados`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

import run_ia_peca_protocolavel as base

_original_request = httpx.Client.request
_case_id: str | None = None
_doc_id: str | None = None


def _request_com_documento_autorizado(self, method, url, **kwargs):
    global _case_id, _doc_id
    method_u = method.upper()
    path = str(url).rstrip("/")

    if method_u == "POST" and path == "/api/cases":
        payload = dict(kwargs.get("json") or {})
        payload.setdefault(
            "proxima_acao",
            "Revisar o conjunto documental fictício e concluir a petição inicial",
        )
        kwargs["json"] = payload
        response = _original_request(self, method, url, **kwargs)
        if response.status_code == 201:
            _case_id = response.json().get("id")
        return response

    if method_u == "POST" and path == "/api/pecas/gerar":
        if not _case_id:
            raise RuntimeError("Caso não capturado antes da geração da peça")
        if not _doc_id:
            evidence = (
                "HOMOLOG-FICTICIO. DOSSIÊ DOCUMENTAL SINTÉTICO.\n\n"
                "1. Contrato fictício de internet residencial celebrado em 10/03/2026.\n"
                "2. Pedido fictício de cancelamento em 25/04/2026.\n"
                "3. Fatura final fictícia de R$ 189,90.\n"
                "4. Comprovante fictício de pagamento em 30/04/2026.\n"
                "5. Aviso fictício de negativação em 20/05/2026.\n"
                "6. Protocolo fictício de atendimento em 21/05/2026.\n"
                "7. Resposta fictícia da fornecedora reconhecendo a quitação.\n"
                "8. Consulta fictícia de 05/06/2026 indicando restrição ainda ativa.\n"
                "9. Declaração sintética de inexistência de inscrição preexistente.\n\n"
                "Todos os nomes, datas e fatos são exclusivamente de homologação e não "
                "correspondem a pessoa, empresa ou processo real."
            )
            upload = _original_request(
                self,
                "POST",
                "/api/documents/upload",
                files={"file": ("homolog-dossie-probatorio.txt", evidence.encode("utf-8"), "text/plain")},
                data={
                    "titulo": "HOMOLOG-FICTICIO Dossiê probatório autorizado",
                    "tipo": "prova",
                    "confidencialidade": "normal",
                    "case_id": _case_id,
                },
            )
            if upload.status_code != 201:
                raise RuntimeError(
                    f"Upload probatório falhou: {upload.status_code} — {upload.text[:1000]}"
                )
            _doc_id = upload.json().get("id")
        payload = dict(kwargs.get("json") or {})
        mode = dict(payload.get("modo_producao") or {})
        mode["documentos_considerados"] = [
            {
                "documento_id": _doc_id,
                "nome": "Dossiê probatório fictício autorizado",
            }
        ]
        mode["aprovado_para_redacao"] = True
        payload["modo_producao"] = mode
        kwargs["json"] = payload

    return _original_request(self, method, url, **kwargs)


httpx.Client.request = _request_com_documento_autorizado

if __name__ == "__main__":
    try:
        base.main()
    except Exception as exc:
        base.REPORT.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "resultado": "FALHA_EXECUCAO",
                    "erro": f"{type(exc).__name__}: {exc}",
                    "case_id_capturado": _case_id,
                    "documento_id_capturado": _doc_id,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise
