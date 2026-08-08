# ── tests/test_heartbeat_resultado.py ────────────────────────────────────────
# Onda 5 — Heartbeats aferem RESULTADO, não só execução.
#
# Armadilha confirmada pela auditoria: "captura DJEN reporta ok há meses sem
# nunca ter capturado nada" — o heartbeat só olhava last_run_at/last_status.
# Agora avaliar_job/avaliar_jobs cruzam a execução com a saúde da fonte
# correspondente em fontes_ingestao (services/ingestao_saude.py):
#   • job em dia + fonte `nunca_produziu`/`parou_de_produzir` → "sem_resultado"
#     (alerta com motivo explícito), nunca "ok";
#   • job saudável com fonte produzindo → "ok";
#   • job sem fonte mapeada → comportamento anterior preservado.
# Tudo SEM Postgres (lógica pura + fakes locais, padrão do repo).
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.config import get_settings
from app.services import diagnostico_service as dg
from app.services import heartbeat_service as hb
from app.services.ingestao_saude import avaliar_saude_fonte

UTC = timezone.utc


def _agora() -> datetime:
    return datetime.now(UTC)


def _saude_nunca_produziu():
    """Veredito REAL de ingestao_saude: executou, acervo em zero."""
    s = avaliar_saude_fonte(
        slug="djen", ativo=True, ultima_execucao=_agora() - timedelta(hours=1),
        ultimo_status="sucesso", ultimo_erro=None, registros_novos=0,
        registros_total=0, execucoes_zeradas_consecutivas=0, ja_produziu=False,
    )
    assert s.situacao == "nunca_produziu" and s.critico
    return s


def _saude_ok():
    s = avaliar_saude_fonte(
        slug="djen", ativo=True, ultima_execucao=_agora() - timedelta(hours=1),
        ultimo_status="sucesso", ultimo_erro=None, registros_novos=3,
        registros_total=10, execucoes_zeradas_consecutivas=0, ja_produziu=True,
    )
    assert s.situacao == "ok"
    return s


def _saude_parou_de_produzir():
    s = avaliar_saude_fonte(
        slug="djen", ativo=True, ultima_execucao=_agora() - timedelta(hours=1),
        ultimo_status="sucesso", ultimo_erro=None, registros_novos=0,
        registros_total=0, execucoes_zeradas_consecutivas=5, ja_produziu=True,
    )
    assert s.situacao == "parou_de_produzir" and s.critico
    return s


# ══════════════════════════════════════════════════════════════════════════════
# avaliar_job — cruzamento execução × resultado (lógica pura)
# ══════════════════════════════════════════════════════════════════════════════

def test_job_em_dia_com_fonte_nunca_produziu_nao_e_ok():
    r = hb.avaliar_job(_agora() - timedelta(hours=2), "ok", max_age_horas=26,
                       saude_fonte=_saude_nunca_produziu())
    assert r["status"] == "sem_resultado"          # NÃO "ok" — o falso positivo
    assert r["fonte_situacao"] == "nunca_produziu"
    assert "nunca_produziu" in r["motivo"]         # motivo explícito no payload


def test_job_em_dia_com_fonte_que_parou_de_produzir_vira_alerta():
    r = hb.avaliar_job(_agora() - timedelta(hours=2), "ok", max_age_horas=26,
                       saude_fonte=_saude_parou_de_produzir())
    assert r["status"] == "sem_resultado"
    assert r["fonte_situacao"] == "parou_de_produzir"


def test_job_saudavel_com_fonte_produzindo_segue_ok():
    r = hb.avaliar_job(_agora() - timedelta(hours=2), "ok", max_age_horas=26,
                       saude_fonte=_saude_ok())
    assert r["status"] == "ok"


def test_job_sem_fonte_mapeada_preserva_comportamento():
    r = hb.avaliar_job(_agora() - timedelta(hours=2), "ok", max_age_horas=26)
    assert r["status"] == "ok"
    assert "fonte_situacao" not in r


def test_defasagem_prevalece_sobre_falta_de_resultado():
    # Job parado é o sinal MAIOR — a fonte crítica não mascara a parada.
    r = hb.avaliar_job(_agora() - timedelta(hours=40), "ok", max_age_horas=26,
                       saude_fonte=_saude_nunca_produziu())
    assert r["status"] == "defasado"


def test_erro_de_execucao_prevalece_sobre_falta_de_resultado():
    r = hb.avaliar_job(_agora() - timedelta(hours=1), "erro", max_age_horas=26,
                       saude_fonte=_saude_nunca_produziu())
    assert r["status"] == "erro"


def test_avaliar_job_aceita_saude_em_dict():
    # O veredito pode chegar serializado (to_dict) — mesmo rebaixamento.
    r = hb.avaliar_job(_agora() - timedelta(hours=1), "ok", max_age_horas=26,
                       saude_fonte=_saude_nunca_produziu().to_dict())
    assert r["status"] == "sem_resultado"


# ══════════════════════════════════════════════════════════════════════════════
# avaliar_jobs — mapeamento job → fonte (FONTE_POR_JOB)
# ══════════════════════════════════════════════════════════════════════════════

