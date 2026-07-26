# ── app/services/visual_law_files.py ─────────────────────────────────────────
# Arnês ÚNICO de persistência/download dos PDFs Visual Law dos verticais
# (Tributário, Ambiental, LGPD, Previdenciário, Provas, Trabalhista, Data Room).
#
# Motivo (#27): cada router copiava verbatim três primitivas SENSÍVEIS —
# diretório de saída, purga por TTL (retenção LGPD: os PDFs carregam PII/dados
# fiscais de terceiros) e a validação anti-path-traversal do arquivo_id como
# UUID. Cópia manual é propensa a omitir o guard num vertical novo. Centralizar
# aqui garante que todos herdam a MESMA proteção.
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()

# TTL de retenção dos PDFs gerados (segundos). Configurável via settings quando
# existir; senão 24h — janela suficiente p/ o advogado baixar, sem reter PII.
PDF_TTL_SEGUNDOS = int(getattr(settings, "PDF_TTL_SEGUNDOS", 24 * 3600))

# TTL do TOKEN de download assinado (segundos). Muito mais curto que a retenção
# do arquivo — a URL só precisa viver o suficiente para o navegador abrir o
# blob logo após a geração. Configurável via settings/env quando existir.
PDF_DOWNLOAD_TTL_SEGUNDOS = int(
    getattr(settings, "PDF_DOWNLOAD_TTL_SEGUNDOS", os.getenv("PDF_DOWNLOAD_TTL_SEGUNDOS", 900))
)

# UUID canônico (o único formato aceito para o nome de arquivo — barra traversal).
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def preparar_dir(subdir: str) -> str:
    """Diretório de saída dos PDFs de um vertical (UPLOAD_DIR/subdir), criado."""
    out_dir = os.path.join(settings.UPLOAD_DIR, subdir)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def purgar_antigos(out_dir: str, ttl_segundos: int = PDF_TTL_SEGUNDOS) -> None:
    """Remoção best-effort dos PDFs mais antigos que o TTL (retenção LGPD).
    Sem estado externo, tolerante a falhas — nunca quebra a resposta."""
    try:
        agora = time.time()
        for nome in os.listdir(out_dir):
            if not nome.endswith(".pdf"):
                continue
            caminho = os.path.join(out_dir, nome)
            try:
                if agora - os.path.getmtime(caminho) > ttl_segundos:
                    os.remove(caminho)
            except OSError:
                continue
    except OSError:
        pass


def validar_uuid(arquivo_id: str) -> None:
    """Valida o arquivo_id como UUID; 400 caso contrário. Barra path traversal
    (o id é interpolado no nome do arquivo servido ao cliente)."""
    if not _UUID_RE.fullmatch(arquivo_id or ""):
        raise HTTPException(status_code=422, detail="Identificador de relatório inválido.")


def caminho_pdf(subdir: str, prefixo: str, arquivo_id: str) -> str:
    """Valida o UUID e devolve o caminho seguro do PDF (subdir/prefixo+id.pdf)."""
    validar_uuid(arquivo_id)
    return os.path.join(preparar_dir(subdir), f"{prefixo}{arquivo_id}.pdf")


# ── Token de download assinado (DOC-086/DOC-087) ──────────────────────────────
# O UUID sozinho autoriza o download a QUALQUER usuário autenticado que conheça
# o id (o artefato carrega PII/dados fiscais de terceiros). O token amarra o
# arquivo ao usuário que o gerou (e, quando aplicável, ao cliente/caso), com
# expiração curta. É HMAC-SHA256 sobre SECRET_KEY — stateless, sem migration.

def _segredo() -> bytes:
    return ((getattr(get_settings(), "SECRET_KEY", "") or "")).encode("utf-8")


def _b64u(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _assinar(corpo: str) -> str:
    mac = hmac.new(_segredo(), corpo.encode("ascii"), hashlib.sha256).digest()
    return _b64u(mac)


def emitir_token(
    arquivo_id: str,
    *,
    user_id: str,
    client_id: str | None = None,
    caso_id: str | None = None,
    ttl: int | None = None,
) -> str:
    """Emite um token assinado (arquivo_id + user_id [+ client_id/caso_id] + exp).

    Deve ser chamado na GERAÇÃO do artefato; o valor entra na `download_url`
    (query `?t=`). O download revalida com `validar_token`.
    """
    validar_uuid(arquivo_id)
    exp = int(time.time()) + int(ttl if ttl is not None else PDF_DOWNLOAD_TTL_SEGUNDOS)
    payload = {
        "a": arquivo_id,
        "u": str(user_id or ""),
        "c": str(client_id) if client_id else "",
        "k": str(caso_id) if caso_id else "",
        "e": exp,
    }
    corpo = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{corpo}.{_assinar(corpo)}"


def validar_token(
    token: str | None,
    arquivo_id: str,
    cu,
    *,
    client_id: str | None = None,
    caso_id: str | None = None,
) -> dict:
    """Valida assinatura + expiração + binding do token ao arquivo/usuário.

    - `cu` é o usuário autenticado: o token precisa ter sido emitido para ele.
    - `client_id`/`caso_id`, quando passados, precisam bater com o binding do
      token (RIPD: o download reavalia o vínculo com o cliente — DOC-087).
    Levanta 403 em qualquer divergência. Retorna o payload em caso de sucesso.
    """
    validar_uuid(arquivo_id)
    if not token or "." not in token:
        raise HTTPException(status_code=403, detail="Token de download ausente ou inválido.")
    corpo, _, assinatura = token.partition(".")
    if not hmac.compare_digest(assinatura, _assinar(corpo)):
        raise HTTPException(status_code=403, detail="Token de download inválido.")
    try:
        payload = json.loads(urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    except Exception:
        raise HTTPException(status_code=403, detail="Token de download malformado.")
    if int(payload.get("e", 0)) < int(time.time()):
        raise HTTPException(
            status_code=403,
            detail="Token de download expirado — gere o documento novamente.",
        )
    if payload.get("a") != arquivo_id:
        raise HTTPException(
            status_code=403, detail="Token de download não corresponde ao arquivo."
        )
    if payload.get("u") != str(getattr(cu, "id", "") or ""):
        raise HTTPException(
            status_code=403, detail="Token de download emitido para outro usuário."
        )
    if client_id is not None and payload.get("c") != str(client_id):
        raise HTTPException(
            status_code=403, detail="Token de download não vinculado a este cliente."
        )
    if caso_id is not None and payload.get("k") != str(caso_id):
        raise HTTPException(
            status_code=403, detail="Token de download não vinculado a este caso."
        )
    return payload
