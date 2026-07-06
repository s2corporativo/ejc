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
