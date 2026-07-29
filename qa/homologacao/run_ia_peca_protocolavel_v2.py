#!/usr/bin/env python3
"""Executa o cenário de IA acrescentando o campo obrigatório do contrato atual.

Mantém o roteiro original intacto como evidência do drift encontrado na rodada 2.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

import run_ia_peca_protocolavel as base

_original_request = httpx.Client.request


def _request_com_contrato_atual(self, method, url, **kwargs):
    if method.upper() == "POST" and str(url).rstrip("/") == "/api/cases":
        payload = dict(kwargs.get("json") or {})
        payload.setdefault(
            "proxima_acao",
            "Revisar o conjunto documental fictício e concluir a petição inicial",
        )
        kwargs["json"] = payload
    return _original_request(self, method, url, **kwargs)


httpx.Client.request = _request_com_contrato_atual

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
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        raise
