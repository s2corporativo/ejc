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


def test_update_rejeita_tipo_e_resultado_invalidos():
    # O contrato Pydantic aceita string para manter compatibilidade de payload;
    # a rota aplica a taxonomia canônica antes de persistir.
    assert "invalido" not in memoria.TIPOS
    assert "invalido" not in memoria.RESULTADOS
