from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_smoke_e_fail_closed_para_runtime_e_nao_muta_dados():
    src = (ROOT / "scripts/post_deploy_smoke.sh").read_text(encoding="utf-8")
    identity = src.index("check_release_identity.py")
    http = src.index("post_deploy_check.sh")
    evidence = src.index("release_evidence.py")
    assert identity < http < evidence
    assert "EJC_USER_PASSWORD" not in src
    assert "POST /api" not in src
    assert "release_evidence" in src


def test_post_deploy_check_cobre_rotas_e_readiness():
    src = (ROOT / "scripts/post_deploy_check.sh").read_text(encoding="utf-8")
    for token in (
        "/api/health/ready", "/login", "/atividades", "/clientes", "/casos",
        "/financeiro", "/documentos", "/inteligencia", "/teses", "/radar",
        "/produtividade", "/configuracoes", "/api/auth/login",
    ):
        assert token in src
