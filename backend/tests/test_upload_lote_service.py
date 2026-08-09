"""Regressões do serviço compartilhado de upload em lote."""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings
from app.services.upload_lote_service import processar_lote

ENTIDADE_ID = "e1111111-1111-1111-1111-111111111111"


def _upload(nome: str, conteudo: bytes) -> UploadFile:
    return UploadFile(filename=nome, file=BytesIO(conteudo))


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Isola a configuração cacheada e a restaura automaticamente por teste."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)
    return tmp_path


async def test_lote_acima_do_teto_levanta_422():
    with pytest.raises(HTTPException) as exc:
        await processar_lote(
            [_upload("a.txt", b"x"), _upload("b.txt", b"y")],
            max_arquivos=1,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir="teste",
            entidade_id=ENTIDADE_ID,
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
            entidade_id=ENTIDADE_ID,
        )


async def test_extensao_nao_permitida_e_fail_soft(upload_dir):
    validos, duplicados, erros = await processar_lote(
        [_upload("malicioso.exe", b"conteudo")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id=ENTIDADE_ID,
    )
    assert validos == []
    assert duplicados == []
    assert erros == [{"arquivo": "malicioso.exe", "erro": "Formato não suportado"}]


async def test_arquivo_vazio_e_fail_soft(upload_dir):
    validos, duplicados, erros = await processar_lote(
        [_upload("vazio.txt", b"")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id=ENTIDADE_ID,
    )
    assert validos == []
    assert erros == [{"arquivo": "vazio.txt", "erro": "Arquivo vazio"}]


async def test_excede_tamanho_maximo_e_fail_soft(upload_dir, monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "MAX_UPLOAD_MB", 0, raising=False)

    validos, duplicados, erros = await processar_lote(
        [_upload("grande.txt", b"conteudo")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=set(),
        storage_subdir="teste",
        entidade_id=ENTIDADE_ID,
    )
    assert validos == []
    assert duplicados == []
    assert erros[0]["arquivo"] == "grande.txt"
    assert "Excede" in erros[0]["erro"]


async def test_duplicado_por_hash_nao_regrava_em_disco(upload_dir):
    import hashlib

    conteudo = b"mesmo conteudo"
    digest = hashlib.sha256(conteudo).hexdigest()
    validos, duplicados, erros = await processar_lote(
        [_upload("repetido.txt", conteudo)],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes={digest},
        storage_subdir="teste",
        entidade_id=ENTIDADE_ID,
    )
    assert validos == []
    assert duplicados == ["repetido.txt"]
    assert erros == []
    assert list(upload_dir.rglob("*.txt")) == []


async def test_arquivo_valido_e_gravado_sob_subdir_da_entidade(upload_dir):
    existing_hashes: set[str] = set()
    validos, duplicados, erros = await processar_lote(
        [_upload("peticao.txt", b"conteudo real do documento")],
        max_arquivos=5,
        extensoes_permitidas={".txt"},
        existing_hashes=existing_hashes,
        storage_subdir="minha-entidade",
        entidade_id=ENTIDADE_ID,
    )
    assert erros == []
    assert duplicados == []
    assert len(validos) == 1
    arquivo = validos[0]
    assert arquivo.nome_original == "peticao.txt"
    assert arquivo.filepath.startswith("minha-entidade/")
    assert ENTIDADE_ID in arquivo.filepath
    assert (upload_dir / arquivo.filepath).read_bytes() == b"conteudo real do documento"
    assert arquivo.sha256 in existing_hashes
    assert not hasattr(arquivo, "content")


@pytest.mark.parametrize(
    "storage_subdir,entidade_id",
    [
        ("../fora", ENTIDADE_ID),
        ("..", ENTIDADE_ID),
        (".", ENTIDADE_ID),
        ("teste", "../../etc"),
        ("teste", ".."),
        ("teste", "."),
        ("/absoluto", ENTIDADE_ID),
    ],
)
async def test_segmentos_de_storage_inseguros_sao_rejeitados(
    upload_dir, storage_subdir, entidade_id
):
    with pytest.raises(ValueError):
        await processar_lote(
            [_upload("peticao.txt", b"conteudo")],
            max_arquivos=5,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir=storage_subdir,
            entidade_id=entidade_id,
        )
    assert list(upload_dir.rglob("*")) == []


async def test_destino_resolvido_permanece_na_raiz_mesmo_com_symlink(
    tmp_path, monkeypatch
):
    """Defesa em profundidade: um subdiretório symlink não pode escapar da raiz."""
    raiz = tmp_path / "uploads"
    fora = tmp_path / "fora"
    raiz.mkdir()
    fora.mkdir()
    (raiz / "teste").symlink_to(fora, target_is_directory=True)
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(raiz), raising=False)

    with pytest.raises(ValueError, match="escapou"):
        await processar_lote(
            [_upload("peticao.txt", b"conteudo")],
            max_arquivos=5,
            extensoes_permitidas={".txt"},
            existing_hashes=set(),
            storage_subdir="teste",
            entidade_id=ENTIDADE_ID,
        )
    assert list(fora.rglob("*.txt")) == []
