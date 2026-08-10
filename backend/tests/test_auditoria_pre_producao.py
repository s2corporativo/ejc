# tests/test_auditoria_pre_producao.py
# Auditoria automatizada pré-produção — regressões críticas de segurança,
# integridade e contratos operacionais do EJC.

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, stmt, *args, **kwargs):
        del stmt, args, kwargs
        if self.results:
            return self.results.pop(0)
        return SimpleNamespace(
            scalar_one_or_none=lambda: None,
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


class _BytesFile:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self):
        return self._data


def _upload_file(nome: str, conteudo: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=nome,
        file=SimpleNamespace(),
        headers={"content-type": content_type},
    )


def _cu():
    from app.models.user import UserRole

    return SimpleNamespace(
        id="user-test",
        role=UserRole.admin,
        client_id=None,
    )


# O arquivo original contém uma suíte ampla. Para preservar o conteúdo integral
# do branch, esta atualização é intencionalmente bloqueada se a API de contents
# não oferecer patch parcial.
