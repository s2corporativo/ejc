"""Análise assíncrona do Raio-X (Onda 1 — app/tasks/raio_x_tasks.py).

Tudo mockado — nenhum teste toca rede/DB/Redis/IA real. Fake DB local por
arquivo (padrão do repo), bordas externas monkeypatchadas nos módulos de
origem (documento_service.extrair_e_analisar, raio_x_service.preview_conversao,
dispatcher._redis_alcancavel). Cobre:
  (a) o endpoint de upload responde SEM executar a IA inline: persiste o
      documento pendente, marca `fila` e despacha a task;
  (b) upload com análise já em fila/em_processamento → 409 (sem despacho duplo);
  (c) a task transita fila → em_processamento → aguardando_conferencia e
      preenche resultado_analise/custo_ia;
  (d) falha inesperada marca `erro` com mensagem legível em
      relatorio["erro_processamento"];
  (e) falha por documento (lote novo) remove o documento e registra o erro em
      relatorio["erros_processamento"] → documentos_pendentes;
  (f) fallback sem Celery: agendar_analise usa BackgroundTasks; com Celery e
      Redis de pé, enfileira via .delay;
  (g) `fila` e `erro` entram no vocabulário canônico de status.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.schemas.raio_x import STATUS_RAIO_X, RaioXUpdate
from app.tasks import raio_x_tasks


def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _analise(status: str = "novo") -> RaioXAnalise:
    analise = RaioXAnalise(
        id="a1",
        titulo="Análise fictícia",
        status=status,
        created_by="u1",
        prazo_urgente=False,
        dados_extraidos={},
        relatorio={},
        revisao_humana={},
        alertas_conflito=[],
        custo_ia={},
    )
    analise.documentos = []
    return analise


def _documento(analise: RaioXAnalise, filepath: str) -> RaioXDocumento:
    doc = RaioXDocumento(
        id="d1",
        analise_id=analise.id,
        nome_original="peticao.txt",
        filepath=filepath,
        mimetype="text/plain",
        size_bytes=100,
        sha256="hash-d1",
        ocr_utilizado=False,
        resultado_analise={},
        uploaded_by="u1",
    )
    analise.documentos = [doc]
    return doc


# ── Fakes de banco (padrão do repo: fake local por arquivo) ──────────────────

class _FakeResult:
    def __init__(self, valor):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor

    def scalars(self):
        valor = self._valor if isinstance(self._valor, list) else [self._valor]
        return SimpleNamespace(all=lambda: list(valor))


class _FakeDB:
    """Sessão fake para o ROUTER: toda query devolve a análise."""

    def __init__(self, analise: RaioXAnalise):
        self.analise = analise
        self.added: list = []
        self.commits = 0

    async def execute(self, stmt):
        return _FakeResult(self.analise)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    async def refresh(self, obj):
        pass


class _FakeSessionTask:
    """Sessão fake para a TASK: 1ª query → análise; demais → documentos."""

    def __init__(self, analise: RaioXAnalise, falhar_primeira: bool = False):
        self.analise = analise
        self.falhar_primeira = falhar_primeira
        self.queries = 0
        self.added: list = []
        self.deleted: list = []
        self.status_nos_commits: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def _e_lock_de_analise(self, stmt):
        # Consultas com for_update (admissão/erro/progresso) sempre carregam a
        # análise; apenas consultas sem lock listam os documentos restantes.
        try:
            for_update = getattr(stmt, "_for_update_arg", None)
            return for_update is not None
        except Exception:  # noqa: BLE001
            return False

    async def execute(self, stmt):
        self.queries += 1
        if self._e_lock_de_analise(stmt):
            if self.falhar_primeira:
                raise RuntimeError("banco indisponível (simulado)")
            return _FakeResult(self.analise)
        docs = [d for d in self.analise.documentos if d not in self.deleted]
        return _FakeResult(docs)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.status_nos_commits.append(self.analise.status)


# ── (a)/(b) Endpoint: enfileira sem IA inline ────────────────────────────────

def _app(analise: RaioXAnalise) -> tuple[FastAPI, _FakeDB]:
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.routers.raio_x import router

    app = FastAPI()
    app.include_router(router)
    db = _FakeDB(analise)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _user
    return app, db


def test_upload_responde_com_fila_sem_executar_ia(monkeypatch, tmp_path):
    """(a) O POST persiste o documento pendente, marca `fila`, despacha a task
    e responde imediatamente — a IA jamais roda no caminho do request."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    async def ia_proibida(*args, **kwargs):  # pragma: no cover — guarda
        raise AssertionError("extrair_e_analisar não pode rodar no request")

    from app.services import documento_service
    monkeypatch.setattr(documento_service, "extrair_e_analisar", ia_proibida)

    despacho: dict = {}

    async def fake_agendar(analise_id, user_id, user_role, documento_ids, reprocessar, background_tasks):
        despacho.update(
            analise_id=analise_id, user_id=user_id, user_role=user_role,
            documento_ids=documento_ids, reprocessar=reprocessar,
        )
        return "background"

    monkeypatch.setattr(raio_x_tasks, "agendar_analise", fake_agendar)

    analise = _analise("novo")
    app, db = _app(analise)
    with TestClient(app) as client:
        resp = client.post(
            "/raio-x/a1/documentos/analisar",
            files=[("files", ("peticao.txt", b"Conteudo ficticio de peticao para teste.", "text/plain"))],
        )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["analise"]["status"] == "fila"
    assert corpo["processamento"] == "background"
    assert corpo["erros"] == []
    # Documento persistido PENDENTE (sem resultado de IA).
    docs = [obj for obj in db.added if isinstance(obj, RaioXDocumento)]
    assert len(docs) == 1
    assert docs[0].resultado_analise == {}
    # Task despachada com o lote novo.
    assert despacho["documento_ids"] == [docs[0].id]
    assert despacho["reprocessar"] is False
    # Arquivo gravado em disco para a task processar depois.
    assert (Path(str(tmp_path)) / docs[0].filepath).exists()


