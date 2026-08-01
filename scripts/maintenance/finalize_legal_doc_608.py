#!/usr/bin/env python3
"""Aplica de forma idempotente o fechamento do fluxo de peças do PR #608.

O script é transitório: após executar, remove de sua própria árvore todos os
mecanismos operacionais usados para a materialização. Não faz deploy, não
acessa produção e não altera dados.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content.rstrip() + "\n", encoding="utf-8")


def async_function_bounds(source: str, name: str) -> tuple[int, int]:
    marker = f"async def {name}("
    start = source.index(marker)
    end = source.find("\n\n@router.", start + len(marker))
    return start, len(source) if end < 0 else end


def patch_ai_hitl() -> None:
    path = "backend/app/routers/ai.py"
    source = read(path)
    marker = 'legal_doc_id = getattr(log, "legal_doc_id", None)'
    if marker not in source:
        old = '    if req.status in ("revisado", "aplicado") and log.legal_doc_id:\n'
        new = (
            '    legal_doc_id = getattr(log, "legal_doc_id", None)\n'
            '    if req.status in ("revisado", "aplicado") and legal_doc_id:\n'
        )
        if source.count(old) != 1:
            raise RuntimeError(
                f"ai.py: âncora HITL inesperada; ocorrências={source.count(old)}"
            )
        source = source.replace(old, new, 1)
        start, end = async_function_bounds(source, "atualizar_hitl")
        block = source[start:end]
        query_old = "LegalDoc.id == log.legal_doc_id"
        if block.count(query_old) != 1:
            raise RuntimeError("ai.py: consulta legal_doc_id inesperada")
        block = block.replace(query_old, "LegalDoc.id == legal_doc_id", 1)
        source = source[:start] + block + source[end:]
    write(path, source)


def patch_orchestrator_validation() -> None:
    path = "backend/app/services/legal_case_orchestrator.py"
    source = read(path)
    old_import = "from sqlalchemy import func, or_, select"
    new_import = "from sqlalchemy import and_, func, or_, select"
    if new_import not in source:
        if source.count(old_import) != 1:
            raise RuntimeError("orquestrador: import SQLAlchemy inesperado")
        source = source.replace(old_import, new_import, 1)

    if "_VALIDACAO_TIPO_FILTRO" in source:
        start = source.index('    # (7) CR-15: "Citações verificadas"')
        end = source.index("    snaps_conteudo", start)
        replacement = '''    # (7) "Citações verificadas" usa o mesmo contrato estrutural do
    # fluxo de peças: FK LegalDoc↔AILog, flag corrente e SHA-256 exato.
    n_validacoes = 0
    if pecas:
        import hashlib

        from app.models.ai_log import AILog

        hashes_por_peca = {
            d.id: hashlib.sha256((d.conteudo or "").encode("utf-8")).hexdigest()
            for d in pecas
        }
        pares_correntes = or_(*[
            and_(
                AILog.legal_doc_id == doc_id,
                AILog.legal_doc_content_hash == content_hash,
            )
            for doc_id, content_hash in hashes_por_peca.items()
        ])
        n_validacoes = (await db.execute(
            select(func.count()).select_from(AILog).where(
                AILog.legal_doc_id.in_(list(hashes_por_peca)),
                AILog.legal_doc_validation_current.is_(True),
                pares_correntes,
            )
        )).scalar() or 0

'''
        source = source[:start] + replacement + source[end:]

    if "_VALIDACAO_TIPO_FILTRO" in source:
        raise RuntimeError("orquestrador: filtro textual legado permaneceu")
    write(path, source)


def patch_legal_docs() -> None:
    path = "backend/app/routers/legal_docs.py"
    source = read(path)

    if "campos_imutaveis_protocolados" not in source:
        old = '''    # Peça protocolada é registro imutável. Uma nova redação deve nascer como
    # nova peça/versão, nunca sobrescrever a prova do que foi protocolado.
    if conteudo_alterado and status_atual == "protocolada":
        raise HTTPException(
            status_code=422,
            detail=(
                "Peça protocolada é imutável. Crie uma nova peça ou versão para "
                "qualquer alteração posterior ao protocolo."
            ),
        )'''
        new = '''    # Peça protocolada é registro imutável. O endpoint genérico não pode
    # alterar redação, título, tipo, origem ou regredir o status. Retificações
    # devem nascer como nova peça/versão, preservando a prova protocolada.
    campos_imutaveis_protocolados = {
        "titulo", "conteudo", "tipo_peca", "status", "ai_generated"
    }
    if (
        status_atual == "protocolada"
        and campos_imutaveis_protocolados.intersection(mudancas)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Peça protocolada é imutável. Crie uma nova peça ou versão para "
                "qualquer alteração posterior ao protocolo."
            ),
        )'''
        start, end = async_function_bounds(source, "atualizar")
        block = source[start:end]
        if block.count(old) != 1:
            raise RuntimeError(
                f"legal_docs: contrato de imutabilidade inesperado; "
                f"ocorrências={block.count(old)}"
            )
        source = source[:start] + block.replace(old, new, 1) + source[end:]

    start, end = async_function_bounds(source, "_gates_exportacao_protocolo")
    gate = source[start:end]
    if "d.ai_generated and not d.human_reviewed" not in gate:
        anchor = "    status_atual = _status_value(d.status)\n"
        guard = '''    if d.ai_generated and not d.human_reviewed:
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF de protocolo bloqueado: peça gerada por IA exige "
                "revisão humana registrada antes da exportação final."
            ),
        )
'''
        if gate.count(anchor) != 1:
            raise RuntimeError(
                f"legal_docs: âncora PDF HITL inesperada; ocorrências={gate.count(anchor)}"
            )
        gate = gate.replace(anchor, anchor + guard, 1)
        source = source[:start] + gate + source[end:]

    stale = '''            # Este endpoint exporta em QUALQUER status (rascunho incluso): a marca
            # de origem-IA precisa viajar com o PDF de impressão do rascunho.'''
    fixed = '''            # Os gates acima garantem versão protocolável revisada. Mantemos o
            # parâmetro defensivo para que qualquer drift futuro siga marcado.'''
    if stale in source:
        source = source.replace(stale, fixed, 1)

    write(path, source)


def patch_contract_tests() -> None:
    path = "backend/tests/test_legal_doc_flow_contract.py"
    source = read(path)
    if "def test_mutacoes_serializadas_e_pdf_falha_fechado_sem_hitl" not in source:
        source += '''


def test_mutacoes_serializadas_e_pdf_falha_fechado_sem_hitl():
    src = _source("app/routers/legal_docs.py")
    for function_name in ("atualizar", "revisar", "registrar_protocolo"):
        bloco = _function_source(src, function_name)
        assert ".with_for_update()" in bloco

    gate = _function_source(src, "_gates_exportacao_protocolo")
    assert "d.ai_generated and not d.human_reviewed" in gate
    assert "revisão humana registrada" in gate

    atualizar = _function_source(src, "atualizar")
    assert "campos_imutaveis_protocolados" in atualizar
    assert '"status"' in atualizar


def test_orquestrador_nao_depende_de_filtro_textual_legado():
    src = _source("app/services/legal_case_orchestrator.py")
    assert "_VALIDACAO_TIPO_FILTRO" not in src
    assert "AILog.legal_doc_id" in src
    assert "AILog.legal_doc_content_hash" in src
'''
    write(path, source)


def patch_e2e() -> None:
    path = "qa/homologacao/run_fluxo_legal_doc_e2e.py"
    source = read(path)
    if 'json={"status": "em_revisao"}' not in source:
        anchor = '''        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {422},
            json={"conteudo": conteudo + "\\nTentativa proibida após protocolo."},
        )'''
        replacement = '''        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {422},
            json={"status": "em_revisao"},
        )
        request(
            client,
            "PATCH",
            f"/api/legal-docs/{doc_id}",
            {422},
            json={"conteudo": conteudo + "\\nTentativa proibida após protocolo."},
        )'''
        if source.count(anchor) != 1:
            raise RuntimeError(
                f"E2E: âncora de imutabilidade inesperada; ocorrências={source.count(anchor)}"
            )
        source = source.replace(anchor, replacement, 1)
    write(path, source)


def remove_transient_files() -> None:
    transient = (
        ".github/workflows/_patch-legal-doc-mutation-locks.yml",
        ".github/workflows/_finalize-legal-doc-hardening.yml",
        ".github/workflows/temporary-legal-doc-finalizer.yml",
        ".github/workflows/_ops-finalize-legal-doc-608-v3.yml",
        "scripts/maintenance/.trigger-final-legal-doc-hardening",
        "scripts/maintenance/.trigger-final-legal-doc-hardening-v2",
        "scripts/maintenance/.trigger-finalize-legal-doc-608-v3",
        "scripts/maintenance/finalize_legal_doc_608.py",
    )
    for relative in transient:
        path = ROOT / relative
        if path.exists():
            path.unlink()


def main() -> None:
    patch_ai_hitl()
    patch_orchestrator_validation()
    patch_legal_docs()
    patch_contract_tests()
    patch_e2e()
    remove_transient_files()


if __name__ == "__main__":
    main()
