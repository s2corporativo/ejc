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
    assert payload["mode"] == "configuration_and_operational"
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



def test_operational_error_rebaixa_falso_verde_sem_expor_erro_bruto():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        DJEN_INGEST_ENABLED=True,
        DJEN_OABS_MONITORADAS="12345:MG",
    )
    payload = build_integration_status(
        settings,
        operational_states={
            "djen": {
                "state": "error",
                "detail": "Última execução operacional falhou; consulte o diagnóstico da fonte.",
                "checked_at": "2026-09-18T06:30:06+00:00",
            }
        },
    )
    djen = _items_by_key(payload)["djen"]
    assert djen["configured"] is True
    assert djen["status"] == "attention"
    assert djen["operational_state"] == "error"
    assert djen["last_checked_at"] == "2026-09-18T06:30:06+00:00"
    assert "falhou" in djen["detail"]


def test_operational_ok_nao_promove_integracao_desabilitada():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        JUDICIAL_FILING_ENABLED=False,
    )
    item = _items_by_key(build_integration_status(
        settings,
        operational_states={
            "ajuizamento": {
                "state": "ok",
                "detail": "perfil homologado",
                "checked_at": "2026-09-18T00:00:00+00:00",
            }
        },
    ))["ajuizamento"]
    assert item["status"] == "disabled"
    assert item["operational_state"] == "ok"


def test_drive_knowledge_exige_configuracao_e_sync(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID", "folder-id")
    monkeypatch.setenv("GOOGLE_DRIVE_AUTH_MODE", "oauth")
    monkeypatch.setenv("GOOGLE_DRIVE_OAUTH_USER_JSON", "{}")

    settings = Settings(_env_file=None, APP_ENV="development")
    item = _items_by_key(build_integration_status(
        settings,
        operational_states={
            "google_drive_knowledge": {
                "state": "not_ready",
                "detail": "Google Drive Knowledge configurado, mas nenhuma sincronização foi iniciada.",
                "checked_at": None,
            }
        },
    ))["google_drive_knowledge"]
    assert item["enabled"] is True
    assert item["configured"] is True
    assert item["status"] == "attention"
    assert item["operational_state"] == "not_ready"
