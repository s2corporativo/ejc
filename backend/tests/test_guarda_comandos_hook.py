"""Regressão do guarda de comandos destrutivos (.claude/hooks/guarda_comandos.py).

O guarda converte em bloqueio automático as proibições escritas em `CLAUDE.md`
regra 12 e `docs/GOVERNANCA_IA.md` §6.1/§6.10. Um guarda que só bloqueia é
inútil se bloquear demais: a maior parte dos casos abaixo cobre o que ele
precisa **deixar passar** — citar a proibição num documento, apagar o próprio
scratchpad, rodar teste. Falso positivo aqui ensina a contornar o guarda.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guarda_comandos.py"


def executa(comando: str, cwd: Path | None = None) -> bool:
    """True quando o guarda nega o comando."""
    resultado = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": comando}}),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    assert resultado.returncode == 0, resultado.stderr
    return '"deny"' in resultado.stdout


@pytest.fixture(scope="module")
def repo_em_branch_de_trabalho(tmp_path_factory) -> Path:
    """Repo temporário numa branch de trabalho.

    O guarda consulta a branch ATUAL do diretório (nega git mutante na main —
    guarda_comandos.py). Sem cwd fixo, o veredito dependia de onde a suíte
    roda: no CI de PR o checkout é detached (permite) e no push da main o
    checkout está na main (nega) — o mesmo teste passava no PR e reprovava na
    main. Todos os casos parametrizados rodam aqui dentro para o resultado
    depender só do COMANDO; o comportamento na main tem teste próprio
    (test_nega_commit_na_main).
    """
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
        "docker compose down",
        "rm -rf /tmp/claude/lixo",
        "rm backend/app/obsoleto.py",
        "pytest backend/tests -q",
        "npm run build",
        "python -m alembic upgrade head",
        # Citar a proibição não é executá-la:
        'grep -rn "/opt/ejc" docs/',
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


def test_nega_commit_na_main(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
             "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"},
    )
    assert executa("git commit -m x", cwd=tmp_path)
    assert executa("git push", cwd=tmp_path)


def test_permite_commit_fora_da_main(tmp_path: Path) -> None:
    ambiente = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True, env=ambiente,
    )
    subprocess.run(["git", "-C", str(tmp_path), "checkout", "-q", "-b", "fix/1"], check=True)
    assert not executa("git commit -m x", cwd=tmp_path)