def test_upload_com_analise_em_processamento_da_409(monkeypatch, tmp_path):
    """(b) Lote novo com análise já em fila/em_processamento → 409, sem
    despacho duplicado."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)
    analise = _analise("fila")
    # No banco real updated_at nunca é NULL (server_default=now); execução
    # recente e viva → o guard de staleness não pode destravar.
    analise.updated_at = datetime.now(timezone.utc)
    app, _ = _app(analise)
    with TestClient(app) as client:
        resp = client.post(
            "/raio-x/a1/documentos/analisar",
            files=[("files", ("peticao.txt", b"Conteudo ficticio.", "text/plain"))],
        )
    assert resp.status_code == 409


def test_reanalisar_reprocessa_via_fila(monkeypatch, tmp_path):
    """(a) reanalisar?reprocessar=true também sai do caminho do request:
    marca `fila` e despacha a task com reprocessar=True."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    despacho: dict = {}

    async def fake_agendar(analise_id, user_id, user_role, documento_ids, reprocessar, background_tasks):
        despacho.update(documento_ids=documento_ids, reprocessar=reprocessar)
        return "background"

    monkeypatch.setattr(raio_x_tasks, "agendar_analise", fake_agendar)

    analise = _analise("aguardando_conferencia")
    _documento(analise, "raio-x/2026/08/a1/d1.txt")
    app, _ = _app(analise)
    with TestClient(app) as client:
        resp = client.post("/raio-x/a1/reanalisar?reprocessar=true")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["analise"]["status"] == "fila"
    assert corpo["reprocessado"] is True
    assert corpo["processamento"] == "background"
    assert despacho == {"documento_ids": None, "reprocessar": True}


# ── (c)/(d)/(e) Task: transição de estados ───────────────────────────────────

