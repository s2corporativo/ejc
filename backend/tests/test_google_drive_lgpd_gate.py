from app.services import google_drive_service as gds


class _DbBomba:
    async def commit(self):
        raise AssertionError("não deve persistir peça restrita")

    async def rollback(self):
        pass


async def test_peca_cliente_drive_nao_baixa_nem_indexa(monkeypatch):
    arquivo = gds.DriveFile(
        id="drive-1",
        name="Contestação 0801234-56.2023.8.13.0079 Fulano.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    def download_proibido(*args, **kwargs):
        raise AssertionError("peça restrita não pode ser baixada")

    async def upsert_proibido(*args, **kwargs):
        raise AssertionError("peça restrita não pode entrar no RAG global")

    monkeypatch.setattr(gds, "_download_drive_file_sync", download_proibido)
    monkeypatch.setattr(gds, "upsert_documento", upsert_proibido)

    resultado = await gds._processar_arquivo(
        _DbBomba(),
        arquivo,
        categoria="auto",
        confianca="media",
        categorizar_automaticamente=True,
    )
    assert resultado["status"] == "ignorado"
    assert resultado["categoria"] == "peca_interna"
    assert "LGPD" in resultado["motivo"]


def test_auditoria_marca_peca_cliente_como_nao_indexavel():
    arquivo = gds.DriveFile(
        id="drive-2",
        name="Petição inicial 0801234-56.2023.8.13.0079.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    item = gds._arquivo_auditado(arquivo, gds.DEFAULT_ALLOWED_MIME_TYPES)
    assert item["restrito_sem_escopo"] is True
    assert item["indexavel"] is False
