from sqlalchemy import UniqueConstraint

from app.models.signature import (
    SignatureRequest,
    SignatureSigner,
    SignatureSignerStatus,
)


def test_signatario_e_entidade_individual_com_evidencia_propria():
    colunas = set(SignatureSigner.__table__.columns.keys())
    assert {
        "signature_request_id",
        "user_id",
        "nome_snapshot",
        "email_snapshot",
        "status",
        "assinado_em",
        "ip",
        "user_agent",
    } <= colunas


def test_request_nao_substitui_signers_por_um_unico_usuario():
    # Campos legados permanecem para leitura histórica/compatibilidade, mas a
    # tabela nova é a fonte de verdade multiparte.
    assert "assinado_por_user" in SignatureRequest.__table__.columns
    assert SignatureSignerStatus.pendente.value == "pendente"
    assert SignatureSignerStatus.assinado.value == "assinado"
    assert SignatureSignerStatus.recusado.value == "recusado"


def test_request_user_e_unico_por_signatario():
    uniques = [
        constraint
        for constraint in SignatureSigner.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    nomes = {constraint.name for constraint in uniques}
    assert "uq_signature_signers_request_user" in nomes
