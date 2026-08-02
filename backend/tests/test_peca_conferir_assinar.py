"""Bloco 2 — desobstruir o caminho da peça até o protocolo.

Três mudanças, três riscos distintos a travar:

1. `POST /{id}/conferir-e-assinar` consolida validar → marcar HITL → aprovar em
   um ato. O risco é a consolidação virar afrouxamento: sumir com os gates de
   qualidade, com a exigência de observações, ou com o registro de quem assinou.
   A Lei 8.906/94, art. 32 responsabiliza o advogado pela peça — consolidar
   ETAPAS é o objetivo; apagar o RASTRO não é.

2. `GET /{id}/pdf-minuta` libera a leitura antes da assinatura. O risco é o
   inverso: virar uma porta lateral para tirar PDF de protocolo sem passar pelos
   gates. Ele tem de sair sempre marcado como minuta.

3. O rótulo de `rascunho` mudou. O risco é alguém "arrumar" o VALOR do enum
   junto — o que quebraria o banco, já que a coluna é ENUM nativo.

Segue o padrão de `test_legal_doc_flow_contract.py`: inspeção de fonte para
invariantes estruturais, que é o que o repositório usa para este router.

Review do PR #622 (Codex) — regressões comportamentais adicionadas, no padrão
TestClient + fakes de `test_legal_doc_protocolo.py`:

  - 403 quando quem assina não é o autor do AILog nem sócio+ (mesma regra do
    PATCH /ai/logs/{id}/hitl);
  - 409/503 propagados do gate antialucinação (aplicar_gate_hitl) — o atalho
    não pode promover o log a 'revisado' por fora do gate;
  - 409 para peça 'final'/'protocolada' (imutável — reassinar rebaixaria o
    status e sobrescreveria revisor/data/notas);
  - 422/503 traduzindo ValueError/RuntimeError de validar_rascunho_juridico
    (mesma tradução do router dedicado validador_juridico.py);
  - a validação roda com commit=False (flush) — nada persiste se um gate
    posterior abortar a transação.
"""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.routers import legal_docs as legal_docs_router
from app.services import citation_gate as citation_gate_service


def _source(path: str) -> str:
    return (Path(__file__).parents[1] / path).read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    tail = source[start:]
    marker = tail.find("\n\n@router.")
    return tail if marker < 0 else tail[:marker]


# ── 1. Conferir e assinar ────────────────────────────────────────────────────


def test_conferir_e_assinar_existe_e_e_um_post():
    src = _source("app/routers/legal_docs.py")
    assert '@router.post("/{doc_id}/conferir-e-assinar")' in src


def test_conferir_e_assinar_mantem_os_dois_gates_de_qualidade():
    """Os MESMOS gates do /aprovar. Consolidar não pode baixar a régua."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "_bloquear_sem_validacao" in bloco
    assert "_bloquear_jurisprudencia_nao_validada" in bloco


def test_conferir_e_assinar_exige_observacoes_para_peca_de_ia():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "d.ai_generated and not observacoes" in bloco
    assert "status_code=422" in bloco


def test_conferir_e_assinar_registra_quem_quando_e_sobre_qual_versao():
    """O rastro do ato profissional — Lei 8.906/94, art. 32."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "d.revisor_id = cu.id" in bloco
    assert "d.revisado_em = datetime.now(timezone.utc)" in bloco
    assert "d.notas_revisao = observacoes" in bloco
    assert 'criar_audit_log' in bloco
    assert '"APROVAR_HITL"' in bloco


def test_conferir_e_assinar_usa_lock_pessimista():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert ".with_for_update()" in bloco


def test_conferir_e_assinar_grava_tudo_em_uma_transacao():
    """Um único commit, no fim.

    Gravação em dois lugares sem transação é a classe de defeito que a auditoria
    encontrou repetida cinco vezes neste código. Se aparecer um commit no meio,
    uma reprovação de gate deixaria a peça meio-assinada.
    """
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert bloco.count("await db.commit()") == 1
    corpo_antes_dos_gates = bloco[: bloco.index("_bloquear_sem_validacao")]
    assert "await db.commit()" not in corpo_antes_dos_gates, (
        "commit antes dos gates deixaria validação e HITL gravados numa peça reprovada"
    )


