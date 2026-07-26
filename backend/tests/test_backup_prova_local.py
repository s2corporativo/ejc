"""SYS-099 — prova local cifrada REALMENTE persiste quando o offsite falha.

Antes, os artefatos ficavam no TemporaryDirectory e eram apagados na saída do
bloco, mas local_ok=true (prova fantasma). Estes testes provam que, com offsite
falho e não obrigatório, os artefatos são MOVIDOS para BACKUP_LOCAL_DIR e o
arquivo existe/é não-vazio no disco — e que, sem persistência possível, o ciclo
vira erro (sem prova). Fakes locais (padrão de test_backup_offsite.py).
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet

from app.services import backup_service

CHAVE = Fernet.generate_key().decode()


class _FakeResult:
    def first(self):
        return None

    def mappings(self):
        return self


class _FakeDB:
    async def execute(self, *a, **k):
        return _FakeResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass

    def add(self, obj):
        pass


def _prepara(monkeypatch, tmp_path, **overrides):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "doc.pdf").write_bytes(b"%PDF fake" * 20)
    valores = {
        "BACKUP_ENCRYPTION_KEY": CHAVE,
        "BACKUP_DESTINO": "rclone",
        "BACKUP_RCLONE_REMOTE": "onedrive:EJC-Backups",
        "BACKUP_OFFSITE_OBRIGATORIO": False,
        "BACKUP_DRIVE_FOLDER_ID": "",
        "BACKUP_RETENCAO_DIAS": 14,
        "UPLOAD_DIR": str(uploads),
        **overrides,
    }
    for nome, valor in valores.items():
        monkeypatch.setattr(backup_service.settings, nome, valor)

    def _fake_pg_dump(destino):
        with open(destino, "wb") as f:
            f.write(b"PGDMP fake dump")
        return 15

    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    # rclone "presente" mas sempre falha o upload → cai no ramo de retenção local.
    monkeypatch.setattr(backup_service.shutil, "which", lambda nome: f"/usr/bin/{nome}")

    class _Falha:
        returncode = 1
        stderr = "token expired"

    monkeypatch.setattr(backup_service.subprocess, "run", lambda *a, **k: _Falha())


async def test_offsite_falho_persiste_prova_local_no_disco(monkeypatch, tmp_path):
    persist = tmp_path / "persist_backups"
    _prepara(monkeypatch, tmp_path, BACKUP_LOCAL_DIR=str(persist))

    resultado = await backup_service.executar_backup(_FakeDB(), origem="pre_deploy")

    assert resultado["ok"] is True and resultado["status"] == "parcial"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is False

    # Prova REAL no disco: arquivos cifrados não-vazios no diretório persistente.
    assert persist.is_dir()
    persistidos = sorted(os.listdir(persist))
    assert any(n.endswith("_db.dump.enc") for n in persistidos)
    assert any(n.endswith("_uploads.tar.gz.enc") for n in persistidos)
    for nome in persistidos:
        caminho = persist / nome
        assert caminho.stat().st_size > 0            # equivalente ao `test -s` do gate
        Fernet(CHAVE.encode()).decrypt(caminho.read_bytes())  # continua cifrado

    # Metadado de prova local retornado ao chamador (observabilidade do gate).
    assert resultado["prova_local"]["dir"] == str(persist)
    assert len(resultado["prova_local"]["arquivos"]) >= 2
    assert CHAVE not in str(resultado)              # segredo nunca vaza


async def test_sem_persistencia_possivel_vira_erro_sem_prova(monkeypatch, tmp_path):
    # BACKUP_LOCAL_DIR aponta para um caminho cujo "pai" é um ARQUIVO → makedirs
    # falha → retenção impossível → sem offsite e sem prova local = erro.
    arquivo = tmp_path / "bloqueio"
    arquivo.write_text("nao sou diretorio")
    _prepara(monkeypatch, tmp_path, BACKUP_LOCAL_DIR=str(arquivo / "backups"))

    resultado = await backup_service.executar_backup(_FakeDB(), origem="pre_deploy")

    assert resultado["ok"] is False and resultado["status"] == "erro"
    assert resultado["local_ok"] is False and resultado["offsite_ok"] is False
