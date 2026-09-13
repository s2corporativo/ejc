# ── tests/test_deduplicar_base_conhecimento_dblevel.py ───────────────────────
# A suíte pura (test_deduplicar_base_conhecimento.py) cobre agrupamento e
# pontuação, nunca a execução SQL real de `--aplicar`/`--reverter`. Foi
# exatamente esse ponto cego que deixou passar um defeito onde `--aplicar`
# quebrava em TODA execução real: `:marca::jsonb` (bind param PostgreSQL
# seguido imediatamente de `::cast`) não é reconhecido como parâmetro pelo
# extrator de bindparams do SQLAlchemy — a query ia para o banco com
# `:marca::jsonb` literal, e o asyncpg recusava com erro de sintaxe no `:`.
# O dry-run nunca executa esse UPDATE, então nunca acusava o problema; a
# quebra só aparecia na aplicação real (o ato que este script existe para
# fazer). Corrigido trocando `:marca::jsonb` por `CAST(:marca AS jsonb)`.
#
# Postgres é OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py). Sem
# RUN_DB_TESTS=1, pula. Os testes também isolam explicitamente o conjunto de
# candidatos e a reversão aos IDs do fixture: mesmo se alguém apontar a suíte
# por engano para um banco reutilizado, nenhuma linha preexistente entra no
# plano de deduplicação nem na reversão.
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from scripts import deduplicar_base_conhecimento as dedup_mod
from scripts.deduplicar_base_conhecimento import DocCandidato, executar, reverter

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _inserir_doc(db, *, titulo, fonte=None, chave_origem=None,
                        revisado=False) -> str:
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO knowledge_docs "
            "(id, titulo, categoria, fonte, chave_origem, revisado, versao, "
            " vigente, client_id) "
            "VALUES (:id, :titulo, 'legislacao', :fonte, :chave, :revisado, "
            " 1, true, NULL)"
        ),
        {"id": doc_id, "titulo": titulo, "fonte": fonte, "chave": chave_origem,
         "revisado": revisado},
    )
    return doc_id


async def _limpar(db, doc_ids: list[str]) -> None:
    for did in doc_ids:
        await db.execute(text("DELETE FROM knowledge_docs WHERE id = :id"), {"id": did})
    await db.commit()


def _isolar_candidatos(monkeypatch, candidatos: list[DocCandidato]) -> None:
    """Impede que `executar()` forme plano com qualquer linha fora do fixture."""
    async def _carregar_fixture(_db):
        return candidatos

    monkeypatch.setattr(dedup_mod, "carregar_candidatos", _carregar_fixture)


def _candidato(doc_id: str, titulo: str, *, fonte=False, chave=False,
               revisado=False) -> DocCandidato:
    return DocCandidato(
        id=doc_id,
        titulo=titulo,
        categoria="legislacao",
        tem_fonte=fonte,
        tem_chave_origem=chave,
        revisado=revisado,
        versao=1,
        atualizado_em_ts=0.0,
        n_chunks=0,
    )


def _isolar_reversao(monkeypatch, ids: list[str]) -> None:
    """Mantém a semântica da reversão, mas restringe o UPDATE aos IDs do fixture."""
    placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
    sql = text(
        "UPDATE knowledge_docs "
        "SET vigente = true, extra = extra - :chave_dedup - :chave_vencedor "
        "WHERE vigente = false AND extra ? :chave_dedup "
        f"AND id IN ({placeholders})"
    )
    # `reverter()` fornece apenas as chaves; bindamos os IDs diretamente no
    # statement para não ampliar a assinatura de produção só por causa do teste.
    sql = sql.bindparams(**{f"id_{i}": value for i, value in enumerate(ids)})
    monkeypatch.setattr(dedup_mod, "_SQL_REVERTER", sql)


