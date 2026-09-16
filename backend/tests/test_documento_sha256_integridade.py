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


def test_upload_calcula_hash_no_pipeline_streaming_canonico():
    """O router não materializa bytes; o digest nasce no stream e é persistido.

    A prova de integridade continua derivada exatamente dos bytes recebidos, mas
    agora em SHA-256 incremental no pipeline canônico, com memória limitada por
    chunk. O router só delega a ingestão autorizada.
    """
    import inspect

    from app.routers import documents as router_documents
    from app.services import document_persistence_service, document_upload_stream

    fonte_router = inspect.getsource(router_documents.upload)
    fonte_stream = inspect.getsource(document_upload_stream.receber_em_staging)
    fonte_persistencia = inspect.getsource(
        document_persistence_service.persistir_documento_local
    )

    assert "ingerir_documento_local(" in fonte_router
    assert "await file.read()" not in fonte_router
    assert "hashlib.sha256()" in fonte_stream
    assert "digest.update(chunk)" in fonte_stream
    assert "sha256=ingestao.sha256" in fonte_persistencia


def test_hash_muda_quando_o_conteudo_muda():
    """Guarda contra hash constante: um valor fixo passaria nos dois acima."""
    a = hashlib.sha256(b"peticao inicial v1").hexdigest()
    b = hashlib.sha256(b"peticao inicial v2").hexdigest()
    assert a != b and len(a) == 64


def test_migration_149_e_aditiva_e_reversivel():
    """Coluna nova em tabela com dado real: aditiva, com downgrade funcional.

    Renumerada de 147 para 149 ao mesclar a main (colisão com
    147_pendencia_impacto_providencia, mesclada primeiro).
    """
    from pathlib import Path

    fonte = Path(__file__).resolve().parents[1] / (
        "alembic/versions/149_documents_sha256_integridade.py"
    )
    texto = fonte.read_text(encoding="utf-8")
    assert "op.add_column" in texto and "nullable=True" in texto
    assert "def downgrade" in texto and "op.drop_column" in texto
    for destrutivo in ("drop_table", "DELETE FROM", "TRUNCATE"):
        assert destrutivo not in texto, f"migration aditiva não pode ter {destrutivo}"


# ── Achado 30 (revisão do Codex sobre o head 4490d492) ───────────────────────
# A correção acima cobria só `POST /documents/upload`. Os demais caminhos que
# criam Document gravavam NULL — e como a coluna é nullable para o acervo
# legado, o NULL de um upload NOVO fica indistinguível de documento anterior à
# migration 147. A prova de integridade faltava justamente onde mais importa:
# documento enviado PELO CLIENTE e documento baixado do TRIBUNAL.
#
# Em três dos quatro caminhos o digest JÁ EXISTIA e era descartado:
#   entrada_universal          -> `sha256_bytes(raw)`, calculado logo abaixo
#                                 para o DocumentIntakeItem, sobre os mesmos bytes
#   document_persistence       -> `ingestao.sha256`, propriedade já exposta
#   cópia isolada da Entrada   -> `documento.sha256` do original (copy2 dos
#                                 mesmos bytes)
# Só o mapper do MNI precisava calcular de fato.

CAMINHOS_QUE_CRIAM_DOCUMENT = (
    # O upload local delega ao persistence service, mas /drive/upload ainda
    # constrói Document diretamente e também precisa persistir o digest.
    ("app/routers/documents.py", "upload remoto pelo Google Drive"),
    ("app/routers/portal_documentos.py", "upload do cliente pelo Portal"),
    ("app/routers/entrada_universal.py", "Entrada Universal (lote e cópia isolada)"),
    ("app/services/document_persistence_service.py", "persistência local/Drive"),
    (
        "app/services/processo_eletronico_document_mapper.py",
        "documento baixado do tribunal (MNI)",
    ),
)


def test_todo_caminho_que_cria_documento_grava_o_hash():
    """Cada construtor de Document precisa preencher `sha256`.

    Teste por arquivo, não por chamada: o que se quer travar é que nenhum
    caminho NOVO de criação apareça sem o digest. Se um arquivo desta lista
    passar a criar Document sem `sha256=`, ele reprova aqui.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    faltando = []
    for caminho, descricao in CAMINHOS_QUE_CRIAM_DOCUMENT:
        texto = (raiz / caminho).read_text(encoding="utf-8")
        if "sha256=" not in texto:
            faltando.append(f"{caminho} ({descricao})")
    assert not faltando, (
        "caminho cria Document sem prova de integridade:\n  "
        + "\n  ".join(faltando)
    )


def test_upload_drive_deriva_hash_dos_bytes_enviados():
    import inspect

    from app.routers import documents

    fonte = inspect.getsource(documents.upload_para_drive)
    assert "sha256=hashlib.sha256(content).hexdigest()" in fonte


def test_upload_do_portal_deriva_o_hash_do_conteudo_recebido():
    """O caminho do cliente externo, que era o mais grave dos que faltavam."""
    import inspect

    from app.routers import portal_documentos

    fonte = inspect.getsource(portal_documentos)
    assert "hashlib.sha256(conteudo).hexdigest()" in fonte, (
        "o upload do Portal precisa derivar o hash dos bytes recebidos"
    )


def test_entrada_universal_reusa_o_digest_ja_calculado():
    """Mesma fonte para o Document e para o DocumentIntakeItem.

    Se os dois calculassem por caminhos diferentes, poderiam divergir — e duas
    linhas do mesmo arquivo com hashes diferentes é pior que uma sem hash.
    """
    import inspect

    from app.routers import entrada_universal

    fonte = inspect.getsource(entrada_universal)
    assert fonte.count("sha256=sha256_bytes(raw)") >= 2, (
        "Document e DocumentIntakeItem devem sair do mesmo sha256_bytes(raw)"
    )