def test_avaliar_jobs_cruza_apenas_jobs_mapeados():
    agora = _agora()
    heartbeats = {
        nome: {"last_run_at": agora - timedelta(hours=1), "last_status": "ok"}
        for nome in hb.JOBS_MONITORADOS
    }
    saudes = {"djen": _saude_nunca_produziu(), "datajud_processos": _saude_ok()}
    jobs = {j["job_name"]: j
            for j in hb.avaliar_jobs(heartbeats, agora=agora,
                                     saudes_fontes=saudes)}
    assert jobs[hb.JOB_DJEN]["status"] == "sem_resultado"
    assert jobs[hb.JOB_DJEN]["fonte_slug"] == "djen"
    assert jobs[hb.JOB_DJEN]["motivo"]
    assert jobs[hb.JOB_DATAJUD]["status"] == "ok"
    # Sem fonte mapeada (prazos, DOU) → avaliação por execução preservada.
    assert jobs[hb.JOB_PRAZOS_VENCIDOS]["status"] == "ok"
    assert jobs[hb.JOB_PRAZOS_VENCIDOS]["fonte_slug"] is None
    assert jobs[hb.JOB_DIARIO]["status"] == "ok"


def test_avaliar_jobs_sem_saudes_preserva_contrato_antigo():
    agora = _agora()
    heartbeats = {hb.JOB_DJEN: {"last_run_at": agora - timedelta(hours=1),
                                "last_status": "ok"}}
    jobs = {j["job_name"]: j for j in hb.avaliar_jobs(heartbeats, agora=agora)}
    assert jobs[hb.JOB_DJEN]["status"] == "ok"


def test_fonte_por_job_mapeia_capturas_conhecidas():
    # DJEN e DataJud têm linha em fontes_ingestao; DOU não registra fonte.
    assert hb.FONTE_POR_JOB[hb.JOB_DJEN] == "djen"
    assert hb.FONTE_POR_JOB[hb.JOB_DATAJUD] == "datajud_processos"
    assert hb.JOB_DIARIO not in hb.FONTE_POR_JOB


# ══════════════════════════════════════════════════════════════════════════════
# diagnostico._probe_heartbeat_jobs — painel rebaixa para alerta com motivo
# ══════════════════════════════════════════════════════════════════════════════

class _Res:
    def __init__(self, lista):
        self._lista = lista

    def scalars(self):
        return self

    def all(self):
        return self._lista


class _SessaoComFontes:
    """Despacha o SELECT pela tabela: scheduler_heartbeat vs fontes_ingestao."""

    def __init__(self, heartbeats, fontes=None, falha_fontes=False):
        self._heartbeats = heartbeats
        self._fontes = fontes or []
        self._falha_fontes = falha_fontes

    async def execute(self, stmt, params=None):
        if "fontes_ingestao" in str(stmt):
            if self._falha_fontes:
                raise RuntimeError("relation fontes_ingestao does not exist")
            return _Res(self._fontes)
        return _Res(self._heartbeats)


def _hb_row(job_name, last_run_at, last_status="ok", detail=None):
    return SimpleNamespace(job_name=job_name, last_run_at=last_run_at,
                           last_status=last_status, detail=detail)


def _fonte_row(slug, novos=0, total=0, ja_produziu=False, zeradas=0):
    return SimpleNamespace(
        slug=slug, ativo=True, ultima_execucao=_agora() - timedelta(hours=1),
        ultimo_status="sucesso", ultimo_erro=None, registros_novos=novos,
        registros_total=total, execucoes_zeradas_consecutivas=zeradas,
        ja_produziu=ja_produziu,
    )


async def test_probe_rebaixa_job_ok_com_fonte_improdutiva(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    heartbeats = [_hb_row(nome, agora - timedelta(hours=1))
                  for nome in hb.JOBS_MONITORADOS]
    fontes = [_fonte_row("djen")]                 # executou e nunca produziu
    r = await dg._probe_heartbeat_jobs(
        _SessaoComFontes(heartbeats, fontes), s)
    assert r["status"] == "alerta"
    assert r["resumo"]["sem_resultado"] == 1
    dj = [j for j in r["jobs"] if j["job_name"] == hb.JOB_DJEN][0]
    assert dj["status"] == "sem_resultado"
    assert "nunca_produziu" in r["detalhe"]       # motivo explícito no painel


async def test_probe_ok_quando_fontes_produzem(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    heartbeats = [_hb_row(nome, agora - timedelta(hours=1))
                  for nome in hb.JOBS_MONITORADOS]
    fontes = [_fonte_row("djen", novos=4, total=9, ja_produziu=True),
              _fonte_row("datajud_processos", novos=1, total=2,
                         ja_produziu=True)]
    r = await dg._probe_heartbeat_jobs(
        _SessaoComFontes(heartbeats, fontes), s)
    assert r["status"] == "ok"
    assert r["resumo"]["sem_resultado"] == 0


async def test_probe_sem_tabela_de_fontes_preserva_comportamento(monkeypatch):
    # fontes_ingestao indisponível → avaliação por execução (best-effort).
    s = get_settings()
    monkeypatch.setattr(s, "ENABLE_SCHEDULER", True)
    agora = _agora()
    heartbeats = [_hb_row(nome, agora - timedelta(hours=1))
                  for nome in hb.JOBS_MONITORADOS]
    r = await dg._probe_heartbeat_jobs(
        _SessaoComFontes(heartbeats, falha_fontes=True), s)
    assert r["status"] == "ok"
