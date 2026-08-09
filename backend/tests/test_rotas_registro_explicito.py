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
    # DPT Empresarial 360 — Onda 2: agregador read-only da carteira empresarial.
    ("/api/dpt360/dashboard", "GET"),
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
    # Issue #762 (Fase A): integração de processo eletrônico via MNI 2.2.2,
    # somente leitura (TJMG). Sincronização assíncrona (Celery) + cofre de
    # credenciais dedicado — nunca ecoa segredo, todo uso audita.
    ("/api/processo-eletronico/sincronizar", "POST"),
    ("/api/processo-eletronico/status/{case_id}", "GET"),
    ("/api/processo-eletronico/credenciais", "GET"),
    ("/api/processo-eletronico/credenciais", "POST"),
    ("/api/processo-eletronico/credenciais/{credencial_id}/testar", "POST"),
}

# Remoções INTENCIONAIS posteriores ao snapshot. Rota que some sem estar aqui
# continua reprovando — sumiço silencioso de endpoint é o defeito que esta trava
# existe para pegar. Cada entrada precisa da decisão que a justifica.
REMOCOES_INTENCIONAIS = {
    # Bloco 4 do plano de lançamento. Decisão do ESCRITÓRIO, não achado técnico:
    # "dossiê de pressão" e "análise de magistrado" num sistema de advocacia são
    # risco reputacional e disciplinar indefensável se expostos numa perícia ou
    # numa representação — independentemente do que o código faça. Nenhuma tela
    # do sistema chamava os dois. Não reintroduzir sem decisão escrita do titular.
    ("/api/diplomacia-v3/dossie-pressao", "POST"),
    ("/api/diplomacia-v3/analisar-magistrado", "POST"),
    # docs/PLANO_FUSAO_CASO_UNICO.md (F1a) — quatro endpoints de Casos sem
    # nenhum consumidor no frontend (grep confirmado antes da remoção), dois
    # deles duplicando outra rota já em uso: /resumo (contadores nunca lidos —
    # e continha o bug do prazos_pendentes sempre 0, corrigido junto),
    # /linha-do-tempo (superseded por /visual-law/casos/{id}/timeline, que o
    # frontend de fato chama), /assistente-estrategico (chamada de IA sem rate
    # limit nem piso de papel, duplicando o endpoint real em ai.py) e
    # /movimentos/{mov_id}/traduzir (o gatilho automático de
    # services/movimento_ia.py via event_subscribers continua intacto — só o
    # re-disparo manual sem UI foi removido).
    ("/api/cases/{case_id}/resumo", "GET"),
    ("/api/cases/{case_id}/linha-do-tempo", "GET"),
    ("/api/cases/{case_id}/assistente-estrategico", "POST"),
    ("/api/cases/{case_id}/movimentos/{mov_id}/traduzir", "POST"),
    # Jornada de 9 etapas (jornada_caso.py): endpoint sem nenhum consumidor —
    # a página React /casos/:id/jornada é um redirect puro para
    # /casos/:id?tab=resumo desde a Fase 1 do plano de simplificação e nunca
    # chamou esta rota. A jornada visível ao usuário é o orquestrador de 16
    # etapas (legal_case_orchestrator.py, /cases/{id}/orquestrador), intacto.
    ("/api/casos/{case_id}/jornada", "GET"),
    # Issue #716 revertida — /timeline e /operational-health (case_timeline.py)
    # eram fachadas de leitura sem nenhum consumidor (mesma varredura acima);
    # a saúde do caso segue exposta em Analytics via case_health.py, que
    # não foi tocado. Nunca chegaram a existir no snapshot baseline (eram
    # ADICOES_INTENCIONAIS), por isso não entram como remoção — apenas saem
    # da lista de adições abaixo.
}


def _baseline() -> list[dict]:
    caminho = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "snapshots",
        "openapi_rotas_baseline.json",
    )
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


# ── Onda 2: oito routers saíram de /api/v1/… para /api/… ─────────────────────
# Eles declaravam `prefix="/v1/..."` e eram montados com `prefix="/api"`,
# caindo em /api/v1/... — exatamente o endereço que o
# APIVersionCompatibilityMiddleware reescreve para /api/... ANTES do dispatch.
# Consequência: inalcançáveis pelo contrato público (/api/v1/despesas → 404) e
# alcançáveis só pelo acidente /api/v1/v1/despesas. Era a causa do "Financeiro:
# Despesas, Contratos e Sociedade hoje 404" da auditoria.
#
# Nenhum endpoint foi criado nem removido: cada par abaixo é a MESMA rota, no
# endereço correto. O par (removida em /api/v1/X, adicionada em /api/X) é
# gerado do próprio snapshot para não haver lista escrita à mão divergindo do
# fato.
_MOVIDAS_ONDA2 = tuple(
    (r["path"], r["method"])
    for r in _baseline()
    if r["path"].startswith("/api/v1/")
)
REMOCOES_INTENCIONAIS |= set(_MOVIDAS_ONDA2)
ADICOES_INTENCIONAIS |= {
    ("/api" + path[len("/api/v1"):], metodo) for path, metodo in _MOVIDAS_ONDA2
}


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


def test_movimentacao_onda2_preservou_as_dependencias_de_auth():
    """A rota mudou de endereço — o gate NÃO pode ter mudado junto.

    A trava de paridade compara `auth_deps` só das rotas que sobreviveram com o
    mesmo par (path, método). As 33 movidas contam como removida+adicionada e
    escapariam dessa comparação: um `dependencies=[...]` perdido no caminho
    passaria como "rota nova". Aqui a comparação é feita explicitamente, par a
    par, entre o endereço antigo e o novo.
    """
    from app.main import app

    atual = {(r["path"], r["method"]): r for r in _extrair_rotas(app)}
    divergentes = []
    for r in _baseline():
        antigo = r["path"]
        if not antigo.startswith("/api/v1/"):
            continue
        novo = "/api" + antigo[len("/api/v1") :]
        destino = atual.get((novo, r["method"]))
        assert destino is not None, f"{antigo} {r['method']} não reapareceu em {novo}"
        if destino["auth_deps"] != r["auth_deps"]:
            divergentes.append((antigo, novo, r["auth_deps"], destino["auth_deps"]))
    assert not divergentes, (
        "a mudança de prefixo alterou o gate de auth de "
        f"{len(divergentes)} rota(s): {divergentes[:3]}"
    )