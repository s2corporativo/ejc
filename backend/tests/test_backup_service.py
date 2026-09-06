# ── tests/test_backup_service.py ─────────────────────────────────────────────
# Backup diário cifrado → Google Drive: testes unitários SEM pg_dump nem Drive
# reais (fakes/monkeypatch). Cobre: ciclo cifra/decifra, montagem do nome com
# prefixo, seleção de rotação, gates (flag desligada / chave ausente) e o ciclo
# completo com colaboradores falsificados.
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from app.services import backup_service


CHAVE = Fernet.generate_key().decode()


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def first(self):
        return self._row

    def mappings(self):
        return self


class _FakeDB:
    """Sessão mínima: aceita execute/commit/rollback/add sem banco real."""

    def __init__(self):
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return _FakeResult()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    def add(self, obj):
        pass


# ── Cifra/decifra ─────────────────────────────────────────────────────────────

def test_cifra_decifra_roundtrip(tmp_path):
    original = tmp_path / "dump.bin"
    conteudo = b"pg_dump custom format \x00\x01\x02" * 100
    original.write_bytes(conteudo)

    cifrado = tmp_path / "dump.bin.enc"
    tamanho = backup_service.cifrar_arquivo(str(original), str(cifrado), CHAVE)
    assert tamanho == cifrado.stat().st_size
    # Artefato cifrado não pode conter o conteúdo em claro.
    assert conteudo[:16] not in cifrado.read_bytes()

    restaurado = tmp_path / "dump.restaurado"
    backup_service.decifrar_arquivo(str(cifrado), str(restaurado), CHAVE)
    assert restaurado.read_bytes() == conteudo


def test_decifrar_com_chave_errada_falha(tmp_path):
    original = tmp_path / "a.txt"
    original.write_bytes(b"dados sensiveis")
    cifrado = tmp_path / "a.enc"
    backup_service.cifrar_arquivo(str(original), str(cifrado), CHAVE)

    outra = Fernet.generate_key().decode()
    with pytest.raises(Exception):
        backup_service.decifrar_arquivo(str(cifrado), str(tmp_path / "b"), outra)


def test_fernet_exige_chave_configurada(monkeypatch):
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError, match="BACKUP_ENCRYPTION_KEY"):
        backup_service._fernet()
    # Chave malformada: erro claro SEM ecoar o valor (segredo fora de log).
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", "nao-e-fernet")
    with pytest.raises(RuntimeError) as exc:
        backup_service._fernet()
    assert "nao-e-fernet" not in str(exc.value)


# ── Nome/prefixo ──────────────────────────────────────────────────────────────

def test_nome_artefato_prefixo_e_timestamp():
    ts = datetime(2026, 7, 11, 5, 0, 0, tzinfo=timezone.utc)
    nome = backup_service._nome_artefato("db.dump", ts)
    assert nome == "ejc_backup_20260711T050000Z_db.dump.enc"
    assert nome.startswith(backup_service.PREFIXO_BACKUP)


def test_hora_backup_utc_parse_e_fallback(monkeypatch):
    monkeypatch.setattr(backup_service.settings, "BACKUP_HORA_UTC", "23:45")
    assert backup_service.hora_backup_utc() == (23, 45)
    # Malformada → fallback 05:00 (nunca derruba o boot do scheduler).
    for invalida in ("", "25:00", "abc", "5"):
        monkeypatch.setattr(backup_service.settings, "BACKUP_HORA_UTC", invalida)
        assert backup_service.hora_backup_utc() == (5, 0)


# ── Rotação ──────────────────────────────────────────────────────────────────

