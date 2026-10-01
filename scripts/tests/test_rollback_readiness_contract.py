from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_drill_isolado_nao_faz_cutover_nem_toca_banco():
    src=(ROOT/"scripts/rollback_readiness_drill.sh").read_text()
    assert "--network none" in src
    assert "ejc-backend:rollback-last" in src
    assert "ejc-worker:rollback-last" in src
    assert "ejc-frontend:rollback-last" in src
    assert '"database_mutated":False' in src
    assert "docker compose up" not in src

def test_deploy_preserva_uma_geracao_anterior():
    src=(ROOT/"scripts/deploy_vps_safe.sh").read_text()
    assert "ejc-backend:rollback-last" in src
    assert ".rollback_last_sha" in src
