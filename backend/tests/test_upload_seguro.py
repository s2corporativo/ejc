"""ler_upload_com_teto: teto aplicado DURANTE a leitura, não depois (DADOS-019).

`await file.read()` lia o corpo inteiro para a RAM antes de qualquer checagem
de tamanho. `ler_upload_com_teto` lê em blocos e para no primeiro byte acima
do teto — nunca bufferiza mais que `limite + 1 bloco`.
"""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core.upload_seguro import ler_upload_com_teto


def _upload(conteudo: bytes) -> UploadFile:
    return UploadFile(filename="x.pdf", file=io.BytesIO(conteudo))


async def test_arquivo_dentro_do_teto_e_lido_por_completo():
    dados = b"x" * 1000
    resultado = await ler_upload_com_teto(_upload(dados), limite_bytes=2000)
    assert resultado == dados


async def test_arquivo_no_limite_exato_passa():
    dados = b"y" * 2000
    resultado = await ler_upload_com_teto(_upload(dados), limite_bytes=2000)
    assert resultado == dados


async def test_arquivo_acima_do_teto_levanta_413_sem_terminar_a_leitura():
    dados = b"z" * (5 * 1024 * 1024)  # 5 MiB — maior que vários blocos de 1 MiB
    with pytest.raises(HTTPException) as exc:
        await ler_upload_com_teto(_upload(dados), limite_bytes=1024)
    assert exc.value.status_code == 413


async def test_mensagem_customizada_e_usada_no_413():
    with pytest.raises(HTTPException) as exc:
        await ler_upload_com_teto(_upload(b"12345"), limite_bytes=2, mensagem_413="Excede o combinado")
    assert exc.value.detail == "Excede o combinado"


async def test_arquivo_vazio_devolve_bytes_vazio_sem_erro():
    resultado = await ler_upload_com_teto(_upload(b""), limite_bytes=100)
    assert resultado == b""


async def test_le_em_blocos_nunca_bufferiza_mais_que_teto_mais_um_bloco(monkeypatch):
    """Prova que a leitura é DE FATO incremental — não um `.read()` cru seguido
    de corte. Um arquivo bem maior que o teto precisa gerar MÚLTIPLAS chamadas
    de `.read(n)`, não uma única leitura do corpo inteiro."""
    from app.core import upload_seguro

    monkeypatch.setattr(upload_seguro, "_CHUNK_BYTES", 10)  # blocos pequenos p/ o teste
    chamadas = {"n": 0}
    upload = _upload(b"a" * 100)
    original_read = upload.read

    async def _read_contado(size=-1):
        chamadas["n"] += 1
        return await original_read(size)

    monkeypatch.setattr(upload, "read", _read_contado)

    with pytest.raises(HTTPException):
        await ler_upload_com_teto(upload, limite_bytes=25)

    # Parou perto do teto (25 bytes / 10 por bloco ≈ 3 leituras), não leu o
    # arquivo inteiro (100 bytes / 10 = 10 leituras) antes de reprovar.
    assert chamadas["n"] <= 4
