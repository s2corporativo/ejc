"""Migração de valores obsoletos do .env (AI-043) — consolidação 2026-07-29.

A troca do modelo Groq depreciado vivia embutida em `scripts/deploy-vps.sh`,
que é um bootstrap MANUAL e não faz parte do caminho de deploy real
(.github/workflows/deploy-vps.yml → scripts/deploy_vps_safe.sh). Na prática a
correção nunca rodava na VPS. Agora é um script único, chamado pelos dois
caminhos, e estes testes exercitam o script de verdade sobre .env temporários.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "migrar_env_obsoletos.sh"
DEPRECIADO = "llama-3.3-70b-versatile"
ATUAL = "openai/gpt-oss-120b"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash indisponível"
)


def _rodar(env_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), str(env_path), *args],
        capture_output=True, text=True, timeout=60,
    )


ENV_BASE = f"""\
# Comentário que precisa sobreviver
SECRET_KEY=chave-super-secreta-ficticia

GROQ_API_KEY=gsk-ficticia-nao-e-real
GROQ_MODEL={DEPRECIADO}
GROQ_MODEL_LARGE={DEPRECIADO}

# outro comentário
DATABASE_URL=postgresql+asyncpg://u:p@db:5432/ejc
"""


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text(ENV_BASE, encoding="utf-8")
    p.chmod(0o600)
    return p


class TestMigracaoDoModeloGroq:
    def test_migra_as_duas_chaves(self, env_file):
        r = _rodar(env_file)
        assert r.returncode == 0, r.stderr
        conteudo = env_file.read_text(encoding="utf-8")
        assert f"GROQ_MODEL={ATUAL}" in conteudo
        assert f"GROQ_MODEL_LARGE={ATUAL}" in conteudo
        assert DEPRECIADO not in conteudo

    def test_preserva_comentarios_ordem_e_demais_variaveis(self, env_file):
        _rodar(env_file)
        conteudo = env_file.read_text(encoding="utf-8")
        assert "# Comentário que precisa sobreviver" in conteudo
        assert "# outro comentário" in conteudo
        assert "SECRET_KEY=chave-super-secreta-ficticia" in conteudo
        assert "DATABASE_URL=postgresql+asyncpg://u:p@db:5432/ejc" in conteudo
        # Mesma quantidade de linhas: nada foi reescrito em bloco.
        assert len(conteudo.splitlines()) == len(ENV_BASE.splitlines())

    def test_e_idempotente(self, env_file):
        _rodar(env_file)
        depois_da_primeira = env_file.read_text(encoding="utf-8")
        r2 = _rodar(env_file)
        assert r2.returncode == 0
        assert env_file.read_text(encoding="utf-8") == depois_da_primeira
        assert "nenhum valor obsoleto" in r2.stdout

    def test_nao_altera_valor_personalizado_pelo_titular(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text("GROQ_MODEL=modelo-escolhido-pelo-escritorio\n", encoding="utf-8")
        r = _rodar(p)
        assert r.returncode == 0
        assert p.read_text(encoding="utf-8") == (
            "GROQ_MODEL=modelo-escolhido-pelo-escritorio\n"
        )

    def test_nao_casa_chave_por_prefixo(self, tmp_path):
        """`OUTRO_GROQ_MODEL=` não pode ser confundido com `GROQ_MODEL=`."""
        p = tmp_path / ".env"
        p.write_text(f"OUTRO_GROQ_MODEL={DEPRECIADO}\n", encoding="utf-8")
        _rodar(p)
        assert p.read_text(encoding="utf-8") == f"OUTRO_GROQ_MODEL={DEPRECIADO}\n"

    def test_ausencia_da_variavel_nao_e_erro(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text("SECRET_KEY=abc\n", encoding="utf-8")
        r = _rodar(p)
        assert r.returncode == 0
        assert p.read_text(encoding="utf-8") == "SECRET_KEY=abc\n"

    def test_env_inexistente_sai_zero(self, tmp_path):
        r = _rodar(tmp_path / "nao-existe.env")
        assert r.returncode == 0


class TestBackupERollback:
    def test_cria_backup_antes_de_alterar(self, env_file):
        _rodar(env_file)
        backups = list(env_file.parent.glob(".env.bak.*"))
        assert len(backups) == 1
        # O backup é o estado ANTERIOR — é o rollback.
        assert backups[0].read_text(encoding="utf-8") == ENV_BASE

    def test_backup_nao_e_legivel_por_outros(self, env_file):
        _rodar(env_file)
        backup = next(env_file.parent.glob(".env.bak.*"))
        modo = stat.S_IMODE(os.stat(backup).st_mode)
        assert modo & 0o077 == 0, f"backup com segredos em modo {oct(modo)}"

    def test_sem_alteracao_nao_cria_backup(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text(f"GROQ_MODEL={ATUAL}\n", encoding="utf-8")
        _rodar(p)
        assert list(tmp_path.glob(".env.bak.*")) == []


class TestNaoVazaSegredo:
    def test_saida_nao_contem_valor_de_variavel(self, env_file):
        r = _rodar(env_file)
        saida = r.stdout + r.stderr
        assert "gsk-ficticia-nao-e-real" not in saida
        assert "chave-super-secreta-ficticia" not in saida
        assert "postgresql+asyncpg" not in saida
        # O nome do modelo novo não é segredo e é útil no log de deploy.
        assert ATUAL in saida


class TestDryRun:
    def test_dry_run_nao_escreve(self, env_file):
        antes = env_file.read_text(encoding="utf-8")
        r = _rodar(env_file, "--dry-run")
        assert r.returncode == 0
        assert env_file.read_text(encoding="utf-8") == antes
        assert list(env_file.parent.glob(".env.bak.*")) == []
        assert "dry-run" in r.stdout


class TestAvisoDoAgente:
    def test_avisa_agente_de_escrita_ligado_sem_alterar(self, tmp_path):
        p = tmp_path / ".env"
        p.write_text("AI_AGENT_ENABLED=true\n", encoding="utf-8")
        r = _rodar(p)
        assert "AI_AGENT_ENABLED" in r.stdout
        # Só avisa: desligar é decisão do titular.
        assert p.read_text(encoding="utf-8") == "AI_AGENT_ENABLED=true\n"


class TestWiringNosDeploys:
    """A correção só vale se o caminho REAL de deploy chamar o script."""

    def test_deploy_seguro_chama_a_migracao(self):
        conteudo = (RAIZ / "scripts" / "deploy_vps_safe.sh").read_text(encoding="utf-8")
        assert "migrar_env_obsoletos.sh" in conteudo

    def test_bootstrap_manual_chama_a_migracao(self):
        conteudo = (RAIZ / "scripts" / "deploy-vps.sh").read_text(encoding="utf-8")
        assert "migrar_env_obsoletos.sh" in conteudo

    def test_workflow_de_deploy_usa_o_script_seguro(self):
        wf = (RAIZ / ".github" / "workflows" / "deploy-vps.yml").read_text(encoding="utf-8")
        assert "scripts/deploy_vps_safe.sh" in wf