def test_rotacao_seleciona_somente_antigos_com_prefixo():
    agora = datetime(2026, 7, 11, 5, 0, tzinfo=timezone.utc)

    def _iso(dias_atras):
        return (agora - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    arquivos = [
        {"id": "novo", "name": "ejc_backup_x_db.dump.enc", "createdTime": _iso(1)},
        {"id": "limite", "name": "ejc_backup_y_db.dump.enc", "createdTime": _iso(13)},
        {"id": "velho", "name": "ejc_backup_z_db.dump.enc", "createdTime": _iso(15)},
        {"id": "muito_velho", "name": "ejc_backup_w_uploads.tar.gz.enc", "createdTime": _iso(60)},
        # Arquivo alheio na mesma pasta: NUNCA apagar, mesmo antigo.
        {"id": "alheio", "name": "contrato_cliente.pdf", "createdTime": _iso(400)},
        # Sem data confiável → fail-safe: não apagar.
        {"id": "sem_data", "name": "ejc_backup_q_db.dump.enc", "createdTime": "invalida"},
    ]
    apagar = backup_service.selecionar_para_rotacao(
        arquivos, retencao_dias=14, agora=agora
    )
    assert sorted(a["id"] for a in apagar) == ["muito_velho", "velho"]


# ── Gates ────────────────────────────────────────────────────────────────────

async def test_job_agendado_respeita_flag_desligada(monkeypatch):
    chamadas = []

    async def _fake_bg(**kwargs):
        chamadas.append(kwargs)

    monkeypatch.setattr(backup_service, "executar_backup_background", _fake_bg)
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENABLED", False)
    await backup_service.job_backup_drive()
    assert chamadas == []

    monkeypatch.setattr(backup_service.settings, "BACKUP_ENABLED", True)
    await backup_service.job_backup_drive()
    assert len(chamadas) == 1 and chamadas[0]["origem"] == "agendado"


async def test_executar_backup_falha_sem_chave(monkeypatch):
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", "")
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    resultado = await backup_service.executar_backup(_FakeDB(), origem="manual")
    assert resultado["ok"] is False
    assert resultado["status"] == "erro"
    assert "BACKUP_ENCRYPTION_KEY" in (resultado["erro"] or "")


# Nota: pasta do Drive ausente deixou de ser falha total — virou falha de
# OFFSITE (status "parcial" com prova local, ou "erro" quando
# BACKUP_OFFSITE_OBRIGATORIO=true). Casos cobertos em test_backup_offsite.py.


def test_pg_dump_ausente_erro_cita_dependencia(monkeypatch):
    monkeypatch.setattr(backup_service.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="postgresql-client"):
        backup_service._pg_dump_para("/tmp/nunca_criado.dump")


# ── Ciclo completo com fakes (sem pg_dump nem Drive reais) ───────────────────

async def test_ciclo_completo_com_fakes(monkeypatch, tmp_path):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "doc.pdf").write_bytes(b"%PDF fake" * 50)

    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", CHAVE)
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    monkeypatch.setattr(backup_service.settings, "BACKUP_UPLOADS_MAX_MB", 10)
    monkeypatch.setattr(backup_service.settings, "UPLOAD_DIR", str(uploads_dir))

    def _fake_pg_dump(destino):
        with open(destino, "wb") as f:
            f.write(b"PGDMP fake dump")
        return 15

    enviados: list[tuple[str, str]] = []

    def _fake_upload(service, caminho, nome, folder_id):
        # O artefato enviado precisa estar CIFRADO (nunca em claro).
        with open(caminho, "rb") as f:
            Fernet(CHAVE.encode()).decrypt(f.read())  # levanta se não-Fernet
        enviados.append((nome, folder_id))
        return {"id": f"drive-{len(enviados)}", "name": nome}

    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    monkeypatch.setattr(backup_service, "_drive_client_escrita", lambda: object())
    monkeypatch.setattr(backup_service, "_upload_drive_sync", _fake_upload)
    monkeypatch.setattr(backup_service, "_rotacionar_sync", lambda s, f, r: 2)

    db = _FakeDB()
    resultado = await backup_service.executar_backup(db, origem="manual")

    assert resultado["ok"] is True and resultado["status"] == "sucesso"
    assert resultado["rotacao_removidos"] == 2
    assert len(enviados) == 2  # db.dump.enc + uploads.tar.gz.enc
    nomes = [n for n, _ in enviados]
    assert all(n.startswith(backup_service.PREFIXO_BACKUP) for n in nomes)
    assert any(n.endswith("_db.dump.enc") for n in nomes)
    assert any(n.endswith("_uploads.tar.gz.enc") for n in nomes)
    assert all(pasta == "pasta123" for _, pasta in enviados)
    # Nenhum segredo no resultado (vai para log/estado/status).
    assert CHAVE not in str(resultado)


