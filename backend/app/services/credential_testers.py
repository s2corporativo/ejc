# ── app/services/credential_testers.py ───────────────────────────────────────
# Cofre de Credenciais — PR-4: testadores de conexão por integração.
#
# Um testador async por provider do credential_registry. Cada um devolve
# (estado, detalhe) no vocabulário fechado abaixo — o MESMO domínio do
# integration_credentials.last_test_status (models/integration_credential.py):
#
#   configurada   — credencial presente e validada (ou "metadado, sem teste
#                   remoto" nos providers sem endpoint barato/seguro);
#   ausente       — campo(s) obrigatório(s) do provider vazio(s) no runtime;
#   invalida      — credencial rejeitada (401 sem sinal de expiração / 404);
#   expirada      — token/cert expirado (401 com sinal de expiração no corpo);
#   sem_permissao — 403 (autenticou, mas sem escopo/permissão para o recurso);
#   indisponivel  — timeout, DNS, erro de transporte ou 5xx (falha transitória).
#
# REGRAS DE SEGURANÇA (mesma higiene do resto do cofre):
#   * a fonte dos valores é SEMPRE get_settings() — o singleton já recebeu o
#     overlay do cofre (credential_vault_service.aplicar_overlay); ler settings
#     ao vivo garante que o teste use o valor VIGENTE, e não um cliente de SDK
#     cacheado com a chave antiga (limitação de reusar health() dos providers);
#   * NENHUM segredo, header de Authorization, corpo de resposta ou URL com
#     token vai para log, detalhe ou exceção — os `detalhe` são strings fixas
#     que carregam no máximo o código HTTP;
#   * timeout curto (5–8s) e try/except que mapeia QUALQUER exceção de rede em
#     `indisponivel` (o teste nunca derruba a requisição do chamador).
#
# Reuso: as URLs/headers espelham os conectores existentes — datajud_service
# (_datajud_search / APIKey), notification_service (Z-API status), nfse/
# nuvem_fiscal (_obter_token / client_credentials), infosimples_service
# (account) e as healths de groq/anthropic/maritaca (ai_gateway.health) — mas
# aqui a classificação é granular (401 vs 403 vs timeout vs expirado), o que o
# health() booleano não distingue.
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Awaitable, Callable

import httpx

from app.core.config import get_settings

logger = logging.getLogger("ejc.cofre.testes")

# ── Vocabulário de estados (domínio de last_test_status) ─────────────────────
CONFIGURADA = "configurada"
AUSENTE = "ausente"
INVALIDA = "invalida"
EXPIRADA = "expirada"
SEM_PERMISSAO = "sem_permissao"
INDISPONIVEL = "indisponivel"

TesteResultado = tuple[str, str]  # (estado, detalhe) — detalhe NUNCA tem segredo

# Timeout curto e limitado à janela 5–8s (teste é interativo; não pode pendurar).
_TIMEOUT_PADRAO = 8.0
_TIMEOUT_MIN = 5.0
_TIMEOUT_MAX = 8.0

# Sinais de EXPIRAÇÃO num corpo 401 (distingue expirada de invalida). Usados só
# para CLASSIFICAR — o corpo em si nunca é logado nem devolvido.
_SINAIS_EXPIRACAO = (
    "expired", "expirado", "expirada", "token_expired", "invalid_grant",
    "has expired", "jwt expired",
)


def _clamp_timeout(valor: object) -> float:
    try:
        v = float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        v = _TIMEOUT_PADRAO
    return min(max(v, _TIMEOUT_MIN), _TIMEOUT_MAX)


def _vazio(*valores: object) -> bool:
    """True se QUALQUER valor obrigatório estiver ausente/em branco."""
    return any(not str(v or "").strip() for v in valores)


def _basic_auth(usuario: str, senha: str) -> str:
    token = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    return f"Basic {token}"


# ── Mapeadores comuns (status HTTP / exceção → estado) ───────────────────────

def _corpo_para_classificar(resp: httpx.Response) -> str:
    """Trecho minúsculo do corpo APENAS para classificar 401 (expirada vs
    invalida). Nunca é logado nem devolvido ao chamador."""
    try:
        return (resp.text or "")[:600].lower()
    except Exception:  # noqa: BLE001 — corpo ilegível não pode quebrar o teste
        return ""


