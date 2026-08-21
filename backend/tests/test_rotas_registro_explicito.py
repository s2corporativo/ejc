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
    # Saneamento 19/08/2026 (item 16): auditoria semântica da superfície real,
    # restrita a superadmin/admin/sócio; não expõe dados de caso/cliente.
    ("/api/architecture/semantic-audit", "GET"),
    # Saneamento 19/08/2026 (item 14): heartbeat técnico do DOU, advogado+,
    # sem keyword, conteúdo de publicação, PII ou segredo.
    ("/api/diario-oficial/status", "GET"),
    ("/api/sala-juridica/{session_id}/conversao/preview", "GET"),
    ("/api/diagnostico/integridade", "GET"),
    # PR #547: decisão explícita de publicar/despublicar arquivo no Data Room.
    ("/api/data-rooms/{room_id}/arquivos/{arquivo_id}/publicacao", "PATCH"),
    # Issue #698: ato EXPLÍCITO de publicação/despublicação ao Portal do
    # Cliente, separado do PATCH de metadados comuns — mesmo desenho do
    # PR #547 para o Data Room (linha acima), agora para documents.
    ("/api/documents/{doc_id}/publicacao-portal", "PATCH"),
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
    # Issue #836: onda de fontes públicas oficiais, já integrada na main pelo
    # PR #887. O PR #905 preserva explicitamente essas rotas ao acrescentar os
    # contratos canônicos de Jurimetria abaixo.
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
    # PR #905: jurimetria passa a expor, de forma explícita, apenas métricas
    # internas e cobertura agregada do RAG. Os aliases /ext legados permanecem,
    # mas estes são os contratos canônicos novos e deliberados.
    ("/api/jurimetria/interno/stats", "GET"),
    ("/api/jurimetria/interno/benchmarks", "GET"),
    ("/api/jurimetria/interno/analise-prospectiva", "GET"),
    ("/api/jurimetria/analise-prospectiva", "POST"),
    ("/api/jurimetria/cobertura-rag", "GET"),
    ("/api/jurimetria/cobertura-mg-jec", "GET"),
    # PR #938: vínculo canônico de documento solto ao caso. A busca filtra
    # candidatos server-side e o POST aplica domínio/auditoria de forma atômica.
    ("/api/cases/{case_id}/documentos/candidatos", "GET"),
    ("/api/cases/{case_id}/documentos/{document_id}/vincular", "POST"),
    # DPT Empresarial 360 — superfície nova declarada nominalmente. Não usar
    # wildcard: cada contrato precisa ser revisto quando surgir ou desaparecer.
    ("/api/dpt360/dashboard", "GET"),
    ("/api/dpt360/companies/{client_id}", "GET"),
    ("/api/dpt360/diagnostics/readiness/{client_id}", "GET"),
    ("/api/dpt360/radar/today", "GET"),
    ("/api/dpt360/reports/executive/{client_id}", "GET"),
    ("/api/dpt360/intake/opportunities", "GET"),
    ("/api/dpt360/intake/opportunities", "POST"),
    ("/api/dpt360/actions", "POST"),
    # Manutenção do gate (12/08/2026): duas rotas publicadas após o snapshot
    # sem registro nominal — export de eventos de produtividade (Analytics)
    # e avanço de ciclo de vida de lote de oportunidades (DPT360).
    ("/api/analytics/produtividade/export-event", "POST"),
    ("/api/dpt360/oportunidades/{batch_id}/ciclo-vida", "POST"),
    # PR #1120 (assinaturas): leitura do DOCUMENTO assinado por ID de
    # assinatura — o fix de produção que criou o endpoint de documento.
    ("/api/signatures/{sig_id}/documento", "GET"),
    # #1199: documentos de admissão privados e vinculados ao cliente.
    ("/api/clients/{client_id}/pecas-geradas", "GET"),
    ("/api/clients/{client_id}/gerar-documentos", "POST"),
    # Consolidação 12/08/2026: intelligence_v3.py renomeado para
    # intelligence.py e prefixo normalizado para /intelligence (a única tela
    # consumidora, Radar Legislativo, foi atualizada junto — a mudança é de
    # ENDEREÇO canônico, não de contrato).
    ("/api/intelligence/radar/legislativo", "GET"),
    ("/api/intelligence/analise-impacto", "POST"),
    # PR #1132 (14/08/2026): motor de teses assíncrono — o frontend passou a
    # fazer polling de status em vez de esperar a resposta síncrona (E02–E09).
    ("/api/teses/motor/async", "POST"),
    ("/api/teses/motor/async/{task_id}", "GET"),
    # Homologação M08 (16/08/2026): edição de parte processual com auditoria —
    # PATCH /cases/{case_id}/partes/{parte_id} não existia (só listagem,
    # criação e remoção). Contrato novo e deliberado.
    ("/api/cases/{case_id}/partes/{parte_id}", "PATCH"),
    # Homologação M12 (16/08/2026): edição e remoção de movimentações — CRUD
    # completo de andamentos com auditoria, criado para saneamento dos
    # bloqueios e datas inconsistentes do banco real.
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "PATCH"),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "DELETE"),
    # Auditoria de IA 18/08 (dívida 5.3): inventário canônico dos prompts do
    # NÚCLEO (código), com versão por conteúdo. Distinto de /prompts, que lista
    # os prompts jurídicos do usuário no banco. Somente admin/sócio.
    ("/api/ia-governanca/prompts-sistema", "GET"),
    # PR #1215 (Bloco P1+P2, D4 — 20/08/2026): consolidação dos roteadores de
    # honorários (honorarios_calc/exito_rateio → honorarios_oab.py). Os quatro
    # endpoints já EXISTIAM nos prefixos /honorarios-calc e /honorarios-exito
    # (mantidos como redirect 308 nos shims) — em /honorarios-oab são a mesma
    # implementação consolidada sob o prefixo canônico, sem alteração de
    # contrato. Registro nominal conforme padrão do §4.1.
    ("/api/honorarios-oab/cases/{case_id}/provisionamento", "GET"),
    ("/api/honorarios-oab/cases/{case_id}/teto-etico", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "GET"),
    ("/api/honorarios-oab/{fee_id}/rateio", "POST"),
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
    # Consolidação de routers 12/08/2026 (docs/consolidacao/MAPA_VERDADE_V1.md):
    # seis routers comprovadamente órfãos (varredura de chamadas de API em
    # frontend e backend antes da remoção) foram movidos para
    # app/routers/_dead_code/ — teses_v4 (shim deprecated; canônico /api/teses),
    # data_room_v4 (idem /api/data-rooms), diplomacia_v3 (calculadora segue
    # em /visual-law/*), peca_geracao_router (/document-templates; canônico
    # /api/pecas), veredito_ia_router (/veredito_ia/analisar; o core continua
    # em app/core/veredito_ia.py) e victory_vault_router (/victory_vault/*;
    # tela era redirect para /inteligencia?tab=conhecimento). Não reintroduzir
    # sem decisão escrita do titular.
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
    # Consolidação 12/08/2026: ver acima (intelligence_v3 → intelligence).
    ("/api/intelligence-v3/radar/legislativo", "GET"),
    ("/api/intelligence-v3/analise-impacto", "POST"),
    # PR #1211 (auditoria de redundâncias 19/08/2026): decorator
    # @router.get("/") redundante no handler de busca global de search.py — o
    # mesmo handler já era registrado por @router.get("") (path canônico
    # GET /search). Nenhum consumer (frontend ou backend) chama /search/ com
    # trailing slash; a rota duplicada não tem contrato de consumo.
    ("/api/search/", "GET"),
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
# PR #1218 (P3 — 20/08/2026): prefixos canônicos nos 6 routers
ADICOES_INTENCIONAIS |= {
    ("/api/datajud/intelligence/reconstruir-lote", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/datajud/intelligence/{case_id}/andamentos/alimentar-ia", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/kanban/columns", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/cofre/documentos/{document_id}/logs", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/cofre/documentos/{document_id}/registrar-acesso", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/cofre/documentos/{document_id}/sensibilidade", "PATCH"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/cofre/relatorio", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/due-diligence/templates", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/due-diligence/templates", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/inadimplencia/alertas", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/inadimplencia/alertas/{alert_id}/resolver", "PATCH"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/inadimplencia/varrer", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/precificacao/calcular/{rule_id}", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/precificacao/regras", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/modulos/precificacao/tabela", "GET"),  # PR #1218 (P3): rota canônica pós-prefixo
    ("/api/sumulas/verificar-conflito", "POST"),  # PR #1218 (P3): rota canônica pós-prefixo
}



