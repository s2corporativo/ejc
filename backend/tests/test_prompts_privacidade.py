"""Prompt privado é do autor — não do escritório inteiro.

Achado da revisão automatizada do PR (03/09/2026): `publico=False` é opt-out
explícito do compartilhamento (a tela cria prompt privado por padrão), mas o
filtro de visibilidade só existia para quem estava ABAIXO de estagiário.
Qualquer membro da equipe listava, lia e EXECUTAVA o prompt privado de qualquer
colega — e executar devolve o conteúdo do prompt na resposta.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.prompt_juridico import PromptCategoria, PromptJuridico
from app.models.user import User, UserRole
from app.routers import prompts_juridicos as pj

pytestmark = pytest.mark.anyio

_TABELAS = [User.__table__, PromptJuridico.__table__]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _usuario(role: UserRole, nome: str) -> User:
    return User(id=str(uuid4()), email=f"{nome}-{uuid4().hex[:6]}@teste.local",
                hashed_password="x", full_name=nome, role=role, is_active=True)


def _prompt(*, autor: str | None, publico: bool, titulo: str) -> PromptJuridico:
    return PromptJuridico(
        id=str(uuid4()), titulo=titulo, categoria=PromptCategoria.peticao,
        conteudo="Redija uma petição sobre {{tema}} com no mínimo vinte caracteres.",
        created_by=autor, publico=publico,
    )


@pytest.fixture
async def cenario(db):
    autora = _usuario(UserRole.advogado, "Autora")
    colega = _usuario(UserRole.advogado, "Colega")
    socio = _usuario(UserRole.socio, "Socio")
    db.add_all([autora, colega, socio])

    privado = _prompt(autor=autora.id, publico=False, titulo="Privado da autora")
    publico = _prompt(autor=autora.id, publico=True, titulo="Público do escritório")
    orfao = _prompt(autor=None, publico=False, titulo="Privado órfão")
    db.add_all([privado, publico, orfao])
    await db.commit()
    return {"autora": autora, "colega": colega, "socio": socio,
            "privado": privado, "publico": publico, "orfao": orfao}


async def _titulos(db, cu) -> set[str]:
    # Chamada direta da função: os defaults de Query() não são resolvidos fora
    # do FastAPI, então os filtros vão explícitos.
    r = await pj.listar_prompts(categoria=None, favorito=None, busca=None,
                                page=1, per_page=100, db=db, cu=cu)
    return {i["titulo"] for i in r["items"]}


async def test_colega_nao_lista_prompt_privado_alheio(db, cenario):
    assert await _titulos(db, cenario["colega"]) == {"Público do escritório"}


async def test_autora_lista_o_proprio_privado(db, cenario):
    assert await _titulos(db, cenario["autora"]) == {
        "Privado da autora", "Público do escritório"}


async def test_socio_ve_o_orfao_mas_nao_o_privado_de_colega(db, cenario):
    assert await _titulos(db, cenario["socio"]) == {
        "Público do escritório", "Privado órfão"}


async def test_leitura_direta_de_privado_alheio_responde_404(db, cenario):
    with pytest.raises(HTTPException) as e:
        await pj.obter_prompt(cenario["privado"].id, db=db, cu=cenario["colega"])
    assert e.value.status_code == 404
    # A autora continua lendo o próprio.
    assert (await pj.obter_prompt(
        cenario["privado"].id, db=db, cu=cenario["autora"]))["titulo"] == "Privado da autora"


async def test_execucao_de_privado_alheio_responde_404(db, cenario):
    # Executar devolve o conteúdo do prompt: sem este filtro, o 404 da leitura
    # seria contornável por POST /{id}/executar.
    req = pj.ExecutarPromptReq(variaveis={"tema": "dano moral"})
    with pytest.raises(HTTPException) as e:
        await pj.executar_prompt(cenario["privado"].id, req, db=db, cu=cenario["colega"])
    assert e.value.status_code == 404


async def test_edicao_de_privado_alheio_responde_404(db, cenario):
    patch = pj.PromptPatch(titulo="Sequestrado")
    with pytest.raises(HTTPException) as e:
        await pj.atualizar_prompt(cenario["privado"].id, patch, db=db, cu=cenario["colega"])
    assert e.value.status_code == 404


async def test_cliente_externo_so_ve_publico(db, cenario):
    externo = _usuario(UserRole.cliente_externo, "Externo")
    db.add(externo)
    await db.commit()
    assert await _titulos(db, externo) == {"Público do escritório"}
