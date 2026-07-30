from app.core.config import Settings
from app.services.integration_status import build_integration_status


def _items_by_key(payload):
    return {item["key"]: item for item in payload["items"]}


def test_integration_status_never_exposes_secrets():
    secret_values = [
        "anthropic-super-secret",
        "groq-super-secret",
        "smtp-super-secret",
        "vapid-private-secret",
    ]
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        ANTHROPIC_API_KEY=secret_values[0],
        GROQ_API_KEY=secret_values[1],
        EMAIL_ENABLED=True,
        SMTP_USER="contato@example.com",
        SMTP_PASSWORD=secret_values[2],
        PUSH_ENABLED=True,
        VAPID_PUBLIC_KEY="public-key",
        VAPID_PRIVATE_KEY=secret_values[3],
    )

    payload = build_integration_status(settings)
    serialized = str(payload)

    for secret in secret_values:
        assert secret not in serialized
    assert payload["mode"] == "configuration_only"
    assert payload["notice"]


def test_enabled_but_incomplete_integration_requires_attention():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        EMAIL_ENABLED=True,
        SMTP_USER="",
        SMTP_PASSWORD="",
    )

    email = _items_by_key(build_integration_status(settings))["email"]

    assert email["enabled"] is True
    assert email["configured"] is False
    assert email["status"] == "attention"


def test_disabled_integration_is_not_reported_as_failure():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        WHATSAPP_ENABLED=False,
    )

    whatsapp = _items_by_key(build_integration_status(settings))["whatsapp"]

    assert whatsapp["enabled"] is False
    assert whatsapp["status"] == "disabled"


def test_backup_cifrado_atual_e_legado_tem_status_independentes():
    segredo = "backup-encryption-secret"
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_ENCRYPTION_KEY=segredo,
        BACKUP_DESTINO="gdrive",
        BACKUP_DRIVE_FOLDER_ID="folder-id",
        BACKUP_REMOTE="",
    )

    payload = build_integration_status(settings)
    items = _items_by_key(payload)

    assert items["backup_offsite"]["enabled"] is True
    assert items["backup_offsite"]["configured"] is True
    assert items["backup_offsite"]["status"] == "ready"
    assert items["backup_legacy"]["enabled"] is False
    assert items["backup_legacy"]["status"] == "disabled"
    assert segredo not in str(payload)


def test_backup_cifrado_habilitado_sem_chave_requer_atencao():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_ENCRYPTION_KEY="",
        BACKUP_DESTINO="rclone",
        BACKUP_RCLONE_REMOTE="onedrive:EJC-Backups",
        BACKUP_REMOTE="legacy:backup",
    )

    items = _items_by_key(build_integration_status(settings))

    assert items["backup_offsite"]["enabled"] is True
    assert items["backup_offsite"]["configured"] is False
    assert items["backup_offsite"]["status"] == "attention"
    assert items["backup_legacy"]["status"] == "ready"


def test_backup_cifrado_com_destino_invalido_requer_atencao():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_ENCRYPTION_KEY="configured-but-not-exposed",
        BACKUP_DESTINO="destino-inexistente",
    )

    backup = _items_by_key(build_integration_status(settings))["backup_offsite"]

    assert backup["enabled"] is True
    assert backup["configured"] is False
    assert backup["status"] == "attention"
    assert backup["mode"] == (
        "destino inválido (destino-inexistente); retenção offsite 14 dias"
    )
