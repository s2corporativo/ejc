from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from openai import AsyncOpenAI
from agents import (
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
    set_tracing_export_api_key,
)

try:
    from . import runner
except ImportError:  # pragma: no cover - permite execução direta do arquivo
    import runner  # type: ignore[no-redef]


OMNIROUTE_BASE_URL_PADRAO = "http://127.0.0.1:20128/v1"
OMNIROUTE_MODELO_PADRAO = "auto/best-coding"


@dataclass(frozen=True)
class ConfiguracaoOmniRoute:
    """Configuração host-side do gateway, sem qualquer materialização no sandbox."""

    base_url: str
    api_key: str
    modelo: str
    tracing_api_key: str | None = None


def _validar_base_url_loopback(base_url: str) -> str:
    """Aceita somente o endpoint local esperado e impede roteamento acidental à internet."""
    valor = base_url.strip().rstrip("/")
    parsed = urlparse(valor)
    if parsed.scheme != "http":
        raise ValueError("OmniRoute deve usar HTTP local por loopback")
    if parsed.hostname != "127.0.0.1":
        raise ValueError("OmniRoute de engenharia deve permanecer em 127.0.0.1")
    if parsed.port != 20128:
        raise ValueError("OmniRoute de engenharia deve usar a porta local 20128")
    if parsed.path != "/v1" or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("base URL do OmniRoute deve terminar exatamente em /v1")
    return valor


def resolver_configuracao_omniroute(
    ambiente: Mapping[str, str] | None = None,
) -> ConfiguracaoOmniRoute:
    """Resolve somente variáveis do processo host e nunca lê arquivos de produção."""
    env = os.environ if ambiente is None else ambiente
    base_url = _validar_base_url_loopback(
        env.get("EJC_OMNIROUTE_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or OMNIROUTE_BASE_URL_PADRAO
    )
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY deve conter a endpoint key do OmniRoute")

    modelo = env.get("OPENAI_AGENTS_MODEL", "").strip() or OMNIROUTE_MODELO_PADRAO
    tracing_api_key = env.get("EJC_AGENTS_TRACING_API_KEY", "").strip() or None
    return ConfiguracaoOmniRoute(
        base_url=base_url,
        api_key=api_key,
        modelo=modelo,
        tracing_api_key=tracing_api_key,
    )


def aplicar_configuracao_omniroute(config: ConfiguracaoOmniRoute) -> None:
    """Configura o SDK para o gateway e separa explicitamente credencial de tracing."""
    cliente = AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)
    set_default_openai_client(cliente, use_for_tracing=False)
    set_default_openai_api("chat_completions")

    if config.tracing_api_key:
        set_tracing_disabled(False)
        set_tracing_export_api_key(config.tracing_api_key)
    else:
        # A endpoint key do OmniRoute não é uma credencial de tracing da OpenAI.
        # Desabilitar export remoto evita reutilização acidental dessa chave.
        set_tracing_disabled(True)


def main() -> int:
    """Configura o gateway de engenharia e delega a execução ao runner endurecido."""
    try:
        config = resolver_configuracao_omniroute()
    except ValueError as exc:
        print(f"ERRO_CONFIG_OMNIROUTE: {exc}")
        return 5

    aplicar_configuracao_omniroute(config)
    os.environ["OPENAI_AGENTS_MODEL"] = config.modelo
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
