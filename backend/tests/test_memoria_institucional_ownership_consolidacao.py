from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import memoria_institucional as memoria


class _Mappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class _DbLeitura:
    def __init__(self, row):
        self._row = row

    async def execute(self, *_args, **_kwargs):
        return _Result(self._row)


@pytest.mark.asyncio
async def test_memoria_vinculada_aplica_ownership_do_caso(monkeypatch):
    db = _DbLeitura({"id": "mem-1", "case_id": "case-1", "titulo": "Tese"})
    cu = SimpleNamespace(id="user-1")
    gate = AsyncMock()
    monkeypatch.setattr(memoria, "verificar_acesso_caso", gate)

    row = await memoria._obter_memoria_autorizada(db, cu, "mem-1")

    assert row["id"] == "mem-1"
    gate.assert_awaited_once_with(db, cu, "case-1")


@pytest.mark.asyncio
async def test_memoria_institucional_sem_caso_preserva_acervo_transversal(monkeypatch):
    db = _DbLeitura({"id": "mem-global", "case_id": None, "titulo": "Modelo"})
    cu = SimpleNamespace(id="user-1")
    gate = AsyncMock()
    monkeypatch.setattr(memoria, "verificar_acesso_caso", gate)

    row = await memoria._obter_memoria_autorizada(db, cu, "mem-global")

    assert row["id"] == "mem-global"
    gate.assert_not_awaited()


@pytest.mark.asyncio
async def test_memoria_inexistente_retorna_404():
    db = _DbLeitura(None)
    cu = SimpleNamespace(id="user-1")

    with pytest.raises(HTTPException) as exc:
        await memoria._obter_memoria_autorizada(db, cu, "ausente")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["obter", "atualizar", "remover"])
async def test_get_patch_delete_bloqueiam_antes_de_operar_sem_ownership(monkeypatch, handler):
    async def _negado(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail="Acesso negado")

    monkeypatch.setattr(memoria, "_obter_memoria_autorizada", _negado)
    db = object()
    cu = SimpleNamespace(id="user-1")

    with pytest.raises(HTTPException) as exc:
        if handler == "obter":
            await memoria.obter("mem-1", db=db, cu=cu)
        elif handler == "atualizar":
            await memoria.atualizar(
                "mem-1",
                memoria.MemoriaUpdate(titulo="Novo título"),
                db=db,
                cu=cu,
            )
        else:
            await memoria.remover("mem-1", db=db, cu=cu)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        memoria.MemoriaUpdate(tipo="invalido"),
        memoria.MemoriaUpdate(resultado="invalido"),
    ],
)
async def test_update_rejeita_taxonomia_invalida_antes_de_persistir(monkeypatch, body):
    autorizacao = AsyncMock(return_value={"id": "mem-1", "case_id": None})
    monkeypatch.setattr(memoria, "_obter_memoria_autorizada", autorizacao)

    with pytest.raises(HTTPException) as exc:
        await memoria.atualizar(
            "mem-1",
            body,
            db=object(),
            cu=SimpleNamespace(id="user-1"),
        )

    assert exc.value.status_code == 422
    autorizacao.assert_awaited_once()


class _MappingsMany:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ResultMany:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _MappingsMany(self._rows)


class _DbLista:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    async def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _ResultMany(self.rows)


@pytest.mark.asyncio
async def test_listagem_global_filtra_case_scoped_antes_do_limit(monkeypatch):
    db = _DbLista([
        {"id": "mem-global", "case_id": None},
        {"id": "mem-permitida", "case_id": "case-ok"},
    ])
    cu = SimpleNamespace(id="user-1")
    monkeypatch.setattr(memoria, "is_gestao", lambda _cu: False)

    rows = await memoria.listar(limit=2, db=db, cu=cu)

    assert [r["id"] for r in rows] == ["mem-global", "mem-permitida"]
    assert "case_id IS NULL OR case_id IN" in db.statement
    assert "advogado_responsavel_id = :cu_id" in db.statement
    assert "advogado_auxiliar_id = :cu_id" in db.statement
    assert "LIMIT :limit" in db.statement
    assert db.statement.index("case_id IS NULL OR case_id IN") < db.statement.index("LIMIT :limit")
    assert db.params["cu_id"] == "user-1"
    assert db.params["limit"] == 2


@pytest.mark.asyncio
async def test_listagem_global_gestao_preserva_acervo_completo(monkeypatch):
    db = _DbLista([{"id": "mem-qualquer", "case_id": "case-x"}])
    cu = SimpleNamespace(id="socio-1")
    monkeypatch.setattr(memoria, "is_gestao", lambda _cu: True)

    rows = await memoria.listar(limit=10, db=db, cu=cu)

    assert rows == [{"id": "mem-qualquer", "case_id": "case-x"}]
    assert "case_id IS NULL OR case_id IN" not in db.statement
    assert "cu_id" not in db.params
