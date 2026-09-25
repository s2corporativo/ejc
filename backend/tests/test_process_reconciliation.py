from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import process_reconciliation as pr


def test_extrair_cnjs_normaliza_e_remove_repeticoes():
    texto = (
        "Processo 1018284-13.2026.8.13.0027 e novamente "
        "1018284-13.2026.8.13.0027; outro 0709938-44.2026.8.07.0018."
    )
    assert pr.extrair_cnjs(texto) == [
        "1018284-13.2026.8.13.0027",
        "0709938-44.2026.8.07.0018",
    ]


@pytest.mark.anyio
async def test_reconciliacao_sem_banco_nao_inventa_correspondencia():
    resultado = await pr.reconciliar_entrada(
        None,
        SimpleNamespace(),
        texto="Relato sem processo confirmado",
        cliente_id=None,
        cliente_nome="Cliente",
        parte_contraria="Parte",
        assunto="Dano moral",
    )
    assert resultado["status"] == "informacoes_insuficientes"
    assert resultado["correspondencias"] == []
    assert resultado["bloquear_criacao"] is False


@pytest.mark.anyio
async def test_cnj_exato_bloqueia_nova_criacao(monkeypatch):
    async def _exato(_db, _user, numero):
        assert numero == "1018284-13.2026.8.13.0027"
        return [
            {
                "case_id": "case-1",
                "numero_interno": "DPT-2026-0001",
                "titulo": "Caso existente",
                "score": 100,
            }
        ]

    monkeypatch.setattr(pr, "buscar_casos_por_cnj", _exato)

    resultado = await pr.reconciliar_entrada(
        object(),
        SimpleNamespace(),
        texto="1018284-13.2026.8.13.0027",
        cliente_id="client-1",
        cliente_nome="Betim Baterias",
        parte_contraria="Facebook",
        assunto="Dano moral",
    )
    assert resultado["status"] == "ja_cadastrado"
    assert resultado["bloquear_criacao"] is True
    assert resultado["acao_sugerida"] == "abrir_caso_existente"


@pytest.mark.anyio
async def test_pre_processual_correspondente_sugere_vinculo(monkeypatch):
    async def _sem_exato(_db, _user, _numero):
        return []

    async def _candidatos(*_args, **_kwargs):
        return [
            {
                "case_id": "case-64",
                "numero_interno": "DPT-2026-0064",
                "titulo": "Betim Baterias x DER/DF",
                "score": 95,
                "pode_converter_pre_processual": True,
            }
        ]

    monkeypatch.setattr(pr, "buscar_casos_por_cnj", _sem_exato)
    monkeypatch.setattr(pr, "_candidatos_por_partes", _candidatos)

    resultado = await pr.reconciliar_entrada(
        object(),
        SimpleNamespace(),
        texto=(
            "0709938-44.2026.8.07.0018 TJDFT "
            "Betim Baterias x Departamento de Estradas"
        ),
        cliente_id="client-betim",
        cliente_nome="Betim Baterias",
        parte_contraria="Departamento de Estrada de Rodagem do DF",
        assunto="Acidente de trânsito",
    )
    assert resultado["status"] == "provavel_correspondencia"
    assert resultado["bloquear_criacao"] is False
    assert resultado["acao_sugerida"] == "revisar_e_vincular_pre_processual"
    assert resultado["correspondencias"][0]["case_id"] == "case-64"


def test_detecta_tribunal_sem_inferir_comarca_ou_vara():
    assert pr._tribunal_norm("TJDFT - 2ª Vara da Fazenda Pública do DF") == "TJDFT"
    assert pr._tribunal_norm("TJMG - Unidade Jurisdicional Única") == "TJMG"



class _LockDb:
    def __init__(self):
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params))


@pytest.mark.anyio
async def test_lock_cnj_usa_chave_normalizada_e_transacional():
    db = _LockDb()
    await pr.serializar_escrita_cnj(db, "1018284-13.2026.8.13.0027")

    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "pg_advisory_xact_lock" in sql
    assert params == {"chave": "entrada-cnj:10182841320268130027"}
