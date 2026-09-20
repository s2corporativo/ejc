from app.core.config import Settings
from app.services.integration_status import build_integration_status
from app.services.integration_runtime_status import _classificar_backup_estado


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


def test_conectores_judiciais_declaram_capacidades_sem_protocolar():
    """Cada conector judicial diz o que oferece; nenhum protocola (peticionamento
    é manual — PATCH /legal-docs/{id}/protocolo). Itens não judiciais não têm
    capacidades (contrato aditivo, sem inventar conector)."""
    settings = Settings(_env_file=None, APP_ENV="development")
    items = _items_by_key(build_integration_status(settings))

    chaves = {"consultar_processo", "sincronizar_movimentacoes", "partes",
              "audiencias", "baixar_documentos", "intimacoes", "protocolar"}
    for key in ("datajud", "processo_eletronico", "djen", "infosimples"):
        caps = items[key]["capacidades"]
        assert set(caps) == chaves, key
        assert caps["protocolar"] is False, key
    assert items["datajud"]["capacidades"]["sincronizar_movimentacoes"] is True
    assert items["processo_eletronico"]["capacidades"]["baixar_documentos"] is True
    assert items["djen"]["capacidades"]["intimacoes"] is True
    assert items["email"]["capacidades"] is None
    assert items["processo_eletronico"]["mode"] == "somente leitura (sem peticionamento)"


def test_runtime_failure_rebaixa_ready_sem_expor_erro_bruto():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        DJEN_INGEST_ENABLED=True,
        DJEN_OABS_MONITORADAS="12345/MG",
    )
    item = _items_by_key(build_integration_status(
        settings,
        operational_states={
            "djen": {
                "state": "erro",
                "detail": "Última execução de djen falhou; consulte o diagnóstico da fonte.",
                "checked_at": "2026-09-18T06:30:00+00:00",
            }
        },
    ))["djen"]
    assert item["status"] == "attention"
    assert item["operational_state"] == "erro"
    assert item["last_operational_at"] == "2026-09-18T06:30:00+00:00"
    assert "falhou" in item["detail"]


def test_runtime_antigo_nao_rebaixa_integracao_desligada():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        TJMG_INGEST_ENABLED=False,
    )
    item = _items_by_key(build_integration_status(
        settings,
        operational_states={"tjmg": {"state": "erro", "detail": "falha antiga"}},
    ))["tjmg"]
    assert item["status"] == "disabled"
    assert item["operational_state"] == "erro"


def test_backup_usa_flag_canonica_em_vez_de_backup_remote(monkeypatch):
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_REMOTE="",
        BACKUP_ENCRYPTION_KEY="presente-sem-expor",
        BACKUP_DESTINO="rclone",
        BACKUP_RCLONE_REMOTE="onedrive:EJC-Backups",
    )

    backup = _items_by_key(build_integration_status(settings))["backup_offsite"]

    assert backup["enabled"] is True
    assert backup["configured"] is True
    assert backup["status"] == "ready"
    assert "rclone" in (backup["mode"] or "")


def test_backup_habilitado_sem_configuracao_completa_exige_atencao():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_ENCRYPTION_KEY="",
        BACKUP_DESTINO="rclone",
        BACKUP_RCLONE_REMOTE="onedrive:EJC-Backups",
    )

    backup = _items_by_key(build_integration_status(settings))["backup_offsite"]

    assert backup["enabled"] is True
    assert backup["configured"] is False
    assert backup["status"] == "attention"


def test_backup_runtime_sucesso_confirma_offsite():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        BACKUP_ENABLED=True,
        BACKUP_ENCRYPTION_KEY="presente-sem-expor",
        BACKUP_DESTINO="rclone",
        BACKUP_RCLONE_REMOTE="onedrive:EJC-Backups",
    )
    item = _items_by_key(build_integration_status(
        settings,
        operational_states={
            "backup_offsite": {
                "state": "ok",
                "detail": "Último backup cifrado concluiu o envio offsite com sucesso.",
                "checked_at": "2026-09-20T00:03:28+00:00",
            }
        },
    ))["backup_offsite"]

    assert item["status"] == "ready"
    assert item["operational_state"] == "ok"
    assert item["last_operational_at"] == "2026-09-20T00:03:28+00:00"
    assert "sucesso" in item["detail"]


def test_classificador_backup_nao_expoe_erro_bruto():
    estado = _classificar_backup_estado({
        "last_status": "erro",
        "offsite_ok": False,
        "last_run_at": None,
        "last_error": "token-secreto-nao-pode-vazar",
    })

    assert estado["state"] == "erro"
    assert "token-secreto-nao-pode-vazar" not in str(estado)


def test_classificador_backup_parcial_distingue_local_de_offsite():
    estado = _classificar_backup_estado({
        "last_status": "parcial",
        "offsite_ok": False,
        "last_run_at": None,
    })

    assert estado["state"] == "alerta"
    assert "offsite" in estado["detail"].lower()
