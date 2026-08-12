"""Regressão A11 (auditoria 2026-08-12, LGPD art. 37) — a leitura do resultado
de um lote da Entrada Universal que contém dado pessoal extraído por um usuário
que NÃO é o criador deve gerar evento de auditoria `LEITURA_PII`. A leitura por
um resultado SEM PII ou pelo próprio criador NÃO gera o evento (evita ruído e
duplicação com o UPLOAD)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.routers.entrada_universal import (
    _lote_contem_pii,
)


def _usuario(user_id: str):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value="advogado"))


class TestLoteContemPiiDBFree:
    """O detector de PII é determinístico e não toca o banco — roda sempre."""

    def test_partes_com_autor_pegam_pii(self):
        assert _lote_contem_pii({"partes": {"autor": "João da Silva", "reu": None, "terceiros": []}})
        assert _lote_contem_pii({"partes": {"autor": None, "reu": "Empresa X", "terceiros": []}})
        assert _lote_contem_pii({"partes": {"autor": None, "reu": None, "terceiros": ["Maria"]}})

    def test_partes_vazias_nao_pegam_pii(self):
        assert not _lote_contem_pii({"partes": {"autor": None, "reu": None, "terceiros": []}})
        assert not _lote_contem_pii({"partes": {}})
        assert not _lote_contem_pii({})
        assert not _lote_contem_pii({"documento": "algo sem pii"})

    def test_dados_pessoais_e_resumo_pegam_pii(self):
        assert _lote_contem_pii({"dados_pessoais": {"nome": "João", "cpf": None, "cnpj": None}})
        assert _lote_contem_pii({"resumo_executivo": {"fatos": "Fato relevante", "situacao": None, "providencia_principal": None}})

    def test_lista_vazia_nao_pegam(self):
        assert not _lote_contem_pii({"partes": {"autor": None, "reu": None, "terceiros": []}})

    def test_string_vazia_nao_pegam(self):
        assert not _lote_contem_pii({"resumo_executivo": {"fatos": "", "situacao": None, "providencia_principal": None}})


class TestObterLoteRegistraLeituraPii:
    """GET /{batch_id}: o evento LEITURA_PII entra apenas quando o resultado
    contém PII E o leitor não é o criador. Falha de auditoria nunca bloqueia."""

    async def _obter(self, batch, user, *, registrar=True):
        from app.routers.entrada_universal import obter_lote

        # Substitui criar_audit_log por um mock que grava as chamadas no batch
        import app.routers.entrada_universal as router_mod

        chamadas = []
        original = router_mod.criar_audit_log

        async def mock_log(*a, **k):
            chamadas.append((a, k))

        # _acesso_batch exige db real (verificar_acesso_caso) — mockar o guard.
        async def acesso_mock(_db, _cu, _bid):
            return batch

        acesso_original = router_mod._acesso_batch
        router_mod._acesso_batch = acesso_mock
        if registrar:
            router_mod.criar_audit_log = mock_log
        try:
            return await obter_lote(batch_id=batch.id, db=AsyncMock(), cu=user), chamadas
        finally:
            router_mod._acesso_batch = acesso_original
            router_mod.criar_audit_log = original

    async def test_leitor_diferente_com_pii_registra(self):
        batch = SimpleNamespace(id="batch-1", created_by="user-criador", resultado={
            "partes": {"autor": "João da Silva", "reu": None, "terceiros": []},
        })
        _, chamadas = await self._obter(batch, _usuario("user-terceiro"))
        assert len(chamadas) == 1
        assert chamadas[0][1]["acao"] == "LEITURA_PII"
        assert chamadas[0][1]["entidade"] == "document_intake_batch"
        assert chamadas[0][1]["registro_id"] == "batch-1"
        assert chamadas[0][1]["user_id"] == "user-terceiro"

    async def test_criador_do_lote_nao_registra_duplicado(self):
        batch = SimpleNamespace(id="batch-2", created_by="user-criador", resultado={
            "partes": {"autor": "João da Silva", "reu": None, "terceiros": []},
        })
        _, chamadas = await self._obter(batch, _usuario("user-criador"))
        assert chamadas == []

    async def test_sem_pii_nao_registra(self):
        batch = SimpleNamespace(id="batch-3", created_by="user-criador", resultado={
            "ok": True, "documentos": [], "nivel_prontidao": "apto",
        })
        _, chamadas = await self._obter(batch, _usuario("user-terceiro"))
        assert chamadas == []

    async def test_falha_de_auditoria_nao_bloqueia_leitura(self):
        import app.routers.entrada_universal as router_mod

        batch = SimpleNamespace(id="batch-4", created_by="user-criador", resultado={
            "partes": {"autor": "João da Silva", "reu": None, "terceiros": []},
        })

        async def log_que_falha(*a, **k):
            raise RuntimeError("auditoria indisponível")

        original = router_mod.criar_audit_log
        router_mod.criar_audit_log = log_que_falha
        try:
            resposta, _ = await self._obter(batch, _usuario("user-terceiro"), registrar=False)
        finally:
            router_mod.criar_audit_log = original

        assert resposta["partes"]["autor"] == "João da Silva"
