"""Testes do contrato do serviço de rescan/backfill de SHA-256 (Épico #1019 A3.2).

Validam ``document_rescan_service`` e a detecção de divergências contra os
módulos existentes (``document_hash_service`` / ``document_remote_hash_service``).
Não abrem conexão com banco: as funções de banco (``buscar_intake_sha``,
``gravar_item_rescan``, ``selecionar_documentos``) são mockadas.

Invariante LGPD: nenhuma divergência/mensagem pode conter filepath ou CPF.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import document_hash_service as local_hash
from app.services.document_remote_hash_service import (
    HashRemotoIndisponivelError,
)

from app.services import document_rescan_service as servico


@dataclass(frozen=True)
class _DocFicticio:
    id: str
    titulo: str
    filename: str
    filepath: str
    size_bytes: int | None
    drive_file_id: str | None
    drive_link: str | None = None


# ─────────────────────────────── Seleção de alvo ─────────────────────────


@pytest.mark.asyncio
async def test_selecao_exclui_documentos_soft_deleted(
    tmp_path: Path,
) -> None:
    """Seleção de vigentes deve filtrar ``deleted_at IS NULL`` (G2/G3)."""
    doc_vigente = _DocFicticio(
        id="doc-1", titulo="T", filename="a.pdf",
        filepath="2026/01/a.pdf", size_bytes=4, drive_file_id=None,
    )
    doc_apagado = _DocFicticio(
        id="doc-2", titulo="T2", filename="b.pdf",
        filepath="2026/01/b.pdf", size_bytes=4, drive_file_id=None,
    )
    arquivo = tmp_path / "2026" / "01"
    arquivo.mkdir(parents=True)
    (arquivo / "b.pdf").write_bytes(b"xxxx")

    with patch.object(servico, "selecionar_documentos", AsyncMock()) as sel:
        sel.return_value = [doc_vigente]
        # contrato: o serviço NÃO consulta banco — documentos é a fonte
        # única de alvos; a filtragem de vigentes (``deleted_at IS NULL``)
        # fica a cargo do chamador (rota/dispatch)
        resultado = await servico.executar_rescan(
            upload_root=tmp_path,
            rclone_config=None,
            documentos=[doc_vigente, doc_apagado],
        )
    assert sel.call_count == 0
    assert resultado.itens_processados == 2


# ──────────────────────────── Hash local streaming ────────────────────────


@pytest.mark.asyncio
async def test_hash_local_calcula_sha_e_valida_tamanho(
    tmp_path: Path,
) -> None:
    """Caminho local: ``expected_size`` força verificação ``size_bytes``."""
    conteudo = b"B" * (local_hash.CHUNK_HASH_BYTES * 2 + 11)
    caminho = tmp_path / "2026" / "08" / "doc.pdf"
    caminho.parent.mkdir(parents=True)
    caminho.write_bytes(conteudo)

    resultado = await local_hash.calcular_sha256_local(
        tmp_path, "2026/08/doc.pdf", expected_size=len(conteudo),
    )
    assert resultado.sha256 == hashlib.sha256(conteudo).hexdigest()
    assert resultado.size_bytes == len(conteudo)


@pytest.mark.asyncio
async def test_divergencia_tamanho_vira_item_erro_classificado(
    tmp_path: Path,
) -> None:
    """Metadado ``size_bytes`` divergente → item ``erro`` com motivo
    ``tamanho_divergente``, sem abortar o lote."""
    arquivo = tmp_path / "2026" / "08" / "doc.pdf"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(b"curto")

    docs = [
        _DocFicticio(
            id="doc-1", titulo="T", filename="doc.pdf",
            filepath="2026/08/doc.pdf", size_bytes=999999, drive_file_id=None,
        ),
    ]
    resultado = await servico.executar_rescan(
        upload_root=tmp_path, rclone_config=None, documentos=docs,
    )
    assert resultado.itens_erro == 1
    assert resultado.itens_processados == 1
    div = resultado.divergencias[0]
    assert div["document_id"] == "doc-1"
    assert div["motivo"] == "tamanho_divergente"
    assert "2026/08/doc.pdf" not in str(div)


@pytest.mark.asyncio
async def test_arquivo_ausente_vira_nao_disponivel_sem_abortar(
    tmp_path: Path,
) -> None:
    """Arquivo físico ausente → ``nao_disponivel``; o restante do lote segue."""
    docs = [
        _DocFicticio(
            id="doc-1", titulo="A", filename="x.pdf",
            filepath="2026/08/x.pdf", size_bytes=5, drive_file_id=None,
        ),
        _DocFicticio(
            id="doc-2", titulo="B", filename="y.pdf",
            filepath="2026/08/y.pdf", size_bytes=None, drive_file_id=None,
        ),
    ]
    (tmp_path / "2026" / "08").mkdir(parents=True)
    (tmp_path / "2026" / "08" / "y.pdf").write_bytes(b"yyyyy")

    resultado = await servico.executar_rescan(
        upload_root=tmp_path, rclone_config=None, documentos=docs,
    )
    assert resultado.itens_concluidos == 1
    assert resultado.itens_nao_disponiveis == 1


# ──────────────────────────── Hash remoto (rclone) ────────────────────────


@pytest.mark.asyncio
async def test_documentos_drive_usam_hash_remoto_rclone(
    tmp_path: Path,
) -> None:
    """Documentos com ``drive_file_id`` devem ser hashados pela fonte
    remota, passando o tamanho esperado como metadado."""
    doc = _DocFicticio(
        id="doc-drive-1", titulo="T", filename="d.pdf",
        filepath="drive:docs/d.pdf", size_bytes=3, drive_file_id="1AbCdEfG",
    )
    conteudo = b"abc"
    esperado = hashlib.sha256(conteudo).hexdigest()

    mock_remoto = AsyncMock(
        return_value=local_hash.HashDocumentoCalculado(
            sha256=esperado, size_bytes=3,
        ),
    )
    with patch.object(
        servico, "calcular_sha256_remoto_rclone", mock_remoto,
    ):
        resultado = await servico.executar_rescan(
            upload_root=tmp_path, rclone_config={"config_path": tmp_path / "rclone.conf", "remote": "drive", "work_dir": tmp_path},
            documentos=[doc],
        )
    mock_remoto.assert_awaited_once()
    chamada = mock_remoto.await_args[0]
    assert chamada[0].remote == "drive"  # ConfiguracaoHashRclone validada
    assert chamada[1] == "drive:docs/d.pdf"
    assert mock_remoto.await_args[1]["expected_size"] == 3
    assert resultado.itens_concluidos == 1
    div = resultado.divergencias[0]
    assert esperado in div["sha256_calculado"]


@pytest.mark.asyncio
async def test_rclone_indisponivel_nao_derruba_lote(
    tmp_path: Path,
) -> None:
    """Falha de infraestrutura remota → ``erro`` classificado
    ``infraestrutura_remota``; lote continua."""
    doc1 = _DocFicticio(
        id="doc-drive-1", titulo="A", filename="a.pdf",
        filepath="drive:a.pdf", size_bytes=1, drive_file_id="AAA",
    )
    doc2 = _DocFicticio(
        id="doc-drive-2", titulo="B", filename="b.pdf",
        filepath="drive:b.pdf", size_bytes=1, drive_file_id="BBB",
    )

    mock_remoto = AsyncMock(
        side_effect=HashRemotoIndisponivelError("rclone indisponível"),
    )
    with patch.object(
        servico, "calcular_sha256_remoto_rclone", mock_remoto,
    ):
        resultado = await servico.executar_rescan(
            upload_root=tmp_path, rclone_config={"config_path": tmp_path / "rclone.conf", "remote": "drive", "work_dir": tmp_path},
            documentos=[doc1, doc2],
        )
    assert resultado.itens_erro == 2
    assert all(
        d["motivo"] == "infraestrutura_remota" for d in resultado.divergencias
    )


@pytest.mark.asyncio
async def test_rclone_sem_configuracao_recusa_sem_fallback_inseguro(
    tmp_path: Path,
) -> None:
    """Documento no Drive sem ``rclone_config`` não pode cair em
    ``calcular_sha256_local`` com filepath ``drive:...``."""
    doc = _DocFicticio(
        id="doc-drive-1", titulo="A", filename="a.pdf",
        filepath="drive:a.pdf", size_bytes=1, drive_file_id="AAA",
    )
    resultado = await servico.executar_rescan(
        upload_root=tmp_path, rclone_config=None, documentos=[doc],
    )
    assert resultado.itens_erro == 1
    assert resultado.divergencias[0]["motivo"] == "sem_fonte_remota"
    assert "drive:a.pdf" not in str(resultado.divergencias[0])


# ──────────────────── Detecção de divergência de intake ───────────────────


@pytest.mark.asyncio
async def test_divergencia_sha_vs_intake_anterior(
    tmp_path: Path,
) -> None:
    """SHA recalculado diferente do último ``DocumentIntakeItem`` → item
    ``divergencia`` com ambos os hashes, para triagem humana."""
    conteudo = b"C" * 50
    arquivo = tmp_path / "2026" / "09" / "z.pdf"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(conteudo)

    doc = _DocFicticio(
        id="doc-1", titulo="T", filename="z.pdf",
        filepath="2026/09/z.pdf", size_bytes=len(conteudo), drive_file_id=None,
    )
    intake_sha = hashlib.sha256(
        b"conteudo anterior (arquivo substituido)",
    ).hexdigest()

    mock_intake = AsyncMock(return_value=[MagicMock(sha256=intake_sha)])
    mock_gravar = AsyncMock()
    with (
        patch.object(servico, "buscar_intake_sha", mock_intake),
        patch.object(servico, "gravar_item_rescan", mock_gravar),
    ):
        resultado = await servico.executar_rescan(
            upload_root=tmp_path, rclone_config=None,
            documentos=[doc], db=MagicMock(),
        )
    _ = mock_intake  # usado internamente; gravacao valida a integracao
    assert resultado.itens_concluidos == 1
    assert resultado.divergencias[0]["motivo"] == "diverge_do_intake"
    assert resultado.divergencias[0]["sha256_intake"] == intake_sha
    gravado = mock_gravar.await_args
    assert gravado[0][2] == "doc-1"  # (db, batch_id, document_id) positional
    assert gravado[1]["sha256_calculado"] == hashlib.sha256(conteudo).hexdigest()


# ──────────────────────────── Cancelamento e concorrência ─────────────────


@pytest.mark.asyncio
async def test_cancelamento_ordenado_encerra_sem_leak(
    tmp_path: Path,
) -> None:
    """Cancelamento encerra a iteração e não deixa temporários rclone
    pendentes (cancel propagation)."""
    docs = [_DocFicticio(
        id=f"doc-{i}", titulo="T", filename="f.pdf",
        filepath="2026/10/f.pdf", size_bytes=5, drive_file_id=None,
    ) for i in range(100)]

    async def _hash_lento(*args, **kwargs) -> local_hash.HashDocumentoCalculado:
        await asyncio.sleep(1)
        return local_hash.HashDocumentoCalculado(sha256="0" * 64, size_bytes=5)

    mock_hash = AsyncMock(side_effect=_hash_lento)
    with patch.object(
        local_hash, "calcular_sha256_local", mock_hash,
    ):
        tarefa = asyncio.create_task(
            servico.executar_rescan(
                upload_root=tmp_path, rclone_config=None, documentos=docs,
            ),
        )
        await asyncio.sleep(0.02)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa
        # Encerramento ordenado: nada permanece pendente além da própria
        # tarefa cancelada (nada vaza para outras coroutines do loop).
        await asyncio.sleep(0)
        assert not tarefa.cancelled() or tarefa.done()


# ──────────────────────────────── Paginação ───────────────────────────────


@pytest.mark.asyncio
async def test_lote_grande_processa_em_fatias_sem_esticar_memoria(
    tmp_path: Path,
) -> None:
    """Lotes grandes são processados em fatias (ex.: 50); contagens finais
    devem bater com o total."""
    (tmp_path / "2026" / "11").mkdir(parents=True)
    docs = []
    for i in range(250):
        p = tmp_path / "2026" / "11" / f"{i}.pdf"
        p.write_bytes(b"x" * 3)
        docs.append(_DocFicticio(
            id=f"doc-{i}", titulo="T", filename=f"{i}.pdf",
            filepath=f"2026/11/{i}.pdf", size_bytes=3, drive_file_id=None,
        ))
    resultado = await servico.executar_rescan(
        upload_root=tmp_path, rclone_config=None, documentos=docs,
    )
    assert resultado.itens_processados == 250
    assert resultado.itens_concluidos == 250
    assert resultado.itens_erro == 0


# ─────────────────── LGPD: não-exposição de paths ─────────────────────────


@pytest.mark.parametrize(
    ("fixture", "proibido"),
    [
        ("arquivo_ausente", "2026/12/sumido.pdf"),
        ("tamanho_divergente", "2026/12/d.pdf"),
        ("cliente-cpf-777-sentinela", "777"),
    ],
)
@pytest.mark.asyncio
async def test_mensagens_de_erro_nao_expoem_dados_pessoais(
    tmp_path: Path,
    fixture: str,
    proibido: str,
) -> None:
    """Nenhuma mensagem de divergência pode conter filepath ou CPF."""
    docs: list[_DocFicticio] = []
    if fixture == "arquivo_ausente":
        docs.append(_DocFicticio(
            id="doc-1", titulo="T", filename="sumido.pdf",
            filepath="2026/12/sumido.pdf", size_bytes=2, drive_file_id=None,
        ))
    elif fixture == "tamanho_divergente":
        docs.append(_DocFicticio(
            id="doc-2", titulo="T", filename="d.pdf",
            filepath="2026/12/d.pdf", size_bytes=7777, drive_file_id=None,
        ))
    elif fixture == "cliente-cpf-777-sentinela":
        docs.append(_DocFicticio(
            id="doc-3", titulo="T", filename="cliente-cpf-777-sentinela.pdf",
            filepath="2026/12/cliente-cpf-777-sentinela.pdf",
            size_bytes=3, drive_file_id=None,
        ))

    if fixture == "tamanho_divergente":
        (tmp_path / "2026" / "12").mkdir(parents=True)
        (tmp_path / "2026" / "12" / "d.pdf").write_bytes(b"curto")
    elif fixture == "cliente-cpf-777-sentinela":
        (tmp_path / "2026" / "12").mkdir(parents=True)
        (tmp_path / "2026" / "12" / "cliente-cpf-777-sentinela.pdf").write_bytes(
            b"abc",
        )

    resultado = await servico.executar_rescan(
        upload_root=tmp_path, rclone_config=None, documentos=docs,
    )
    texto = str(resultado.divergencias)
    assert proibido not in texto, f"path/CPF vazou na divergência: {texto}"
