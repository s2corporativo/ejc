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

import json
import os
import re
import time

from fastapi import HTTPException

from app.core.config import get_settings

settings = get_settings()

# TTL de retenção dos PDFs gerados (segundos). Configurável via settings quando
# existir; senão 24h — janela suficiente p/ o advogado baixar, sem reter PII.
PDF_TTL_SEGUNDOS = int(getattr(settings, "PDF_TTL_SEGUNDOS", 24 * 3600))

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
    Sem estado externo, tolerante a falhas — nunca quebra a resposta.
    Remove também os sidecars de binding (.origem.json) expirados."""
    try:
        agora = time.time()
        for nome in os.listdir(out_dir):
            if not (nome.endswith(".pdf") or nome.endswith(SUFIJO_ORIGEM)):
                continue
            caminho = os.path.join(out_dir, nome)
            try:
                if agora - os.path.getmtime(caminho) > ttl_segundos:
                    os.remove(caminho)
            except OSError:
                continue
    except OSError:
        pass


# ── Binding usuário↔arquivo (Auditoria 2026-09-20 §11 S2/S3/S10) ─────────────
# A confidencialidade dos arquivos gerados não pode ser apenas a não-
# adivinhabilidade do UUID (capability URL). Cada geração registra um sidecar
# com o criador; o download exige o próprio criador (ou gestão). Fail-closed:
# sidecar ausente (arquivo pré-hardening) → 403 com instrução de regenerar.
SUFIJO_ORIGEM = ".origem.json"


def registrar_origem(out_dir: str, arquivo_id: str, criado_por: str) -> None:
    """Grava o sidecar de binding do arquivo gerado. Best-effort: se falhar,
    o download será negado (fail-closed) — nunca liberar sem vínculo."""
    try:
        with open(
            os.path.join(out_dir, f"{arquivo_id}{SUFIJO_ORIGEM}"),
            "w",
            encoding="utf-8",
        ) as fh:
            json.dump({"criado_por": criado_por, "ts": time.time()}, fh)
    except OSError:
        pass


def exigir_origem(out_dir: str, arquivo_id: str, cu) -> None:
    """Impõe o binding: só o criador (ou perfil de gestão) baixa o arquivo."""
    from app.core.ownership import is_gestao

    if cu is not None and is_gestao(cu):
        return
    try:
        with open(
            os.path.join(out_dir, f"{arquivo_id}{SUFIJO_ORIGEM}"),
            encoding="utf-8",
        ) as fh:
            origem = json.load(fh)
    except (OSError, ValueError):
        raise HTTPException(
            403,
            "Arquivo sem vínculo registrado — gere o documento novamente.",
        )
    if not cu or (origem.get("criado_por") or "") != (getattr(cu, "id", "") or ""):
        raise HTTPException(
            403, "Este arquivo pertence a outro usuário — gere o seu PDF."
        )


def validar_uuid(arquivo_id: str) -> None:
    """Valida o arquivo_id como UUID; 400 caso contrário. Barra path traversal
    (o id é interpolado no nome do arquivo servido ao cliente)."""
    if not _UUID_RE.fullmatch(arquivo_id or ""):
        raise HTTPException(status_code=422, detail="Identificador de relatório inválido.")


def caminho_pdf(subdir: str, prefixo: str, arquivo_id: str) -> str:
    """Valida o UUID e devolve o caminho seguro do PDF (subdir/prefixo+id.pdf)."""
    validar_uuid(arquivo_id)
    return os.path.join(preparar_dir(subdir), f"{prefixo}{arquivo_id}.pdf")
