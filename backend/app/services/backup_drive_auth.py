"""Autenticação exclusiva do backup no Google Drive.

A integração de conhecimento usa escopo somente leitura por desenho. O backup
precisa de escrita e, portanto, não deve ampliar silenciosamente a credencial do
RAG. Este módulo prefere credenciais exclusivas ``BACKUP_GOOGLE_DRIVE_*`` e só
reutiliza ``GOOGLE_DRIVE_*`` quando o modo ``inherit`` for escolhido ou quando
``auto`` não encontrar uma credencial dedicada.

Nenhum segredo é devolvido por ``auth_status`` ou registrado em log.
"""
from __future__ import annotations

import json
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build

DRIVE_WRITE_SCOPE = "https://www.googleapis.com/auth/drive"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def auth_mode() -> str:
    mode = _env("BACKUP_GOOGLE_DRIVE_AUTH_MODE").lower() or "auto"
    if mode not in {"auto", "oauth", "service_account", "inherit"}:
        raise RuntimeError(
            "BACKUP_GOOGLE_DRIVE_AUTH_MODE inválido. Use auto, oauth, "
            "service_account ou inherit."
        )
    return mode


def auth_status() -> dict[str, Any]:
    """Retorna somente presença/completude, sem valores secretos."""
    oauth_user_file = bool(_env("BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE"))
    oauth_user_json = bool(_env("BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON"))
    oauth_client_id = bool(_env("BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_ID"))
    oauth_client_secret = bool(_env("BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET"))
    oauth_refresh_token = bool(_env("BACKUP_GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN"))
    service_account_file = bool(
        _env("BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE")
    )
    service_account_json = bool(
        _env("BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
    )
    oauth_trio_completo = oauth_client_id and oauth_client_secret and oauth_refresh_token
    credencial_dedicada = any(
        (
            service_account_file,
            service_account_json,
            oauth_user_file,
            oauth_user_json,
            oauth_trio_completo,
        )
    )
    if service_account_json:
        source = "service_account_json"
    elif service_account_file:
        source = "service_account_file"
    elif oauth_user_json:
        source = "oauth_user_json"
    elif oauth_user_file:
        source = "oauth_user_file"
    elif oauth_trio_completo:
        source = "oauth_refresh_token"
    else:
        source = "none"
    return {
        "auth_mode": auth_mode(),
        "credential_source": source,
        "credencial_dedicada_configurada": credencial_dedicada,
        "oauth_user_file_configurado": oauth_user_file,
        "oauth_user_json_configurado": oauth_user_json,
        "oauth_client_id_configurado": oauth_client_id,
        "oauth_client_secret_configurado": oauth_client_secret,
        "oauth_refresh_token_configurado": oauth_refresh_token,
        "oauth_trio_completo": oauth_trio_completo,
        "service_account_file_configurado": service_account_file,
        "service_account_json_configurado": service_account_json,
    }


def _refresh_if_needed(creds):
    if not creds.valid and getattr(creds, "refresh_token", None):
        creds.refresh(Request())
    return creds


def _service_account_dedicated():
    raw_json = _env("BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
    path = _env("BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE")
    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON inválido"
            ) from exc
        return service_account.Credentials.from_service_account_info(
            info, scopes=[DRIVE_WRITE_SCOPE]
        )
    if path:
        if not os.path.exists(path):
            raise RuntimeError(
                "BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE não encontrado"
            )
        return service_account.Credentials.from_service_account_file(
            path, scopes=[DRIVE_WRITE_SCOPE]
        )
    return None


def _oauth_dedicated():
    raw_json = _env("BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON")
    path = _env("BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE")
    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON inválido") from exc
        creds = user_credentials.Credentials.from_authorized_user_info(
            info, scopes=[DRIVE_WRITE_SCOPE]
        )
        return _refresh_if_needed(creds)
    if path:
        if not os.path.exists(path):
            raise RuntimeError("BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE não encontrado")
        creds = user_credentials.Credentials.from_authorized_user_file(
            path, scopes=[DRIVE_WRITE_SCOPE]
        )
        return _refresh_if_needed(creds)

    client_id = _env("BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_ID")
    client_secret = _env("BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET")
    refresh_token = _env("BACKUP_GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        creds = user_credentials.Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=[DRIVE_WRITE_SCOPE],
        )
        return _refresh_if_needed(creds)
    return None


def _inherited_credentials():
    """Compatibilidade explícita com as credenciais do conector de conhecimento."""
    from app.services import google_drive_service as gdrive

    creds = gdrive._build_credentials()
    if isinstance(creds, service_account.Credentials):
        return creds.with_scopes([DRIVE_WRITE_SCOPE])
    creds = user_credentials.Credentials(
        token=None,
        refresh_token=getattr(creds, "refresh_token", None),
        token_uri=getattr(creds, "token_uri", None) or GOOGLE_TOKEN_URI,
        client_id=getattr(creds, "client_id", None),
        client_secret=getattr(creds, "client_secret", None),
        scopes=[DRIVE_WRITE_SCOPE],
    )
    return _refresh_if_needed(creds)


def build_credentials():
    """Constrói credencial com escrita, preferindo identidade exclusiva.

    ``auto``: service account dedicada → OAuth dedicado → credencial herdada.
    ``service_account`` e ``oauth`` são fail-closed: não caem para outra fonte.
    ``inherit`` preserva deliberadamente o comportamento legado.
    """
    mode = auth_mode()
    if mode in {"auto", "service_account"}:
        creds = _service_account_dedicated()
        if creds is not None:
            return creds
        if mode == "service_account":
            raise RuntimeError(
                "Credencial exclusiva de service account do backup ausente. "
                "Configure BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON ou "
                "BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE."
            )

    if mode in {"auto", "oauth"}:
        creds = _oauth_dedicated()
        if creds is not None:
            return creds
        if mode == "oauth":
            raise RuntimeError(
                "Credencial OAuth exclusiva do backup ausente. Configure "
                "BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON/FILE ou CLIENT_ID, "
                "CLIENT_SECRET e REFRESH_TOKEN."
            )

    if mode in {"auto", "inherit"}:
        return _inherited_credentials()

    raise RuntimeError("Credencial Google Drive do backup não configurada")


def build_client():
    return build(
        "drive",
        "v3",
        credentials=build_credentials(),
        cache_discovery=False,
    )
