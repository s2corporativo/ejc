"""Onda 3 §4.1 — registro EXPLÍCITO dos routers antes montados por side effect.

Cinco grupos de rotas (precedentes, advogado_estilo, rag_governance,
datajud_intelligence, ia_provider_metrics) eram anexados aos routers-pais dentro
de app/services/event_subscribers.py, datajud_cognitive_patch.py e
ai/provider_metrics_runtime.py — o que tornava a superfície da API dependente da
ORDEM de import. Agora são registrados em app/main.py como os demais.

Este arquivo trava a PARIDADE: o snapshot em tests/snapshots/ foi capturado com
o código ANTERIOR à mudança; qualquer divergência de path, método ou dependência
de auth falha aqui.
"""
from __future__ import annotations

import json
import os

import pytest


def _extrair_rotas(app) -> list[dict]:
    def deps_flat(dep, out, depth=0):
        if dep is None or depth > 6:
            return
        for d in getattr(dep, "dependencies", []) or []:
            c = getattr(d, "call", None)
            if c is not None:
                out.add(getattr(c, "__name__", type(c).__name__))
            deps_flat(d, out, depth + 1)

    rotas = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        nomes: set[str] = set()
        deps_flat(getattr(r, "dependant", None), nomes)
        for metodo in sorted(getattr(r, "methods", None) or []):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            rotas.append({
                "path": path,
                "method": metodo,
                "auth_deps": sorted(nomes),
                "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
            })
    rotas.sort(key=lambda x: (x["path"], x["method"]))
    return rotas


# Adições INTENCIONAIS posteriores ao snapshot. O registro explícito (§4.1) não
# pode criar nem remover rota; qualquer outra novidade falha o teste.
ADICOES_INTENCIONAIS = {
    ("/api/architecture/uso-rotas", "GET"),
    ("/api/sala-juridica/{session_id}/conversao/preview", "GET"),
    ("/api/diagnostico/integridade", "GET"),
    # PR #547: decisão explícita de publicar/despublicar arquivo no Data Room.
    ("/api/data-rooms/{room_id}/arquivos/{arquivo_id}/publicacao", "PATCH"),
    # PR #622 (Bloco 2): conferência e assinatura da peça em um ato só, no lugar
    # da cadeia validar → marcar HITL → aprovar. Não substitui os endpoints
    # antigos, que o frontend ainda usa.
    ("/api/legal-docs/{doc_id}/conferir-e-assinar", "POST"),
    # PR #622 (Bloco 2): PDF de LEITURA da minuta, sem gate de protocolo — o
    # advogado precisa ler antes de assinar. O /pdf de protocolo segue intacto.
    ("/api/legal-docs/{doc_id}/pdf-minuta", "GET"),
    # Bloco 3 (entrada única, docs/DESENHO_BLOCO3_TELAS.md §4): orquestração do
    # que já existe — relato/documentos → proposta conferível → caso em uma
    # transação. Piso advogado + rate limit; rascunho vive no batch (sem tabela
    # nova).
    ("/api/entrada/analisar", "POST"),
    ("/api/entrada/{rascunho_id}/criar-caso", "POST"),
}

# Remoções INTENCIONAIS posteriores ao snapshot. Rota que some sem estar aqui
# continua reprovando — sumiço silencioso de endpoint é o defeito que esta trava
# existe para pegar. Cada entrada precisa da decisão que a justifica.
REMOCOES_INTENCIONAIS: set[tuple[str, str]] = {
    # Bloco 4 do plano de lançamento. Decisão do ESCRITÓRIO, não achado técnico:
    # "dossiê de pressão" e "análise de magistrado" num sistema de advocacia são
    # risco reputacional e disciplinar indefensável se expostos numa perícia ou
    # numa representação — independentemente do que o código faça. Nenhuma tela
    # do sistema chamava os dois. Não reintroduzir sem decisão escrita do titular.
    ("/api/diplomacia-v3/dossie-pressao", "POST"),
    ("/api/diplomacia-v3/analisar-magistrado", "POST"),
}

