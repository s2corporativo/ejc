from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WATCHER = ROOT / "scripts" / "ci-fallback-watch.sh"


def _src() -> str:
    return WATCHER.read_text(encoding="utf-8")


def test_retry_de_infra_e_limitado_e_tem_backoff():
    src = _src()
    assert 'EJC_FALLBACK_INFRA_MAX_RETRIES:-3' in src
    assert 'EJC_FALLBACK_INFRA_RETRY_SECONDS:-300' in src
    assert 'EJC_FALLBACK_INFRA_RETRY_MAX_SECONDS:-1800' in src
    assert "retry_delay_seconds" in src
    assert '[ "$RETRY_ATTEMPTS" -lt "$INFRA_MAX_RETRIES" ]' in src
    assert "infra-retry.json" in src


def test_retry_automatico_so_aceita_sinais_de_infraestrutura():
    src = _src()
    assert "failure_is_infrastructure" in src
    for marker in (
        "Could not resolve host",
        "Temporary failure in name resolution",
        "EAI_AGAIN",
        "ECONNRESET",
        "ETIMEDOUT",
        "429 Too Many Requests",
        "503 Service Unavailable",
        "504 Gateway Timeout",
    ):
        assert marker in src
    assert "reprovou em teste/gate real" in src
    assert "mesmo SHA não será repetido automaticamente" in src


def test_classificacao_usa_somente_log_da_tentativa_atual():
    src = _src()
    assert "latest_attempt_log" in src
    assert 'started="$now"' in src or 'started="$(date +%s)"' in src
    assert 'failure_is_infrastructure "$sha" "$started"' in src
    function = src[src.index("failure_is_infrastructure() {") : src.index("retry_delay_seconds() {")]
    assert 'latest_attempt_log "$sha" "$started"' in function
    assert 'grep -Eiq "$INFRA_ERROR_RE" -- "$logfile"' in function
    assert "invocation_log" not in function


def test_auto_merge_desligado_usa_promote_only():
    src = _src()
    green_start = src.index('if local_evidence_green "$sha"; then')
    green_end = src.index('if [ -f "$marker" ]', green_start)
    green = src[green_start:green_end]
    assert 'if [ "$AUTO_MERGE" = "1" ]' in green
    assert '--merge-only' in green
    assert '--promote-only' in green


def test_retry_transitorio_nunca_vira_sucesso_por_si_so():
    src = _src()
    start = src.index('if failure_is_infrastructure "$sha" "$started"; then')
    end = src.index("else", start)
    infra = src[start:end]
    assert 'write_retry_state "$retry_file"' in infra
    assert 'failure' in infra
    assert 'success' not in infra
