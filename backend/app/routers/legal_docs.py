"""Fachada de compatibilidade do módulo de peças jurídicas — Parte 10.

A implementação histórica foi preservada integralmente em
``legal_docs_legacy.py``. Esta fachada substitui apenas duas rotas:

* PATCH /legal-docs/{id}: conserva a lógica anterior, corrigindo a mensagem que
  atribuía indevidamente o fluxo interno ao Provimento OAB 205/2021;
* PATCH /legal-docs/{id}/aprovar: encaminha consumidores antigos ao novo ato
  único de conferência e assinatura, sem exigir uma etapa separada de revisão.

Todas as demais rotas, símbolos públicos e helpers privados continuam disponíveis
com os mesmos nomes, evitando regressão em imports internos e testes existentes.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.routers import legal_docs_legacy as _legacy

# Reexporta inclusive helpers privados usados por outros módulos do EJC. O router
# é deliberadamente excluído porque esta fachada controla a ordem e elimina as
# rotas duplicadas antes de montar o conjunto legado.
for _nome in dir(_legacy):
    if _nome != "router" and not _nome.startswith("__"):
        globals()[_nome] = getattr(_legacy, _nome)

router = APIRouter(tags=["Peças Jurídicas"])


@router.patch("/legal-docs/{doc_id}", response_model=_legacy.LegalDocDetail)
async def atualizar_compativel(
    doc_id: str,
    payload: _legacy.LegalDocUpdate,
    background: BackgroundTasks,
    db: _legacy.AsyncSession = Depends(_legacy.get_db),
    cu: _legacy.User = Depends(_legacy.get_current_user),
):
    """Executa a atualização histórica sem expor fundamento normativo incorreto."""
    try:
        return await _legacy.atualizar(doc_id, payload, background, db, cu)
    except HTTPException as exc:
        detalhe = exc.detail
        if isinstance(detalhe, str) and "Provimento OAB 205/2021" in detalhe:
            detalhe = detalhe.replace(". Provimento OAB 205/2021.", ".")
            detalhe = detalhe.replace(
                "exige revisao humana registrada antes de aprovar",
                "exige conferencia afirmativa do advogado antes do uso oficial",
            )
            detalhe = detalhe.replace(
                "(use POST /legal-docs/{id}/revisar)",
                "(use PATCH /legal-docs/{id}/conferir-assinar)",
            )
        raise HTTPException(
            status_code=exc.status_code,
            detail=detalhe,
            headers=exc.headers,
        ) from exc


@router.patch("/legal-docs/{doc_id}/aprovar", response_model=_legacy.LegalDocDetail)
async def aprovar_compativel(
    doc_id: str,
    payload: _legacy.LegalDocAprovacao,
    background: BackgroundTasks,
    db: _legacy.AsyncSession = Depends(_legacy.get_db),
    cu: _legacy.User = Depends(_legacy.get_current_user),
):
    """Alias de transição: aprovação antiga passa pelo ato único da Parte 10."""
    from app.routers.validador_juridico import (
        ConferenciaAssinaturaRequest,
        conferir_e_assinar,
    )

    return await conferir_e_assinar(
        doc_id,
        ConferenciaAssinaturaRequest(
            confirmado=True,
            observacoes=(payload.observacoes or None),
        ),
        background,
        db,
        cu,
    )


# Monta todas as rotas históricas, exceto as duas substituídas acima. Adicionar os
# objetos APIRoute diretamente preserva path, dependencies, response_model,
# operation_id e callbacks originais, sem duplicação no OpenAPI.
_ROTAS_SUBSTITUIDAS = {
    ("/legal-docs/{doc_id}", "PATCH"),
    ("/legal-docs/{doc_id}/aprovar", "PATCH"),
}
for _rota in _legacy.router.routes:
    _metodos = set(getattr(_rota, "methods", set()) or set())
    if any((_rota.path, _metodo) in _ROTAS_SUBSTITUIDAS for _metodo in _metodos):
        continue
    router.routes.append(_rota)