# Fatia 652-A: correção do prefixo /v1 duplicado (P0 da auditoria 2026-07).
# Oito routers declaravam prefixo próprio "/v1/..." e o main.py já os monta sob
# API = "/api" — o path interno virava /api/v1/x. Como o
# APIVersionCompatibilityMiddleware reescreve /api/v1/x → /api/x, o caminho
# público canônico caía em rota inexistente (404) e o endpoint só respondia no
# defeituoso /api/v1/v1/x. A correção remove o /v1 do router: RELOCAÇÃO 1:1 de
# path interno, sem criar, remover ou renomear endpoint. Para o cliente o
# caminho público /api/v1/... não muda — passa a funcionar de fato.
_ROTAS_V1_REALOCADAS: tuple[tuple[str, str], ...] = (
    ("/api/v1/cases/{case_id}/kanban", "PATCH"),
    ("/api/v1/clients/{client_id}/pending-items", "GET"),
    ("/api/v1/clients/{client_id}/pending-items", "POST"),
    ("/api/v1/clients/{client_id}/pending-items/{item_id}", "DELETE"),
    ("/api/v1/clients/{client_id}/pending-items/{item_id}", "PATCH"),
    ("/api/v1/datajud/cases/{case_id}/sync", "POST"),
    ("/api/v1/datajud/cases/{case_id}/sync-prazos", "POST"),
    ("/api/v1/datajud/process/{numero_cnj}", "GET"),
    ("/api/v1/despesas", "GET"),
    ("/api/v1/despesas", "POST"),
    ("/api/v1/despesas/export/csv", "GET"),
    ("/api/v1/despesas/resumo", "GET"),
    ("/api/v1/despesas/{despesa_id}", "DELETE"),
    ("/api/v1/despesas/{despesa_id}", "PATCH"),
    ("/api/v1/kanban-columns", "GET"),
    ("/api/v1/office-contracts", "GET"),
    ("/api/v1/office-contracts", "POST"),
    ("/api/v1/office-contracts/expiring", "GET"),
    ("/api/v1/office-contracts/{contract_id}", "DELETE"),
    ("/api/v1/office-contracts/{contract_id}", "GET"),
    ("/api/v1/office-contracts/{contract_id}", "PATCH"),
    ("/api/v1/partner-withdrawals", "GET"),
    ("/api/v1/partner-withdrawals", "POST"),
    ("/api/v1/partner-withdrawals/{withdrawal_id}", "DELETE"),
    ("/api/v1/partner-withdrawals/{withdrawal_id}/approve", "PATCH"),
    ("/api/v1/partner-withdrawals/{withdrawal_id}/pay", "PATCH"),
    ("/api/v1/partner-withdrawals/{withdrawal_id}/reject", "PATCH"),
    ("/api/v1/regulatorio/digest-semanal", "GET"),
    ("/api/v1/whatsapp/chats", "GET"),
    ("/api/v1/whatsapp/messages", "POST"),
    ("/api/v1/whatsapp/qrcode", "GET"),
    ("/api/v1/whatsapp/send", "POST"),
    ("/api/v1/whatsapp/status", "GET"),
)

# {(path_interno_antigo, método): (path_interno_novo, método)} — o novo é o
# antigo sem o segmento /v1, mecanicamente.
RELOCACOES_PREFIXO_V1: dict[tuple[str, str], tuple[str, str]] = {
    (antigo, metodo): (antigo.replace("/api/v1/", "/api/", 1), metodo)
    for antigo, metodo in _ROTAS_V1_REALOCADAS
}

# O par entra nas duas listas: o path antigo sai da superfície (e voltar é
# regressão — a assertiva de "ressuscitadas" cobre isso) e o novo entra.
REMOCOES_INTENCIONAIS |= set(RELOCACOES_PREFIXO_V1)
ADICOES_INTENCIONAIS |= set(RELOCACOES_PREFIXO_V1.values())


def _baseline() -> list[dict]:
    caminho = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "snapshots",
        "openapi_rotas_baseline.json",
    )
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


def test_paridade_openapi_com_snapshot_anterior():
    """Path + método + dependências de auth idênticos ao estado pré-mudança."""
    from app.main import app

    atual = _extrair_rotas(app)
    base = _baseline()
    chaves_base = {(r["path"], r["method"]): r for r in base}
    chaves_atual = {(r["path"], r["method"]): r for r in atual}

    sumiram = sorted(
        set(chaves_base) - set(chaves_atual) - REMOCOES_INTENCIONAIS
    )
    surgiram = sorted(
        set(chaves_atual) - set(chaves_base) - ADICOES_INTENCIONAIS
    )
    assert not sumiram, f"{len(sumiram)} rota(s) DESAPARECERAM: {sumiram[:10]}"
    assert not surgiram, f"{len(surgiram)} rota(s) NOVAS não previstas: {surgiram[:10]}"

    ressuscitadas = sorted(REMOCOES_INTENCIONAIS & set(chaves_atual))
    assert not ressuscitadas, (
        f"rota(s) removida(s) por decisão do escritório voltaram: {ressuscitadas}"
    )

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
    ]
    assert not divergentes, f"dependências de auth alteradas: {divergentes[:5]}"
    assert len(base) == 826
    assert len(atual) == (
        len(base) + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)
    )


