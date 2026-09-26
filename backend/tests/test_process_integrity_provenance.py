from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.process_integrity import PartyEntity
from app.services.party_identity_service import inferir_tipo_entidade, normalizar_nome_parte
from app.services.process_provenance_service import registrar_proveniencia


def test_identidade_parte_normaliza_sem_fundir_semantica():
    assert normalizar_nome_parte("Facebook Serviços Online do Brasil LTDA.") == (
        "facebook servicos online do brasil ltda"
    )
    assert normalizar_nome_parte("  João   da Silva ") == "joao da silva"


def test_tipo_entidade_prioriza_documento_e_reconhece_pj():
    assert inferir_tipo_entidade("Maria", "123.456.789-01") == "PF"
    assert inferir_tipo_entidade("Empresa XPTO Ltda") == "PJ"
    assert inferir_tipo_entidade("João da Silva") == "desconhecido"


def test_party_entity_nao_duplica_documento_cifrado():
    colunas = {col.name for col in PartyEntity.__table__.columns}
    assert "cpf_cnpj_hash" in colunas
    assert "cpf_cnpj_enc" not in colunas


class _DBFake:
    def __init__(self):
        self.rows = []
        self.flushes = 0

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        self.flushes += 1


@pytest.mark.asyncio
async def test_proveniencia_serializa_tipos_json_comuns():
    db = _DBFake()
    uid = UUID("12345678-1234-5678-1234-567812345678")

    rows = await registrar_proveniencia(
        db,
        process_id="process-1",
        campos={
            "data_ajuizamento": date(2026, 9, 23),
            "valor_causa": Decimal("1234.56"),
            "referencia": uid,
        },
        source_type="usuario",
        source_ref="teste",
        confirmed_by="user-1",
    )

    assert len(rows) == 3
    valores = {row.field_name: row.value_snapshot["value"] for row in rows}
    assert valores["data_ajuizamento"] == "2026-09-23"
    assert valores["valor_causa"] == "1234.56"
    assert valores["referencia"] == str(uid)
    assert db.flushes == 1


@pytest.mark.asyncio
async def test_proveniencia_rejeita_fonte_desconhecida():
    db = _DBFake()
    with pytest.raises(ValueError, match="Fonte de proveniência inválida"):
        await registrar_proveniencia(
            db,
            process_id="process-1",
            campos={"classe": "Procedimento Comum Cível"},
            source_type="fonte_nao_permitida",
        )
