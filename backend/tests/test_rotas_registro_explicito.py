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
    # PR #1378 — consolidação do Financeiro/Fiscal. Rotas novas deliberadas,
    # autenticadas e de leitura. O subledger respeita escopo/ownership do fee;
    # demonstrativo e pré-fechamento são restritos a gestão/financeiro no router.
    ("/api/fees/{fee_id}/pagamentos", "GET"),
    ("/api/financeiro/demonstrativo", "GET"),
    ("/api/financeiro/fechamento-inteligente", "GET"),
    # Issue #1272 (Classe B do plano-mestre): reabertura de caso ENCERRADO
    # restaurando o estágio de trabalho real, simétrica a /desarquivar (que já
    # existe para o outro estado terminal). O frontend usava PATCH cru com
    # status="aberto" fixo -- passa a chamar este endpoint dedicado.
    ("/api/cases/{case_id}/reabrir", "POST"),
    # Issue #1272 (V2-4.4 do plano-mestre): purga definitiva (hard delete) de
    # registro já soft-deleted, restrita a superadmin — antes não havia
    # caminho pela aplicação para atender pedido de eliminação LGPD (art. 16 e
    # art. 18, VI); DELETE e POST .../purgar respondiam 404.
    ("/api/trash/{entidade}/{registro_id}/purgar", "POST"),
    # Issue #1246 (frente 2 do plano de evolução): varredura REVERSA tese →
    # caso. O Banco de Teses só respondia caso → teses; esta é a rota que diz
    # em quais processos uma tese pode caber. Leitura, determinística (sem IA),
    # restrita à EQUIPE_JURIDICA e filtrada pela visibilidade de casos do
    # usuário — não cria vínculo nem expõe caso que ele já não pudesse abrir.
    ("/api/teses/{tese_id}/casos-candidatos", "GET"),
    # Issue #1246 (frente 1 do plano de evolução): impacto do radar regulatório
    # sobre o Banco de Teses — quais teses reler à luz do que saiu no Diário.
    # Leitura, determinística (sem IA), restrita à EQUIPE_JURIDICA. Os alertas
    # passam pelo `visible_alerts_query` canônico do Diário Oficial: a rota não
    # amplia a superfície de alerta que o usuário já enxergava.
    ("/api/teses/impacto-regulatorio", "GET"),
    # Saneamento 19/08/2026 (item 16): auditoria semântica da superfície real,
    # restrita a superadmin/admin/sócio; não expõe dados de caso/cliente.
    ("/api/architecture/semantic-audit", "GET"),
    # Saneamento 19/08/2026 (item 14): heartbeat técnico do DOU, advogado+,
    # sem keyword, conteúdo de publicação, PII ou segredo.
    ("/api/diario-oficial/status", "GET"),
    ("/api/sala-juridica/{session_id}/conversao/preview", "GET"),
    ("/api/diagnostico/integridade", "GET"),
    ("/api/data-rooms/{room_id}/arquivos/{arquivo_id}/publicacao", "PATCH"),
    ("/api/documents/{doc_id}/publicacao-portal", "PATCH"),
    ("/api/legal-docs/{doc_id}/conferir-e-assinar", "POST"),
    ("/api/legal-docs/{doc_id}/pdf-minuta", "GET"),
    ("/api/entrada/analisar", "POST"),
    ("/api/entrada/{rascunho_id}/criar-caso", "POST"),
    ("/api/processo-eletronico/sincronizar", "POST"),
    ("/api/processo-eletronico/status/{case_id}", "GET"),
    ("/api/processo-eletronico/credenciais", "GET"),
    ("/api/processo-eletronico/credenciais", "POST"),
    ("/api/processo-eletronico/credenciais/{credencial_id}/testar", "POST"),
    ("/api/integracoes/cnj/tpu/versao", "GET"),
    ("/api/integracoes/cnj/tpu/pesquisar", "GET"),
    ("/api/integracoes/tcu/acordaos", "GET"),
    ("/api/integracoes/ibge/municipios/{uf}", "GET"),
    ("/api/integracoes/ibge/canonicalizar", "GET"),
    ("/api/integracoes/dados-publicos/{fonte}/recursos", "GET"),
    ("/api/integracoes/pgfn/divida-ativa/recursos", "GET"),
    ("/api/integracoes/querido-diario/{codigo_ibge}", "GET"),
    ("/api/integracoes/ide-sisema/camadas", "GET"),
    ("/api/integracoes/ide-sisema/feicoes", "GET"),
    ("/api/jurimetria/interno/stats", "GET"),
    ("/api/jurimetria/interno/benchmarks", "GET"),
    ("/api/jurimetria/interno/analise-prospectiva", "GET"),
    ("/api/jurimetria/analise-prospectiva", "POST"),
    ("/api/jurimetria/cobertura-rag", "GET"),
    ("/api/jurimetria/cobertura-mg-jec", "GET"),
    ("/api/cases/{case_id}/documentos/candidatos", "GET"),
    ("/api/cases/{case_id}/documentos/{document_id}/vincular", "POST"),
    ("/api/dpt360/dashboard", "GET"),
    ("/api/dpt360/companies/{client_id}", "GET"),
    ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
    ("/api/dpt360/radar/today", "GET"),
    ("/api/dpt360/reports/executive/{client_id}", "GET"),
    ("/api/dpt360/intake/opportunities", "GET"),
    ("/api/dpt360/intake/opportunities", "POST"),
    ("/api/dpt360/actions", "POST"),
    ("/api/analytics/produtividade/export-event", "POST"),
    ("/api/dpt360/oportunidades/{batch_id}/ciclo-vida", "POST"),
    ("/api/signatures/{sig_id}/documento", "GET"),
    ("/api/intelligence/radar/legislativo", "GET"),
    ("/api/intelligence/analise-impacto", "POST"),
    ("/api/teses/motor/async", "POST"),
    ("/api/teses/motor/async/{task_id}", "GET"),
    ("/api/cases/{case_id}/partes/{parte_id}", "PATCH"),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "PATCH"),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "DELETE"),
    ("/api/ia-governanca/prompts-sistema", "GET"),
    ("/api/honorarios-oab/cases/{case_id}/provisionamento", "GET"),
    ("/api/honorarios-oab/cases/{case_id}/teto-etico", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "POST"),
    ("/api/clients/{client_id}/gerar-documentos", "POST"),
    ("/api/clients/{client_id}/pecas-geradas", "GET"),
    ("/api/saneamento/excecoes", "GET"),
    ("/api/saneamento/duplicatas", "GET"),
    ("/api/saneamento/duplicatas/{plano_id}/aplicar", "POST"),
    ("/api/saneamento/indicativos", "GET"),
    ("/api/saneamento/indicativos/{indicativo_id}/decidir", "POST"),
    ("/api/saneamento/divergencias", "GET"),
    ("/api/saneamento/tpu/cobertura", "GET"),
    ("/api/saneamento/varredura", "POST"),
    ("/api/documents/{doc_id}", "GET"),
    # PR #1365 (Issue #1075): registro de visualização prévia do documento
    # pelo signatário antes da assinatura (portal). Publicada sem entrada
    # neste ledger — o merge deixou a suíte vermelha; regularizada aqui.
    ("/api/signatures/{sig_id}/documento-visualizado", "POST"),
}

