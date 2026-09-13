from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


DIRETORIO_AGENTES = Path(__file__).resolve().parents[1]
if str(DIRETORIO_AGENTES) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_AGENTES))

import omniroute  # noqa: E402


class TestesOmniRoute(unittest.TestCase):
    """Contratos determinísticos do gateway; nenhum teste chama rede ou modelo."""

    def test_resolve_padrao_local_e_modelo_de_codigo(self) -> None:
        """Sem base/modelo explícitos, o launcher usa loopback e rota de código."""
        config = omniroute.resolver_configuracao_omniroute({"OPENAI_API_KEY": "teste-local"})
        self.assertEqual(config.base_url, "http://127.0.0.1:20128/v1")
        self.assertEqual(config.modelo, "auto/best-coding")
        self.assertIsNone(config.tracing_api_key)

    def test_rejeita_gateway_publico(self) -> None:
        """A camada de engenharia não pode enviar tráfego para OmniRoute publicado na internet."""
        with self.assertRaisesRegex(ValueError, "HTTP local|127.0.0.1"):
            omniroute.resolver_configuracao_omniroute(
                {
                    "OPENAI_API_KEY": "teste-local",
                    "OPENAI_BASE_URL": "https://gateway.example.com/v1",
                }
            )

    def test_rejeita_porta_ou_path_diferente(self) -> None:
        """O endpoint deve coincidir com o serviço loopback endurecido do EJC."""
        with self.assertRaisesRegex(ValueError, "porta local 20128"):
            omniroute.resolver_configuracao_omniroute(
                {
                    "OPENAI_API_KEY": "teste-local",
                    "OPENAI_BASE_URL": "http://127.0.0.1:9999/v1",
                }
            )
        with self.assertRaisesRegex(ValueError, "exatamente em /v1"):
            omniroute.resolver_configuracao_omniroute(
                {
                    "OPENAI_API_KEY": "teste-local",
                    "OPENAI_BASE_URL": "http://127.0.0.1:20128/outro",
                }
            )

    def test_exige_endpoint_key_no_host(self) -> None:
        """Execução sem credencial de inferência deve falhar antes de criar o cliente."""
        with self.assertRaisesRegex(ValueError, "endpoint key"):
            omniroute.resolver_configuracao_omniroute({})

    @patch.object(omniroute, "set_tracing_disabled")
    @patch.object(omniroute, "set_default_openai_api")
    @patch.object(omniroute, "set_default_openai_client")
    @patch.object(omniroute, "AsyncOpenAI")
    def test_chave_omniroute_nao_e_usada_para_tracing(
        self,
        async_openai: MagicMock,
        set_cliente: MagicMock,
        set_api: MagicMock,
        set_tracing_disabled: MagicMock,
    ) -> None:
        """Sem chave de tracing separada, export remoto fica desabilitado."""
        cliente = MagicMock()
        async_openai.return_value = cliente
        config = omniroute.ConfiguracaoOmniRoute(
            base_url="http://127.0.0.1:20128/v1",
            api_key="endpoint-key-sintetica",
            modelo="auto/best-coding",
        )

        omniroute.aplicar_configuracao_omniroute(config)

        async_openai.assert_called_once_with(
            base_url="http://127.0.0.1:20128/v1",
            api_key="endpoint-key-sintetica",
        )
        set_cliente.assert_called_once_with(cliente, use_for_tracing=False)
        set_api.assert_called_once_with("chat_completions")
        set_tracing_disabled.assert_called_once_with(True)

    @patch.object(omniroute, "set_tracing_export_api_key")
    @patch.object(omniroute, "set_tracing_disabled")
    @patch.object(omniroute, "set_default_openai_api")
    @patch.object(omniroute, "set_default_openai_client")
    @patch.object(omniroute, "AsyncOpenAI")
    def test_tracing_exige_credencial_separada(
        self,
        async_openai: MagicMock,
        set_cliente: MagicMock,
        set_api: MagicMock,
        set_tracing_disabled: MagicMock,
        set_tracing_key: MagicMock,
    ) -> None:
        """Tracing só é reativado quando existe credencial explicitamente separada."""
        cliente = MagicMock()
        async_openai.return_value = cliente
        config = omniroute.ConfiguracaoOmniRoute(
            base_url="http://127.0.0.1:20128/v1",
            api_key="endpoint-key-sintetica",
            modelo="auto/best-coding",
            tracing_api_key="tracing-key-sintetica",
        )

        omniroute.aplicar_configuracao_omniroute(config)

        set_cliente.assert_called_once_with(cliente, use_for_tracing=False)
        set_api.assert_called_once_with("chat_completions")
        set_tracing_disabled.assert_called_once_with(False)
        set_tracing_key.assert_called_once_with("tracing-key-sintetica")


if __name__ == "__main__":
    unittest.main()
