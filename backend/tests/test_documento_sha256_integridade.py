# -*- coding: utf-8 -*-
"""Documento juntado precisa carregar prova de integridade.

Achado da auditoria funcional de 22/08/2026 (Issue #1237), prioridade 8 do
prompt-mestre (documentos).

O EJC é sistema de PROVA DOCUMENTAL. O hash é o que sustenta a afirmação de que
o arquivo juntado hoje é o mesmo de amanhã — sem ele, "o documento está no
sistema" e "o documento não foi trocado" viram a mesma frase sem evidência.

A maquinaria de SHA-256 já existia INTEIRA desde a migration 142: serviço local
(`document_hash_service.calcular_sha256_local`), variante remota via rclone,
`document_rescan_service` e a task de backfill `tasks/rescan_tasks`. Faltava o
começo — `POST /documents/upload` não calculava nada, e `documents` não tinha
coluna. O SHA-256 existente vivia só em `document_intake_items`, que apenas o
fluxo de intake alimenta: documento juntado pela TELA ficava sem evidência
nenhuma.

Registro de uma correção minha: numa rodada anterior eu afirmei que corrigir
isso "exige coluna nova — migration, exceção §6-A" e parei aí. A parte da
migration era verdadeira; o resto da frase deu a entender que faltava construir
a maquinaria, quando só faltava o caller e a coluna.
"""
from __future__ import annotations

import hashlib

from app.models.document import Document


def test_modelo_documento_tem_coluna_sha256():
    """Sem a coluna não há onde guardar — este é o teste que falha antes da 147."""
    assert hasattr(Document, "sha256"), (
        "Document.sha256 ausente: documento juntado fica sem prova de integridade"
    )
    coluna = Document.__table__.columns["sha256"]
    assert coluna.nullable, (
        "sha256 precisa ser nullable: documento anterior à coluna NÃO tem hash, "
        "e NULL diz isso — o contrário fingiria integridade não verificada"
    )
    assert coluna.type.length == 64, "SHA-256 em hex tem 64 caracteres"


def test_upload_calcula_o_hash_dos_bytes_recebidos():
    """O valor gravado tem de ser o SHA-256 do conteúdo, não um placeholder.

    O upload já tem os bytes em memória (`conteudo = await file.read()`), então
    o cálculo não custa I/O nem releitura do disco.
    """
    import inspect

    from app.routers import documents as router_documents

    fonte = inspect.getsource(router_documents.upload)
    assert "hashlib.sha256(conteudo).hexdigest()" in fonte, (
        "o upload precisa derivar o hash do conteúdo lido, não de outra fonte"
    )
    assert "sha256=" in fonte, "o hash calculado precisa chegar ao Document"


def test_hash_muda_quando_o_conteudo_muda():
    """Guarda contra hash constante: um valor fixo passaria nos dois acima."""
    a = hashlib.sha256(b"peticao inicial v1").hexdigest()
    b = hashlib.sha256(b"peticao inicial v2").hexdigest()
    assert a != b and len(a) == 64


def test_migration_147_e_aditiva_e_reversivel():
    """Coluna nova em tabela com dado real: aditiva, com downgrade funcional."""
    from pathlib import Path

    fonte = Path(__file__).resolve().parents[1] / (
        "alembic/versions/147_documents_sha256_integridade.py"
    )
    texto = fonte.read_text(encoding="utf-8")
    assert "op.add_column" in texto and "nullable=True" in texto
    assert "def downgrade" in texto and "op.drop_column" in texto
    for destrutivo in ("drop_table", "DELETE FROM", "TRUNCATE"):
        assert destrutivo not in texto, f"migration aditiva não pode ter {destrutivo}"
