"""O painel de jobs não pode mentir: backup pulado ≠ backup ok, job que bate
ponto tem de ser avaliado, e comentário de gate tem de bater com o default real.

Regressões de três achados:
  1. `_job_backup_drive_monitorado` chamava o motor de backup ANTES de olhar
     `BACKUP_ENABLED` e, com a flag desligada, registrava "ok — pulado":
     painel verde para backup que não existe.
  2. `JOB_ENTRADA_EXPURGO` batia ponto mas estava fora de `JOBS_MONITORADOS` —
     o painel nunca avaliava o expurgo LGPD.
  3. Os comentários do scheduler diziam "DJEN_INGEST_ENABLED (default False)" /
     "TJMG_INGEST_ENABLED (default False)" enquanto o config define os dois
     como True — quem lia o scheduler concluía que a ingestão estava parada.

Sem banco e sem rede: `_bater_ponto` e o motor de backup são substituídos por
duplos; `registrar_heartbeat` roda contra um `_FakeDB` que só guarda o INSERT.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.services import heartbeat_service as hb
from app.services import scheduler as sch


# ── Duplos ────────────────────────────────────────────────────────────────────
class _FakeDB:
    """Sessão mínima: registra os parâmetros do UPSERT do heartbeat."""

    def __init__(self):
        self.execucoes: list[dict] = []
        self.commits = 0

    async def execute(self, _stmt, params=None):
        self.execucoes.append(params or {})
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — caminho de erro
        pass


def _espionar_ponto(monkeypatch) -> list[tuple]:
    batidas: list[tuple] = []

    async def _fake(job, status, detail=None):
        batidas.append((job, status, detail))

    monkeypatch.setattr(sch, "_bater_ponto", _fake)
    return batidas


def _motor_proibido(monkeypatch) -> None:
    """Com BACKUP_ENABLED=false o motor de backup não pode nem ser chamado."""
    from app.services import backup_execution_service as bes

    async def _bomba():
        raise AssertionError(
            "gate BACKUP_ENABLED deve ser verificado ANTES de chamar o motor"
        )

    monkeypatch.setattr(bes, "job_backup_drive_exclusivo", _bomba)


# ── 1. Backup desligado não pode pintar o painel de verde ────────────────────
async def test_backup_desligado_registra_status_nao_saudavel(monkeypatch):
    monkeypatch.setattr(sch.settings, "BACKUP_ENABLED", False)
    _motor_proibido(monkeypatch)
    batidas = _espionar_ponto(monkeypatch)

    await sch._job_backup_drive_monitorado()

    job, status, detalhe = batidas[-1]
    assert job == hb.JOB_BACKUP_DRIVE
    assert status != "ok", "backup pulado não pode bater ponto 'ok'"
    assert status in hb._STATUS_VALIDOS
    assert "BACKUP_ENABLED=false" in (detalhe or "")


async def test_backup_ligado_e_bem_sucedido_continua_ok(monkeypatch):
    monkeypatch.setattr(sch.settings, "BACKUP_ENABLED", True)
    batidas = _espionar_ponto(monkeypatch)
    from app.services import backup_execution_service as bes

    async def _ok():
        return {"ok": True, "status": "ok"}

    monkeypatch.setattr(bes, "job_backup_drive_exclusivo", _ok)
    await sch._job_backup_drive_monitorado()
    assert batidas[-1][:2] == (hb.JOB_BACKUP_DRIVE, "ok")


async def test_status_do_backup_desligado_e_lido_como_problema(monkeypatch):
    """Ponta a ponta do vocabulário: o que o job registra é o que o painel lê."""
    monkeypatch.setattr(sch.settings, "BACKUP_ENABLED", False)
    _motor_proibido(monkeypatch)
    registrados: list[tuple] = []

    async def _ponto(job, status, detail=None):
        db = _FakeDB()
        await hb.registrar_heartbeat(db, job, status, detail)
        registrados.append((db.execucoes[-1]["status"], db.execucoes[-1]["detail"]))

    monkeypatch.setattr(sch, "_bater_ponto", _ponto)
    await sch._job_backup_drive_monitorado()

    status_persistido, detalhe = registrados[-1]
    avaliacao = hb.avaliar_job(
        datetime.now(timezone.utc), status_persistido, max_age_horas=26
    )
    assert avaliacao["status"] != "ok"
    assert "BACKUP_ENABLED=false" in (detalhe or "")


def test_heartbeat_so_aceita_ok_ou_erro():
    """Documenta o vocabulário: qualquer outra palavra é coagida a 'erro'."""
    assert hb._STATUS_VALIDOS == {"ok", "erro"}


async def test_status_inventado_vira_erro_no_upsert():
    db = _FakeDB()
    await hb.registrar_heartbeat(db, hb.JOB_BACKUP_DRIVE, "pulado", "x")
    assert db.execucoes[-1]["status"] == "erro"


# ── 2. Cobertura do painel: todo job que bate ponto é avaliado ───────────────
def test_expurgo_da_entrada_unica_e_monitorado():
    config = hb.JOBS_MONITORADOS.get(hb.JOB_ENTRADA_EXPURGO)
    assert config is not None, "job bate ponto e o painel precisa avaliá-lo"
    assert "03h50" in config["cadencia"]          # CronTrigger(hour=3, minute=50)
    assert config["max_age_horas"] == hb._MAX_DIARIO  # cadência diária


def test_todo_job_constante_esta_no_dict_de_monitorados():
    """Trava a classe do defeito: constante nova sem entrada no dict."""
    constantes = {
        valor
        for nome, valor in vars(hb).items()
        if nome.startswith("JOB_") and isinstance(valor, str)
    }
    assert constantes == set(hb.JOBS_MONITORADOS)


def test_expurgo_entra_na_avaliacao_do_painel():
    agora = datetime.now(timezone.utc)
    heartbeats = {
        hb.JOB_ENTRADA_EXPURGO: {
            "last_run_at": agora - timedelta(hours=1),
            "last_status": "ok",
            "detail": '{"batches_removidos": 0}',
        }
    }
    avaliados = {j["job_name"]: j for j in hb.avaliar_jobs(heartbeats, agora=agora)}
    assert avaliados[hb.JOB_ENTRADA_EXPURGO]["status"] == "ok"
    # Sem heartbeat, o painel diz "nunca_executou" (gate opt-in desligado) —
    # nunca "ok" mudo.
    sem = {j["job_name"]: j for j in hb.avaliar_jobs({}, agora=agora)}
    assert sem[hb.JOB_ENTRADA_EXPURGO]["status"] == "nunca_executou"


# ── 3. Comentários de gate têm de bater com o default real do config ─────────
def _comentario_acima(fonte: str, marcador: str) -> str:
    linhas = fonte.splitlines()
    idx = next(i for i, linha in enumerate(linhas) if marcador in linha)
    bloco: list[str] = []
    for j in range(idx - 1, -1, -1):
        atual = linhas[j].strip()
        if atual.startswith("#"):
            bloco.insert(0, atual)
        elif bloco:
            break
    return "\n".join(bloco)


@pytest.mark.parametrize(
    "marcador,flag",
    [
        ('id="ing_djen"', "DJEN_INGEST_ENABLED"),
        ('id="ing_tjmg"', "TJMG_INGEST_ENABLED"),
    ],
)
def test_comentario_do_gate_declara_o_default_real(marcador, flag):
    fonte = inspect.getsource(sch)
    comentario = _comentario_acima(fonte, marcador)
    default = getattr(Settings(_env_file=None), flag)
    esperado = f"{flag} (default {default}"
    assert esperado in comentario, comentario
    mentira = f"{flag} (default {not default}"
    assert mentira not in comentario
