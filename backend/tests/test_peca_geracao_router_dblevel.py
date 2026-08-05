"""T-P0-1 — o gerador de documento por template, exercitado de verdade.

`peca_geracao_router` renderiza documento jurídico a partir dos modelos do
Victory Vault e, até esta auditoria, **não tinha teste nenhum** — nem de rota,
nem de render, nem do sandbox. É o achado T-P0-1 de `docs/auditoria-ejc/14-testes.md`:
o núcleo do produto sem cobertura, num repositório com 4 700 testes.

O arquivo tem 52 linhas e três invariantes que valem mais que o tamanho sugere:

1. **o render funciona** — o histórico deste código é de estar quebrado sem que
   ninguém soubesse: até 28/06/2026 o engine chamava o vault async sem `await` e
   referenciava um campo `m.nome` que não existe no schema. Um teste que
   exercite o caminho é o que impede a terceira vez;
2. **o sandbox Jinja2 segura** — o template vem do BANCO e é editável pelo
   usuário; os dados são arbitrários. Sem sandbox, `{{ ''.__class__ }}` é SSTI
   com execução de código. O `SandboxedEnvironment` foi posto na auditoria de
   2026-06-30 e nunca teve teste — trocar por `Template` passaria despercebido;
3. **gerar é ato jurídico** — piso advogado+ (P1-2 desta auditoria), enquanto
   listar o catálogo segue aberto a staff.

Contra Postgres real (RUN_DB_TESTS=1): o `vault` abre sessão própria via
`AsyncSessionLocal`, então um fake de banco testaria o fake, não o caminho.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _criar_user(db, role: str):
    from sqlalchemy import select
    from app.models.user import User

    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
            "VALUES (:id, :email, 'x', 'Teste Geracao', :role, true)"
        ),
        {"id": uid, "email": f"gera-{uid[:8]}@teste.local", "role": role},
    )
    await db.commit()
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _criar_modelo(db, conteudo: str, area: str = "trabalhista") -> str:
    mid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO modelos_documentos "
            "(id, tipo_documento, area_juridica, conteudo_template, descricao) "
            "VALUES (:id, 'peticao_inicial', :area, :conteudo, 'Modelo de teste')"
        ),
        {"id": mid, "area": area, "conteudo": conteudo},
    )
    await db.commit()
    return mid


async def _limpar(db, modelo_ids=(), user_ids=()):
    for mid in modelo_ids:
        await db.execute(text("DELETE FROM modelos_documentos WHERE id = :id"), {"id": mid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


async def test_gera_documento_substituindo_as_variaveis_do_modelo():
    """O caminho feliz — e o que prova que o engine NÃO está quebrado.

    Duas vezes na história deste arquivo ele esteve inerte em produção sem
    ninguém notar (chamada async sem await; campo inexistente no schema). O
    teste renderiza um modelo real, gravado no banco real.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import gerar_documento

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        modelo = await _criar_modelo(
            db,
            "EXCELENTÍSSIMO JUÍZO. {{ autor }}, portador do CPF {{ cpf }}, "
            "vem propor AÇÃO em face de {{ reu }}.",
        )
        try:
            resp = await gerar_documento(
                {"template_id": modelo,
                 "data": {"autor": "Fulano de Tal", "cpf": "390.533.447-05",
                          "reu": "Empresa Ré LTDA"}},
                cu=advogado,
            )
            doc = resp["documento"]
            assert "Fulano de Tal" in doc
            assert "Empresa Ré LTDA" in doc
            assert "390.533.447-05" in doc
            # Nenhum placeholder sobrou por renderizar — peça com `{{ }}` no
            # corpo é peça que não se protocola.
            assert "{{" not in doc and "}}" not in doc
        finally:
            await _limpar(db, [modelo], [advogado.id])


