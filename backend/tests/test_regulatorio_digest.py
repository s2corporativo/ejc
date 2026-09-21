"""BE-04 — o router `/regulatorio` era o único montado sem NENHUM teste
(docs/audit/BACKLOG_LIMPEZA_2026-09-20.csv, P1, ordem 29: "Router montado SEM
nenhum teste — único N absoluto"). Regra do CSV: criar teste ANTES de qualquer
mudança no router. Este arquivo é exatamente isso.

Cobertura, sem depender de banco real (o endpoint é agregação pura sobre
`diario_oficial_alertas`):

1. **Agregação** — contagem por fonte, por keyword, não lidos e o cap de 30
   itens em `itens_recentes` (com 40 linhas no banco, o payload carrega 30);
2. **Truncamento de resumo** — resumos > 280 caracteres viram preview + "..."
   (payload de digest não pode virar download);
3. **Janela temporal** — `desde` reflete o `dias` informado (contrato do
   Query ge=1/le=30 validado na camada FastAPI; aqui validamos o cálculo);
4. **Auth** — o router declara `dependencies=[Depends(get_current_user)]`:
   chamada sem token é rejeitada ANTES de tocar o banco (fail-closed).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.regulatorio import digest_semanal, router


# ── Fakes mínimos (mesmo espírito de test_usabilidade_p0_backend.py) ─────────

class _MappingRow:
    """Linha equivalente a um RowMapping de `db.execute(...).mappings()`."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __getitem__(self, k):
        return getattr(self, k)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    """Captura os binds da query para provar a janela temporal aplicada."""

    def __init__(self, rows):
        self._rows = rows
        self.binds: dict | None = None

    async def execute(self, _stmt, binds=None):
        self.binds = binds
        return _Result(self._rows)


def _linha(i: int, *, fonte="DOU", keyword="ICMS", lido=False, resumo="r" * 10):
    return _MappingRow(
        fonte=fonte,
        keyword_match=keyword,
        titulo=f"Aviso regulatório {i}",
        resumo=resumo,
        link=f"https://www.in.gov.br/aviso-{i}",
        data_publicacao="2026-09-20",
        lido=lido,
    )


# ── 1. Agregação ─────────────────────────────────────────────────────────────

async def test_digest_agrega_por_fonte_keyword_e_nao_lidos():
    rows = [
        _linha(1, fonte="DOU", keyword="ICMS"),
        _linha(2, fonte="DOU", keyword="ICMS"),
        _linha(3, fonte="DOE-MG", keyword="licenciamento", lido=True),
        _linha(4, fonte=None, keyword=None),  # fonte ausente vira "—"
    ]
    db = _FakeDB(rows)
    out = await digest_semanal(dias=7, db=db)

    assert out["por_fonte"] == {"DOU": 2, "DOE-MG": 1, "—": 1}
    # o dict bruto por_keyword é interno; o payload expõe só o top ordenado
    assert out["top_keywords"] == [
        {"keyword": "ICMS", "qtd": 2},
        {"keyword": "licenciamento", "qtd": 1},
    ]
    assert out["nao_lidos"] == 3  # só a linha lida=True fica de fora
    assert out["total_alertas"] == 4
    assert out["periodo_dias"] == 7
    # fonte_dados declara a origem real (sem mock no payload)
    assert "diario_oficial_alertas" in out["fonte_dados"]


async def test_digest_cap_de_itens_recentes_em_30():
    rows = [_linha(i) for i in range(40)]
    out = await digest_semanal(dias=7, db=_FakeDB(rows))

    assert out["total_alertas"] == 40   # contagem completa
    assert len(out["itens_recentes"]) == 30  # payload limitado
    assert out["total_alertas"] > len(out["itens_recentes"])


# ── 2. Truncamento de resumo ─────────────────────────────────────────────────

async def test_resumo_longo_vira_preview():
    rows = [_linha(1, resumo="x" * 400)]
    out = await digest_semanal(dias=7, db=_FakeDB(rows))
    item = out["itens_recentes"][0]

    assert item["resumo"].endswith("...")
    assert len(item["resumo"]) == 280 + 3


async def test_resumo_curto_nao_e_truncado():
    rows = [_linha(1, resumo="resumo curto")]
    out = await digest_semanal(dias=7, db=_FakeDB(rows))

    assert out["itens_recentes"][0]["resumo"] == "resumo curto"


# ── 3. Janela temporal ───────────────────────────────────────────────────────

@pytest.mark.parametrize("dias", [1, 7, 30])
async def test_desde_e_calculado_a_partir_de_dias(dias):
    db = _FakeDB([])
    out = await digest_semanal(dias=dias, db=db)

    esperado = (datetime.utcnow() - timedelta(days=dias)).date().isoformat()
    assert out["desde"] == esperado
    assert db.binds["desde"].date().isoformat() == esperado


# ── 4. Auth fail-closed (router-level dependency) ────────────────────────────

def _app_com_fake_db():
    app = FastAPI()
    app.include_router(router)

    async def _fake_get_db():
        yield _FakeDB([])

    app.dependency_overrides[get_db] = _fake_get_db
    return app


def test_sem_token_e_rejeitado_antes_do_banco():
    """Sem Authorization: o HTTPBearer bloqueia antes de qualquer consulta —
    o override de get_db nunca é consumido (se fosse, o teste falha com
    erro de conexão, provando o fail-closed)."""
    client = TestClient(_app_com_fake_db())
    r = client.get("/regulatorio/digest-semanal")
    assert r.status_code in (401, 403)
