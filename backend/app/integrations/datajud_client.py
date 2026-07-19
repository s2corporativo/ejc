"""
Cliente de integração com a API Pública do DataJud (CNJ).

Documentação oficial: https://datajud-wiki.cnj.jus.br/api-publica/
Base URL: https://api-publica.datajud.cnj.jus.br/
Autenticação: API Key pública, fornecida e mantida pelo CNJ (pode ser alterada
a qualquer momento pelo CNJ — não é uma credencial pessoal do usuário).

Uso no EJC: consulta de metadados processuais (capa e movimentações) por
número de processo, para qualquer tribunal brasileiro, via alias do tribunal.

IMPORTANTE (revisão técnica):
- Esta API é somente leitura (metadados processuais), respeitando sigilo de
  processos protegidos por segredo de justiça (Portaria CNJ 160/2020).
- A API Key abaixo é PÚBLICA (publicada oficialmente pelo CNJ na Wiki do
  Datajud) e pode ser alterada pelo CNJ sem aviso prévio. Trate-a como
  configuração, não como segredo — mas mantenha-a em variável de ambiente
  para facilitar atualização futura sem alterar código.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Valor publicado em https://datajud-wiki.cnj.jus.br/api-publica/acesso
# Pode mudar a qualquer momento por decisão do CNJ — sempre confirme na Wiki
# antes de assumir que este valor ainda é válido.
DATAJUD_API_KEY_DEFAULT = (
    "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
)

# Aliases de tribunal mais usados pelo escritório (ajustar conforme a
# distribuição real de casos do EJC). Lista completa em:
# https://datajud-wiki.cnj.jus.br/api-publica/endpoints
TRIBUNAL_ALIASES = {
    "TJMG": "api_publica_tjmg",
    "TRT3": "api_publica_trt3",
    "TRF1": "api_publica_trf1",
    "STJ": "api_publica_stj",
    "TST": "api_publica_tst",
}


class DataJudError(RuntimeError):
    """Erro de integração com a API Pública do DataJud."""


class DataJudClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_s: float = 15.0,
    ) -> None:
        # "or" (e não default do getenv): o .env/docker-compose exporta
        # DATAJUD_API_KEY= VAZIA — string vazia também deve cair no fallback.
        self.api_key = api_key or os.getenv("DATAJUD_API_KEY") or DATAJUD_API_KEY_DEFAULT
        self._timeout = httpx.Timeout(timeout_s)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"APIKey {self.api_key}",
            "Content-Type": "application/json",
        }

    async def consultar_processo(
        self,
        numero_processo: str,
        tribunal_alias: str,
    ) -> dict[str, Any]:
        """
        Consulta metadados de um processo pelo número (formato CNJ, 20 dígitos,
        com ou sem máscara) em um tribunal específico.

        `tribunal_alias`: alias do tribunal, ex. "api_publica_tjmg".
        Use TRIBUNAL_ALIASES para os mais comuns, ou consulte a lista completa
        na Wiki do Datajud antes de assumir um alias que não esteja mapeado
        aqui.
        """
        numero_limpo = "".join(ch for ch in numero_processo if ch.isdigit())
        url = f"{DATAJUD_BASE_URL}/{tribunal_alias}/_search"
        payload = {
            "query": {
                "match": {"numeroProcesso": numero_limpo}
            }
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
        if resp.status_code != 200:
            raise DataJudError(
                f"DataJud retornou HTTP {resp.status_code} para "
                f"{tribunal_alias}/{numero_limpo}: {resp.text[:500]}"
            )
        return resp.json()