async def test_aplicar_rebaixa_perdedor_e_marca_extra_sem_apagar(monkeypatch):
    """Regressão do bug real: --aplicar tem de gravar vigente=false + extra."""
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(dedup_mod, "input", lambda *_a: dedup_mod.PALAVRA_CONFIRMACAO,
                        raising=False)
    tok = uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        titulo_manual = f"CPC upload manual {tok}"
        titulo_oficial = f"Código de Processo Civil (Lei 13.105/2015) {tok}"
        manual = await _inserir_doc(db, titulo=titulo_manual)
        oficial = await _inserir_doc(
            db, titulo=titulo_oficial,
            fonte="https://planalto.gov.br/l13105", chave_origem=f"planalto:l13105:{tok}",
            revisado=True,
        )
        await db.commit()
        _isolar_candidatos(monkeypatch, [
            _candidato(manual, titulo_manual),
            _candidato(oficial, titulo_oficial, fonte=True, chave=True, revisado=True),
        ])
        try:
            rc = await executar(aplicar=True)
            assert rc == 0

            linhas = (await db.execute(
                text("SELECT id, vigente, extra->>'duplicata_de' AS venc "
                     "FROM knowledge_docs WHERE id IN (:a, :b)"),
                {"a": manual, "b": oficial},
            )).mappings().all()
            por_id = {l["id"]: l for l in linhas}

            assert por_id[manual]["vigente"] is False, (
                "cópia sem fonte/revisão deveria ter sido rebaixada"
            )
            assert por_id[manual]["venc"] == oficial
            assert por_id[oficial]["vigente"] is True, (
                "cópia com fonte oficial + revisada é quem deveria vencer"
            )
        finally:
            await _limpar(db, [manual, oficial])


async def test_reverter_devolve_vigente_true_so_ao_que_este_script_marcou(monkeypatch):
    from app.core.database import AsyncSessionLocal

    monkeypatch.setattr(dedup_mod, "input", lambda *_a: dedup_mod.PALAVRA_CONFIRMACAO,
                        raising=False)
    tok = uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        titulo_manual = f"CLT upload manual {tok}"
        titulo_oficial = f"CLT (Decreto-Lei 5.452/1943) {tok}"
        manual = await _inserir_doc(db, titulo=titulo_manual)
        oficial = await _inserir_doc(
            db, titulo=titulo_oficial,
            fonte="https://planalto.gov.br/dl5452", chave_origem=f"planalto:dl5452:{tok}",
        )
        await db.commit()
        _isolar_candidatos(monkeypatch, [
            _candidato(manual, titulo_manual),
            _candidato(oficial, titulo_oficial, fonte=True, chave=True),
        ])
        _isolar_reversao(monkeypatch, [manual])
        try:
            await executar(aplicar=True)

            vigente_antes = (await db.scalar(
                text("SELECT vigente FROM knowledge_docs WHERE id = :id"), {"id": manual},
            ))
            assert vigente_antes is False

            rc = await reverter()
            assert rc == 0

            linha = (await db.execute(
                text("SELECT vigente, extra FROM knowledge_docs WHERE id = :id"),
                {"id": manual},
            )).mappings().one()
            assert linha["vigente"] is True
            assert "deduplicado_em" not in (linha["extra"] or {})
        finally:
            await _limpar(db, [manual, oficial])


async def test_dry_run_nao_altera_nada(monkeypatch):
    from app.core.database import AsyncSessionLocal

    tok = uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        titulo_manual = f"Código Civil upload {tok}"
        titulo_oficial = f"Código Civil (Lei 10.406/2002) {tok}"
        manual = await _inserir_doc(db, titulo=titulo_manual)
        oficial = await _inserir_doc(
            db, titulo=titulo_oficial,
            fonte="https://planalto.gov.br/l10406",
        )
        await db.commit()
        _isolar_candidatos(monkeypatch, [
            _candidato(manual, titulo_manual),
            _candidato(oficial, titulo_oficial, fonte=True),
        ])
        try:
            rc = await executar(aplicar=False)
            assert rc == 0

            vigentes = (await db.execute(
                text("SELECT count(*) FROM knowledge_docs "
                     "WHERE id IN (:a, :b) AND vigente = true"),
                {"a": manual, "b": oficial},
            )).scalar()
            assert vigentes == 2, "dry-run não pode alterar nenhuma linha"
        finally:
            await _limpar(db, [manual, oficial])