def _estado_por_resposta(resp: httpx.Response) -> TesteResultado:
    status = resp.status_code
    if 200 <= status < 300:
        return (CONFIGURADA, "Conexão validada.")
    if status == 401:
        if any(s in _corpo_para_classificar(resp) for s in _SINAIS_EXPIRACAO):
            return (EXPIRADA, "Credencial expirada (HTTP 401).")
        return (INVALIDA, "Credencial inválida (HTTP 401).")
    if status == 403:
        return (SEM_PERMISSAO, "Autenticou, mas sem permissão para o recurso (HTTP 403).")
    if status == 429:
        return (INDISPONIVEL, "Limite de requisições atingido no teste (HTTP 429).")
    if status >= 500:
        return (INDISPONIVEL, f"Serviço externo indisponível (HTTP {status}).")
    if status == 404:
        return (INVALIDA, "Recurso não encontrado (HTTP 404).")
    return (INVALIDA, f"Resposta inesperada da integração (HTTP {status}).")


def _estado_por_excecao(exc: BaseException) -> TesteResultado:
    if isinstance(exc, httpx.TimeoutException):
        return (INDISPONIVEL, "Tempo de resposta esgotado (timeout).")
    if isinstance(exc, httpx.TransportError):  # ConnectError, ReadError, DNS…
        return (INDISPONIVEL, f"Falha de conexão ({type(exc).__name__}).")
    if isinstance(exc, httpx.HTTPError):
        return (INDISPONIVEL, f"Falha de comunicação ({type(exc).__name__}).")
    return (INDISPONIVEL, f"Erro inesperado no teste ({type(exc).__name__}).")


