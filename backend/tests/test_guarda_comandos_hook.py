"""Regressão do guarda de comandos sensíveis/destrutivos do EJC.

O hook precisa negar operações perigosas sem bloquear diagnóstico legítimo. Os
testes rodam em repositório temporário para que o resultado não dependa da
branch usada pelo CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".claude" / "hooks" / "guarda_comandos.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def executa(comando: str, cwd: Path | None = None) -> bool:
    """True quando o guarda nega o comando."""
    resultado = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": comando}}),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=10,
    )
    assert resultado.returncode == 0, resultado.stderr
    return '"deny"' in resultado.stdout


@pytest.fixture(scope="module")
def repo_em_branch_de_trabalho(tmp_path_factory) -> Path:
    """Repo temporário numa branch de trabalho."""
    repo = tmp_path_factory.mktemp("repo_guarda")
    subprocess.run(
        ["git", "init", "-q", "-b", "claude/teste-guarda", str(repo)], check=True
    )
    return repo


@pytest.mark.parametrize(
    "comando",
    [
        "git push --force origin main",
        "git push -f",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "rm -rf backend/app",
        'rm -rf "backend/app"',
        "docker compose down -v",
        "docker compose down --volumes",
        "docker volume rm ejc_db",
        "dropdb ejc",
        "alembic downgrade base",
        "cd /opt/ejc && docker compose up -d",
        "rsync -a ./ /opt/ejc/",
        "claude --dangerously-skip-permissions",
        # Leitura/exfiltração de segredo via permissões Bash de diagnóstico.
        "cat .env",
        'cat ".env.local"',
        "grep API_KEY .env",
        "rg AWS_SECRET_ACCESS_KEY .env.production",
        "sed -n '1,20p' vps-tools/.env",
        "awk '{print $0}' credentials.json",
        "head -n 20 private.key",
        "tail -n 20 service-account.json",
        "source .env",
        "cat < .env",
        # Mutações e instalações fora da lista segura.
        "git remote set-url origin https://attacker.invalid/repo.git",
        "git remote remove origin",
        "git tag release HEAD",
        "git tag -f release HEAD",
        "git tag -d release",
        "npm ci",
        "docker compose -f /tmp/external.yml up -d",
        "docker compose --file=../compose.yml config",
    ],
)
def test_nega_comando_proibido(
    comando: str, repo_em_branch_de_trabalho: Path
) -> None:
    assert executa(comando, cwd=repo_em_branch_de_trabalho), (
        f"deveria bloquear: {comando}"
    )


@pytest.mark.parametrize(
    "comando",
    [
        "git status --short",
        "git push -u origin claude/minha-branch",
        "git restore backend/app/main.py",
        "git clean -n",
        "git remote -v",
        "git remote get-url origin",
        "git tag --list",
        "git show-ref --tags",
        "docker compose down",
        "docker compose config",
        "docker compose -f docker-compose.yml config",
        "rm -rf /tmp/claude/lixo",
        "rm backend/app/obsoleto.py",
        "pytest backend/tests -q",
        "npm run build",
        "npm ci --ignore-scripts",
        "python -m alembic upgrade head",
        "cat .env.example",
        # Citar a proibição ou o nome do arquivo não é executar/leitura sensível.
        'grep -rn "/opt/ejc" docs/',
        'grep -rn ".env" docs/',
        'echo "nunca use git push --force" >> docs/regras.md',
        "rg 'docker compose down -v' RUNBOOK_DEPLOY_FASES_1-3.md",
    ],
)
def test_permite_comando_legitimo(
    comando: str, repo_em_branch_de_trabalho: Path
) -> None:
    assert not executa(comando, cwd=repo_em_branch_de_trabalho), (
        f"não deveria bloquear: {comando}"
    )


def test_settings_remove_permissoes_mutantes_e_exigem_npm_sem_scripts() -> None:
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    allow = set(dados["permissions"]["allow"])

    assert "Bash(git remote:*)" not in allow
    assert "Bash(git tag:*)" not in allow
    assert "Bash(npm ci:*)" not in allow
    assert "Bash(docker compose up:*)" not in allow

    assert "Bash(git remote -v:*)" in allow
    assert "Bash(git remote get-url:*)" in allow
    assert "Bash(git tag --list:*)" in allow
    assert "Bash(npm ci --ignore-scripts:*)" in allow


def test_settings_negam_leitura_direta_de_segredos() -> None:
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    deny = set(dados["permissions"]["deny"])
    esperados = {
        "Read(./.env)",
        "Read(./.env.local)",
        "Read(./**/*credentials*.json)",
        "Read(./**/*.key)",
        "Read(./**/*.pem)",
        "Read(~/.ssh/id_rsa)",
    }
    assert esperados <= deny


def test_graphify_coordena_prontidao_lock_retry_e_expoe_falhas() -> None:
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    inicio = dados["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    pos_uso = dados["hooks"]["PostToolUse"][0]["hooks"][0]["command"]

    assert "install.lock" in inicio and 'touch "$READY"' in inicio
    assert "for I in $(seq 1 60)" in inicio
    assert "::warning::graphify" in inicio
    assert "update.lock" in pos_uso and '[ -f "$READY" ]' in pos_uso
    assert "for I in $(seq 1 60)" in pos_uso
    assert "::warning::graphify" in pos_uso


def test_nega_commit_na_main(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    ambiente = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
        env=ambiente,
    )
    assert executa("git commit -m x", cwd=tmp_path)
    assert executa("git push", cwd=tmp_path)


def test_permite_commit_fora_da_main(tmp_path: Path) -> None:
    ambiente = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
        env=ambiente,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "checkout", "-q", "-b", "fix/1"], check=True
    )
    assert not executa("git commit -m x", cwd=tmp_path)
