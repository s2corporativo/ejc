from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "governanca" / "branch-protection-bootstrap.sh"
BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "bootstrap-protection-governance.yml"
GOVERNANCE_WORKFLOW = ROOT / ".github" / "workflows" / "governanca.yml"
RULESET_NAME = "EJC main protection bootstrap #998"
INTEGRATION_ID = 15368
CONTEXTS = [
    "Backend — suíte completa + schema/RAG (Postgres pgvector)",
    "Eval — smoke dos gold sets (offline, bloqueante)",
    "Frontend — testes + typecheck + build",
    "P0 guard — conflitos e segredos",
    "Governança — travas de PR",
    "Bootstrap protection — security auditor",
]


def _expected_ruleset() -> dict:
    return {
        "id": 998,
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["squash", "rebase"],
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": True,
                    "require_last_push_approval": True,
                    "required_approving_review_count": 1,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": context, "integration_id": INTEGRATION_ID}
                        for context in CONTEXTS
                    ],
                    "strict_required_status_checks_policy": True,
                },
            },
        ],
    }


def _write_fake_gh(tmp_path: Path) -> None:
    gh = tmp_path / "gh"
    gh.write_text(
        r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
scenario = os.environ.get("FAKE_GH_SCENARIO", "success")
log = pathlib.Path(os.environ["FAKE_GH_LOG"])
state = pathlib.Path(os.environ["FAKE_GH_STATE"])
payload_file = pathlib.Path(os.environ["FAKE_GH_PAYLOAD"])
expected = json.loads(os.environ["FAKE_GH_RULESET"])

with log.open("a", encoding="utf-8") as fh:
    fh.write(" ".join(args) + "\n")

if args[:2] == ["auth", "status"]:
    raise SystemExit(0)
if not args or args[0] != "api":
    raise SystemExit(2)

endpoint = next((arg for arg in args[1:] if arg.startswith("repos/")), "")
method = "GET"
if "-X" in args:
    method = args[args.index("-X") + 1]

if endpoint.endswith("/branches/main"):
    print('{"name":"main","protected":false}')
    raise SystemExit(0)

if "/rulesets?" in endpoint:
    exists = state.exists() and state.read_text(encoding="utf-8") == "created"
    if scenario.startswith("existing") or exists:
        print(json.dumps([{"id": 998, "name": expected["name"], "enforcement": "active"}]))
    elif scenario == "duplicate":
        print(json.dumps([
            {"id": 998, "name": expected["name"], "enforcement": "active"},
            {"id": 999, "name": expected["name"], "enforcement": "active"},
        ]))
    else:
        print("[]")
    raise SystemExit(0)

if endpoint.endswith("/rulesets/998"):
    current = expected
    if scenario == "existing_divergent":
        current = json.loads(json.dumps(expected))
        current["rules"] = [rule for rule in current["rules"] if rule["type"] != "pull_request"]
    print(json.dumps(current))
    raise SystemExit(0)

if endpoint.endswith("/rulesets") and method == "POST":
    payload = sys.stdin.read()
    payload_file.write_text(payload, encoding="utf-8")
    if scenario == "post_rejected":
        raise SystemExit(1)
    state.write_text("created", encoding="utf-8")
    if scenario == "transport_after_apply":
        raise SystemExit(1)
    print(json.dumps(expected))
    raise SystemExit(0)

raise SystemExit(3)
''',
        encoding="utf-8",
    )
    gh.chmod(0o755)


def _run(
    tmp_path: Path,
    *,
    scenario: str = "success",
    authorization: str = "998",
    repo: str = "s2corporativo/ejc",
    branch: str = "main",
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write_fake_gh(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "FAKE_GH_SCENARIO": scenario,
            "FAKE_GH_LOG": str(tmp_path / "log"),
            "FAKE_GH_STATE": str(tmp_path / "state"),
            "FAKE_GH_PAYLOAD": str(tmp_path / "payload"),
            "FAKE_GH_RULESET": json.dumps(_expected_ruleset()),
            "EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION": authorization,
            "EJC_REPO": repo,
            "EJC_BRANCH": branch,
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


def test_bootstrap_exige_autorizacao_repo_e_main(tmp_path):
    result, log = _run(tmp_path / "auth", authorization="")
    assert result.returncode != 0
    assert "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998" in result.stderr
    assert "-X POST" not in log

    result, log = _run(tmp_path / "repo", repo="someone/another-repo")
    assert result.returncode != 0
    assert "bootstrap autorizado somente para s2corporativo/ejc" in result.stderr
    assert "-X POST" not in log

    result, log = _run(tmp_path / "branch", branch="feature")
    assert result.returncode != 0
    assert "bootstrap autorizado somente para main" in result.stderr
    assert "-X POST" not in log


def test_bootstrap_cria_ruleset_aditivo_sem_put_patch_delete(tmp_path):
    result, log = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "-X POST repos/s2corporativo/ejc/rulesets" in log
    assert "-X PUT" not in log
    assert "-X PATCH" not in log
    assert "-X DELETE" not in log

    payload = json.loads((tmp_path / "payload").read_text(encoding="utf-8"))
    assert payload["name"] == RULESET_NAME
    assert payload["enforcement"] == "active"
    assert payload["bypass_actors"] == []
    assert payload["conditions"]["ref_name"] == {
        "include": ["refs/heads/main"],
        "exclude": [],
    }
    rules = {rule["type"]: rule for rule in payload["rules"]}
    assert {"deletion", "non_fast_forward", "required_linear_history", "pull_request", "required_status_checks"} == set(rules)
    pull_request = rules["pull_request"]["parameters"]
    assert sorted(pull_request["allowed_merge_methods"]) == ["rebase", "squash"]
    assert pull_request["dismiss_stale_reviews_on_push"] is True
    assert pull_request["require_code_owner_review"] is True
    assert pull_request["require_last_push_approval"] is True
    assert pull_request["required_approving_review_count"] >= 1
    assert pull_request["required_review_thread_resolution"] is True
    checks = rules["required_status_checks"]["parameters"]
    assert checks["strict_required_status_checks_policy"] is True
    assert checks["required_status_checks"] == [
        {"context": context, "integration_id": INTEGRATION_ID} for context in CONTEXTS
    ]


def test_bootstrap_e_idempotente_e_recusa_ruleset_divergente(tmp_path):
    result, log = _run(tmp_path / "ok", scenario="existing")
    assert result.returncode == 0, result.stderr
    assert "já estava ativo e íntegro" in result.stdout
    assert "-X POST" not in log

    result, log = _run(tmp_path / "bad", scenario="existing_divergent")
    assert result.returncode != 0
    assert "diverge do baseline" in result.stderr
    assert "-X POST" not in log


def test_bootstrap_falha_fechado_em_nome_canônico_duplicado(tmp_path):
    result, log = _run(tmp_path, scenario="duplicate")
    assert result.returncode != 0
    assert "mais de um ruleset com nome canônico" in result.stderr
    assert "-X POST" not in log


def test_bootstrap_reconcilia_falha_de_transporte_apos_criacao(tmp_path):
    result, log = _run(tmp_path, scenario="transport_after_apply")
    assert result.returncode == 0, result.stderr
    assert "POST não retornou resposta confiável" in result.stderr
    assert "-X POST" in log
    assert "rulesets/998" in log


def test_bootstrap_post_rejeitado_falha_fechado_sem_estado(tmp_path):
    result, log = _run(tmp_path, scenario="post_rejected")
    assert result.returncode != 0
    assert "POST não retornou resposta confiável" in result.stderr
    assert "esperado exatamente um ruleset canônico após bootstrap; encontrados 0" in result.stderr
    assert "-X POST" in log
    assert not (tmp_path / "state").exists()


def test_bootstrap_nao_tem_mutacao_destrutiva_de_branch_protection():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "branches/$BRANCH/protection" not in src
    assert "-X PUT" not in src
    assert "-X PATCH" not in src
    assert "-X DELETE" not in src


def test_bootstrap_security_gate_usa_workflow_confiavel_e_contexto_bloqueante():
    workflow = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    governanca = GOVERNANCE_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request_target:" in workflow
    assert "types: [opened, synchronize, reopened, edited]" in workflow
    assert "actions/checkout" not in workflow
    assert "gh api --paginate" in workflow
    assert "Bootstrap protection — security auditor" in workflow
    assert "Bootstrap protection — security auditor" in script
    assert "scripts/governanca/branch-protection-bootstrap.sh" in workflow
    assert ".github/workflows/bootstrap-protection-governance.yml" in workflow
    assert ".github/workflows/governanca.yml" in workflow
    assert "types: [opened, synchronize, reopened, edited]" in governanca
    assert "scripts/governanca/branch-protection-bootstrap\\.sh" in governanca


def test_security_gate_rejeita_marcador_autodeclarado_e_vincula_revisao_ao_head():
    workflow = BOOTSTRAP_WORKFLOW.read_text(encoding="utf-8")
    governanca = GOVERNANCE_WORKFLOW.read_text(encoding="utf-8")

    for src in (workflow, governanca):
        assert "security-auditor: executado" not in src
        assert "pulls/$PR_NUMBER/reviews?per_page=100" in src
        assert "| jq -s 'add'" in src
        assert 'select(.user.login == "coderabbitai[bot]")' in src
        assert "select(.commit_id == $sha)" in src
        assert '.state == "APPROVED" or .state == "COMMENTED"' in src
        assert 'test("Actionable comments posted:"; "i") | not' in src
        assert "HEAD_SHA" in src
