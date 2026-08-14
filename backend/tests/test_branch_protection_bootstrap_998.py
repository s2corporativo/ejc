import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governanca" / "branch-protection-bootstrap.sh"

CONTEXTS = [
    "Backend — suíte completa + schema/RAG (Postgres pgvector)",
    "Eval — smoke dos gold sets (offline, bloqueante)",
    "Frontend — testes + typecheck + build",
    "P0 guard — conflitos e segredos",
    "Governança — travas de PR",
]
APP_ID = 15368


def _protection(**overrides):
    data = {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": context, "app_id": APP_ID} for context in CONTEXTS],
        },
        "enforce_admins": {"enabled": True},
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
            "bypass_pull_request_allowances": {"users": [], "teams": [], "apps": []},
        },
        "restrictions": None,
        "required_linear_history": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "block_creations": {"enabled": False},
        "required_conversation_resolution": {"enabled": True},
        "lock_branch": {"enabled": False},
        "allow_fork_syncing": {"enabled": False},
    }
    for key, value in overrides.items():
        data[key] = value
    return data


def _write_fake_gh(tmp_path: Path):
    gh = tmp_path / "gh"
    gh.write_text(
        """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
state = pathlib.Path(os.environ["FAKE_GH_STATE"])
log = pathlib.Path(os.environ["FAKE_GH_LOG"])
scenario = os.environ.get("FAKE_GH_SCENARIO", "success")

with log.open("a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\\n")

if args[:2] == ["auth", "status"]:
    raise SystemExit(0)

if not args or args[0] != "api":
    raise SystemExit(2)

is_put = "PUT" in args
endpoint = next((a for a in args[1:] if a.startswith("repos/")), "")

if endpoint.endswith("/branches/main"):
    calls = int(state.read_text() or "0") if state.exists() else 0
    calls += 1
    state.write_text(str(calls))
    if scenario == "missing_protected":
        print("{}")
    elif scenario == "null_protected":
        print('{"protected":null}')
    elif scenario == "string_false":
        print('{"protected":"false"}')
    elif scenario == "concurrent" and calls >= 2:
        print('{"protected":true}')
    else:
        print('{"protected":false}')
    raise SystemExit(0)

if endpoint.endswith("/branches/main/protection") and is_put:
    payload = sys.stdin.read()
    pathlib.Path(os.environ["FAKE_GH_PAYLOAD"]).write_text(payload, encoding="utf-8")
    if scenario == "transport_after_apply":
        raise SystemExit(1)
    print(json.dumps(json.loads(payload)))
    raise SystemExit(0)

if endpoint.endswith("/branches/main/protection"):
    protection = json.loads(os.environ["FAKE_GH_PROTECTION"])
    print(json.dumps(protection))
    raise SystemExit(0)

raise SystemExit(3)
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return gh


def _run(
    tmp_path: Path,
    scenario="success",
    protection=None,
    authorization="998",
    branch="main",
    repo="s2corporativo/ejc",
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write_fake_gh(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "FAKE_GH_STATE": str(tmp_path / "state"),
            "FAKE_GH_LOG": str(tmp_path / "log"),
            "FAKE_GH_PAYLOAD": str(tmp_path / "payload"),
            "FAKE_GH_SCENARIO": scenario,
            "FAKE_GH_PROTECTION": json.dumps(_protection() if protection is None else protection),
            "EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION": authorization,
            "EJC_BRANCH": branch,
            "EJC_REPO": repo,
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    log_path = tmp_path / "log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log


def test_bootstrap_exige_autorizacao_main_e_repo_canonico(tmp_path):
    result, log = _run(tmp_path, authorization="")
    assert result.returncode != 0
    assert "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998" in result.stderr
    assert "-X PUT" not in log

    result, log = _run(tmp_path / "branch", branch="feature")
    assert result.returncode != 0
    assert "bootstrap autorizado somente para main" in result.stderr
    assert "-X PUT" not in log

    result, log = _run(tmp_path / "repo", repo="someone/another-repo")
    assert result.returncode != 0
    assert "bootstrap autorizado somente para s2corporativo/ejc" in result.stderr
    assert "-X PUT" not in log


def test_bootstrap_falha_fechado_para_protected_ambiguo(tmp_path):
    for scenario in ("missing_protected", "null_protected", "string_false"):
        case = tmp_path / scenario
        case.mkdir()
        result, log = _run(case, scenario=scenario)
        assert result.returncode != 0
        assert "estado de proteção ausente, ambíguo ou já protegido" in result.stderr
        assert "-X PUT" not in log


def test_bootstrap_revalida_antes_do_put_e_recusa_corrida(tmp_path):
    result, log = _run(tmp_path, scenario="concurrent")
    assert result.returncode != 0
    assert log.count("repos/s2corporativo/ejc/branches/main -H") == 2
    assert "-X PUT" not in log


def test_bootstrap_vincula_checks_ao_github_actions_e_remove_bypass(tmp_path):
    result, log = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "-X PUT" in log
    payload = json.loads((tmp_path / "payload").read_text(encoding="utf-8"))
    assert payload["required_status_checks"]["strict"] is True
    assert payload["required_status_checks"]["checks"] == [
        {"context": context, "app_id": APP_ID} for context in CONTEXTS
    ]
    assert payload["required_pull_request_reviews"]["bypass_pull_request_allowances"] == {
        "users": [],
        "teams": [],
        "apps": [],
    }


def test_bootstrap_reconcilia_put_com_falha_de_transporte(tmp_path):
    result, log = _run(tmp_path, scenario="transport_after_apply")
    assert result.returncode == 0, result.stderr
    assert "PUT não retornou resposta confiável" in result.stderr
    assert "-X PUT" in log
    assert log.rstrip().endswith("repos/s2corporativo/ejc/branches/main/protection -H Accept: application/vnd.github+json")


def test_bootstrap_rejeita_baseline_divergente_ou_incompleto(tmp_path):
    reviews_sem_bypass = {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": True,
        "required_approving_review_count": 1,
        "require_last_push_approval": True,
    }
    bad_cases = [
        {},
        _protection(required_pull_request_reviews=reviews_sem_bypass),
        _protection(
            required_pull_request_reviews={
                **reviews_sem_bypass,
                "bypass_pull_request_allowances": {"users": [], "teams": []},
            }
        ),
        _protection(
            required_pull_request_reviews={
                **reviews_sem_bypass,
                "bypass_pull_request_allowances": {"users": [{"login": "admin"}], "teams": [], "apps": []},
            }
        ),
        _protection(
            required_status_checks={
                "strict": True,
                "checks": [{"context": context, "app_id": 999} for context in CONTEXTS],
            }
        ),
        _protection(block_creations={"enabled": True}),
        _protection(lock_branch={"enabled": True}),
        _protection(allow_fork_syncing={"enabled": True}),
        _protection(restrictions={"users": [], "teams": [], "apps": []}),
    ]
    for index, protection in enumerate(bad_cases):
        case = tmp_path / str(index)
        case.mkdir()
        result, _ = _run(case, protection=protection)
        assert result.returncode != 0
        assert "estado efetivo não corresponde ao baseline fail-closed" in result.stderr
