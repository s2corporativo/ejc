"""
Cliente de integração com a API do DJEN — Diário de Justiça Eletrônico
Nacional (CNJ), via o serviço "Comunica" (comunicaapi.pje.jus.br).

Endpoint de CONSULTA (o que interessa ao EJC) é público e NÃO exige
autenticação — verificado empiricamente em 2026-07-18 com requisição real
(GET .../api/v1/comunicacao?numeroOab=1&ufOab=MG), que retornou JSON
estruturado com 589 registros.

Endpoint de ENVIO/PUBLICAÇÃO de comunicações (usado pelos próprios tribunais
para publicar) é DIFERENTE e exige usuário/senha do sistema Corporativo do
CNJ — não é o caso de uso do EJC e não está implementado aqui.

Documentação de referência:
- Portal CNJ: https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/orientacoes-aos-tribunais/
- Swagger: https://comunicaapi.pje.jus.br/
- Portal de consulta (uso humano): https://comunica.pje.jus.br/

USO NO EJC: localizar automaticamente todas as intimações/comunicações
processuais publicadas no DJEN para os advogados do escritório, por número
de OAB — substitui monitoramento manual do diário oficial para os processos
que já migraram para o DJEN (a partir de 27/01/2025 em MG, conforme TJMG).

ATENÇÃO — risco de uso indevido: esta API retorna dados de partes e
processos que, embora publicados oficialmente, envolvem terceiros. Trate o
resultado com os mesmos cuidados de sigilo e LGPD já aplicados a dados
processuais no EJC (ver auditor-lgpd-etica).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import httpx

from app.services.djen_http import (
    DJEN_COMUNICA_BASE_URL,
    DJEN_ITENS_POR_PAGINA,
    criar_cliente_djen,
)

COMUNICA_BASE_URL = DJEN_COMUNICA_BASE_URL


class DjenComunicaError(RuntimeError):
    """Erro de integração com a API do DJEN/Comunica."""


class DjenComunicaClient:
    def __init__(self, timeout_s: float = 15.0) -> None:
        self._timeout = httpx.Timeout(timeout_s)

    async def consultar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
        pagina: int = 1,
    ) -> dict[str, Any]:
        """
        Consulta comunicações/intimações publicadas no DJEN vinculadas a um
        número de OAB.

        Retorno inclui, por item: numero_processo, siglaTribunal,
        tipoComunicacao, texto (HTML da intimação), link (PDF), data de
        disponibilização, destinatarios e destinatarioadvogados.
        """
        params: dict[str, Any] = {
            "numeroOab": numero_oab,
            "ufOab": uf_oab,
            "pagina": pagina,
            "itensPorPagina": DJEN_ITENS_POR_PAGINA,
        }
        if data_inicio:
            params["dataDisponibilizacaoInicio"] = data_inicio.isoformat()
        if data_fim:
            params["dataDisponibilizacaoFim"] = data_fim.isoformat()

        async with criar_cliente_djen(timeout=self._timeout) as client:
            resp = await client.get(f"{COMUNICA_BASE_URL}/comunicacao", params=params)
        if resp.status_code != 200:
            raise DjenComunicaError(
                f"DJEN/Comunica retornou HTTP {resp.status_code}"
            )
        return resp.json()

    async def consultar_por_processo(self, numero_processo: str) -> dict[str, Any]:
        """Consulta comunicações vinculadas a um número de processo específico."""
        numero_limpo = "".join(ch for ch in numero_processo if ch.isdigit())
        params = {"numeroProcesso": numero_limpo}
        async with criar_cliente_djen(timeout=self._timeout) as client:
            resp = await client.get(f"{COMUNICA_BASE_URL}/comunicacao", params=params)
        if resp.status_code != 200:
            raise DjenComunicaError(
                f"DJEN/Comunica retornou HTTP {resp.status_code}"
            )
        return resp.json()