def test_conferir_e_assinar_reaproveita_validacao_da_versao_corrente():
    """Texto idêntico não é revalidado — o hash da migration 123 decide."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "_ultima_validacao_peca" in bloco
    assert 'validacao.get("ai_log_id") is None' in bloco


# ── 2. PDF de minuta ─────────────────────────────────────────────────────────


def test_pdf_minuta_existe():
    assert '@router.get("/{doc_id}/pdf-minuta")' in _source("app/routers/legal_docs.py")


def test_pdf_minuta_nao_e_porta_lateral_para_o_pdf_de_protocolo():
    """Sai sempre marcado como minuta, nunca como pronto para protocolo."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "pronto_protocolo=False" in bloco
    assert "pronto_protocolo=True" not in bloco
    assert "_gates_exportacao_protocolo" not in bloco, (
        "o PDF de leitura não passa pelos gates de protocolo — e por isso NÃO "
        "pode sair com a marca de protocolo"
    )


def test_pdf_minuta_preserva_o_controle_de_acesso_ao_caso():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "verificar_acesso_caso" in bloco


def test_pdf_minuta_carrega_a_marca_de_ia_no_arquivo_baixado():
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf_minuta")
    assert "minuta_ia=bool(d.ai_generated and not d.human_reviewed)" in bloco


def test_pdf_de_protocolo_continua_atras_dos_gates():
    """Regressão: a liberação da minuta não pode ter afrouxado o PDF final."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "exportar_pdf")
    assert "_gates_exportacao_protocolo" in bloco
    assert "pronto_protocolo=True" in bloco


# ── 3. Rótulo ────────────────────────────────────────────────────────────────


def test_rotulo_de_rascunho_nomeia_a_acao_pendente():
    from app.services.peca_numeracao import status_label

    assert status_label("rascunho") == "Minuta final — conferir e assinar"


def test_valor_do_enum_permanece_rascunho():
    """A coluna é ENUM nativo no Postgres: renomear o VALOR quebraria o banco."""
    from app.models.legal_doc import PecaStatus

    assert PecaStatus.rascunho.value == "rascunho"
    assert [s.value for s in PecaStatus] == [
        "rascunho", "em_revisao", "corrigida", "aprovada", "final", "protocolada",
    ]


def test_frontend_mantem_a_chave_do_enum_no_filtro_da_fila():
    """O rótulo mudou no frontend; a chave enviada ao backend, não."""
    fonte = (
        Path(__file__).parents[2] / "frontend" / "src" / "pages" / "Pecas.tsx"
    ).read_text(encoding="utf-8")
    assert 'key: "rascunho"' in fonte
    assert 'label: "Minuta final"' in fonte


# ── 4. Review PR #622 — invariantes estruturais das correções ────────────────


def test_conferir_e_assinar_valida_sem_commit_intermediario():
    """A validação roda com commit=False: o AILog entra por flush na MESMA
    transação e nada persiste se um gate posterior abortar (review item 4)."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert "commit=False" in bloco


def test_servico_de_validacao_preserva_commit_default():
    """`commit: bool = True` — os chamadores existentes seguem commitando."""
    src = _source("app/services/validador_juridico_service.py")
    assert "commit: bool = True" in src
    assert "if commit:" in src
    assert "await db.flush()" in src


