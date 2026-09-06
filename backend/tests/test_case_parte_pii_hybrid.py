"""`CaseParte.cpf_cnpj` (DB-03, migration 159) — escreve cifrado, lê com fallback.

Sem banco: exercita só o mapeamento ORM e o pii_crypto (chaves efêmeras de
dev). O lado do banco (backfill, índice cego, anonimização) está em
`test_case_partes_pii_dblevel.py`.
"""
from __future__ import annotations

from app.models.case_parte import CaseParte
from app.services.pii_crypto import decrypt, hash_documento


def test_setter_cifra_hasheia_e_zera_texto_puro():
    parte = CaseParte(id="p1", case_id="c1", tipo="reu", nome="Fulano")
    parte.cpf_cnpj_plain = "legado-em-claro"
    parte.cpf_cnpj = "153.509.460-56"

    assert parte.cpf_cnpj_plain is None, "o ORM nunca mais grava documento em claro"
    assert parte.cpf_cnpj_enc and parte.cpf_cnpj_enc != "15350946056"
    assert decrypt(parte.cpf_cnpj_enc) == "15350946056"  # normalizado (só dígitos)
    assert parte.cpf_cnpj_hash == hash_documento("15350946056")
    assert parte.cpf_cnpj == "15350946056"


def test_construtor_aceita_cpf_cnpj_e_passa_pelo_setter():
    parte = CaseParte(id="p2", case_id="c1", tipo="autor", nome="X", cpf_cnpj="12.345.678/0001-95")
    assert parte.cpf_cnpj_plain is None
    assert parte.cpf_cnpj_hash == hash_documento("12345678000195")
    assert parte.cpf_cnpj == "12345678000195"


def test_leitura_cai_no_texto_puro_quando_nao_ha_cifra():
    """Linha legada (router de SQL cru ou backfill ainda não rodado)."""
    parte = CaseParte(id="p3", case_id="c1", tipo="reu", nome="Y")
    parte.cpf_cnpj_plain = "111.222.333-44"
    assert parte.cpf_cnpj == "111.222.333-44"


def test_setter_com_valor_vazio_ou_lixo_limpa_tudo():
    parte = CaseParte(id="p4", case_id="c1", tipo="reu", nome="Z", cpf_cnpj="sem digitos")
    assert parte.cpf_cnpj_enc is None and parte.cpf_cnpj_hash is None
    assert parte.cpf_cnpj is None
    parte.cpf_cnpj = None
    assert parte.cpf_cnpj is None


def test_ciphertext_indecifravel_degrada_com_marcador_visivel():
    from app.models.client import PII_INDECIFRAVEL
    parte = CaseParte(id="p5", case_id="c1", tipo="reu", nome="W")
    parte.cpf_cnpj_enc = "gAAAAA-nao-e-um-token-valido"
    assert parte.cpf_cnpj == PII_INDECIFRAVEL


def test_expressao_sql_e_a_coluna_em_claro():
    """`clients.py:333` e `search.py:167` filtram por `CaseParte.cpf_cnpj` em
    SQL; até migrarem para o hash, a expressão precisa continuar compilando
    para a coluna física `cpf_cnpj`."""
    from sqlalchemy import select
    assert "case_partes.cpf_cnpj" in str(select(CaseParte.cpf_cnpj))
    col = CaseParte.cpf_cnpj.expression
    assert (col.table.name, col.name) == ("case_partes", "cpf_cnpj")