async def _probe(
    method: str, url: str, *,
    headers: dict | None = None,
    data: dict | None = None,
    json: dict | None = None,
    timeout: float = _TIMEOUT_PADRAO,
) -> TesteResultado:
    """Faz UMA requisição e mapeia status/exceção em estado. Nunca loga o header
    de auth, o corpo, nem a URL (podem carregar token)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method, url, headers=headers, data=data, json=json,
            )
    except Exception as exc:  # noqa: BLE001 — qualquer falha de rede vira indisponivel
        return _estado_por_excecao(exc)
    return _estado_por_resposta(resp)


# ── Testadores por integração ────────────────────────────────────────────────

async def testar_datajud() -> TesteResultado:
    """Query mínima (size=0) no endpoint público do DataJud com header APIKey.
    Espelha datajud_service._datajud_search sem tocar em processo real."""
    s = get_settings()
    if _vazio(s.DATAJUD_API_KEY):
        return (AUSENTE, "DATAJUD_API_KEY não configurada.")
    base = (s.DATAJUD_BASE_URL or "https://api-publica.datajud.cnj.jus.br").rstrip("/")
    url = f"{base}/api_publica_tjmg/_search"
    headers = {
        "Authorization": f"APIKey {s.DATAJUD_API_KEY}",
        "Content-Type": "application/json",
    }
    # match_all + size=0 = só contagem; não retorna nem processa metadados.
    payload = {"query": {"match_all": {}}, "size": 0}
    return await _probe(
        "POST", url, headers=headers, json=payload,
        timeout=_clamp_timeout(s.DATAJUD_TIMEOUT_SECONDS),
    )


async def testar_groq() -> TesteResultado:
    """Liveness da chave Groq via GET /models (mais barato que uma completion;
    mesma intenção do groq_provider.health(), com classificação granular)."""
    s = get_settings()
    if _vazio(s.GROQ_API_KEY):
        return (AUSENTE, "GROQ_API_KEY não configurada.")
    return await _probe(
        "GET", "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {s.GROQ_API_KEY}"},
    )


async def testar_anthropic() -> TesteResultado:
    """Valida a chave Anthropic via GET /v1/models (barato). Espelha o intent do
    anthropic_provider.health() (que só checa presença) com teste real de rede."""
    s = get_settings()
    key = s.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")
    if _vazio(key):
        return (AUSENTE, "ANTHROPIC_API_KEY não configurada.")
    return await _probe(
        "GET", "https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )


async def testar_maritaca() -> TesteResultado:
    """Valida a chave Maritaca via GET /models (endpoint OpenAI-compatible).
    Reusa MARITACA_BASE_URL do maritaca_provider; sem consumir tokens de chat."""
    s = get_settings()
    if _vazio(s.MARITACA_API_KEY):
        return (AUSENTE, "MARITACA_API_KEY não configurada.")
    base = (s.MARITACA_BASE_URL or "https://chat.maritaca.ai/api").rstrip("/")
    return await _probe(
        "GET", f"{base}/models",
        headers={"Authorization": f"Bearer {s.MARITACA_API_KEY}"},
    )


def _estado_infosimples_code(code: int) -> TesteResultado:
    """Infosimples devolve HTTP 200 com um `code` no corpo (padrão da API v2)."""
    if code == 200:
        return (CONFIGURADA, "Conta acessível (endpoint gratuito de saldo/conta).")
    if code in (401, 402):  # token inválido / crédito
        return (INVALIDA, f"Token recusado pela Infosimples (code {code}).")
    if code == 403:
        return (SEM_PERMISSAO, "Sem permissão na Infosimples (code 403).")
    return (INDISPONIVEL, f"Resposta inesperada da Infosimples (code {code}).")


async def testar_infosimples() -> TesteResultado:
    """Consulta o endpoint GRATUITO de conta/saldo (nunca um endpoint cobrado).
    O token vai no corpo (POST) para não ir na URL/log."""
    s = get_settings()
    token = (s.INFOSIMPLES_TOKEN or "").strip()
    if _vazio(token):
        return (AUSENTE, "INFOSIMPLES_TOKEN não configurado.")
    base = (s.INFOSIMPLES_BASE_URL
            or "https://api.infosimples.com/api/v2/consultas").rstrip("/")
    # .../api/v2/consultas → .../api/v2/account (endpoint de conta, gratuito).
    raiz = base.rsplit("/", 1)[0]
    url = f"{raiz}/account"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_PADRAO) as client:
            resp = await client.post(url, data={"token": token})
    except Exception as exc:  # noqa: BLE001
        return _estado_por_excecao(exc)
    # Erros de transporte HTTP primeiro (alguns 401/403/5xx vêm no status).
    if resp.status_code in (401, 403) or resp.status_code >= 500:
        return _estado_por_resposta(resp)
    try:
        code = int((resp.json() or {}).get("code") or resp.status_code)
    except Exception:  # noqa: BLE001 — corpo não-JSON → usa o status HTTP
        code = resp.status_code
    return _estado_infosimples_code(code)


def _estado_por_excecao_smtp(exc: BaseException) -> TesteResultado:
    import smtplib
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (INVALIDA, "Autenticação SMTP recusada (usuário/senha).")
    if isinstance(exc, smtplib.SMTPConnectError):
        return (INDISPONIVEL, "Falha ao conectar no servidor SMTP.")
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (INDISPONIVEL, "Servidor SMTP desconectou durante o teste.")
    if isinstance(exc, smtplib.SMTPException):
        return (INDISPONIVEL, f"Erro SMTP no teste ({type(exc).__name__}).")
    # socket.timeout é TimeoutError; ConnectionError/OSError = rede.
    if isinstance(exc, (TimeoutError, OSError)):
        return (INDISPONIVEL, f"Falha de rede no SMTP ({type(exc).__name__}).")
    return (INDISPONIVEL, f"Erro inesperado no teste SMTP ({type(exc).__name__}).")


async def testar_smtp() -> TesteResultado:
    """Connect + STARTTLS + LOGIN + QUIT, SEM enviar e-mail. Espelha o setup do
    notification_service.enviar_email (mesmo host/porta/credencial)."""
    s = get_settings()
    if _vazio(s.SMTP_USER, s.SMTP_PASSWORD):
        return (AUSENTE, "SMTP_USER/SMTP_PASSWORD não configurados.")
    host = s.SMTP_HOST
    porta = int(s.SMTP_PORT or 587)
    usuario, senha = s.SMTP_USER, s.SMTP_PASSWORD
    timeout = _clamp_timeout(_TIMEOUT_PADRAO)

    def _run() -> None:
        import smtplib
        servidor = smtplib.SMTP(host, porta, timeout=timeout)
        try:
            servidor.starttls()
            servidor.login(usuario, senha)
        finally:
            try:
                servidor.quit()
            except Exception:  # noqa: BLE001 — quit best-effort; o login já decidiu o teste
                pass

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        return _estado_por_excecao_smtp(exc)
    return (CONFIGURADA, "Autenticação SMTP validada (sem envio de e-mail).")


async def testar_whatsapp_zapi() -> TesteResultado:
    """Status da instância na Z-API. Espelha a URL do notification_service; o
    Client-Token (quando presente) vai só no header, nunca em log."""
    s = get_settings()
    if _vazio(s.ZAPI_INSTANCE_ID, s.ZAPI_TOKEN):
        return (AUSENTE, "ZAPI_INSTANCE_ID/ZAPI_TOKEN não configurados.")
    url = (
        f"https://api.z-api.io/instances/{s.ZAPI_INSTANCE_ID}"
        f"/token/{s.ZAPI_TOKEN}/status"
    )
    headers: dict[str, str] = {}
    if (s.ZAPI_CLIENT_TOKEN or "").strip():
        headers["Client-Token"] = s.ZAPI_CLIENT_TOKEN
    return await _probe("GET", url, headers=headers)


async def testar_nfse() -> TesteResultado:
    """OAuth2 client_credentials no auth_url da NuvemFiscal; o token é DESCARTADO
    (só valida as credenciais). Espelha nuvem_fiscal._obter_token."""
    s = get_settings()
    if _vazio(s.NFSE_NUVEMFISCAL_CLIENT_ID, s.NFSE_NUVEMFISCAL_CLIENT_SECRET):
        return (AUSENTE, "NFSE_NUVEMFISCAL_CLIENT_ID/CLIENT_SECRET não configurados.")
    auth = (s.NFSE_NUVEMFISCAL_AUTH_URL
            or "https://auth.nuvemfiscal.com.br").rstrip("/")
    dados = {
        "grant_type": "client_credentials",
        "client_id": s.NFSE_NUVEMFISCAL_CLIENT_ID,
        "client_secret": s.NFSE_NUVEMFISCAL_CLIENT_SECRET,
        "scope": "nfse empresa",
    }
    estado, detalhe = await _probe("POST", f"{auth}/oauth/token", data=dados)
    if estado == CONFIGURADA:
        return (CONFIGURADA, "OAuth client_credentials validado (token descartado).")
    return (estado, detalhe)


async def testar_transparencia() -> TesteResultado:
    """Listagem barata (CEIS, página 1) com header chave-api-dados — dado
    público, gratuito; valida a chave do Portal da Transparência."""
    s = get_settings()
    if _vazio(s.TRANSPARENCIA_API_KEY):
        return (AUSENTE, "TRANSPARENCIA_API_KEY não configurada.")
    base = (s.TRANSPARENCIA_BASE_URL
            or "https://api.portaldatransparencia.gov.br/api-de-dados").rstrip("/")
    return await _probe(
        "GET", f"{base}/ceis?pagina=1",
        headers={"chave-api-dados": s.TRANSPARENCIA_API_KEY,
                 "Accept": "application/json"},
    )


async def testar_langfuse() -> TesteResultado:
    """Autentica no self-hosted via Basic (public:secret) num endpoint leve
    (/api/public/projects). Valida o par de chaves sem enviar traces."""
    s = get_settings()
    if _vazio(s.LANGFUSE_PUBLIC_KEY, s.LANGFUSE_SECRET_KEY):
        return (AUSENTE, "LANGFUSE_PUBLIC_KEY/SECRET_KEY não configurados.")
    host = (s.LANGFUSE_HOST or "").rstrip("/")
    if _vazio(host):
        return (INDISPONIVEL, "LANGFUSE_HOST não configurado.")
    return await _probe(
        "GET", f"{host}/api/public/projects",
        headers={"Authorization": _basic_auth(s.LANGFUSE_PUBLIC_KEY,
                                              s.LANGFUSE_SECRET_KEY)},
    )


async def testar_push_vapid() -> TesteResultado:
    """Par de chaves VAPID é LOCAL (Web Push) — não há endpoint remoto barato e
    seguro para exercê-lo. Sem testador automático: só presença (configurada)
    vs ausência."""
    s = get_settings()
    if _vazio(s.VAPID_PUBLIC_KEY, s.VAPID_PRIVATE_KEY):
        return (AUSENTE, "VAPID_PUBLIC_KEY/PRIVATE_KEY não configurados.")
    return (CONFIGURADA, "Par VAPID presente (chave local; sem teste remoto).")


# ── Registro provider_key → testador ─────────────────────────────────────────
TESTERS: dict[str, Callable[[], Awaitable[TesteResultado]]] = {
    "datajud": testar_datajud,
    "groq": testar_groq,
    "anthropic": testar_anthropic,
    "maritaca": testar_maritaca,
    "infosimples": testar_infosimples,
    "smtp": testar_smtp,
    "whatsapp_zapi": testar_whatsapp_zapi,
    "nfse": testar_nfse,
    "transparencia": testar_transparencia,
    "langfuse": testar_langfuse,
    "push_vapid": testar_push_vapid,
}


async def testar_provider(provider_key: str) -> TesteResultado:
    """Executa o testador do provider. Provider sem testador → `configurada`
    (metadado, sem teste) — o vocabulário admite esse estado explicitamente."""
    tester = TESTERS.get(provider_key)
    if tester is None:
        return (CONFIGURADA, "Sem testador automático para este provider.")
    return await tester()