REMOCOES_INTENCIONAIS = {
    # `routers/curadoria_renomada.py` REMOVIDO (04/09/2026). Os três endpoints
    # respondiam 503 INCONDICIONAL desde a auditoria de 19/07: a "base de teses
    # renomadas" curada nunca existiu, e o 503 substituiu handlers que fingiam
    # lista vazia e ingestão bem-sucedida. Grep confirmou zero chamadores no
    # frontend. Um router que só sabe recusar não é funcionalidade desligada —
    # é superfície de API que promete o que ninguém construiu, e ela aparece no
    # OpenAPI, no mapa de módulos e na conta de rotas órfãs. Busca real segue em
    # /api/search e /api/rag (RAG híbrido), como o próprio 503 já indicava.
    ("/api/curadoria/teses", "GET"),
    ("/api/curadoria/teses/sincronizar", "POST"),
    ("/api/curadoria/analise-vencedora/{caso_id}", "GET"),
    # Bloco 4 do plano de lançamento. Decisão do ESCRITÓRIO, não achado técnico:
    # "dossiê de pressão" e "análise de magistrado" num sistema de advocacia são
    # risco reputacional e disciplinar indefensável se expostos numa perícia ou
    # numa representação — independentemente do que o código faça. Nenhuma tela
    # do sistema chamava os dois. Não reintroduzir sem decisão escrita do titular.
    ("/api/diplomacia-v3/dossie-pressao", "POST"),
    ("/api/diplomacia-v3/analisar-magistrado", "POST"),
    ("/api/cases/{case_id}/resumo", "GET"),
    ("/api/cases/{case_id}/linha-do-tempo", "GET"),
    ("/api/cases/{case_id}/assistente-estrategico", "POST"),
    ("/api/cases/{case_id}/movimentos/{mov_id}/traduzir", "POST"),
    ("/api/casos/{case_id}/jornada", "GET"),
    ("/api/teses-v4/", "GET"),
    ("/api/teses-v4/", "POST"),
    ("/api/teses-v4/sugestao-ia", "GET"),
    ("/api/data-room-v4/", "GET"),
    ("/api/data-room-v4/", "POST"),
    ("/api/diplomacia-v3/calcular-acordo", "POST"),
    ("/api/document-templates/", "GET"),
    ("/api/document-templates/generate", "POST"),
    ("/api/veredito_ia/analisar", "POST"),
    ("/api/victory_vault/modelos", "GET"),
    ("/api/victory_vault/modelos", "POST"),
    ("/api/victory_vault/teses", "GET"),
    ("/api/victory_vault/teses", "POST"),
    ("/api/intelligence-v3/radar/legislativo", "GET"),
    ("/api/intelligence-v3/analise-impacto", "POST"),
    ("/api/search/", "GET"),
    ("/api/honorarios-calc/cases/{case_id}/provisionamento", "GET"),
    ("/api/honorarios-calc/cases/{case_id}/teto-etico", "GET"),
    ("/api/honorarios-exito/{fee_id}/rateio", "GET"),
    ("/api/honorarios-exito/{fee_id}/rateio", "POST"),
    ("/api/prompts-biblioteca/", "GET"),
    ("/api/prompts-biblioteca/", "POST"),
    ("/api/prompts-biblioteca/{prompt_id}/executar", "POST"),
    ("/api/kanban-columns", "GET"),
    ("/api/precificacao/tabela", "GET"),
    ("/api/precificacao/calcular/{rule_id}", "GET"),
    ("/api/precificacao/regras", "POST"),
    ("/api/inadimplencia/alertas", "GET"),
    ("/api/inadimplencia/varrer", "POST"),
    ("/api/inadimplencia/alertas/{alert_id}/resolver", "PATCH"),
    ("/api/due-diligence/templates", "GET"),
    ("/api/due-diligence/templates", "POST"),
    ("/api/cofre/documentos/{document_id}/logs", "GET"),
    ("/api/cofre/documentos/{document_id}/registrar-acesso", "POST"),
    ("/api/cofre/documentos/{document_id}/sensibilidade", "PATCH"),
    ("/api/cofre/relatorio", "GET"),
    ("/api/casos/inteligencia/datajud/reconstruir-lote", "POST"),
    ("/api/casos/{case_id}/andamentos/alimentar-ia", "POST"),
    ("/api/casos/verificar-conflito", "POST"),
}