async def test_execucao_simultanea_segundo_retorna_em_execucao(monkeypatch, tmp_path):
    """TOCTOU do disparo: dois executar_backup concorrentes → só UM executa;
    o outro retorna status em_execucao na hora (flag síncrona, sem await entre
    o teste e o set)."""
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", CHAVE)
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    monkeypatch.setattr(backup_service.settings, "UPLOAD_DIR", str(tmp_path / "sem-uploads"))

    execucoes: list[str] = []

    def _fake_pg_dump(destino):
        execucoes.append(destino)
        with open(destino, "wb") as f:
            f.write(b"PGDMP fake dump")
        return 15

    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    monkeypatch.setattr(backup_service, "_drive_client_escrita", lambda: object())
    monkeypatch.setattr(
        backup_service, "_upload_drive_sync",
        lambda s, c, n, f: {"id": "x", "name": n},
    )
    monkeypatch.setattr(backup_service, "_rotacionar_sync", lambda s, f, r: 0)

    r1, r2 = await asyncio.gather(
        backup_service.executar_backup(_FakeDB(), origem="manual"),
        backup_service.executar_backup(_FakeDB(), origem="manual"),
    )
    # UPLOAD_DIR inexistente → o backup que roda termina "parcial" (aviso).
    assert sorted([r1["status"], r2["status"]]) == ["em_execucao", "parcial"]
    assert len(execucoes) == 1          # pg_dump rodou UMA vez
    assert backup_service.em_execucao() is False   # flag liberada no finally


async def test_dump_acima_do_teto_falha_sem_ler_o_arquivo(monkeypatch, tmp_path):
    """Teto BACKUP_DB_MAX_MB: dump maior que o limite → erro claro ANTES de
    carregar o dump em RAM (a cifragem Fernet leria o arquivo inteiro)."""
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", CHAVE)
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    monkeypatch.setattr(backup_service.settings, "BACKUP_DB_MAX_MB", 1)

    def _fake_pg_dump(destino):
        with open(destino, "wb") as f:
            f.write(b"PGDMP")
        return 2 * 1024 * 1024          # acima do teto de 1 MB

    cifrados: list[tuple] = []
    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    monkeypatch.setattr(
        backup_service, "cifrar_arquivo",
        lambda *a, **kw: cifrados.append(a) or 0,
    )

    resultado = await backup_service.executar_backup(_FakeDB(), origem="agendado")
    assert resultado["ok"] is False and resultado["status"] == "erro"
    assert "BACKUP_DB_MAX_MB" in (resultado["erro"] or "")
    assert cifrados == []               # o dump nunca foi lido/cifrado


async def test_uploads_acima_do_limite_gera_parcial(monkeypatch, tmp_path):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "grande.bin").write_bytes(b"x" * (2 * 1024 * 1024))

    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", CHAVE)
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    monkeypatch.setattr(backup_service.settings, "BACKUP_UPLOADS_MAX_MB", 1)
    monkeypatch.setattr(backup_service.settings, "UPLOAD_DIR", str(uploads_dir))

    def _fake_pg_dump(destino):
        with open(destino, "wb") as f:
            f.write(b"PGDMP fake dump")
        return 15

    enviados = []
    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    monkeypatch.setattr(backup_service, "_drive_client_escrita", lambda: object())
    monkeypatch.setattr(
        backup_service, "_upload_drive_sync",
        lambda s, c, n, f: enviados.append(n) or {"id": "x", "name": n},
    )
    monkeypatch.setattr(backup_service, "_rotacionar_sync", lambda s, f, r: 0)

    resultado = await backup_service.executar_backup(_FakeDB(), origem="agendado")
    assert resultado["status"] == "parcial"
    assert resultado["ok"] is True
    assert len(enviados) == 1 and enviados[0].endswith("_db.dump.enc")
    assert any("BACKUP_UPLOADS_MAX_MB" in a for a in resultado["avisos"])


# ── Retenção local cifrada (INF-04) ──────────────────────────────────────────

