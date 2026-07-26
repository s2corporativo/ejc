# ── tests/test_backup_offsite.py ─────────────────────────────────────────────
# Backup offsite flexível (BACKUP_DESTINO=gdrive|rclone) + semântica
# local_ok/offsite_ok. Sem Postgres, sem pg_dump e sem rclone reais —
# fakes/monkeypatch locais (padrão de test_backup_service.py). Cobre:
# - destino rclone chama `rclone copyto` com os args e timeout corretos;
# - rclone falho com prova local → status "parcial" e ok=True (novo default);
# - BACKUP_OFFSITE_OBRIGATORIO=true → falha offsite derruba o ciclo (ok=False);
# - destino gdrive preserva o fluxo original (upload Drive + rotação);
# - pasta do Drive ausente virou falha de OFFSITE, não do ciclo inteiro.
from __future__ import annotations

from cryptography.fernet import Fernet

from app.services import backup_service

CHAVE = Fernet.generate_key().decode()


class _FakeResult:
    def first(self):
        return None

    def mappings(self):
        return self


class _FakeDB:
    """Sessão mínima: aceita execute/commit/rollback sem banco real."""

    async def execute(self, *args, **kwargs):
        return _FakeResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass

    def add(self, obj):
        pass


def _prepara(monkeypatch, tmp_path, **overrides):
    """Config coerente + pg_dump falso: a fase LOCAL sempre produz os dois
    artefatos cifrados (db.dump.enc + uploads.tar.gz.enc)."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "doc.pdf").write_bytes(b"%PDF fake" * 20)
    valores = {
        "BACKUP_ENCRYPTION_KEY": CHAVE,
        "BACKUP_DESTINO": "rclone",
        "BACKUP_RCLONE_REMOTE": "onedrive:EJC-Backups",
        "BACKUP_RCLONE_TIMEOUT": 123,
        "BACKUP_OFFSITE_OBRIGATORIO": False,
        "BACKUP_DRIVE_FOLDER_ID": "",
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


# ── Destino rclone ────────────────────────────────────────────────────────────

async def test_destino_rclone_chama_subprocess_com_args_corretos(monkeypatch, tmp_path):
    _prepara(monkeypatch, tmp_path)
    chamadas: list[dict] = []

    class _Retorno:
        returncode = 0
        stderr = ""

    def _fake_run(cmd, **kwargs):
        # O artefato enviado precisa estar CIFRADO (nunca em claro).
        with open(cmd[3], "rb") as f:  # cmd = [rclone, copyto, --, caminho, destino]
            Fernet(CHAVE.encode()).decrypt(f.read())  # levanta se não-Fernet
        chamadas.append({"cmd": cmd, **kwargs})
        return _Retorno()

    monkeypatch.setattr(backup_service.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    monkeypatch.setattr(backup_service.subprocess, "run", _fake_run)

    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is True and resultado["status"] == "sucesso"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is True
    assert resultado["destino"] == "rclone"
    assert len(chamadas) == 2  # db.dump.enc + uploads.tar.gz.enc
    for chamada in chamadas:
        cmd = chamada["cmd"]
        assert cmd[0] == "rclone" and cmd[1] == "copyto"
        assert cmd[2] == "--"  # remote iniciado em "-" nunca vira flag
        assert cmd[4].startswith("onedrive:EJC-Backups/ejc_backup_")
        assert chamada["timeout"] == 123
    destinos = [c["cmd"][4] for c in chamadas]
    assert any(d.endswith("_db.dump.enc") for d in destinos)
    assert any(d.endswith("_uploads.tar.gz.enc") for d in destinos)
    # Segredo nunca vaza no payload (vai para log/estado/status).
    assert CHAVE not in str(resultado)


async def test_rclone_falha_com_local_ok_gera_parcial(monkeypatch, tmp_path):
    _prepara(monkeypatch, tmp_path)

    class _Retorno:
        returncode = 1
        stderr = "Failed to copy: token expired"

    monkeypatch.setattr(backup_service.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    monkeypatch.setattr(backup_service.subprocess, "run", lambda *a, **k: _Retorno())

    resultado = await backup_service.executar_backup(_FakeDB(), origem="pre_deploy")

    assert resultado["ok"] is True          # prova local sustenta o ciclo
    assert resultado["status"] == "parcial"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is False
    assert "rclone" in (resultado["offsite_erro"] or "")
    assert any(
        "AVISO GRAVE" in a and "rclone" in a for a in resultado["avisos"]
    )
    # Artefatos cifrados seguem no payload como prova local.
    nomes = [a["nome"] for a in resultado["artefatos"]]
    assert any(n.endswith("_db.dump.enc") for n in nomes)
    assert any(n.endswith("_uploads.tar.gz.enc") for n in nomes)


async def test_rclone_falha_com_offsite_obrigatorio_derruba_backup(monkeypatch, tmp_path):
    _prepara(monkeypatch, tmp_path, BACKUP_OFFSITE_OBRIGATORIO=True)

    class _Retorno:
        returncode = 1
        stderr = "connection refused"

    monkeypatch.setattr(backup_service.shutil, "which", lambda nome: f"/usr/bin/{nome}")
    monkeypatch.setattr(backup_service.subprocess, "run", lambda *a, **k: _Retorno())

    resultado = await backup_service.executar_backup(_FakeDB(), origem="agendado")

    assert resultado["ok"] is False and resultado["status"] == "erro"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is False
    assert "rclone" in (resultado["erro"] or "")


async def test_rclone_sem_binario_gera_parcial_com_erro_acionavel(monkeypatch, tmp_path):
    _prepara(monkeypatch, tmp_path)
    monkeypatch.setattr(backup_service.shutil, "which", lambda nome: None)

    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is True and resultado["status"] == "parcial"
    assert resultado["offsite_ok"] is False
    assert "rclone" in (resultado["offsite_erro"] or "")


# ── Destino gdrive (fluxo original preservado) ────────────────────────────────

async def test_destino_gdrive_preserva_fluxo(monkeypatch, tmp_path):
    _prepara(
        monkeypatch, tmp_path,
        BACKUP_DESTINO="gdrive",
        BACKUP_RCLONE_REMOTE="",
        BACKUP_DRIVE_FOLDER_ID="pasta123",
    )
    enviados: list[tuple[str, str]] = []
    monkeypatch.setattr(backup_service, "_drive_client_escrita", lambda: object())
    monkeypatch.setattr(
        backup_service, "_upload_drive_sync",
        lambda s, c, n, f: enviados.append((n, f)) or {"id": "x", "name": n},
    )
    monkeypatch.setattr(backup_service, "_rotacionar_sync", lambda s, f, r: 3)

    def _nunca(*args, **kwargs):
        raise AssertionError("rclone não deve ser chamado no destino gdrive")

    monkeypatch.setattr(backup_service, "_upload_rclone_sync", _nunca)

    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is True and resultado["status"] == "sucesso"
    assert resultado["destino"] == "gdrive"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is True
    assert resultado["rotacao_removidos"] == 3
    assert len(enviados) == 2 and all(pasta == "pasta123" for _, pasta in enviados)


async def test_gdrive_sem_pasta_default_gera_parcial(monkeypatch, tmp_path):
    """Antes: pasta ausente derrubava o ciclo. Agora é falha de OFFSITE —
    status parcial com prova local (BACKUP_OFFSITE_OBRIGATORIO=false)."""
    _prepara(
        monkeypatch, tmp_path,
        BACKUP_DESTINO="gdrive",
        BACKUP_DRIVE_FOLDER_ID="",
    )
    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is True and resultado["status"] == "parcial"
    assert resultado["local_ok"] is True and resultado["offsite_ok"] is False
    assert "BACKUP_DRIVE_FOLDER_ID" in (resultado["offsite_erro"] or "")


async def test_gdrive_sem_pasta_com_offsite_obrigatorio_falha(monkeypatch, tmp_path):
    _prepara(
        monkeypatch, tmp_path,
        BACKUP_DESTINO="gdrive",
        BACKUP_DRIVE_FOLDER_ID="",
        BACKUP_OFFSITE_OBRIGATORIO=True,
    )
    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is False and resultado["status"] == "erro"
    assert "BACKUP_DRIVE_FOLDER_ID" in (resultado["erro"] or "")


async def test_destino_invalido_falha_cedo(monkeypatch, tmp_path):
    _prepara(monkeypatch, tmp_path, BACKUP_DESTINO="ftp")
    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")

    assert resultado["ok"] is False and resultado["status"] == "erro"
    assert "BACKUP_DESTINO" in (resultado["erro"] or "")
    assert resultado["local_ok"] is False


def test_contrato_infra_rclone_no_container():
    # O upload offsite roda DENTRO do container (backup.sh → docker exec):
    # a imagem precisa do binário rclone e o compose precisa montar a config
    # OAuth do host (read-only). Regressão real observada em produção
    # (2026-07-26): host com rclone configurado, container sem o binário.
    from pathlib import Path

    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "rclone" in dockerfile

    compose = (
        Path(__file__).resolve().parents[2] / "docker-compose.yml"
    ).read_text()
    assert "/root/.config/rclone:ro" in compose