def _baseline() -> list[dict]:
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots", "openapi_rotas_baseline.json")
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


_MOVIDAS_ONDA2 = tuple(
    (r["path"], r["method"])
    for r in _baseline()
    if r["path"].startswith("/api/v1/")
)
REMOCOES_INTENCIONAIS |= set(_MOVIDAS_ONDA2)
ADICOES_INTENCIONAIS |= {
    ("/api" + path[len("/api/v1"):], metodo) for path, metodo in _MOVIDAS_ONDA2
}
ADICOES_INTENCIONAIS |= {
    ("/api/datajud/intelligence/reconstruir-lote", "POST"),
    ("/api/datajud/intelligence/{case_id}/andamentos/alimentar-ia", "POST"),
    ("/api/kanban/columns", "GET"),
    ("/api/modulos/cofre/documentos/{document_id}/logs", "GET"),
    ("/api/modulos/cofre/documentos/{document_id}/registrar-acesso", "POST"),
    ("/api/modulos/cofre/documentos/{document_id}/sensibilidade", "PATCH"),
    ("/api/modulos/cofre/relatorio", "GET"),
    ("/api/modulos/due-diligence/templates", "GET"),
    ("/api/modulos/due-diligence/templates", "POST"),
    ("/api/modulos/inadimplencia/alertas", "GET"),
    ("/api/modulos/inadimplencia/alertas/{alert_id}/resolver", "PATCH"),
    ("/api/modulos/inadimplencia/varrer", "POST"),
    ("/api/modulos/precificacao/calcular/{rule_id}", "GET"),
    ("/api/modulos/precificacao/regras", "POST"),
    ("/api/modulos/precificacao/tabela", "GET"),
    ("/api/sumulas/verificar-conflito", "POST"),
}
# I1 (análise E2E de 03/09/2026) — UMA PORTA DE IA POR CAPACIDADE.
# Cinco rotas NOVAS e canônicas (`routers/ia_capacidades.py`), todas resolvidas
# pelo Núcleo Único (sigilo, escopo, RAG, gate de citações, HITL, AILog). As
# portas antigas de /ai/* e /ia-especializada/* seguem registradas — nada foi
# removido aqui, então não há entrada correspondente em REMOCOES_INTENCIONAIS.
ADICOES_INTENCIONAIS |= {
    ("/api/ia/analisar", "POST"),
    ("/api/ia/conversar", "POST"),
    ("/api/ia/extrair", "POST"),
    ("/api/ia/redigir", "POST"),
    ("/api/ia/resumir", "POST"),
}


