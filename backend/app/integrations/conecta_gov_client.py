"""
Scaffold de integração com o Catálogo de APIs Governamentais (Conecta gov.br).

Catálogo: https://www.gov.br/conecta/catalogo/

DIFERENÇA CRÍTICA em relação aos demais clientes deste pacote: as APIs do
Conecta gov.br (CPF - Cadastro Base do Cidadão, CNPJ - Consulta de Empresas,
CEP - Cadastro Base de Endereço, CND - Consulta Certidão Negativa de
Débitos, Certidão de Antecedentes Criminais, Relação Trabalhista, DOU -
Publicar no Diário Oficial da União, SICAR, CADIN, entre outras) NÃO são de
acesso anônimo. Exigem:

1. Credenciamento institucional prévio da S2/De Paula Teixeira junto ao
   Conecta gov.br (cadastro como "Órgão/Empresa consumidora");
2. Emissão de client_id e client_secret por API contratada;
3. Fluxo OAuth2 client_credentials para obter um access_token antes de cada
   chamada.

Este arquivo é um SCAFFOLD funcional do fluxo OAuth2 — não contém nenhuma
credencial real (não invento client_id/client_secret). Para ativar,
preencha as variáveis de ambiente CONECTA_CLIENT_ID e CONECTA_CLIENT_SECRET
após concluir o credenciamento oficial.

Sem essas credenciais, as chamadas abaixo falharão com 401 — isso é
esperado até a conclusão do credenciamento, não é um bug do código.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

CONECTA_TOKEN_URL = "https://api.conecta.serpro.gov.br/token"  # confirmar no manual da API específica contratada
CONECTA_BASE_URL = "https://api.conecta.serpro.gov.br"  # varia por API — ajustar por serviço contratado


class ConectaGovError(RuntimeError):
    """Erro de integração com o Conecta gov.br (credenciamento pendente ou falha de API)."""


class ConectaGovClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.client_id = client_id or os.getenv("CONECTA_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("CONECTA_CLIENT_SECRET")
        self._timeout = httpx.Timeout(timeout_s)
        self._token: Optional[str] = None
        self._token_expira_em: float = 0.0

    def _credenciais_configuradas(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _obter_token(self) -> str:
        if not self._credenciais_configuradas():
            raise ConectaGovError(
                "CONECTA_CLIENT_ID/CONECTA_CLIENT_SECRET não configurados — "
                "conclua o credenciamento institucional no Conecta gov.br "
                "antes de usar este cliente."
            )
        if self._token and time.time() < self._token_expira_em:
            return self._token

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                CONECTA_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
        if resp.status_code != 200:
            raise ConectaGovError(
                f"Falha ao obter token OAuth2 do Conecta gov.br: "
                f"HTTP {resp.status_code} — {resp.text[:300]}"
            )
        data = resp.json()
        self._token = data["access_token"]
        self._token_expira_em = time.time() + float(data.get("expires_in", 300)) - 30
        return self._token

    async def consultar_cpf(self, cpf: str) -> dict[str, Any]:
        """
        Consulta CPF via API "CPF - Cadastro Base do Cidadão".
        Endpoint exato varia conforme documentação entregue no credenciamento
        — ajustar path abaixo após leitura do manual técnico específico.
        """
        token = await self._obter_token()
        cpf_limpo = "".join(ch for ch in cpf if ch.isdigit())
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{CONECTA_BASE_URL}/cpf/v1/{cpf_limpo}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ConectaGovError(
                f"Conecta gov.br (CPF) retornou HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    async def consultar_cnpj(self, cnpj: str) -> dict[str, Any]:
        """Consulta CNPJ via API oficial "CNPJ – Consulta de Empresas"."""
        token = await self._obter_token()
        cnpj_limpo = "".join(ch for ch in cnpj if ch.isdigit())
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{CONECTA_BASE_URL}/cnpj/v1/{cnpj_limpo}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ConectaGovError(
                f"Conecta gov.br (CNPJ) retornou HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()
