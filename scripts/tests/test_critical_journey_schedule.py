from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_runner_exige_credencial_dedicada_e_cleanup():
    src=(ROOT/"scripts/run_daily_critical_journey.sh").read_text()
    assert "/etc/ejc/critical-journey.env" in src
    assert "EJC_ALLOW_PRODUCTION_E2E=true" in src
    assert "EJC_E2E_CLEANUP=true" in src
    assert "EJC_CASE_CREATION_MODE=manual" in src
    assert "run_case_journey.py" in src
    assert "EJC_TEST_PASSWORD" in src

def test_timer_diario_e_sem_loop_agressivo():
    timer=(ROOT/"infra/host-automation/systemd/ejc-critical-journey.timer").read_text()
    assert "OnCalendar=*-*-* 09:10:00 America/Sao_Paulo" in timer
    assert "RandomizedDelaySec=15m" in timer
    assert "OnUnitActiveSec" not in timer


def test_jornada_cobre_pesquisa_e_logout():
    src=(ROOT/"qa/e2e/run_case_journey.py").read_text()
    assert "jornada.pesquisa.global" in src
    assert "/api/search?q=" in src
    assert "jornada.logout" in src
    assert "/api/auth/logout" in src
    assert "jornada.logout.refresh_revogado" in src
    assert "EJC_CASE_CREATION_MODE" in src
    assert "core._create_case(client, state, matrix)" in src
