"""
Cliente de integração com a API Pública do DataJud (CNJ).

Documentação oficial: https://datajud-wiki.cnj.jus.br/api-publica/
Base URL: https://api-publica.datajud.cnj.jus.br/
Autenticação: API Key pública, fornecida e mantida pelo CNJ (pode ser alterada
a qualquer momento pelo CNJ — não é uma credencial pessoal do usuário).

Uso no EJC: consulta de metadados processuais (capa e movimentações) por
número de processo, para qualquer tribunal brasileiro, via alias do tribunal.

IMPORTANTE (Onda 3 — achado de segurança/consistência):
- A chave embutida no código foi REMOVIDA. A única fonte da chave é a
  configuração central (settings.DATAJUD_API_KEY, que o pydantic-settings lê
  do .env/variável de ambiente DATAJUD_API_KEY). Sem chave ou com
  DATAJUD_ENABLED=false, a consulta levanta DataJudDesabilitadoError —
  degradação graciosa, no MESMO idioma de services/datajud_service.py.
- Este módulo é um wrapper fino: a chamada HTTP real (retry/backoff, base URL
  e timeout configuráveis) é delegada a datajud_service.buscar_processo_bruto,
  eliminando o caminho paralelo sem retry que existia aqui.
"""

from __future__ import annotations

from typing import Any

from app.services.datajud_service import (  # noqa: F401  (reexport p/ consumidores)
    DataJudDesabilitadoError,
    buscar_processo_bruto,
)

DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

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
    """Wrapper fino sobre datajud_service (caminho único de saída ao CNJ).

    Não guarda chave própria: flag e chave são resolvidas pelo serviço no
    momento da chamada (kill-switch DATAJUD_ENABLED prevalece sempre).
    """

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

        Levanta DataJudDesabilitadoError (flag/chave ausentes) ou httpx.*
        (falha de rede/HTTP após os retries do serviço).
        """
        return await buscar_processo_bruto(numero_processo, tribunal_alias)
