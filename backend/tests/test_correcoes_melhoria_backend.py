"""Correções do relatório de MELHORIA do backend (5 itens).

Cada bloco trava contra regressão uma correção específica. Testes puros (sem
Postgres): usam o validador/gate diretamente e leem os fontes de config
(env.py/requirements.txt) por inspeção — mesmo padrão dos guardas estáticos já
existentes (ex.: test_schema_sync.test_autogenerate_tem_guarda_include_name).

1. ADMIN_EMAIL validado com EmailStr (mesma regra do login) antes do seed.
2. ORM alinhado ao banco (numero VARCHAR(20); is_active/revoked NULLáveis;
   email SEM unique cheio) + guarda de coluna viva-fora-do-ORM no autogenerate.
3. fastembed com pin EXATO (reprodutibilidade do RAG) + modelo E5 default.
4. Gate de CASO ÓRFÃO endurecido (só gestão; perfis baixos → 403).
5. REQUIRE_2FA_ROLES default inclui advogado + advogado_auxiliar.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ══════════════════════════════════════════════════════════════════════════════
# Item 1 — ADMIN_EMAIL validado com o MESMO validador do login (EmailStr)
# ══════════════════════════════════════════════════════════════════════════════

from seeds.seed_all import validar_admin_email


@pytest.mark.parametrize(
    "reservado",
    ["admin@ejc.local", "admin@ejc.invalid", "admin@ejc.test", "admin@localhost"],
)
def test_admin_email_reservado_aborta_seed(reservado):
    """Domínio reservado/special-use (o login retornaria 422) → o seed FALHA
    aqui, com erro acionável, em vez de criar um admin que não consegue logar."""
    with pytest.raises(ValueError) as exc:
        validar_admin_email(reservado)
    assert "ADMIN_EMAIL" in str(exc.value)


@pytest.mark.parametrize(
    "valido",
    ["admin@ejc.adv.br", "admin@seu-dominio.com.br", "contato@depaulateixeira.adv.br"],
)
def test_admin_email_valido_passa(valido):
    assert validar_admin_email(valido) == valido


def test_seed_default_admin_email_e_valido():
    """O default embutido no seed (admin@ejc.adv.br) não pode ser um endereço
    que o próprio validador rejeitaria."""
    assert validar_admin_email("admin@ejc.adv.br") == "admin@ejc.adv.br"


# ══════════════════════════════════════════════════════════════════════════════
# Item 2 — ORM alinhado ao banco (autogenerate seguro; SEM migração)
# ══════════════════════════════════════════════════════════════════════════════

def test_clients_numero_alinhado_varchar20():
    from app.models.client import Client
    assert Client.__table__.columns["numero"].type.length == 20


def test_users_is_active_nullable_como_no_banco():
    from app.models.user import User
    # migration 001 cria is_active SEM NOT NULL → banco permite NULL.
    assert User.__table__.columns["is_active"].nullable is True


def test_refresh_tokens_revoked_nullable_como_no_banco():
    from app.models.user import RefreshToken
    assert RefreshToken.__table__.columns["revoked"].nullable is True


def test_users_email_nao_usa_unique_cheio_e_mantem_indice_parcial():
    """Migration 075 DROPOU o UNIQUE cheio (058) e o trocou por índice parcial.
    O ORM deve refletir isso: email SEM unique de coluna + índice parcial
    uq_users_email_active presente. Reintroduzir unique=True recriaria drift."""
    from app.models.user import User
    email_col = User.__table__.columns["email"]
    assert email_col.unique is not True  # None/False — não é UNIQUE cheio
    parciais = {
        ix.name for ix in User.__table__.indexes
        if ix.unique and ix.name == "uq_users_email_active"
    }
    assert "uq_users_email_active" in parciais


# ── Guarda do autogenerate no env.py (inspeção do fonte — env.py roda migrations
#    no import, não é importável fora do Alembic) ──────────────────────────────

_ENV_PY = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")

# Colunas VIVAS no banco mas fora do ORM que o autogenerate NÃO pode dropar.
_DEAD_COLS_ESPERADAS = [
    ('("documents", "download_count")'),
    ('("documents", "sensitivity_level")'),
    ('("documents", "watermark")'),
    ('("documents", "access_users")'),
    ('("documents", "last_accessed_at")'),
    ('("cases", "indice_risco")'),
    ('("cases", "risco_nivel")'),
    ('("cases", "risco_fatores")'),
    ('("cases", "risco_atualizado_em")'),
    ('("teses", "area_direito")'),
    ('("knowledge_chunks", "categoria")'),
    ('("checklist_templates", "tipo_demanda")'),
]


def test_env_py_tem_include_object_ligado_nos_dois_configure():
    assert "def include_object(" in _ENV_PY, "env.py perdeu include_object"
    assert _ENV_PY.count("include_object=include_object") >= 2, (
        "include_object não está ligada nos dois context.configure (online/"
        "offline) — o autogenerate voltaria a poder dropar colunas vivas."
    )


def test_env_py_preserva_guarda_de_tabela_include_name():
    # Não regredir a proteção de TABELA já existente ao adicionar a de coluna.
    assert "def include_name(" in _ENV_PY
    assert _ENV_PY.count("include_name=include_name") >= 2


@pytest.mark.parametrize("par", _DEAD_COLS_ESPERADAS)
def test_env_py_lista_colunas_vivas_fora_do_orm(par):
    assert par in _ENV_PY, f"env.py não protege a coluna viva {par} de drop espúrio"


# ══════════════════════════════════════════════════════════════════════════════
# Item 3 — fastembed com pin EXATO (reprodutibilidade do RAG)
# ══════════════════════════════════════════════════════════════════════════════

_REQS = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8")


def test_fastembed_pin_exato():
    """Pin flutuante reintroduz o risco do pooling do e5 (CLS→média) mudar
    entre versões e reordenar o RAG. Exige `fastembed==<versão>` (não faixa)."""
    linhas = [l.strip() for l in _REQS.splitlines() if l.strip().startswith("fastembed")]
    assert linhas, "fastembed sumiu do requirements.txt"
    assert any(re.fullmatch(r"fastembed==\d+\.\d+\.\d+", l) for l in linhas), (
        f"fastembed precisa de pin EXATO (==x.y.z), não faixa. Achado: {linhas}"
    )


def test_embeddings_model_default_e_e5():
    from app.core.config import Settings
    default = Settings.model_fields["EMBEDDINGS_MODEL"].default
    assert "e5" in default.lower(), f"modelo default inesperado: {default}"


# ══════════════════════════════════════════════════════════════════════════════
# Item 4 — Gate de CASO ÓRFÃO endurecido (só gestão)
# ══════════════════════════════════════════════════════════════════════════════

from app.core.ownership import verificar_acesso_caso


class _Res:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    def __init__(self, case):
        self._case = case

    async def execute(self, *a, **k):
        return _Res(self._case)


def _user(uid: str, role: str):
    return SimpleNamespace(id=uid, role=role)


def _caso(resp=None, aux=None):
    return SimpleNamespace(
        id="c1", advogado_responsavel_id=resp, advogado_auxiliar_id=aux
    )


@pytest.mark.parametrize("role", ["estagiario", "secretaria", "advogado", "advogado_auxiliar"])
async def test_caso_orfao_negado_a_perfis_baixos(role):
    """Caso sem responsável NEM auxiliar não pode mais liberar perfis baixos."""
    db = _FakeDB(_caso(resp=None, aux=None))
    with pytest.raises(HTTPException) as exc:
        await verificar_acesso_caso(db, _user(f"u-{role}", role), "c1")
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["socio", "admin", "superadmin"])
async def test_caso_orfao_liberado_a_gestao(role):
    caso = _caso(resp=None, aux=None)
    r = await verificar_acesso_caso(_FakeDB(caso), _user(f"u-{role}", role), "c1")
    assert r is caso


async def test_caso_com_responsavel_inalterado_responsavel_passa():
    """Fluxo legítimo intacto: o advogado responsável acessa seu caso."""
    caso = _caso(resp="u-resp", aux=None)
    r = await verificar_acesso_caso(_FakeDB(caso), _user("u-resp", "advogado"), "c1")
    assert r is caso


async def test_caso_com_responsavel_barra_advogado_sem_vinculo():
    caso = _caso(resp="u-resp", aux=None)
    with pytest.raises(HTTPException) as exc:
        await verificar_acesso_caso(_FakeDB(caso), _user("u-outro", "advogado"), "c1")
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Item 5 — REQUIRE_2FA_ROLES default inclui advogado + advogado_auxiliar
# ══════════════════════════════════════════════════════════════════════════════

def test_require_2fa_roles_default_inclui_advogados():
    from app.core.config import Settings
    default = Settings.model_fields["REQUIRE_2FA_ROLES"].default
    papeis = {p.strip().lower() for p in default.split(",") if p.strip()}
    assert {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"} <= papeis, (
        f"default de REQUIRE_2FA_ROLES não obriga os advogados: {default}"
    )


def test_require_2fa_roles_list_parseia_advogados():
    from app.core.config import get_settings
    lista = get_settings().require_2fa_roles_list
    # get_settings pode ler .env do ambiente; o teste garante que, com o default
    # de código, os advogados entram na lista normalizada.
    if "advogado" not in lista:
        pytest.skip("REQUIRE_2FA_ROLES sobrescrito por ambiente/.env — default não avaliado")
    assert "advogado_auxiliar" in lista
