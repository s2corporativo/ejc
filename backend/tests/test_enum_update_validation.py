"""
Regressão de robustez: campos `str`/`Optional[str]` de schemas de create/update
que gravam em colunas SAEnum do Postgres.

Antes destes field_validators, um valor fora do enum passava o Pydantic e só
estourava no INSERT/UPDATE do asyncpg (InvalidTextRepresentationError → HTTP 500
não tratado). Agora a validação acontece na ENTRADA → pydantic.ValidationError,
que o FastAPI serializa como 422. Estes testes fixam esse contrato ao nível do
schema (onde o 422 nasce): inválido levanta ValidationError; válido passa; e
None/"" continuam válidos nos updates parciais.
"""
import pytest
from pydantic import ValidationError

from app.schemas.deadline import DeadlineCreate, DeadlineUpdate
from app.schemas.environmental import EnvCaseCreate, EnvCaseUpdate
from app.schemas.fee import FeeUpdate
from app.schemas.legal_doc import LegalDocCreate, LegalDocUpdate


# ── Deadline ──────────────────────────────────────────────────────────────────
def test_deadline_update_status_invalido_levanta_422():
    with pytest.raises(ValidationError):
        DeadlineUpdate(status="xpto_invalido")


def test_deadline_update_status_valido_ok():
    m = DeadlineUpdate(status="concluido")
    assert m.status == "concluido"


def test_deadline_update_status_none_e_vazio_passam():
    # update parcial: campo ausente/None/"" não deve disparar validação de enum
    assert DeadlineUpdate().status is None
    assert DeadlineUpdate(status=None).status is None
    assert DeadlineUpdate(status="").status == ""


def test_deadline_create_tipo_e_prioridade_invalidos():
    with pytest.raises(ValidationError):
        DeadlineCreate(titulo="Prazo X", tipo="nao_existe")
    with pytest.raises(ValidationError):
        DeadlineCreate(titulo="Prazo X", prioridade="urgentissima")


def test_deadline_create_defaults_validos_ok():
    m = DeadlineCreate(titulo="Contestação")
    assert m.tipo == "processual"
    assert m.prioridade == "media"


# ── Environmental ─────────────────────────────────────────────────────────────
def test_env_create_orgao_autuador_invalido():
    with pytest.raises(ValidationError):
        EnvCaseCreate(case_id="c1", orgao_autuador="PREFEITURA_X", numero_auto="123")


def test_env_create_orgao_autuador_valido_ok():
    m = EnvCaseCreate(case_id="c1", orgao_autuador="IBAMA", numero_auto="123")
    assert m.orgao_autuador == "IBAMA"


def test_env_update_status_defesa_invalido_e_valido():
    with pytest.raises(ValidationError):
        EnvCaseUpdate(status_defesa="inventado")
    assert EnvCaseUpdate(status_defesa="protocolada").status_defesa == "protocolada"
    assert EnvCaseUpdate().status_defesa is None


# ── Fee ───────────────────────────────────────────────────────────────────────
def test_fee_update_status_invalido():
    with pytest.raises(ValidationError):
        FeeUpdate(status="quitadissimo")


def test_fee_update_status_valido_e_none():
    assert FeeUpdate(status="pago").status == "pago"
    assert FeeUpdate().status is None
    assert FeeUpdate(status="").status == ""


# ── LegalDoc (peça) ───────────────────────────────────────────────────────────
def test_legaldoc_create_tipo_peca_invalido():
    with pytest.raises(ValidationError):
        LegalDocCreate(titulo="Peça", tipo_peca="peticao_maluca", conteudo="...")


def test_legaldoc_create_tipo_peca_valido_ok():
    m = LegalDocCreate(titulo="Peça", tipo_peca="contestacao", conteudo="...")
    assert m.tipo_peca == "contestacao"


def test_legaldoc_update_status_invalido_e_valido():
    with pytest.raises(ValidationError):
        LegalDocUpdate(status="quase_pronta")
    assert LegalDocUpdate(status="aprovada").status == "aprovada"
    assert LegalDocUpdate().status is None


# ── Prompt (router prompts-biblioteca) ────────────────────────────────────────
def test_prompt_create_categoria_invalida_e_valida():
    from app.routers.prompts import PromptCreate

    with pytest.raises(ValidationError):
        PromptCreate(titulo="T", categoria="categoria_inexistente", conteudo="c")
    m = PromptCreate(titulo="T", categoria="peticao", conteudo="c")
    assert m.categoria == "peticao"