def test_relocacao_do_prefixo_v1_preserva_auth():
    """Fatia 652-A: tirar o /v1 do router não pode afrouxar RBAC de nenhuma rota.

    `despesas` e `office-contracts` dependem de `_req_fin` no próprio router e
    `regulatorio` de `get_current_user` — dependências declaradas no
    `APIRouter(...)`, exatamente onde o prefixo foi editado. Compara o conjunto
    de dependências de auth do path ANTIGO no snapshot com o do path NOVO no app.
    """
    from app.main import app

    base = {(r["path"], r["method"]): r for r in _baseline()}
    atual = {(r["path"], r["method"]): r for r in _extrair_rotas(app)}

    ausentes = [novo for novo in RELOCACOES_PREFIXO_V1.values() if novo not in atual]
    assert not ausentes, f"rota realocada não existe no app: {ausentes}"

    divergentes = [
        (antigo[0], novo[0], base[antigo]["auth_deps"], atual[novo]["auth_deps"])
        for antigo, novo in RELOCACOES_PREFIXO_V1.items()
        if antigo in base and base[antigo]["auth_deps"] != atual[novo]["auth_deps"]
    ]
    assert not divergentes, (
        "a remoção do prefixo /v1 alterou as dependências de auth: "
        f"{divergentes[:5]}"
    )


@pytest.mark.parametrize(
    "caminho,metodo",
    [
        ("/api/jurisprudencia-externa/precedentes/buscar", "POST"),
        ("/api/pecas/advogado-estilo/me", "GET"),
        ("/api/rag/governanca/saude", "GET"),
        ("/api/casos/{case_id}/andamentos/inteligencia", "GET"),
        ("/api/ia-governanca/provedores", "GET"),
    ],
)
def test_rotas_antes_dinamicas_seguem_montadas(caminho, metodo):
    """Uma rota-testemunha de cada um dos cinco grupos."""
    from app.main import app

    montadas = {
        (getattr(r, "path", ""), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or [])
    }
    assert (caminho, metodo) in montadas


def test_modulos_de_servico_nao_montam_mais_rotas():
    """Regressão: nenhum dos três módulos volta a anexar router por side effect."""
    import inspect

    from app.services import event_subscribers
    from app.services import datajud_cognitive_patch
    from app.services.ai import provider_metrics_runtime

    for modulo in (
        event_subscribers,
        datajud_cognitive_patch,
        provider_metrics_runtime,
    ):
        fonte = inspect.getsource(modulo)
        assert "include_router" not in fonte, (
            f"{modulo.__name__} voltou a montar rota por side effect — "
            "registre o router explicitamente em app/main.py"
        )
        assert ".router.routes.append(" not in fonte, (
            f"{modulo.__name__} voltou a anexar rotas diretamente em outro router"
        )


def test_registro_independe_da_ordem_de_import():
    """Importar os módulos de serviço ANTES do app não altera a superfície."""
    from app.services import event_subscribers  # noqa: F401
    from app.services.ai import provider_metrics_runtime  # noqa: F401
    from app.main import app

    assert len(_extrair_rotas(app)) == (
        826 + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)
    )


def test_efeitos_colaterais_nao_de_rota_preservados():
    """A remoção tocou APENAS a montagem de rota: subscribers e patches seguem."""
    import inspect

    from app.services import datajud_cognitive_patch, event_subscribers
    from app.services.ai import provider_metrics_runtime

    fonte_ev = inspect.getsource(event_subscribers)
    assert "_patch_documents_background_analysis()" in fonte_ev
    assert "_install_ai_core_hardening()" in fonte_ev
    assert "_install_datajud_cognitive_feed()" in fonte_ev
    assert "@on(" in fonte_ev

    fonte_dj = inspect.getsource(datajud_cognitive_patch)
    assert "_instalar_wrappers()" in fonte_dj
    assert "_registrar_job()" in fonte_dj
    assert "_registrar_categoria_restrita()" in fonte_dj

    fonte_pm = inspect.getsource(provider_metrics_runtime)
    assert "_instalar_instrumentacao(gateway)" in fonte_pm
