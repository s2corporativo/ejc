# ── app/core/upload_seguro.py ─────────────────────────────────────────────────
# Leitura de UploadFile com teto de tamanho aplicado DURANTE a leitura, não
# depois dela (DADOS-019).
#
# `await file.read()` lê o corpo inteiro para a RAM antes de qualquer checagem
# de tamanho — o teto (`MAX_UPLOAD_MB` etc.) só reprovava DEPOIS que o arquivo
# inteiro já estava alocado. Um upload de alguns GB (tamanho de arquivo não é
# limitado pelo `Content-Length` do cliente, que pode mentir) consome a RAM do
# processo antes de a validação sequer rodar — o teto existia no papel, mas
# não protegia o processo que deveria proteger.
from __future__ import annotations

from fastapi import HTTPException, UploadFile

_CHUNK_BYTES = 1024 * 1024  # 1 MiB por leitura


async def ler_upload_com_teto(
    file: UploadFile, limite_bytes: int, *, mensagem_413: str | None = None
) -> bytes:
    """Lê `file` em blocos de 1 MiB, parando no PRIMEIRO byte acima do teto.

    Nunca mantém mais que `limite_bytes + _CHUNK_BYTES` na RAM — mesmo para um
    corpo de streaming arbitrariamente grande. Levanta 413 assim que o teto é
    ultrapassado, sem terminar de ler o restante do corpo.
    """
    partes: list[bytes] = []
    total = 0
    while True:
        bloco = await file.read(_CHUNK_BYTES)
        if not bloco:
            break
        partes.append(bloco)
        total += len(bloco)
        if total > limite_bytes:
            raise HTTPException(
                status_code=413,
                detail=mensagem_413 or f"Arquivo excede o limite de {limite_bytes} bytes.",
            )
    return b"".join(partes)
