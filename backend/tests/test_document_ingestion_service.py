from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import document_ingestion_service as svc
from app.services.document_storage_uow import (
    EstadoStorageInvalidoError,
    EstadoStorageLocal,
)
from app.services.malware_scan_service import (
    MalwareScanIndisponivelError,
    MalwareScanStatus,
    ResultadoMalwareScan,
)


class StreamBytes:
    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise AssertionError("ingestão não pode solicitar leitura ilimitada")
        if self._offset >= len(self._conteudo):
            return b""
        fim = min(self._offset + size, len(self._conteudo))
        chunk = self._conteudo[self._offset:fim]
        self._offset = fim
        return chunk


class ScannerFalso:
    def __init__(self, status: MalwareScanStatus) -> None:
        self.status = status
        self.caminho_recebido: Path | None = None

    async def escanear(self, caminho: Path) -> ResultadoMalwareScan:
        self.caminho_recebido = caminho
        assert caminho.exists()
        assert caminho.name.startswith(".")
        assert caminho.name.endswith(".uploading")
        return ResultadoMalwareScan(self.status)


class ScannerIndisponivel:
    async def escanear(self, caminho: Path) -> ResultadoMalwareScan:
        assert caminho.exists()
        raise MalwareScanIndisponivelError("scanner antimalware indisponível")

@pytest.mark.asyncio
async def test_prepara_id_path_mime_e_hash_server_side(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        svc,
        "validar_conteudo",
        lambda ext, amostra: "application/pdf",
    )
    instante = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-1.7\nconteudo"),
        filename="../../pasta/parte-sentinela.pdf",
        upload_root=tmp_path,
        max_bytes=1024 * 1024,
        agora=instante,
    )

    assert ing.filename == "parte-sentinela.pdf"
    assert ing.ext == ".pdf"
    assert ing.mimetype == "application/pdf"
    assert ing.malware_scan_status is MalwareScanStatus.NAO_SOLICITADO
    assert ing.filepath.startswith("2026/08/")
    assert ing.filepath.endswith(".pdf")
    assert "parte-sentinela" not in ing.filepath
    assert "\\" not in ing.filepath
    assert ing.doc_id in ing.filepath
    assert ing.sha256
    assert ing.size_bytes == len(b"%PDF-1.7\nconteudo")
    assert ing.full_path.parent == tmp_path / "2026" / "08"
    assert ing.storage.estado is EstadoStorageLocal.STAGING

    async with ing:
        ing.promover()
        ing.confirmar()

    assert ing.full_path.exists()


@pytest.mark.asyncio
async def test_nome_windows_e_truncado_sem_influenciar_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    nome_longo = "C:\\cliente\\" + ("a" * 280) + ".pdf"

    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-x"),
        filename=nome_longo,
        upload_root=tmp_path,
        max_bytes=1024,
    )

    assert len(ing.filename) == 255
    assert "C:" not in ing.filename
    assert "cliente" not in ing.filename
    assert ing.doc_id in ing.filepath
    assert "a" * 40 not in ing.filepath
    ing.storage.compensar()


@pytest.mark.asyncio
async def test_extensao_invalida_falha_antes_de_criar_staging(tmp_path: Path):
    with pytest.raises(HTTPException) as exc:
        await svc.preparar_ingestao_documento_local(
            StreamBytes(b"conteudo"),
            filename="arquivo.exe",
            upload_root=tmp_path,
            max_bytes=1024,
        )

    assert exc.value.status_code == 422
    assert not list(tmp_path.rglob("*.uploading"))


@pytest.mark.asyncio
async def test_mime_invalido_compensa_staging(tmp_path: Path, monkeypatch):
    def rejeitar(ext: str, amostra: bytes) -> str:
        raise HTTPException(status_code=415, detail="conteúdo incompatível")

    monkeypatch.setattr(svc, "validar_conteudo", rejeitar)

    with pytest.raises(HTTPException) as exc:
        await svc.preparar_ingestao_documento_local(
            StreamBytes(b"nao-e-pdf"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
        )

    assert exc.value.status_code == 415
    assert not list(tmp_path.rglob("*.uploading"))
    assert not list(tmp_path.rglob(".*.uploading"))


@pytest.mark.asyncio
async def test_scanner_limpo_recebe_staging_antes_da_promocao(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    scanner = ScannerFalso(MalwareScanStatus.LIMPO)

    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-clean"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
        scanner=scanner,
    )

    assert ing.malware_scan_status is MalwareScanStatus.LIMPO
    assert scanner.caminho_recebido is not None
    assert scanner.caminho_recebido.exists()
    assert not ing.full_path.exists()

    async with ing:
        ing.promover()
        with pytest.raises(EstadoStorageInvalidoError):
            _ = ing.storage.caminho_staging_para_validacao
        ing.confirmar()

    assert ing.full_path.exists()


@pytest.mark.asyncio
async def test_scanner_infectado_bloqueia_e_remove_quarentena(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    scanner = ScannerFalso(MalwareScanStatus.INFECTADO)

    with pytest.raises(svc.MalwareDetectadoError, match="política antimalware"):
        await svc.preparar_ingestao_documento_local(
            StreamBytes(b"%PDF-conteudo-bloqueado"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
            scanner=scanner,
        )

    assert scanner.caminho_recebido is not None
    assert not scanner.caminho_recebido.exists()
    assert not list(tmp_path.rglob(".*.uploading"))
    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_scanner_solicitado_indisponivel_falha_fechado_e_limpa_staging(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")

    with pytest.raises(MalwareScanIndisponivelError):
        await svc.preparar_ingestao_documento_local(
            StreamBytes(b"%PDF-scanner-offline"),
            filename="arquivo.pdf",
            upload_root=tmp_path,
            max_bytes=1024,
            scanner=ScannerIndisponivel(),
        )

    assert not list(tmp_path.rglob(".*.uploading"))
    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_excecao_apos_promocao_compensa_destino(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-falha-db"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
    )

    with pytest.raises(RuntimeError, match="commit falhou"):
        async with ing:
            ing.promover()
            assert ing.full_path.exists()
            raise RuntimeError("commit falhou")

    assert ing.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not ing.full_path.exists()


@pytest.mark.asyncio
async def test_saida_sem_promover_compensa_staging(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-staging"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
    )

    async with ing:
        pass

    assert ing.storage.estado is EstadoStorageLocal.COMPENSADO
    assert not list(tmp_path.rglob(".*.uploading"))


@pytest.mark.asyncio
async def test_confirmacao_preserva_arquivo(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-confirmado"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
    )

    async with ing:
        ing.promover()
        ing.confirmar()

    assert ing.storage.estado is EstadoStorageLocal.CONFIRMADO
    assert ing.full_path.exists()


@pytest.mark.asyncio
async def test_datetime_naive_e_tratado_como_utc(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(svc, "validar_conteudo", lambda ext, amostra: "application/pdf")
    ing = await svc.preparar_ingestao_documento_local(
        StreamBytes(b"%PDF-naive"),
        filename="arquivo.pdf",
        upload_root=tmp_path,
        max_bytes=1024,
        agora=datetime(2026, 1, 2, 3, 4),
    )

    assert ing.filepath.startswith("2026/01/")
    ing.storage.compensar()