async def test_task_transita_para_aguardando_conferencia(monkeypatch, tmp_path):
    """(c) fila → em_processamento → aguardando_conferencia; resultado_analise
    e custo_ia preenchidos."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    analise = _analise("fila")
    doc = _documento(analise, "d1.txt")
    (tmp_path / "d1.txt").write_bytes(b"Conteudo ficticio.")

    async def fake_extrair(filepath, mimetype, db=None, enriquecer_rag=True, user_id=None):
        return {
            "ok": True,
            "tokens_total": 42,
            "intake_result": {
                "tipo_documento": "petição inicial",
                "resumo_fatos": "Relato fictício.",
            },
        }

    from app.services import documento_service, raio_x_service
    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    async def fake_preview(db, analise, payload=None, user=None):
        return {"alertas_conflito": []}

    monkeypatch.setattr(raio_x_service, "preview_conversao", fake_preview)

    sessao = _FakeSessionTask(analise)
    resultado = await raio_x_tasks.processar_analise(
        "a1", "u1", "advogado", documento_ids=["d1"], reprocessar=False,
        session_factory=lambda: sessao,
    )
    assert resultado == "ok"
    # Estado intermediário observável (commit próprio) e estado final.
    assert sessao.status_nos_commits == ["em_processamento", "aguardando_conferencia"]
    assert doc.resultado_analise["intake_result"]["tipo_documento"] == "petição inicial"
    assert doc.tipo_documento == "petição inicial"
    assert analise.custo_ia["tokens_ultimo_lote"] == 42
    assert analise.custo_ia["arquivos_ultimo_lote"] == 1
    assert "erro_processamento" not in (analise.relatorio or {})


async def test_task_falha_global_marca_erro_com_mensagem(monkeypatch):
    """(d) Falha inesperada nunca propaga: status vira `erro` e a mensagem
    legível fica em relatorio["erro_processamento"] para a UI."""
    analise = _analise("fila")
    sessoes = [_FakeSessionTask(analise, falhar_primeira=True), _FakeSessionTask(analise)]

    def factory():
        return sessoes.pop(0)

    resultado = await raio_x_tasks.processar_analise(
        "a1", "u1", "advogado", session_factory=factory,
    )
    assert resultado == "erro"
    assert analise.status == "erro"
    # Contrato com a UI: erro_processamento é STRING legível (o frontend faz
    # String(relatorio.erro_processamento)).
    erro = analise.relatorio["erro_processamento"]
    assert isinstance(erro, str)
    # Achado da auditoria de segurança: str(exc) de infraestrutura pode
    # carregar SQL/caminho/URL — a UI recebe mensagem sanitizada (nome da
    # exceção + referência), e o detalhe fica só no log do servidor.
    assert "banco indisponível (simulado)" not in erro
    assert "RuntimeError" in erro
    assert "a1" in erro  # referência de correlação com o log
    assert analise.relatorio["erro_processamento_em"]


async def test_task_falha_por_documento_remove_doc_e_registra_erro(monkeypatch, tmp_path):
    """(e) Lote novo com extração falhando: o documento não permanece na
    análise (semântica do fluxo inline anterior), o erro fica visível em
    relatorio["erros_processamento"] e o status cai para documentos_pendentes."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    analise = _analise("fila")
    doc = _documento(analise, "d1.txt")
    (tmp_path / "d1.txt").write_bytes(b"Conteudo ficticio.")

    async def fake_extrair(filepath, mimetype, db=None, enriquecer_rag=True, user_id=None):
        return {"ok": False, "erro": "OCR vazio (simulado)"}

    from app.services import documento_service, raio_x_service
    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    async def fake_preview(db, analise, payload=None, user=None):
        return {"alertas_conflito": []}

    monkeypatch.setattr(raio_x_service, "preview_conversao", fake_preview)

    sessao = _FakeSessionTask(analise)
    resultado = await raio_x_tasks.processar_analise(
        "a1", "u1", "advogado", documento_ids=["d1"], reprocessar=False,
        session_factory=lambda: sessao,
    )
    assert resultado == "ok"
    assert doc in sessao.deleted
    assert analise.status == "documentos_pendentes"
    erros = analise.relatorio["erros_processamento"]
    assert erros[0]["arquivo"] == "peticao.txt"
    assert "OCR vazio (simulado)" in erros[0]["erro"]
    # Arquivo físico do documento que falhou não fica órfão.
    assert not (tmp_path / "d1.txt").exists()


# ── (f) Despacho: Celery quando dá, BackgroundTasks quando não ───────────────

async def test_agendar_sem_celery_usa_background_tasks(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "CELERY_ENABLED", False, raising=False)
    bg = BackgroundTasks()
    mecanismo = await raio_x_tasks.agendar_analise("a1", "u1", "advogado", ["d1"], False, bg)
    assert mecanismo == "background"
    assert len(bg.tasks) == 1
    assert bg.tasks[0].func is raio_x_tasks.processar_analise


