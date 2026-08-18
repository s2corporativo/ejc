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
ID_CONJUNTO_REGRAS_FALSO = 481516
SHA_FALSO = "a" * 40
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
        "id": ID_CONJUNTO_REGRAS_FALSO,
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


def _escrever_gh_falso(diretorio_bin: Path) -> None:
    gh = diretorio_bin / "gh"
    gh.write_text(
        r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import time

argumentos = sys.argv[1:]
cenario = os.environ.get("FAKE_GH_SCENARIO", "success")
raiz_estado = pathlib.Path(os.environ["FAKE_GH_SHARED"])
raiz_estado.mkdir(parents=True, exist_ok=True)
registro = raiz_estado / "log"
arquivo_lock = raiz_estado / "remote-ref-lock"
arquivo_ruleset = raiz_estado / "ruleset.json"
arquivo_payload = raiz_estado / "payload.json"
diretorio_barreira = raiz_estado / "barreira-leitura-vazia"
esperado = json.loads(os.environ["FAKE_GH_RULESET"])
id_conjunto_regras = esperado["id"]

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
    sha = "invalido" if cenario == "invalid_branch_sha" else "a" * 40
    print(json.dumps({"name": "main", "protected": False, "commit": {"sha": sha}}))
    raise SystemExit(0)

if endpoint.endswith("/git/refs") and metodo == "POST":
    if cenario == "lock_failure_no_ref":
        raise SystemExit(1)
    try:
        descritor = os.open(arquivo_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit(1)
    with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
        arquivo.write(sys.stdin.read())
    print(json.dumps({"ref": "refs/tags/ejc-bootstrap-ruleset-lock-998", "object": {"sha": "a" * 40}}))
    raise SystemExit(0)

if "/git/ref/tags/ejc-bootstrap-ruleset-lock-998" in endpoint:
    if arquivo_lock.exists():
        print(json.dumps({"ref": "refs/tags/ejc-bootstrap-ruleset-lock-998", "object": {"sha": "a" * 40}}))
        raise SystemExit(0)
    raise SystemExit(1)

if "/rulesets?" in endpoint:
    if cenario == "duplicate":
        print(json.dumps([
            {"id": id_conjunto_regras, "name": esperado["name"], "enforcement": "active"},
            {"id": id_conjunto_regras + 1, "name": esperado["name"], "enforcement": "active"},
        ]))
    elif cenario.startswith("existing") or arquivo_ruleset.exists():
        print(json.dumps([{"id": id_conjunto_regras, "name": esperado["name"], "enforcement": "active"}]))
    else:
        if cenario == "concurrent" and not arquivo_lock.exists():
            diretorio_barreira.mkdir(exist_ok=True)
            (diretorio_barreira / str(os.getpid())).write_text("pronto", encoding="utf-8")
            limite = time.monotonic() + 3
            while len(list(diretorio_barreira.iterdir())) < 2:
                if time.monotonic() >= limite:
                    raise SystemExit(4)
                time.sleep(0.01)
        print("[]")
    raise SystemExit(0)

if endpoint.endswith(f"/rulesets/{id_conjunto_regras}"):
    atual = esperado
    if cenario == "existing_divergent":
        atual = json.loads(json.dumps(esperado))
        atual["rules"] = [regra for regra in atual["rules"] if regra["type"] != "pull_request"]
    elif arquivo_ruleset.exists():
        atual = json.loads(arquivo_ruleset.read_text(encoding="utf-8"))
    print(json.dumps(atual))
    raise SystemExit(0)

if endpoint.endswith("/rulesets") and metodo == "POST":
    payload = sys.stdin.read()
    arquivo_payload.write_text(payload, encoding="utf-8")
    if cenario == "post_rejected":
        raise SystemExit(1)
    arquivo_ruleset.write_text(json.dumps(esperado), encoding="utf-8")
    if cenario == "transport_after_apply":
        raise SystemExit(1)
    print(json.dumps(esperado))
    raise SystemExit(0)

raise SystemExit(3)
''',
        encoding="utf-8",
    )
    gh.chmod(0o755)


def _ambiente(diretorio_bin: Path, compartilhado: Path, cenario: str) -> dict[str, str]:
    ambiente = os.environ.copy()
    ambiente.update(
        {
            "PATH": f"{diretorio_bin}:{ambiente['PATH']}",
            "FAKE_GH_SCENARIO": cenario,
            "FAKE_GH_SHARED": str(compartilhado),
            "FAKE_GH_RULESET": json.dumps(_conjunto_regras_esperado()),
            "EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION": "998",
            "EJC_REPO": "s2corporativo/ejc",
            "EJC_BRANCH": "main",
            "EJC_BOOTSTRAP_LOCK_WAIT_ATTEMPTS": "20",
            "EJC_BOOTSTRAP_LOCK_WAIT_SECONDS": "0.05",
        }
    )
    return ambiente


def _executar(
    tmp_path: Path,
    *,
    cenario: str = "success",
    autorizacao: str = "998",
    repositorio: str = "s2corporativo/ejc",
    ramo: str = "main",
):
    diretorio_bin = tmp_path / "bin"
    compartilhado = tmp_path / "shared"
    diretorio_bin.mkdir(parents=True, exist_ok=True)
    compartilhado.mkdir(parents=True, exist_ok=True)
    _escrever_gh_falso(diretorio_bin)
    ambiente = _ambiente(diretorio_bin, compartilhado, cenario)
    ambiente["EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION"] = autorizacao
    ambiente["EJC_REPO"] = repositorio
    ambiente["EJC_BRANCH"] = ramo
    if cenario == "lock_stale":
        (compartilhado / "remote-ref-lock").write_text("stale", encoding="utf-8")
    resultado = subprocess.run(
        ["bash", str(SCRIPT_BOOTSTRAP)],
        cwd=RAIZ,
        env=ambiente,
        text=True,
        capture_output=True,
        check=False,
    )
    caminho_registro = compartilhado / "log"
    registro = caminho_registro.read_text(encoding="utf-8") if caminho_registro.exists() else ""
    return resultado, registro, compartilhado


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
                len(item) - len(item.lstrip()) for item in linhas_bloco if item.strip()
            ]
            recuo_conteudo = min(recuos) if recuos else recuo_run + 2
            blocos.append("\n".join(item[recuo_conteudo:] for item in linhas_bloco))
            continue
        indice += 1
    return blocos


def _validar_sintaxe_bash_dos_blocos_run(conteudo: str) -> None:
    blocos = _extrair_blocos_run(conteudo)
    assert blocos, "workflow sem blocos run: | para validar"
    for bloco in blocos:
        resultado = subprocess.run(
            ["bash", "-n"], input=bloco, text=True, capture_output=True, check=False
        )
        assert resultado.returncode == 0, resultado.stderr


def test_bootstrap_exige_autorizacao_repositorio_e_main(tmp_path):
    resultado, registro, _ = _executar(tmp_path / "auth", autorizacao="")
    assert resultado.returncode != 0
    assert "exige EJC_BRANCH_PROTECTION_BOOTSTRAP_AUTHORIZATION=998" in resultado.stderr
    assert "-X POST" not in registro

    resultado, registro, _ = _executar(tmp_path / "repo", repositorio="someone/another-repo")
    assert resultado.returncode != 0
    assert "bootstrap autorizado somente para s2corporativo/ejc" in resultado.stderr
    assert "-X POST" not in registro

    resultado, registro, _ = _executar(tmp_path / "branch", ramo="feature")
    assert resultado.returncode != 0
    assert "bootstrap autorizado somente para main" in resultado.stderr
    assert "-X POST" not in registro


def test_bootstrap_exige_sha_valido_retornado_pela_api_da_main(tmp_path):
    resultado, registro, _ = _executar(tmp_path, cenario="invalid_branch_sha")
    assert resultado.returncode != 0
    assert "API da main não contém SHA válido" in resultado.stderr
    assert "git/refs" not in registro
    assert "-X POST repos/s2corporativo/ejc/rulesets" not in registro


def test_bootstrap_cria_ruleset_sob_lock_remoto_sem_mutacao_destrutiva(tmp_path):
    resultado, registro, compartilhado = _executar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
    assert "-X POST repos/s2corporativo/ejc/git/refs" in registro
    assert "-X POST repos/s2corporativo/ejc/rulesets" in registro
    assert "-X PUT" not in registro
    assert "-X PATCH" not in registro
    assert "-X DELETE" not in registro
    assert (compartilhado / "remote-ref-lock").exists()

    payload_lock = json.loads((compartilhado / "remote-ref-lock").read_text(encoding="utf-8"))
    assert payload_lock == {
        "ref": "refs/tags/ejc-bootstrap-ruleset-lock-998",
        "sha": SHA_FALSO,
    }

    payload = json.loads((compartilhado / "payload.json").read_text(encoding="utf-8"))
    regras = {regra["type"]: regra for regra in payload["rules"]}
    assert payload["name"] == NOME_CONJUNTO_REGRAS
    assert payload["bypass_actors"] == []
    assert regras["pull_request"]["parameters"]["required_approving_review_count"] >= 1
    assert regras["pull_request"]["parameters"]["require_code_owner_review"] is True
    assert regras["pull_request"]["parameters"]["require_last_push_approval"] is True
    status = regras["required_status_checks"]["parameters"]
    assert status["do_not_enforce_on_create"] is False
    assert status["strict_required_status_checks_policy"] is True
    assert status["required_status_checks"] == [
        {"context": contexto, "integration_id": ID_INTEGRACAO} for contexto in CONTEXTOS
    ]


def test_bootstrap_e_idempotente_e_recusa_ruleset_divergente(tmp_path):
    resultado, registro, _ = _executar(tmp_path / "ok", cenario="existing")
    assert resultado.returncode == 0, resultado.stderr
    assert "já estava ativo e íntegro" in resultado.stdout
    assert "git/refs" not in registro

    resultado, registro, _ = _executar(tmp_path / "bad", cenario="existing_divergent")
    assert resultado.returncode != 0
    assert "diverge do baseline" in resultado.stderr
    assert "git/refs" not in registro


def test_bootstrap_falha_fechado_em_ruleset_duplicado(tmp_path):
    resultado, registro, _ = _executar(tmp_path, cenario="duplicate")
    assert resultado.returncode != 0
    assert "mais de um ruleset" in resultado.stderr
    assert "git/refs" not in registro


def test_bootstrap_reconcilia_falha_transporte_apos_criacao(tmp_path):
    resultado, registro, _ = _executar(tmp_path, cenario="transport_after_apply")
    assert resultado.returncode == 0, resultado.stderr
    assert "POST não retornou resposta confiável" in resultado.stderr
    assert f"rulesets/{ID_CONJUNTO_REGRAS_FALSO}" in registro


def test_bootstrap_post_rejeitado_mantem_sentinela_e_falha_fechado(tmp_path):
    resultado, registro, compartilhado = _executar(tmp_path, cenario="post_rejected")
    assert resultado.returncode != 0
    assert "esperado exatamente um ruleset canônico" in resultado.stderr
    assert (compartilhado / "remote-ref-lock").exists()
    assert not (compartilhado / "ruleset.json").exists()
    assert "-X POST repos/s2corporativo/ejc/rulesets" in registro


def test_bootstrap_lock_stale_falha_fechado_sem_novo_post(tmp_path):
    resultado, registro, _ = _executar(tmp_path, cenario="lock_stale")
    assert resultado.returncode != 0
    assert "possível lock stale" in resultado.stderr
    assert "-X POST repos/s2corporativo/ejc/rulesets" not in registro


def test_bootstrap_falha_aquisicao_sem_ref_nao_cai_para_post(tmp_path):
    resultado, registro, _ = _executar(tmp_path, cenario="lock_failure_no_ref")
    assert resultado.returncode != 0
    assert "ref-sentinela não existe" in resultado.stderr
    assert "-X POST repos/s2corporativo/ejc/rulesets" not in registro


def test_bootstrap_duas_execucoes_distribuidas_fazem_exatamente_um_post(tmp_path):
    diretorio_bin = tmp_path / "bin"
    compartilhado = tmp_path / "shared"
    diretorio_bin.mkdir()
    compartilhado.mkdir()
    _escrever_gh_falso(diretorio_bin)
    ambiente = _ambiente(diretorio_bin, compartilhado, "concurrent")

    processos = [
        subprocess.Popen(
            ["bash", str(SCRIPT_BOOTSTRAP)],
            cwd=RAIZ,
            env=ambiente,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    resultados = [processo.communicate(timeout=10) + (processo.returncode,) for processo in processos]
    assert [item[2] for item in resultados] == [0, 0], resultados

    registro = (compartilhado / "log").read_text(encoding="utf-8")
    assert registro.count("-X POST repos/s2corporativo/ejc/git/refs") == 2
    assert registro.count("-X POST repos/s2corporativo/ejc/rulesets") == 1
    assert (compartilhado / "ruleset.json").exists()
    assert len(list((compartilhado / "barreira-leitura-vazia").iterdir())) == 2


def test_bootstrap_nao_usa_lock_local_nem_mutacao_branch_protection():
    fonte = SCRIPT_BOOTSTRAP.read_text(encoding="utf-8")
    assert "flock" not in fonte
    assert "refs/tags/ejc-bootstrap-ruleset-lock-998" in fonte
    assert 'repos/$REPO/git/refs' in fonte
    assert "EJC_BOOTSTRAP_LOCK_SHA" not in fonte
    assert "git rev-parse HEAD" not in fonte
    assert "branches/$BRANCH/protection" not in fonte
    assert "-X PUT" not in fonte
    assert "-X PATCH" not in fonte
    assert "-X DELETE" not in fonte


def test_bootstrap_gate_seguranca_e_governanca_sao_fail_closed():
    fluxo_bootstrap = FLUXO_BOOTSTRAP.read_text(encoding="utf-8")
    governanca = FLUXO_GOVERNANCA.read_text(encoding="utf-8")
    fonte_bootstrap = SCRIPT_BOOTSTRAP.read_text(encoding="utf-8")

    assert "pull_request_target:" in fluxo_bootstrap
    assert "pull_request_review:" in fluxo_bootstrap
    assert "types: [submitted]" in fluxo_bootstrap
    assert "actions/checkout" not in fluxo_bootstrap
    assert "gh api --paginate" in fluxo_bootstrap
    assert "Bootstrap protection — security auditor" in fluxo_bootstrap
    assert "Bootstrap protection — security auditor" in fonte_bootstrap
    assert "name: Governança — travas de PR" in governanca
    assert "scripts/governanca/branch-protection-bootstrap\\.sh" in governanca

    for fonte in (fluxo_bootstrap, governanca):
        assert "security-auditor: executado" not in fonte
        assert "pulls/$PR_NUMBER/reviews?per_page=100" in fonte
        assert "| jq -s 'add'" in fonte
        assert 'select(.user.login == "coderabbitai[bot]")' in fonte
        assert "select(.commit_id == $sha)" in fonte
        assert 'Actionable comments posted:[[:space:]]*0' in fonte
        assert "HEAD_SHA" in fonte

    _validar_sintaxe_bash_dos_blocos_run(fluxo_bootstrap)
    _validar_sintaxe_bash_dos_blocos_run(governanca)