def test_paridade_openapi_com_snapshot_anterior():
    from app.main import app

    atual = _extrair_rotas(app)
    base = _baseline()
    chaves_base = {(r["path"], r["method"]): r for r in base}
    chaves_atual = {(r["path"], r["method"]): r for r in atual}

    sumiram = sorted(set(chaves_base) - set(chaves_atual) - REMOCOES_INTENCIONAIS)
    surgiram = sorted(set(chaves_atual) - set(chaves_base) - ADICOES_INTENCIONAIS)
    assert not sumiram, f"{len(sumiram)} rota(s) DESAPARECERAM: {sumiram[:10]}"
    assert not surgiram, f"{len(surgiram)} rota(s) NOVAS não previstas: {surgiram[:10]}"

    ressuscitadas = sorted(REMOCOES_INTENCIONAIS & set(chaves_atual))
    assert not ressuscitadas, f"rota(s) removida(s) por decisão do escritório voltaram: {ressuscitadas}"

    AUTH_ALTERACOES_INTENCIONAIS = (
        # PRs #1348/#1349 (auditoria E2E de clientes, set/2026): rate limit
        # (`rate_limit(...)` → dependência `_dep`) adicionado à análise de IA
        # do cliente e ao export CSV de clientes. Só ACRESCENTA uma
        # dependência de throttling; os gates de identidade/RBAC existentes
        # permanecem. Os merges não registraram a alteração aqui e deixaram
        # a suíte vermelha — regularizado na análise ponta a ponta de 03/09.
        (("/api/clients/{client_id}/ia-analise", "POST"), ["HTTPBearer", "_dep", "_req_clientes", "get_current_user", "get_db"]),
        (("/api/export/clientes.csv", "GET"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        # Homologação M20 (16/08/2026): correção crítica — o endpoint
        # substituto _listar_docs_escopado (GET /api/rag/docs) perdia os
        # Depends de db e cu na substituição por side effect, derrubando a
        # listagem com 500. Declarou get_db/get_current_user no topo:
        # a rota deixa de ser anônima e passa a exigir autenticação com
        # escopo de ownership (gestão vê tudo; demais usuários veem público,
        # do próprio cliente e de casos sem atribuição ou nos quais atuam).
        # Decisão deliberada, não achado — a listagem expunha títulos de
        # documentos internos de qualquer caso.
        (("/api/rag/docs", "GET"), ["HTTPBearer", "get_current_user", "get_db"]),
        (("/api/legal-docs/", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/", "POST"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}", "DELETE"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}", "PATCH"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/aprovar", "PATCH"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/documento-unico-impressao", "GET"), ["HTTPBearer", "_dep", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/exportar-docx", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/jurisprudencia-check", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/pdf", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/protocolo", "PATCH"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/revisar", "POST"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/validacao", "GET"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/legal-docs/{doc_id}/validar", "POST"), ["HTTPBearer", "_enforce_client_legal_doc_scope", "get_current_user", "get_db"]),
        (("/api/ai/analisar-caso", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/resumir-documento", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/teses-ocultas", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/auditar-peca", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/preparar-audiencia", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/assistente", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/dual", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/visual-law", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/estrategia", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/analisar-contrato", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/detectar-prazos", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ia-defensiva/analisar", "POST"), ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
    )

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
        and not any(k == chave and deps == chaves_atual[k]["auth_deps"] for chave, deps in AUTH_ALTERACOES_INTENCIONAIS)
    ]
    assert not divergentes, f"dependências de auth alteradas: {divergentes[:5]}"
    assert len(base) == 826
    assert len(atual) == len(base) + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)


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
    from app.main import app
    montadas = {(getattr(r, "path", ""), m) for r in app.routes for m in (getattr(r, "methods", None) or [])}
    assert (caminho, metodo) in montadas


@pytest.mark.parametrize(
    "caminho,metodo",
    [
        ("/api/dpt360/dashboard", "GET"),
        ("/api/dpt360/companies/{client_id}", "GET"),
        ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
        ("/api/dpt360/radar/today", "GET"),
        ("/api/dpt360/reports/executive/{client_id}", "GET"),
        ("/api/dpt360/intake/opportunities", "GET"),
        ("/api/dpt360/intake/opportunities", "POST"),
        ("/api/dpt360/actions", "POST"),
    ],
)
def test_rotas_dpt360_sao_explicitas(caminho, metodo):
    from app.main import app
    montadas = {(getattr(r, "path", ""), m) for r in app.routes for m in (getattr(r, "methods", None) or [])}
    assert (caminho, metodo) in montadas


def test_modulos_de_servico_nao_montam_mais_rotas():
    import inspect
    from app.services import event_subscribers, datajud_cognitive_patch
    from app.services.ai import provider_metrics_runtime
    for modulo in (event_subscribers, datajud_cognitive_patch, provider_metrics_runtime):
        fonte = inspect.getsource(modulo)
        assert "include_router" not in fonte
        assert ".router.routes.append(" not in fonte


def test_registro_independe_da_ordem_de_import():
    from app.services import event_subscribers  # noqa: F401
    from app.services.ai import provider_metrics_runtime  # noqa: F401
    from app.main import app
    assert len(_extrair_rotas(app)) == 826 + len(ADICOES_INTENCIONAIS) - len(REMOCOES_INTENCIONAIS)


def test_efeitos_colaterais_nao_de_rota_preservados():
    import inspect
    from app.services import datajud_cognitive_patch, event_subscribers
    from app.services.ai import provider_metrics_runtime
    fonte_ev = inspect.getsource(event_subscribers)
    assert "_install_document_analysis_hook()" in fonte_ev or "_patch_documents_background_analysis()" in fonte_ev
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
    from app.main import app
    atual = {(r["path"], r["method"]): r for r in _extrair_rotas(app)}
    divergentes = []
    for r in _baseline():
        antigo = r["path"]
        if not antigo.startswith("/api/v1/"):
            continue
        novo = "/api" + antigo[len("/api/v1") :]
        if (novo, r["method"]) in REMOCOES_INTENCIONAIS:
            continue
        destino = atual.get((novo, r["method"]))
        assert destino is not None, f"{antigo} {r['method']} não reapareceu em {novo}"
        if destino["auth_deps"] != r["auth_deps"]:
            divergentes.append((antigo, novo, r["auth_deps"], destino["auth_deps"]))
    assert not divergentes, f"a mudança de prefixo alterou o gate de auth de {len(divergentes)} rota(s): {divergentes[:3]}"