def test_paridade_openapi_com_snapshot_anterior():
    """Path + método + dependências de auth idênticos ao estado pré-mudança."""
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
    assert not ressuscitadas, (
        f"rota(s) removida(s) por decisão do escritório voltaram: {ressuscitadas}"
    )

    # Mudanças INTENCIONAIS de dependências de auth posteriores ao snapshot.
    # Cada entrada declara (chave, auth_deps esperado); rota divergente fora
    # desta lista continua reprovando — a trava existe para pegar alteração
    # de permissão silenciosa, e cada exceção precisa de decisão escrita.
    # Tuple de pares (chave, auth_deps esperado) — não usar dict: a lista de
    # deps não é hashável. Divergência diferente da declarada continua
    # reprovando.
    AUTH_ALTERACOES_INTENCIONAIS = (
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
        # Auditoria de segurança de IA (18/08): 12 endpoints que chamam
        # provedor de IA (custo real por chamada) não tinham @rate_limit —
        # o único determinístico sem LLM da vizinhança (/citacoes/verificar)
        # tinha. `_dep` é o fechamento devolvido por rate_limit(); entra como
        # sub-dependency ANTES de get_current_user na ordem de extração porque
        # está em `dependencies=` do decorator, não na assinatura do handler.
        (("/api/ai/analisar-caso", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/resumir-documento", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/teses-ocultas", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/auditar-peca", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/preparar-audiencia", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/assistente", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/casos/{case_id}/dual", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/visual-law", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/caso/{case_id}/estrategia", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/analisar-contrato", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ai/detectar-prazos", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        (("/api/ia-defensiva/analisar", "POST"),
         ["HTTPBearer", "_dep", "get_current_user", "get_db"]),
        # PR #1215 (Bloco P1+P2, D4 — 20/08/2026): consolidação dos routers de
        # prompts e honorários. Os sete endpoints abaixo viraram REDIRECTS 308
        # (shims de compatibilidade) apontando para os endereços canônicos
        # /prompts-juridicos/* e /honorarios-oab/* — que mantêm a autenticação
        # intacta. O redirect em si é público porque o destino reautentica
        # (HTTPBearer); o contrato público permanece exigindo credencial.
        (("/api/prompts-biblioteca/", "GET"), []),
        (("/api/prompts-biblioteca/", "POST"), []),
        (("/api/prompts-biblioteca/{prompt_id}/executar", "POST"), []),
        (("/api/honorarios-calc/cases/{case_id}/provisionamento", "GET"), []),
        (("/api/honorarios-calc/cases/{case_id}/teto-etico", "GET"), []),
        (("/api/honorarios-exito/{fee_id}/rateio", "GET"), []),
        (("/api/honorarios-exito/{fee_id}/rateio", "POST"), []),
        # PR #1218 (P3 — 20/08/2026): 308 permanentes dos endereços
        # antigos dos 6 routers sem prefixo — o destino canônico
        # preserva o auth; o alias legado vira redirect anônimo.
        (("/api/casos/inteligencia/datajud/reconstruir-lote", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/casos/verificar-conflito", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/casos/{case_id}/andamentos/alimentar-ia", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/cofre/documentos/{document_id}/logs", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/cofre/documentos/{document_id}/registrar-acesso", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/cofre/documentos/{document_id}/sensibilidade", "PATCH"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/cofre/relatorio", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/due-diligence/templates", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/due-diligence/templates", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/honorarios-calc/cases/{case_id}/provisionamento", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/honorarios-calc/cases/{case_id}/teto-etico", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/honorarios-exito/{fee_id}/rateio", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/honorarios-exito/{fee_id}/rateio", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/inadimplencia/alertas", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/inadimplencia/alertas/{alert_id}/resolver", "PATCH"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/inadimplencia/varrer", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/precificacao/calcular/{rule_id}", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/precificacao/regras", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/precificacao/tabela", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/prompts-biblioteca/", "GET"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/prompts-biblioteca/", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
        (("/api/prompts-biblioteca/{prompt_id}/executar", "POST"), []),  # PR #1218 (P3): redirect 308 anônimo
    )

    divergentes = [
        (k, chaves_base[k]["auth_deps"], chaves_atual[k]["auth_deps"])
        for k in sorted(set(chaves_base) & set(chaves_atual))
        if chaves_base[k]["auth_deps"] != chaves_atual[k]["auth_deps"]
        and not any(
            k == chave and deps == chaves_atual[k]["auth_deps"]
            for chave, deps in AUTH_ALTERACOES_INTENCIONAIS
        )
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
    """Toda rota DPT nova precisa continuar explicitamente montada no FastAPI."""
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
    # O adapter legado do hook documental foi renomeado para
    # `_install_document_analysis_hook()` (mesma responsabilidade: instalar a
    # função única de document_analysis_hook no router de documentos).
    assert (
        "_install_document_analysis_hook()" in fonte_ev
        or "_patch_documents_background_analysis()" in fonte_ev
    )
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
