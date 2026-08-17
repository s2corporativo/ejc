from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[2]
SCRIPT_BOOTSTRAP = RAIZ / "scripts" / "governanca" / "branch-protection-bootstrap.sh"
FLUXO_BOOTSTRAP = RAIZ / ".github" / "workflows" / "bootstrap-protection-governance.yml"
FLUXO_GOVERNANCA = RAIZ / ".github" / "workflows" / "governanca-v2.yml"
NOME_CONJUNTO_REGRAS = "EJC main protection bootstrap #998"
ID_INTEGRACAO = 15368
CONTEXTOS = [
    "Backend — suíte completa + schema/RAG (Postgres pgvector)",
    "Eval — smoke dos gold sets (offline, bloqueante)",
    "Frontend — testes + typecheck + build",
    "P0 guard — conflitos e segredos",
    "Governança — travas de PR",
    "Bootstrap protection — security auditor",
]


def _conjunto_regras_esperado() -> dict:
    return {
        "id": 998,
        "name": NOME_CONJUNTO_REGRAS,
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
                        {"context": contexto, "integration_id": ID_INTEGRACAO}
                        for contexto in CONTEXTOS
                    ],
                    "strict_required_status_checks_policy": True,
                },
            },
        ],
    }


def _escrever_gh_falso(caminho_temporario: Path) -> None:
    gh = caminho_temporario / "gh"
    gh.write_text(
        r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys

argumentos = sys.argv[1:]
cenario = os.environ.get("FAKE_GH_SCENARIO", "success")
registro = pathlib.Path(os.environ["FAKE_GH_LOG"])
estado = pathlib.Path(os.environ["FAKE_GH_STATE"])
arquivo_payload = pathlib.Path(os.environ["FAKE_GH_PAYLOAD"])
esperado = json.loads(os.environ["FAKE_GH_RULESET"])

with registro.open("a", encoding="utf-8") as arquivo:
    arquivo.write(" ".join(argumentos) + "\n")

if argumentos[:2] == ["auth", "status"]:
    raise SystemExit(0)
if not argumentos or argumentos[0] != "api":
    raise SystemExit(2)

endpoint = next((argumento for argumento in argumentos[1:] if argumento.startswith("repos/")), "")
metodo = "GET"
if "-X" in argumentos:
    metodo = argumentos[argumentos.index("-X") + 1]

if endpoint.endswith("/branches/main"):
    print('{"name":"main","protected":false}')
    raise SystemExit(0)

if "/rulesets?" in endpoint:
    existe = estado.exists() and estado.read_text(encoding="utf-8") == "created"
    if cenario.startswith("existing") or existe:
        print(json.dumps([{"id": 998, "name": esperado["name"], "enforcement": "active"}]))
    elif cenario == "duplicate":
        print(json.dumps([
            {"id": 998, "name": esperado["name"], "enforcement": "active"},
            {"id": 999, "name": esperado["name"], "enforcement": "active"},
        ]))
    else:
        print("[]")
    raise SystemExit(0)

if endpoint.endswith("/rulesets/998"):
    atual = esperado
    if cenario == "existing_divergent":
        atual = json.loads(json.dumps(esperado))
        atual["rules"] = [regra for regra in atual["rules"] if regra["type"] != "pull_request"]
    print(json.dumps(atual))
    raise SystemExit(0)

if endpoint.endswith("/rulesets") and metodo == "POST":
    payload = sys.stdin.read()
    arquivo_payload.write_text(payload, encoding="utf-8")
    if cenario == "post_rejected":
        raise SystemExit(1)
    estado.write_text("created", encoding="utf-8")
    if cenario == "transport_after_apply":
        raise SystemExit(1)
    print(json.dumps(esperado))
    raise SystemExit(0)

raise SystemExit(3)
''',
        encoding="utf-8",
    )
    gh.chmod(0o755)


def _executar(
    caminho_temporario: Path,
    *,
    cenario: str = "success",
    autorizacao: str = "998",
    repositorio: str = "s2corporativo/ejc",
    ramo: str = "main",
):
    caminho_temporario.mkdir(parents=True, exist_ok=True)
    _escrever_gh_falso(caminho_temporario)
    ambiente = os.environ.copy()
    ambiente.update(
        {
            "PATH": f"{caminho_temporario}:{ambiente['PATH']}",
            "FAKE_GH_SCENARIO": cenario,
            "FAKE_GH_LOG": str(caminho_temporario / "log"),
            "FAKE_GH_STATE": str(caminho_temporario / "state"),
            "FAKE_GH_PAYLOAD": str(caminho_temporario / "payload"),
            "FAKE_GH_RULESET": json.dumps(_conjunto_regras_esperado()),
            "EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION": autorizacao,
            "EJC_REPO": repositorio,
            "EJC_BRANCH": ramo,
        }
    )
    resultado = subprocess.run(
        ["bash", str(SCRIPT_BOOTSTRAP)],
        cwd=RAIZ,
        env=ambiente,
        text=True,
        capture_output=True,
        check=False,
    )
    caminho_registro = caminho_temporario / "log"
    registro = caminho_registro.read_text(encoding="utf-8") if caminho_registro.exists() else ""
    return resultado, registro


def _extrair_blocos_run(conteudo: str) -> list[str]:
    linhas = conteudo.splitlines()
    blocos: list[str] = []
    indice = 0
    while indice < len(linhas):
        linha = linhas[indice]
        if linha.lstrip() == "run: |":
            recuo_run = len(linha) - len(linha.lstrip())
            indice += 1
            linhas_bloco: list[str] = []
            while indice < len(linhas):
                candidata = linhas[indice]
                if candidata.strip():
                    recuo_candidata = len(candidata) - len(candidata.lstrip())
                    if recuo_candidata <= recuo_run:
                        break
                linhas_bloco.append(candidata)
                indice += 1
            recuos = [
                len(linha_bloco) - len(linha_bloco.lstrip())
                for linha_bloco in linhas_bloco
                if linha_bloco.strip()
            ]
            recuo_conteudo = min(recuos) if recuos else recuo_run + 2
            blocos.append("\n".join(linha_bloco[recuo_conteudo:] for linha_bloco in linhas_bloco))
            continue
        indice += 1
    return blocos


def _validar_sintaxe_bash_dos_blocos_run(conteudo: str) -> None:
    blocos = _extrair_blocos_run(conteudo)
    assert blocos, "workflow sem blocos run: | para validar"
    for bloco in blocos:
        resultado = subprocess.run(
            ["bash", "-n"],
            input=bloco,
            text=True,
            capture_output=True,
            check=False,
        )
        assert resultado.returncode == 0, resultado.stderr


def test_bootstrap_exige_autorizacao_repositorio_e_main(tmp_path):
    resultado, registro = _executar(tmp_path / "auth", autorizacao="")
    assert resultado.returncode != 0
    assert "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998" in resultado.stderr
    assert "-X POST" not in registro

    resultado, registro = _executar(tmp_path / "repo", repositorio="someone/another-repo")
    assert resultado.returncode != 0
    assert "bootstrap autorizado somente para s2corporativo/ejc" in resultado.stderr
    assert "-X POST" not in registro

    resultado, registro = _executar(tmp_path / "branch", ramo="feature")
    assert resultado.returncode != 0
    assert "bootstrap autorizado somente para main" in resultado.stderr
    assert "-X POST" not in registro


def test_bootstrap_cria_conjunto_regras_aditivo_sem_put_patch_delete(tmp_path):
    resultado, registro = _executar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
    assert "-X POST repos/s2corporativo/ejc/rulesets" in registro
    assert "-X PUT" not in registro
    assert "-X PATCH" not in registro
    assert "-X DELETE" not in registro

    payload = json.loads((tmp_path / "payload").read_text(encoding="utf-8"))
    assert payload["name"] == NOME_CONJUNTO_REGRAS
    assert payload["enforcement"] == "active"
    assert payload["bypass_actors"] == []
    assert payload["conditions"]["ref_name"] == {
        "include": ["refs/heads/main"],
        "exclude": [],
    }
    regras = {regra["type"]: regra for regra in payload["rules"]}
    assert {"deletion", "non_fast_forward", "required_linear_history", "pull_request", "required_status_checks"} == set(regras)
    regra_pull_request = regras["pull_request"]["parameters"]
    assert sorted(regra_pull_request["allowed_merge_methods"]) == ["rebase", "squash"]
    assert regra_pull_request["dismiss_stale_reviews_on_push"] is True
    assert regra_pull_request["require_code_owner_review"] is True
    assert regra_pull_request["require_last_push_approval"] is True
    assert regra_pull_request["required_approving_review_count"] >= 1
    assert regra_pull_request["required_review_thread_resolution"] is True
    verificacoes = regras["required_status_checks"]["parameters"]
    assert verificacoes["do_not_enforce_on_create"] is False
    assert verificacoes["strict_required_status_checks_policy"] is True
    assert verificacoes["required_status_checks"] == [
        {"context": contexto, "integration_id": ID_INTEGRACAO} for contexto in CONTEXTOS
    ]


def test_bootstrap_e_idempotente_e_recusa_conjunto_regras_divergente(tmp_path):
    resultado, registro = _executar(tmp_path / "ok", cenario="existing")
    assert resultado.returncode == 0, resultado.stderr
    assert "já estava ativo e íntegro" in resultado.stdout
    assert "-X POST" not in registro

    resultado, registro = _executar(tmp_path / "bad", cenario="existing_divergent")
    assert resultado.returncode != 0
    assert "diverge do baseline" in resultado.stderr
    assert "-X POST" not in registro


def test_bootstrap_falha_fechado_em_nome_canonico_duplicado(tmp_path):
    resultado, registro = _executar(tmp_path, cenario="duplicate")
    assert resultado.returncode != 0
    assert "mais de um ruleset com nome canônico" in resultado.stderr
    assert "-X POST" not in registro


def test_bootstrap_reconcilia_falha_transporte_apos_criacao(tmp_path):
    resultado, registro = _executar(tmp_path, cenario="transport_after_apply")
    assert resultado.returncode == 0, resultado.stderr
    assert "POST não retornou resposta confiável" in resultado.stderr
    assert "-X POST" in registro
    assert "rulesets/998" in registro


def test_bootstrap_post_rejeitado_falha_fechado_sem_estado(tmp_path):
    resultado, registro = _executar(tmp_path, cenario="post_rejected")
    assert resultado.returncode != 0
    assert "POST não retornou resposta confiável" in resultado.stderr
    assert "esperado exatamente um ruleset canônico após bootstrap; encontrados 0" in resultado.stderr
    assert "-X POST" in registro
    assert not (tmp_path / "state").exists()


def test_bootstrap_nao_tem_mutacao_destrutiva_protecao_branch():
    fonte = SCRIPT_BOOTSTRAP.read_text(encoding="utf-8")
    assert "branches/$BRANCH/protection" not in fonte
    assert "-X PUT" not in fonte
    assert "-X PATCH" not in fonte
    assert "-X DELETE" not in fonte


def test_bootstrap_security_gate_usa_workflow_confiavel_e_contexto_bloqueante():
    fluxo_bootstrap = FLUXO_BOOTSTRAP.read_text(encoding="utf-8")
    script = SCRIPT_BOOTSTRAP.read_text(encoding="utf-8")
    governanca = FLUXO_GOVERNANCA.read_text(encoding="utf-8")

    assert "pull_request_target:" in fluxo_bootstrap
    assert "pull_request_review:" in fluxo_bootstrap
    assert "types: [submitted]" in fluxo_bootstrap
    assert "types: [opened, synchronize, reopened, edited]" in fluxo_bootstrap
    assert "actions/checkout" not in fluxo_bootstrap
    assert "gh api --paginate" in fluxo_bootstrap
    assert "Bootstrap protection — security auditor" in fluxo_bootstrap
    assert "Bootstrap protection — security auditor" in script
    assert "scripts/governanca/branch-protection-bootstrap.sh" in fluxo_bootstrap
    assert ".github/workflows/bootstrap-protection-governance.yml" in fluxo_bootstrap
    assert ".github/workflows/governanca-v2.yml" in fluxo_bootstrap
    assert "name: Governança — travas de PR" in governanca
    assert "types: [opened, synchronize, reopened, edited]" in governanca
    assert "scripts/governanca/branch-protection-bootstrap\\.sh" in governanca

    _validar_sintaxe_bash_dos_blocos_run(fluxo_bootstrap)
    _validar_sintaxe_bash_dos_blocos_run(governanca)


def test_security_gate_rejeita_marcador_autodeclarado_e_vincula_revisao_ao_head():
    fluxo_bootstrap = FLUXO_BOOTSTRAP.read_text(encoding="utf-8")
    governanca = FLUXO_GOVERNANCA.read_text(encoding="utf-8")

    for fonte in (fluxo_bootstrap, governanca):
        assert "security-auditor: executado" not in fonte
        assert "pulls/$PR_NUMBER/reviews?per_page=100" in fonte
        assert "| jq -s 'add'" in fonte
        assert 'select(.user.login == "coderabbitai[bot]")' in fonte
        assert "select(.commit_id == $sha)" in fonte
        assert '.state == "APPROVED" or .state == "COMMENTED"' in fonte
        assert 'Actionable comments posted:[[:space:]]*0' in fonte
        assert 'test("Actionable comments posted:"; "i") | not' not in fonte
        assert "HEAD_SHA" in fonte
