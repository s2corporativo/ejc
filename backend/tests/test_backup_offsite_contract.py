from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app.services.backup_service import (
    _criar_manifesto_cifrado,
    selecionar_para_rotacao_rclone,
)


def test_rclone_rotation_only_selects_old_canonical_root_files():
    agora = datetime(2026, 9, 21, tzinfo=timezone.utc)
    arquivos = [
        {
            "Path": "ejc_backup_20260101T000000Z_db.dump.enc",
            "ModTime": "2026-01-01T00:00:00Z",
        },
        {
            "Path": "ejc_backup_20260920T000000Z_db.dump.enc",
            "ModTime": "2026-09-20T00:00:00Z",
        },
        {
            "Path": "other_backup_20260101T000000Z.enc",
            "ModTime": "2026-01-01T00:00:00Z",
        },
        {
            "Path": "nested/ejc_backup_20260101T000000Z.enc",
            "ModTime": "2026-01-01T00:00:00Z",
        },
        {
            "Path": "ejc_backup_sem_data.enc",
            "ModTime": "not-a-date",
        },
    ]

    selecionados = selecionar_para_rotacao_rclone(
        arquivos, retencao_dias=14, agora=agora,
    )

    assert [item["Path"] for item in selecionados] == [
        "ejc_backup_20260101T000000Z_db.dump.enc",
    ]


def test_manifest_contains_hashes_and_is_encrypted(tmp_path):
    key = Fernet.generate_key().decode()
    source = tmp_path / "db.dump.enc"
    source.write_bytes(b"encrypted-db-artifact")
    artifact = {
        "nome": "ejc_backup_20260921T000000Z_db.dump.enc",
        "caminho": str(source),
        "bytes_original": 42,
        "bytes_cifrado": source.stat().st_size,
    }

    manifest = _criar_manifesto_cifrado(
        [artifact], str(tmp_path), datetime(2026, 9, 21, tzinfo=timezone.utc), key,
    )

    assert manifest["nome"].endswith("_manifest.json.enc")
    assert manifest["bytes_cifrado"] > manifest["bytes_original"]
    assert (tmp_path / "manifest.json").exists() is False
    assert (tmp_path / "manifest.json.enc").exists()