def test_persistir_local_copia_enc_e_rotaciona(tmp_path):
    """Os .enc do ciclo vão para BACKUP_DIR (0600) e só os `ejc_backup_*.enc`
    mais antigos que a retenção são apagados — nada em claro é tocado."""
    import os
    import time as _time

    origem = tmp_path / "tmp"
    origem.mkdir()
    (origem / "db.dump.enc").write_bytes(b"cifrado-db")
    (origem / "uploads.tar.gz.enc").write_bytes(b"cifrado-up")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    antigo = backup_dir / "ejc_backup_20200101T000000Z_db.dump.enc"
    antigo.write_bytes(b"velho")
    velho_ts = _time.time() - 40 * 86400
    os.utime(antigo, (velho_ts, velho_ts))
    em_claro = backup_dir / "outra_coisa.sql"
    em_claro.write_bytes(b"nao-e-do-ejc")
    os.utime(em_claro, (velho_ts, velho_ts))

    artefatos = [
        {"nome": "ejc_backup_20260906T120000Z_db.dump.enc", "caminho": str(origem / "db.dump.enc")},
        {"nome": "ejc_backup_20260906T120000Z_uploads.tar.gz.enc", "caminho": str(origem / "uploads.tar.gz.enc")},
    ]
    removidos = backup_service._persistir_local_sync(artefatos, str(backup_dir), 30)

    assert removidos == 1
    assert not antigo.exists()
    assert em_claro.exists(), "rotação só toca artefatos do prefixo EJC"
    for art in artefatos:
        destino = backup_dir / art["nome"]
        assert destino.exists()
        assert oct(destino.stat().st_mode & 0o777) == "0o600"
        assert art["retido_localmente"] is True


def test_persistir_local_sem_backup_dir_falha_claro():
    with pytest.raises(RuntimeError, match="BACKUP_DIR"):
        backup_service._persistir_local_sync([], "", 30)


@pytest.mark.asyncio
async def test_ciclo_persiste_retencao_local_mesmo_com_offsite_falho(monkeypatch, tmp_path):
    """Offsite indisponível NÃO deixa o ciclo sem cópia recuperável: os .enc
    ficam em BACKUP_DIR e o resultado expõe retencao_local_ok=True (o gate
    pré-deploy aceita essa prova — INF-04)."""
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "doc.txt").write_text("conteudo")
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(backup_service.settings, "BACKUP_ENCRYPTION_KEY", CHAVE)
    monkeypatch.setattr(backup_service.settings, "BACKUP_DESTINO", "gdrive")
    monkeypatch.setattr(backup_service.settings, "BACKUP_DRIVE_FOLDER_ID", "pasta123")
    monkeypatch.setattr(backup_service.settings, "BACKUP_OFFSITE_OBRIGATORIO", False)
    monkeypatch.setattr(backup_service.settings, "BACKUP_UPLOADS_MAX_MB", 10)
    monkeypatch.setattr(backup_service.settings, "UPLOAD_DIR", str(uploads_dir))
    monkeypatch.setattr(backup_service.settings, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_service.settings, "BACKUP_RETENTION_DAYS", 7)

    def _fake_pg_dump(destino):
        with open(destino, "wb") as f:
            f.write(b"PGDMP fake")
        return 10

    def _drive_indisponivel():
        raise RuntimeError("token expirado")

    monkeypatch.setattr(backup_service, "_pg_dump_para", _fake_pg_dump)
    monkeypatch.setattr(backup_service, "_drive_client_escrita", _drive_indisponivel)

    resultado = await backup_service.executar_backup(_FakeDB(), origem="pre_deploy")

    assert resultado["ok"] is True
    assert resultado["status"] == "parcial"
    assert resultado["offsite_ok"] is False
    assert resultado["retencao_local_ok"] is True
    assert resultado["retencao_local_dir"] == str(backup_dir)
    nomes = sorted(p.name for p in backup_dir.iterdir())
    assert any(n.endswith("_db.dump.enc") for n in nomes)
    assert any(n.endswith("_uploads.tar.gz.enc") for n in nomes)
    assert not any(n.endswith((".dump", ".tar.gz")) for n in nomes), "nada em claro em BACKUP_DIR"
