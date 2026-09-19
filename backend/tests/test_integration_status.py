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
