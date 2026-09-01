"""Migração segura de valores obsoletos do .env.

O script continua criando backup próprio quando usado isoladamente. No deploy,
reutiliza o snapshot transacional já produzido pelo executor para evitar
proliferação de cópias persistentes contendo segredos.
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


def _rodar(env_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(env_path), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
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
    def test_migra_as_duas_chaves(self, env_file: Path):
        r = _rodar(env_file)
        assert r.returncode == 0, r.stderr
        conteudo = env_file.read_text(encoding="utf-8")
        assert f"GROQ_MODEL={ATUAL}" in conteudo
        assert f"GROQ_MODEL_LARGE={ATUAL}" in conteudo
        assert DEPRECIADO not in conteudo

    def test_preserva_comentarios_ordem_e_demais_variaveis(self, env_file: Path):
        _rodar(env_file)
        conteudo = env_file.read_text(encoding="utf-8")
        assert "# Comentário que precisa sobreviver" in conteudo
        assert "# outro comentário" in conteudo
        assert "SECRET_KEY=chave-super-secreta-ficticia" in conteudo
        assert "DATABASE_URL=postgresql+asyncpg://u:p@db:5432/ejc" in conteudo
        assert len(conteudo.splitlines()) == len(ENV_BASE.splitlines())

    def test_e_idempotente(self, env_file: Path):
        _rodar(env_file)
        depois_da_primeira = env_file.read_text(encoding="utf-8")
        r2 = _rodar(env_file)
        assert r2.returncode == 0
        assert env_file.read_text(encoding="utf-8") == depois_da_primeira
        assert "nenhum valor obsoleto" in r2.stdout

    def test_nao_altera_valor_personalizado_pelo_titular(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("GROQ_MODEL=modelo-escolhido-pelo-escritorio\n", encoding="utf-8")
        r = _rodar(p)
        assert r.returncode == 0
        assert p.read_text(encoding="utf-8") == "GROQ_MODEL=modelo-escolhido-pelo-escritorio\n"

    def test_nao_casa_chave_por_prefixo(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text(f"OUTRO_GROQ_MODEL={DEPRECIADO}\n", encoding="utf-8")
        _rodar(p)
        assert p.read_text(encoding="utf-8") == f"OUTRO_GROQ_MODEL={DEPRECIADO}\n"

    def test_ausencia_da_variavel_nao_e_erro(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("SECRET_KEY=abc\n", encoding="utf-8")
        r = _rodar(p)
        assert r.returncode == 0
        assert p.read_text(encoding="utf-8") == "SECRET_KEY=abc\n"

    def test_env_inexistente_sai_zero(self, tmp_path: Path):
        r = _rodar(tmp_path / "nao-existe.env")
        assert r.returncode == 0


class TestBackupERollback:
    def test_standalone_cria_backup_antes_de_alterar(self, env_file: Path):
        _rodar(env_file)
        backups = list(env_file.parent.glob(".env.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == ENV_BASE

    def test_backup_standalone_nao_e_legivel_por_outros(self, env_file: Path):
        _rodar(env_file)
        backup = next(env_file.parent.glob(".env.bak.*"))
        modo = stat.S_IMODE(os.stat(backup).st_mode)
        assert modo & 0o077 == 0, f"backup com segredos em modo {oct(modo)}"

    def test_sem_alteracao_nao_cria_backup(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text(f"GROQ_MODEL={ATUAL}\n", encoding="utf-8")
        _rodar(p)
        assert list(tmp_path.glob(".env.bak.*")) == []

    def test_snapshot_externo_identico_e_owner_only_e_reutilizado(self, env_file: Path, tmp_path: Path):
        snapshot = tmp_path / "env.rollback"
        snapshot.write_bytes(env_file.read_bytes())
        snapshot.chmod(0o600)

        r = _rodar(env_file, "--backup-path", str(snapshot))

        assert r.returncode == 0, r.stderr
        assert "snapshot transacional externo validado" in r.stdout
        assert snapshot.read_text(encoding="utf-8") == ENV_BASE
        assert list(tmp_path.glob(".env.bak.*")) == []
        assert DEPRECIADO not in env_file.read_text(encoding="utf-8")

    def test_snapshot_externo_divergente_falha_antes_de_escrever(self, env_file: Path, tmp_path: Path):
        snapshot = tmp_path / "env.rollback"
        snapshot.write_text("estado-diferente\n", encoding="utf-8")
        snapshot.chmod(0o600)
        antes = env_file.read_bytes()

        r = _rodar(env_file, "--backup-path", str(snapshot))

        assert r.returncode == 2
        assert env_file.read_bytes() == antes
        assert "não corresponde ao estado atual" in r.stderr

    def test_snapshot_externo_com_permissao_ampla_falha_fechado(self, env_file: Path, tmp_path: Path):
        snapshot = tmp_path / "env.rollback"
        snapshot.write_bytes(env_file.read_bytes())
        snapshot.chmod(0o644)
        antes = env_file.read_bytes()

        r = _rodar(env_file, "--backup-path", str(snapshot))

        assert r.returncode == 2
        assert env_file.read_bytes() == antes
        assert "legível por grupo/outros" in r.stderr

    def test_snapshot_externo_symlink_e_rejeitado(self, env_file: Path, tmp_path: Path):
        real = tmp_path / "real.rollback"
        real.write_bytes(env_file.read_bytes())
        real.chmod(0o600)
        link = tmp_path / "env.rollback"
        link.symlink_to(real)
        antes = env_file.read_bytes()

        r = _rodar(env_file, "--backup-path", str(link))

        assert r.returncode == 2
        assert env_file.read_bytes() == antes
        assert "symlink" in r.stderr


class TestNaoVazaSegredo:
    def test_saida_nao_contem_valor_de_variavel(self, env_file: Path):
        r = _rodar(env_file)
        saida = r.stdout + r.stderr
        assert "gsk-ficticia-nao-e-real" not in saida
        assert "chave-super-secreta-ficticia" not in saida
        assert "postgresql+asyncpg" not in saida
        assert ATUAL in saida


class TestDryRun:
    def test_dry_run_nao_escreve(self, env_file: Path):
        antes = env_file.read_text(encoding="utf-8")
        r = _rodar(env_file, "--dry-run")
        assert r.returncode == 0
        assert env_file.read_text(encoding="utf-8") == antes
        assert list(env_file.parent.glob(".env.bak.*")) == []
        assert "dry-run" in r.stdout


class TestAvisoDoAgente:
    def test_avisa_agente_de_escrita_ligado_sem_alterar(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("AI_AGENT_ENABLED=true\n", encoding="utf-8")
        r = _rodar(p)
        assert "AI_AGENT_ENABLED" in r.stdout
        assert p.read_text(encoding="utf-8") == "AI_AGENT_ENABLED=true\n"


class TestWiringNosDeploys:
    def test_deploy_seguro_reutiliza_snapshot_transacional(self):
        conteudo = (RAIZ / "scripts" / "deploy_vps_safe.sh").read_text(encoding="utf-8")
        assert "migrar_env_obsoletos.sh" in conteudo
        assert '--backup-path "$ENV_ROLLBACK_FILE"' in conteudo

    def test_bootstrap_manual_chama_a_migracao(self):
        conteudo = (RAIZ / "scripts" / "deploy-vps.sh").read_text(encoding="utf-8")
        assert "migrar_env_obsoletos.sh" in conteudo

    def test_transacao_de_deploy_usa_o_script_seguro(self):
        """Elo VIVO da cadeia: transaction.sh (mutex + estado) → deploy_vps_safe.sh.

        Era a segunda metade de um teste que começava no workflow do Actions.
        Com o Actions arquivado em 31/08 (`b77ff4c`) a primeira metade perdeu o
        objeto, mas ESTA não: o deploy manual entra exatamente por aqui, e a
        publicação continua tendo que passar pelo script seguro. Separado para
        que o elo vivo não adormeça junto com o que morreu.
        """
        tx = (
            RAIZ / "scripts" / "deploy_workflow_transaction.sh"
        ).read_text(encoding="utf-8")
        assert "bash scripts/deploy_vps_safe.sh" in tx

    @pytest.mark.skipif(
        not (RAIZ / ".github" / "workflows" / "deploy-vps.yml").is_file(),
        reason=("GitHub Actions arquivado em 31/08 (b77ff4c) — workflows movidos "
                "para docs/arquivo/ci/github-actions-legacy/; Woodpecker é o CI oficial"),
    )
    def test_workflow_de_deploy_usa_o_script_seguro(self):
        """Primeiro elo, DORMENTE: workflow → deploy_workflow_transaction.sh.

        Volta a valer sozinho se o Actions for restaurado.
        """
        wf = (RAIZ / ".github" / "workflows" / "deploy-vps.yml").read_text(encoding="utf-8")
        assert "scripts/deploy_workflow_transaction.sh" in wf
