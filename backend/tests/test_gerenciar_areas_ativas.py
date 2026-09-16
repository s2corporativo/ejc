"""Testes do script de gerenciamento de áreas ativas (sem banco).

O que dá para travar sem Postgres: a montagem das queries, a recusa de
desativar área com caso vivo sem --forcar-com-casos, e que ativar nunca exige
essa flag. A decisão de QUAIS áreas manter é humana (dado real de produção,
fora do meu acesso) — este teste só protege o MECANISMO."""
from __future__ import annotations

import pytest

from scripts.gerenciar_areas_ativas import _alterar, _listar


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _DB:
    def __init__(self, linhas_listar=None, linha_alterar=None):
        self.linhas_listar = linhas_listar or []
        self.linha_alterar = linha_alterar
        self.updates = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "GROUP BY a.slug" in sql:
            return _Result(self.linhas_listar)
        if "GROUP BY a.ativo" in sql:
            return _Result([self.linha_alterar] if self.linha_alterar else [])
        if sql.strip().startswith("UPDATE"):
            self.updates.append(params)
            return _Result([])
        raise AssertionError(f"query inesperada: {sql}")

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_listar_devolve_contagem_real_por_area():
    db = _DB(linhas_listar=[
        {"slug": "consumidor", "nome": "Consumidor", "ativo": True, "ordem": 90, "casos_vivos": 7},
        {"slug": "eleitoral", "nome": "Eleitoral", "ativo": True, "ordem": 210, "casos_vivos": 0},
    ])
    linhas = await _listar(db)
    assert linhas[0]["casos_vivos"] == 7
    assert linhas[1]["casos_vivos"] == 0


@pytest.mark.asyncio
async def test_desativar_area_sem_caso_vivo_aplica_direto():
    db = _DB(linha_alterar=(True, 0))
    await _alterar(db, ["eleitoral"], False, forcar_com_casos=False)
    assert db.updates == [{"ativo": False, "slug": "eleitoral"}]
    assert db.committed


@pytest.mark.asyncio
async def test_desativar_area_com_caso_vivo_e_recusado_sem_forcar():
    db = _DB(linha_alterar=(True, 3))
    await _alterar(db, ["consumidor"], False, forcar_com_casos=False)
    assert db.updates == []  # recusado — nada foi alterado


@pytest.mark.asyncio
async def test_desativar_area_com_caso_vivo_aplica_com_forcar():
    db = _DB(linha_alterar=(True, 3))
    await _alterar(db, ["consumidor"], False, forcar_com_casos=True)
    assert db.updates == [{"ativo": False, "slug": "consumidor"}]


@pytest.mark.asyncio
async def test_ativar_nunca_exige_forcar_mesmo_com_casos():
    db = _DB(linha_alterar=(False, 5))
    await _alterar(db, ["eleitoral"], True, forcar_com_casos=False)
    assert db.updates == [{"ativo": True, "slug": "eleitoral"}]


@pytest.mark.asyncio
async def test_slug_inexistente_e_ignorado_sem_quebrar():
    db = _DB(linha_alterar=None)
    await _alterar(db, ["inexistente"], False, forcar_com_casos=False)
    assert db.updates == []
    assert db.committed  # segue para o commit (idempotente, sem erro)