def test_conferir_e_assinar_aplica_o_gate_de_citacoes_antes_do_hitl():
    """Jamais promover o AILog a 'revisado' por fora do aplicar_gate_hitl
    (regra inegociável — review item 2)."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    idx_gate = bloco.index("aplicar_gate_hitl(")
    idx_status = bloco.index("log.status_hitl = AIStatusHITL.revisado")
    assert idx_gate < idx_status, "o gate deve rodar ANTES da mudança de status HITL"


def test_conferir_e_assinar_replica_autorizacao_do_hitl():
    """Mesma regra do PATCH /ai/logs/{id}/hitl: autor do log OU sócio+
    (review item 1)."""
    bloco = _function_source(_source("app/routers/legal_docs.py"), "conferir_e_assinar")
    assert 'log.user_id != cu.id and ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]' in bloco


# ── 5. Review PR #622 — regressões comportamentais (TestClient + fakes) ──────


class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.flushed = 0
        self.refreshed = []

    async def execute(self, stmt, *a, **k):
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        self.flushed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


def _peca(**over):
    base = dict(
        id="peca-1", titulo="Contestação", tipo_peca=PecaTipo.contestacao,
        status=PecaStatus.rascunho, conteudo="corpo da peça", versao=1,
        ai_generated=True, human_reviewed=False, case_id=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return LegalDoc(**base)


def _log_validacao(**over):
    """AILog fake da validação corrente — score alto, veredito não bloqueante,
    pendente de HITL ('gerado')."""
    base = dict(
        id="log-1", user_id="u1", status_hitl="gerado",
        prompt_sanitizado=(
            "LEGAL_DOC_ID:peca-1\nCONTENT_HASH:x\n"
            "VALIDATION_SCORE:90\nVALIDATION_VERDICT:APROVAR\n"
        ),
        resposta="analise da peça", fontes_rag=None,
        created_at=datetime.now(timezone.utc),
        revisado_por=None, revisado_em=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _montar(db: _FakeDB, role: str = "advogado"):
    app = FastAPI()
    app.include_router(legal_docs_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=SimpleNamespace(value=role)
    )
    return TestClient(app)


def _post_conferir(db: _FakeDB, role: str = "advogado"):
    client = _montar(db, role=role)
    return client.post(
        "/legal-docs/peca-1/conferir-e-assinar",
        json={"observacoes": "Conferi fatos, fundamentos e pedidos."},
    )


def test_conferir_e_assinar_403_para_quem_nao_e_autor_do_log_nem_socio():
    """Review item 1: log de OUTRO usuário + papel abaixo de sócio → 403,
    sem promover o HITL e sem commit."""
    log = _log_validacao(user_id="outro-usuario")
    db = _FakeDB(results=[
        _Res(one=_peca()),      # SELECT LegalDoc FOR UPDATE
        _Res(one=log),          # _ultima_validacao_peca (validação corrente)
        _Res(one=log),          # SELECT AILog FOR UPDATE
    ])
    r = _post_conferir(db, role="advogado")
    assert r.status_code == 403, r.text
    assert "permissão" in r.json()["detail"]
    assert log.status_hitl == "gerado" and db.committed == 0


def test_conferir_e_assinar_socio_pode_revisar_log_de_terceiro():
    """Contraprova da autorização: sócio+ passa do 403 (a requisição segue e
    esbarra apenas nos gates seguintes, nunca na posse do log)."""
    log = _log_validacao(user_id="outro-usuario")
    db = _FakeDB(results=[
        _Res(one=_peca()),
        _Res(one=log),
        _Res(one=log),
        _Res(one=log),          # _ultima_validacao_peca após flush
    ])

    async def _gate_ok(*a, **k):
        return None

    async def _liberado(*a, **k):
        return None

    orig_gate = citation_gate_service.aplicar_gate_hitl
    orig_val = legal_docs_router._bloquear_sem_validacao
    orig_juris = legal_docs_router._bloquear_jurisprudencia_nao_validada
    orig_rag = legal_docs_router.indexar_peca_rag
    citation_gate_service.aplicar_gate_hitl = _gate_ok
    legal_docs_router._bloquear_sem_validacao = _liberado
    legal_docs_router._bloquear_jurisprudencia_nao_validada = _liberado
    legal_docs_router.indexar_peca_rag = _liberado
    try:
        r = _post_conferir(db, role="socio")
    finally:
        citation_gate_service.aplicar_gate_hitl = orig_gate
        legal_docs_router._bloquear_sem_validacao = orig_val
        legal_docs_router._bloquear_jurisprudencia_nao_validada = orig_juris
        legal_docs_router.indexar_peca_rag = orig_rag
    assert r.status_code != 403, r.text
    assert r.status_code == 200, r.text
    # O ato promoveu o HITL e registrou quem revisou — em UM commit.
    assert log.status_hitl.value == "revisado"
    assert log.revisado_por == "u1" and log.revisado_em is not None
    assert db.committed == 1


def test_conferir_e_assinar_propaga_409_do_gate_de_citacoes():
    """Review item 2: citações bloqueantes → 409 do aplicar_gate_hitl; o log
    NÃO vira 'revisado' e nada é commitado."""
    log = _log_validacao()
    db = _FakeDB(results=[
        _Res(one=_peca()),
        _Res(one=log),
        _Res(one=log),
    ])

    async def _gate_bloqueia(*a, **k):
        raise HTTPException(status_code=409, detail={
            "erro": "citacoes_nao_verificadas",
            "mensagem": "Output de IA contém citações bloqueantes",
        })

    orig = citation_gate_service.aplicar_gate_hitl
    citation_gate_service.aplicar_gate_hitl = _gate_bloqueia
    try:
        r = _post_conferir(db)
    finally:
        citation_gate_service.aplicar_gate_hitl = orig
    assert r.status_code == 409, r.text
    assert log.status_hitl == "gerado" and db.committed == 0


def test_conferir_e_assinar_propaga_503_do_gate_indisponivel():
    """Review item 2: verificação obrigatória indisponível (política
    'bloquear') → 503 fail-closed, sem promover o HITL."""
    log = _log_validacao()
    db = _FakeDB(results=[
        _Res(one=_peca()),
        _Res(one=log),
        _Res(one=log),
    ])

    async def _gate_indisponivel(*a, **k):
        raise HTTPException(
            status_code=503,
            detail="Verificação de citações indisponível — tente novamente.",
        )

    orig = citation_gate_service.aplicar_gate_hitl
    citation_gate_service.aplicar_gate_hitl = _gate_indisponivel
    try:
        r = _post_conferir(db)
    finally:
        citation_gate_service.aplicar_gate_hitl = orig
    assert r.status_code == 503, r.text
    assert log.status_hitl == "gerado" and db.committed == 0


def test_conferir_e_assinar_409_para_peca_final_ou_protocolada():
    """Review item 3: peça 'final'/'protocolada' é imutável — reassinar
    rebaixaria o status e sobrescreveria revisor/data/notas."""
    for status in (PecaStatus.final, PecaStatus.protocolada):
        peca = _peca(status=status, human_reviewed=True)
        db = _FakeDB(results=[_Res(one=peca)])
        r = _post_conferir(db)
        assert r.status_code == 409, (status, r.text)
        assert "imutável" in r.json()["detail"]
        assert peca.status == status and db.committed == 0


def test_conferir_e_assinar_traduz_valueerror_da_validacao_em_422():
    """Review item 5: ValueError (peça curta / PII residual) → 422, como no
    router dedicado validador_juridico.py."""
    db = _FakeDB(results=[
        _Res(one=_peca()),
        _Res(one=None),         # sem validação corrente → chama o serviço
    ])

    async def _valida_falha(*a, **k):
        raise ValueError("Rascunho muito curto para validacao juridica")

    orig = legal_docs_router.validar_rascunho_juridico
    legal_docs_router.validar_rascunho_juridico = _valida_falha
    try:
        r = _post_conferir(db)
    finally:
        legal_docs_router.validar_rascunho_juridico = orig
    assert r.status_code == 422, r.text
    assert "curto" in r.json()["detail"]
    assert db.committed == 0


def test_conferir_e_assinar_traduz_runtimeerror_da_validacao_em_503():
    """Review item 5: RuntimeError (provedor de IA indisponível) → 503."""
    db = _FakeDB(results=[
        _Res(one=_peca()),
        _Res(one=None),
    ])

    async def _valida_indisponivel(*a, **k):
        raise RuntimeError("Nenhum provedor de IA disponível")

    orig = legal_docs_router.validar_rascunho_juridico
    legal_docs_router.validar_rascunho_juridico = _valida_indisponivel
    try:
        r = _post_conferir(db)
    finally:
        legal_docs_router.validar_rascunho_juridico = orig
    assert r.status_code == 503, r.text
    assert db.committed == 0
