"""Foto de perfil (avatar) — validação de upload (users.py).

Cobre a camada de validação pura (_validar_avatar), sem banco:
magic bytes reais de PNG/JPEG/WebP, content-type inválido, conteúdo
que não bate com imagem e limite de 2MB. Mesmo espírito dos demais
testes unitários da suíte (sem Postgres real).
"""
import struct
import zlib

import pytest
from fastapi import HTTPException

from app.routers.users import (
    AVATAR_MAX_BYTES,
    AVATAR_MIME_EXT,
    _validar_avatar,
)


def _png_minimo() -> bytes:
    """PNG 1x1 válido (magic bytes reais reconhecidos pelo libmagic)."""
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


JPEG_MINIMO = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_MINIMO = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 "


def test_png_valido_aceito():
    mime, ext = _validar_avatar(_png_minimo(), "image/png")
    assert mime == "image/png"
    assert ext == ".png"


def test_jpeg_valido_aceito():
    mime, ext = _validar_avatar(JPEG_MINIMO, "image/jpeg")
    assert (mime, ext) == ("image/jpeg", ".jpg")


def test_webp_valido_aceito():
    mime, ext = _validar_avatar(WEBP_MINIMO, "image/webp")
    assert (mime, ext) == ("image/webp", ".webp")


def test_content_type_invalido_rejeitado_415():
    with pytest.raises(HTTPException) as exc:
        _validar_avatar(_png_minimo(), "application/pdf")
    assert exc.value.status_code == 415


def test_content_type_ausente_rejeitado_415():
    with pytest.raises(HTTPException) as exc:
        _validar_avatar(_png_minimo(), None)
    assert exc.value.status_code == 415


def test_conteudo_nao_imagem_rejeitado_415():
    """content-type mente (diz PNG) mas o conteúdo é PDF — magic bytes barram."""
    with pytest.raises(HTTPException) as exc:
        _validar_avatar(b"%PDF-1.7 conteudo qualquer", "image/png")
    assert exc.value.status_code == 415


def test_extensao_vem_do_mime_real_nao_do_content_type():
    """Conteúdo PNG declarado como JPEG: ext segue o magic byte (PNG)."""
    mime, ext = _validar_avatar(_png_minimo(), "image/jpeg")
    assert (mime, ext) == ("image/png", ".png")


def test_arquivo_grande_rejeitado_413():
    grande = _png_minimo() + b"\x00" * (AVATAR_MAX_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        _validar_avatar(grande, "image/png")
    assert exc.value.status_code == 413


def test_mapa_mime_cobre_somente_formatos_seguros():
    assert set(AVATAR_MIME_EXT) == {"image/jpeg", "image/png", "image/webp"}
