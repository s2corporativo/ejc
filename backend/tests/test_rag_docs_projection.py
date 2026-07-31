"""Regressão P0 de /rag/docs: projeção mínima e contrato estável."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql


class _Resultado:
    def __init__(self, *, escalar=None, linhas=None):
        self._escalar = escalar
        self._linhas = linhas or []

    def scalar(self):
        return self._escalar

    def mappings(self):
        return self

    def all(self):
        return self._linhas


class _DBFalso:
    def __init__(self, linha):
        self.comandos = []
        self._linha = linha

    async def execute(self, comando):
        self.comandos.append(comando)
        if len(self.comandos) == 1:
            return _Resultado(escalar=1)
        return _Resultado(linhas=[self._linha])


async def test_listar_docs_projeta_somente_campos_publicos():
    from app.routers.rag import listar_docs

    criado_em = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
    linha = {
        "id": "doc-ficticio",
        "titulo": "Documento público fictício",
        "categoria": "legislacao",
        "fonte": "https://example.invalid/fonte-oficial-ficticia",
        "tribunal": None,
        "status_indexacao": "pendente",
        "created_at": criado_em,
    }
    db = _DBFalso(linha)

    resposta = await listar_docs(
        page=2,
        page_size=5,
        categoria="legislacao",
        db=db,
        cu=object(),
    )

    assert resposta == {
        "data": [linha],
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    assert len(db.comandos) == 2

    sql = [
        str(
            comando.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        for comando in db.comandos
    ]
    assert "count(knowledge_docs.id)" in sql[0]
    assert "knowledge_docs.categoria = 'legislacao'" in sql[0]
    assert "limit 5 offset 5" in " ".join(sql[1].split())

    combinado = "\n".join(sql)
    for coluna_privada in (
        "knowledge_docs.base_rag",
        "knowledge_docs.extra",
        "knowledge_docs.client_id",
        "knowledge_docs.case_id",
        "knowledge_docs.hash_conteudo",
        "knowledge_docs.revisado_por",
    ):
        assert coluna_privada not in combinado