async def test_variavel_ausente_nao_derruba_a_geracao():
    """Jinja2 resolve ausente como vazio. A peça sai incompleta — e é isso que
    o advogado precisa VER na revisão, em vez de receber um 500 sem documento."""
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import gerar_documento

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        modelo = await _criar_modelo(db, "Autor: {{ autor }} | Réu: {{ reu }}")
        try:
            resp = await gerar_documento(
                {"template_id": modelo, "data": {"autor": "Fulano"}}, cu=advogado
            )
            assert "Fulano" in resp["documento"]
        finally:
            await _limpar(db, [modelo], [advogado.id])


async def test_sandbox_jinja2_bloqueia_ssti_no_template_do_banco():
    """SSTI: o template vem do BANCO e é editável — o sandbox é o que separa
    "modelo de petição" de "execução de código no servidor".

    O `SandboxedEnvironment` entrou na auditoria de 2026-06-30 e nunca teve
    teste. Trocá-lo pelo `Template` padrão do Jinja2 — um refactor de aparência
    inocente — reabriria o RCE em silêncio. Este teste é o que impede.
    """
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import gerar_documento

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        # A cadeia clássica de SSTI em Jinja2: subir de uma string até
        # `__globals__` e daí ao `os`/`subprocess`.
        modelo = await _criar_modelo(
            db, "{{ ''.__class__.__mro__[1].__subclasses__() }}"
        )
        try:
            with pytest.raises(Exception) as exc:
                await gerar_documento({"template_id": modelo, "data": {}}, cu=advogado)
            # O sandbox recusa o acesso ao atributo; qualquer resultado que
            # RENDERIZE a lista de subclasses seria o RCE aberto.
            assert "SecurityError" in type(exc.value).__name__ or "unsafe" in str(exc.value).lower(), (
                f"o sandbox Jinja2 não bloqueou o acesso: {type(exc.value).__name__}: {exc.value}"
            )
        finally:
            await _limpar(db, [modelo], [advogado.id])


async def test_template_inexistente_responde_404_e_nao_500():
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import gerar_documento

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        try:
            with pytest.raises(HTTPException) as exc:
                await gerar_documento(
                    {"template_id": str(uuid4()), "data": {}}, cu=advogado
                )
            assert exc.value.status_code == 404
        finally:
            await _limpar(db, user_ids=[advogado.id])


async def test_sem_template_id_responde_400():
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import gerar_documento

    async with AsyncSessionLocal() as db:
        advogado = await _criar_user(db, "advogado")
        try:
            with pytest.raises(HTTPException) as exc:
                await gerar_documento({"data": {"autor": "x"}}, cu=advogado)
            assert exc.value.status_code == 400
        finally:
            await _limpar(db, user_ids=[advogado.id])


@pytest.mark.parametrize("role", ["secretaria", "estagiario", "financeiro"])
async def test_gerar_documento_exige_advogado(role):
    """P1-2: gerar peça é ato jurídico. O gate vive em `_req_advogado`, que é a
    dependency da rota — aqui exercitado diretamente."""
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import _req_advogado

    async with AsyncSessionLocal() as db:
        usuario = await _criar_user(db, role)
        try:
            with pytest.raises(HTTPException) as exc:
                _req_advogado(usuario)
            assert exc.value.status_code == 403
        finally:
            await _limpar(db, user_ids=[usuario.id])


async def test_listar_templates_segue_aberto_a_staff():
    """A restrição é de GERAR. Consultar o catálogo não é ato jurídico —
    secretaria precisa disso para preparar o trabalho do advogado."""
    from app.core.database import AsyncSessionLocal
    from app.routers.peca_geracao_router import listar_templates

    async with AsyncSessionLocal() as db:
        secretaria = await _criar_user(db, "secretaria")
        modelo = await _criar_modelo(db, "Modelo {{ x }}", area="civel")
        try:
            catalogo = await listar_templates(area_juridica="civel", cu=secretaria)
            ids = [m["id"] for m in catalogo]
            assert modelo in ids
            # O catálogo expõe metadados, NÃO o corpo do template.
            assert all("conteudo_template" not in m for m in catalogo)
        finally:
            await _limpar(db, [modelo], [secretaria.id])