async def test_agendar_com_celery_e_redis_usa_delay(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "CELERY_ENABLED", True, raising=False)

    from app.tasks import dispatcher

    async def redis_ok(url, timeout=1.0):
        return True

    monkeypatch.setattr(dispatcher, "_redis_alcancavel", redis_ok)

    chamado: dict = {}
    monkeypatch.setattr(
        raio_x_tasks.processar_analise_task, "delay",
        lambda *args: chamado.setdefault("args", args),
    )
    bg = BackgroundTasks()
    mecanismo = await raio_x_tasks.agendar_analise("a1", "u1", "advogado", ["d1"], True, bg)
    assert mecanismo == "celery"
    assert chamado["args"] == ("a1", "u1", "advogado", ["d1"], True)
    assert bg.tasks == []


async def test_agendar_com_redis_fora_cai_para_background(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "CELERY_ENABLED", True, raising=False)

    from app.tasks import dispatcher

    async def redis_fora(url, timeout=1.0):
        return False

    monkeypatch.setattr(dispatcher, "_redis_alcancavel", redis_fora)
    bg = BackgroundTasks()
    mecanismo = await raio_x_tasks.agendar_analise("a1", "u1", "advogado", None, True, bg)
    assert mecanismo == "background"
    assert len(bg.tasks) == 1


# ── (g) Vocabulário canônico ─────────────────────────────────────────────────

def test_fila_e_erro_pertencem_ao_vocabulario_canonico():
    assert "fila" in STATUS_RAIO_X
    assert "erro" in STATUS_RAIO_X


def test_patch_aceita_status_do_ciclo_assincrono():
    assert RaioXUpdate(status="fila").status == "fila"
    assert RaioXUpdate(status="erro").status == "erro"


# ── (h) Recuperação de análise presa (worker morto sem marcar erro) ──────────

def test_processamento_preso_respeita_teto_e_status():
    from app.routers.raio_x import PROCESSAMENTO_TIMEOUT_MINUTOS, _processamento_preso

    agora = datetime.now(timezone.utc)

    viva = _analise("em_processamento")
    viva.updated_at = agora
    assert _processamento_preso(viva) is False

    presa = _analise("fila")
    presa.updated_at = agora - timedelta(minutes=PROCESSAMENTO_TIMEOUT_MINUTOS + 1)
    assert _processamento_preso(presa) is True

    # Fora do ciclo assíncrono o teto não se aplica, por mais antiga que seja.
    concluida = _analise("aguardando_conferencia")
    concluida.updated_at = agora - timedelta(days=30)
    assert _processamento_preso(concluida) is False

    # Datetime naive (SQLite/testes) é interpretado como UTC, não explode.
    naive = _analise("em_processamento")
    naive.updated_at = (agora - timedelta(hours=2)).replace(tzinfo=None)
    assert _processamento_preso(naive) is True


def test_upload_com_analise_presa_destrava_e_aceita_o_novo_lote(monkeypatch, tmp_path):
    """(h) Worker morreu no meio (fila/em_processamento além do teto): o novo
    lote NÃO leva 409 — a execução morta vira desfecho `erro` registrado e o
    lote entra na fila normalmente."""
    from app.routers.raio_x import PROCESSAMENTO_TIMEOUT_MINUTOS

    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    despacho: dict = {}

    async def fake_agendar(analise_id, user_id, user_role, documento_ids, reprocessar, background_tasks):
        despacho.update(documento_ids=documento_ids, reprocessar=reprocessar)
        return "background"

    monkeypatch.setattr(raio_x_tasks, "agendar_analise", fake_agendar)

    analise = _analise("em_processamento")
    analise.updated_at = datetime.now(timezone.utc) - timedelta(
        minutes=PROCESSAMENTO_TIMEOUT_MINUTOS + 5
    )
    app, _ = _app(analise)
    with TestClient(app) as client:
        resp = client.post(
            "/raio-x/a1/documentos/analisar",
            files=[("files", ("peticao.txt", b"Conteudo ficticio.", "text/plain"))],
        )
    assert resp.status_code == 200
    assert resp.json()["analise"]["status"] == "fila"
    assert despacho["reprocessar"] is False
    # O desfecho da execução morta ficou registrado antes do novo ciclo.
    assert "expirou" in analise.relatorio["erro_processamento"]
    assert analise.relatorio["erro_processamento_em"]
