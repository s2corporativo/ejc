"""upload_lote_service — extraído de raio_x.py/legal_chat.py (achado F2).

Cobre a lógica compartilhada isoladamente: teto de lote, extensão, tamanho,
dedup por hash e gravação em disco sob o subdiretório do chamador.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings
from app.services.upload_lote_service import processar_lote


def _upload(nome: str, conteudo: bytes) -> UploadFile:
    return UploadFile(filename=nome, file=BytesIO(conteudo))


async def test_lote_acima_do_teto_levanta_422():
    with pytest.raises(HTTPException) as exc:
        await processar_lote(
            [_upload("a.txt", b"x"), _upload("b.txt", b"y")],
            max_arquivos=1,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir="teste",
            entidade_id="e1",
        )
    assert exc.value.status_code == 422


async def test_lote_vazio_levanta_422():
    with pytest.raises(HTTPException):
        await processar_lote(
            [],
            max_arquivos=5,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir="teste",
            entidade_id="e1",
        )


async def test_extensao_nao_permitida_e_fail_soft(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    validos, duplicados, erros = await processar_lote(
        [_upload("malicioso.exe", b"conteudo")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id="e1",
    )
    assert validos == []
    assert duplicados == []
    assert erros == [{"arquivo": "malicioso.exe", "erro": "Formato não suportado"}]


async def test_arquivo_vazio_e_fail_soft(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    validos, duplicados, erros = await processar_lote(
        [_upload("vazio.txt", b"")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id="e1",
    )
    assert validos == []
    assert erros == [{"arquivo": "vazio.txt", "erro": "Arquivo vazio"}]


async def test_excede_tamanho_maximo_e_fail_soft(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(st, "MAX_UPLOAD_MB", 0, raising=False)

    validos, duplicados, erros = await processar_lote(
        [_upload("grande.txt", b"conteudo")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id="e1",
    )
    assert validos == []
    assert erros[0]["arquivo"] == "grande.txt"
    assert "Excede" in erros[0]["erro"]


async def test_duplicado_por_hash_nao_regrava_em_disco(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)
    import hashlib

    conteudo = b"mesmo conteudo"
    digest = hashlib.sha256(conteudo).hexdigest()

    validos, duplicados, erros = await processar_lote(
        [_upload("repetido.txt", conteudo)],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes={digest},
        storage_subdir="teste",
        entidade_id="e1",
    )
    assert validos == []
    assert duplicados == ["repetido.txt"]
    assert erros == []
    assert list(tmp_path.rglob("*.txt")) == []


async def test_arquivo_valido_e_gravado_em_disco_sob_subdir_da_entidade(tmp_path, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    existing_hashes: set[str] = set()
    validos, duplicados, erros = await processar_lote(
        [_upload("peticao.txt", b"conteudo real do documento")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=existing_hashes,
        storage_subdir="minha-entidade",
        entidade_id="e1",
    )
    assert erros == []
    assert duplicados == []
    assert len(validos) == 1
    arquivo = validos[0]
    assert arquivo.nome_original == "peticao.txt"
    assert arquivo.filepath.startswith("minha-entidade/")
    assert "e1" in arquivo.filepath
    assert (tmp_path / arquivo.filepath).read_bytes() == b"conteudo real do documento"
    # hash do arquivo aceito entra no conjunto mutável do chamador.
    assert arquivo.sha256 in existing_hashes
