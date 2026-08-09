# ── app/services/ai_service.py ───────────────────────────────────────────────
# Serviço de IA — via AI Gateway central com:
#  1. Sanitização LGPD obrigatória (sanitizer.py)
#  2. RAG: recuperação de jurisprudências/súmulas do pgvector
#  3. Anti-alucinação: resposta DEVE citar fontes da base; sem fonte = declarado
#  4. AI log gravado em toda chamada (HITL rastreável)
#  5. Saída SEMPRE marcada como rascunho — revisão humana obrigatória (OAB)
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.sanitizer import sanitizar_pii, validar_sem_pii
from app.services.case_context import montar_dossie
from app.services.ai_gateway import chat as gw_chat, GatewayResponse
from app.services.legal_base import BASE_ESTRUTURADA
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Prompts mestres ───────────────────────────────────────────────────────────

SYSTEM_ANALISE_CASO = """Você é um assistente jurídico de um escritório de advocacia brasileiro.
Sua função é analisar fatos descritos pelo advogado e sugerir TESES JURÍDICAS POSSÍVEIS.

REGRAS ABSOLUTAS:
1. Use APENAS as fontes fornecidas no contexto [FONTES]. NUNCA invente súmulas, artigos ou julgados.
2. Se as fontes não cobrirem o tema, declare explicitamente: "Sem base verificável na base de conhecimento para: [tema]".
3. NUNCA afirme que uma tese "vai ganhar" ou prometa resultado (vedação OAB).
4. Cite a fonte exata de cada afirmação: [Fonte N].
5. Responda em português jurídico claro e estruturado.

FORMATO DA RESPOSTA:
## Teses Possíveis
1. **[Nome da tese]** — fundamentação com [Fonte N]
## Base Legal Aplicável
- Dispositivos citados nas fontes
## Súmulas e Precedentes
- Apenas os presentes nas fontes
## Riscos e Pontos de Atenção
- Fragilidades da tese
## Documentos Recomendados
- O que o advogado deve reunir

⚠️ Esta análise é um RASCUNHO gerado por IA. Revisão por advogado é OBRIGATÓRIA antes de qualquer uso."""


SYSTEM_RESUMO_DOC = """Você resume documentos jurídicos em português.
Estruture: 1) Do que se trata, 2) Pontos principais, 3) Prazos mencionados, 4) Próximos passos sugeridos.
Não invente informações ausentes do texto. Marque incertezas explicitamente."""


# ── Busca RAG (pgvector) ──────────────────────────────────────────────────────

_AVISOU_SEM_EMBEDDINGS = False  # warning único de degradação p/ ILIKE

# ── Isolamento por cliente (Fase 3B / LGPD / EOAB art. 25) ────────────────────
# Categorias RESTRITAS = conteúdo derivado de casos de clientes (peças/precedentes
# internos): só recuperáveis no escopo do próprio cliente. Demais categorias
# (legislação, súmulas, jurisprudência, doutrina) são públicas/globais.
# "comunicacao_processual" (DJEN/intimações): fail-closed por cliente — sem
# client_id do escopo, a comunicação NÃO é recuperável (só dentro do escopo do
# cliente dono, populado no ingestor djen.py).
_RESTRICTED_CATS = ["peca_interna", "peca_escritorio", "precedente_interno",
                    "comunicacao_processual"]
# Fail-closed: sem escopo de cliente (scope_cli=""), o conteúdo restrito é
# EXCLUÍDO da busca — fecha o vazamento cruzado entre clientes.
_FILTRO_ESCOPO_RAG = "AND (kd.categoria <> ALL(:restr_cats) OR kd.client_id = :scope_cli)"

# Versionamento (migration 068): por padrão só a versão VIGENTE de cada
# documento entra na busca RAG. `:incl_hist` (bool) permite incluir versões
# históricas (auditoria de citações antigas, pesquisa de evolução de tese).
_FILTRO_VIGENTE_RAG = "AND (kd.vigente = TRUE OR :incl_hist)"

# ── Gate de governança na recuperação (Auditoria RAG) ─────────────────────────
# Os campos de curadoria (confidence_level/rag_status) vivem em
# knowledge_docs.extra (JSONB). Este gate FAIL-CLOSED é aplicado a TODAS as
# consultas de recuperação: um documento explicitamente bloqueado/recusado/
# reprovado/pendente NUNCA entra no prompt. Por padrão, exige aprovação
# explícita; o acervo legado sem curadoria fica em quarentena.
_FILTRO_GATE_RAG = (
    "AND NOT ("
    "COALESCE(kd.extra->>'confidence_level','') = 'bloqueado' "
    "OR COALESCE(kd.extra->>'rag_status','') IN "
    "('bloqueado','recusado','reprovado','pendente'))"
)
# Regime estrito (default): quando RAG_EXIGIR_APROVADO=true, só documentos
# explicitamente aprovados entram na recuperação.
_FILTRO_APROVADO_RAG = "AND COALESCE(kd.extra->>'rag_status','') = 'aprovado'"
# Quarentena de súmulas: o seed foi reconstruído e cada verbete reconferido
# individualmente contra fonte oficial (sumulas_ingestion.py), gravando
# extra->>'conferido'='true' SÓ nos que passaram nessa reconferência. Enquanto
# RAG_SUMULAS_QUARENTENA=true (padrão), qualquer doc de súmula (chave_origem
# 'sumula:%' ou fonte='sumula') SEM esse marcador é excluído — protege contra
# reintrodução de conteúdo não conferido (seed antigo, ingestão manual futura).
_FILTRO_SUMULAS_QUARENTENA = (
    "AND NOT ("
    "(COALESCE(kd.chave_origem,'') LIKE 'sumula:%' OR COALESCE(kd.fonte,'') = 'sumula') "
    "AND COALESCE((kd.extra->>'conferido')::boolean, false) = false"
    ")"
)
# Corpus FICTÍCIO (Bíblia EJC): extra->>'ficticio'='true'. É material de
# estrutura/metodologia, NUNCA fundamentação — excluído por padrão das buscas
# amplas; só entra quando o call site pede incluir_ficticio=True (geração de
# peça a partir de modelos).
_FILTRO_FICTICIO_RAG = "AND COALESCE((kd.extra->>'ficticio')::boolean, false) = false"

# ── Situação JURÍDICA na recuperação (Issue #636) ─────────────────────────────
# Curadoria (rag_status) e vigência da norma são campos DISTINTOS: um documento
# podia estar 'aprovado' para o RAG e, ao mesmo tempo, revogado — nada na
# recuperação olhava a situação jurídica. Estes filtros espelham, em SQL, a
# leitura que knowledge_governance.inferir_situacao_juridica faz de
# knowledge_docs.extra: MESMA precedência de chaves (legal_status →
# situacao_normativa → vigencia_status) e MESMA normalização (minúsculas,
# espaços colapsados, aliases com espaço/acento).
#
# Onde o espelho é DELIBERADAMENTE mais apertado que a inferência (e por quê):
#   • a inferência devolve 'historica' — não 'revogada' — para qualquer versão
#     não vigente, mesmo com extra.legal_status='revogada'. _FILTRO_REVOGADA_RAG
#     lê o extra INDEPENDENTE de kd.vigente: uma norma declarada revogada não
#     volta nem como histórico. Erro possível aqui só remove, nunca inclui.
#   • a governança também nega fundamentação atual a 'suspensa' e
#     'parcialmente_revogada'; o gate NÃO as exclui, porque continuam citáveis
#     com ressalva (a peça precisa do texto para discutir a suspensão). Está
#     registrado como follow-up conhecido no PR — assimetria intencional.
_SQL_SITUACAO_JURIDICA = (
    "regexp_replace(lower(btrim(COALESCE("
    "NULLIF(btrim(kd.extra->>'legal_status'),''),"
    "NULLIF(btrim(kd.extra->>'situacao_normativa'),''),"
    "NULLIF(btrim(kd.extra->>'vigencia_status'),''),''))),'\\s+',' ','g')"
)
# Norma REVOGADA nunca é fundamentação atual: exclusão INCONDICIONAL (sem flag),
# em qualquer categoria. Cobre as duas grafias que uma ingestão pode gravar.
_FILTRO_REVOGADA_RAG = (
    f"AND {_SQL_SITUACAO_JURIDICA} NOT IN ('revogada','revogado')"
)
# Valores que inferir_situacao_juridica reconhece como situação DECLARADA
# (LEGAL_STATUS_VALUES + aliases). Qualquer outro conteúdo — extra ausente,
# valor desconhecido ou o próprio 'vigencia_nao_verificada' — é vigência NÃO
# conferida, exatamente como na inferência.
_SQL_SITUACAO_DECLARADA = (
    "('vigente','parcialmente_revogada','parcialmente revogada','revogada',"
    "'revogado','suspensa','nao_aplicavel','nao aplicavel','não aplicável',"
    "'historica')"
)
# Sob RAG_EXIGIR_VIGENCIA_VERIFICADA (default true), documento de LEGISLAÇÃO com
# vigência 'vigente' só passa se tiver proveniência POSITIVA COMPLETA: origem
# preenchida, data de verificação preenchida E carimbo de inferência AUSENTE.
# Três recortes, e cada um reproduz um ramo de inferir_situacao_juridica:
#
#   1. kd.vigente — a inferência testa `if not bool(doc.vigente)` ANTES de olhar
#      o extra e devolve 'historica', que é situação DECLARADA. Versões
#      históricas (vigente=false) PASSAM (bypass), porque a análise histórica é
#      válida. Coluna NULL vale como não vigente, igual ao bool() do Python —
#      daí o COALESCE(...,false).
#   2. categoria LIKE '%legisl%' — só nessa faixa a inferência devolve
#      'vigencia_nao_verificada'; para o restante do acervo devolve
#      'nao_aplicavel' (que PERMITE fundamentação), então súmulas,
#      jurisprudência, doutrina, modelos e peças internas seguem recuperáveis.
#      ATENÇÃO: o LIKE também alcança 'proposicao_legislativa' (ingestors
#      camara.py/senado.py), que NÃO grava legal_status. A exclusão desse corpus
#      é INTENCIONAL e permanente, não transitória: proposição é projeto em
#      tramitação e não pode fundamentar peça como se fosse lei em vigor. Se um
#      dia proposição precisar voltar, o caminho é categoria própria fora do
#      recorte — não afrouxar o filtro.
#   3. Condição POSITIVA: para legislação vigente, exige legal_status='vigente'
#      COM proveniência positiva completa (origem e data de verificação
#      preenchidos e carimbo de inferência ausente). Situações 'suspensa' ou
#      'parcialmente_revogada' NÃO passam sem conferência humana específica.
_FILTRO_VIGENCIA_VERIFICADA_RAG = (
    "AND ("
    # Bypass: versões históricas sempre passam (vigente=false ou NULL)
    "COALESCE(kd.vigente, false) = false "
    # OU não é legislação (outros acervos sempre passam)
    "OR lower(COALESCE(kd.categoria,'')) NOT LIKE '%legisl%' "
    # OU legislação vigente com situação 'vigente' E proveniência positiva completa
    "OR ("
    f"{_SQL_SITUACAO_JURIDICA} = 'vigente' "
    "AND NULLIF(btrim(kd.extra->>'legal_status_origem'),'') IS NOT NULL "
    "AND NULLIF(btrim(kd.extra->>'legal_status_verificado_em'),'') IS NOT NULL "
    "AND NULLIF(btrim(kd.extra->>'legal_status_inferido_em'),'') IS NULL"
    ")"
    ")"
)


def _filtros_gate_rag(incluir_ficticio: bool = False) -> str:
    """Fragmento SQL (sem bind params) com o gate de governança/quarentena
    aplicado a TODAS as consultas de recuperação RAG. A decisão é feita em
    Python a partir das flags de config, então não há parâmetros novos para
    propagar aos dicionários de params das queries. Fail-closed."""
    partes = [_FILTRO_GATE_RAG, _FILTRO_REVOGADA_RAG]
    if settings.RAG_EXIGIR_APROVADO:
        partes.append(_FILTRO_APROVADO_RAG)
    if settings.RAG_EXIGIR_VIGENCIA_VERIFICADA:
        partes.append(_FILTRO_VIGENCIA_VERIFICADA_RAG)
    if settings.RAG_SUMULAS_QUARENTENA:
        partes.append(_FILTRO_SUMULAS_QUARENTENA)
    if not incluir_ficticio:
        partes.append(_FILTRO_FICTICIO_RAG)
    return "\n              ".join(partes)

# RAG-04: limiar mínimo de similaridade na busca semântica — evita que matches
# fracos/irrelevantes entrem como "fonte" e poluam o contexto da IA (risco de
# alucinação). Similaridade = 1 - distância de cosseno. min_sim 0.55 → max_dist 0.45.
# Limiar de similaridade da busca vetorial — agora CONFIGURÁVEL (RAG_MIN_SIM;
# auditoria IA 2026-07-17, achado A-2); antes hardcoded em 0.55. Calibrável por
# um eval set sem tocar código. Distância de cosseno = 1 - similaridade.
_RAG_MIN_SIM_DEFAULT = 0.55


def _rag_max_dist() -> float:
    """Distância máxima de cosseno aceita na busca vetorial, derivada de
    RAG_MIN_SIM (fallback 0.55). Clamp defensivo em [0, 2]."""
    try:
        sim = float(settings.RAG_MIN_SIM)
    except Exception:
        sim = _RAG_MIN_SIM_DEFAULT
    return max(0.0, min(2.0, 1.0 - sim))

# Confiança do documento (curadoria de governança — ia_governanca._conf):
# vive em knowledge_docs.extra (JSONB), chave canônica "confidence_level"
# (legado "confianca"), default "media". Exposta em todo resultado de busca
# para que o consumidor (IA/frontend) pondere a fonte.
_SQL_CONFIANCA = (
    "COALESCE(kd.extra->>'confidence_level', kd.extra->>'confianca', 'media') AS confianca"
)


async def _escopo_cliente_do_caso(db: AsyncSession, case_id: str | None) -> str | None:
    """Escopo de isolamento do RAG (Bloco 5): retorna o client_id do caso, para
    que o conteúdo RESTRITO (peças/precedentes internos) do PRÓPRIO cliente seja
    recuperável — e só o dele. Sem caso (case_id None) ou caso inexistente,
    retorna None: o RAG mantém o comportamento fail-closed (nenhum conteúdo
    restrito é recuperado). Nunca deriva o client_id de outro cliente — a chave
    é sempre o client_id do próprio caso em contexto."""
    if not case_id:
        return None
    row = (await db.execute(
        text("SELECT client_id FROM cases WHERE id = :cid AND deleted_at IS NULL"),
        {"cid": case_id},
    )).first()
    return row[0] if row else None


async def _fundir_lexical(db, consulta, semanticos, limite, categorias, scope_client_id=None,
                          incluir_historico=False, incluir_ficticio=False):
    """Busca híbrida: funde ranking SEMÂNTICO (pgvector) + LEXICAL (pg_trgm) via
    Reciprocal Rank Fusion (RRF). Aditivo — se a parte lexical falhar, devolve o
    semântico intacto. k=60 é o padrão de RRF."""
    from sqlalchemy import text as _text
    K = 60
    fusion = {}
    meta = {}
    for rank, r in enumerate(semanticos):
        cid = r.get("chunk_id")
        if cid is None:
            continue
        fusion[cid] = fusion.get(cid, 0.0) + 1.0 / (K + rank + 1)
        meta[cid] = r
    try:
        params = {"q": consulta[:300], "lim": max(limite * 3, 12),
                  "restr_cats": _RESTRICTED_CATS, "scope_cli": scope_client_id or "",
                  "incl_hist": incluir_historico}
        filtro = ""
        if categorias:
            filtro = "AND kd.categoria = ANY(:cats)"
            params["cats"] = categorias
        sql = _text(f"""
            SELECT kc.id, kc.doc_id, kc.conteudo, kd.titulo, kd.categoria, kd.fonte, kd.versao,
                   {_SQL_CONFIANCA},
                   similarity(kc.conteudo, :q) AS sim
            FROM knowledge_chunks kc
            JOIN knowledge_docs kd ON kd.id = kc.doc_id
            WHERE kd.deleted_at IS NULL
              AND similarity(kc.conteudo, :q) > 0.05
              {filtro}
              {_FILTRO_ESCOPO_RAG}
              {_FILTRO_VIGENTE_RAG}
              {_filtros_gate_rag(incluir_ficticio)}
            ORDER BY sim DESC
            LIMIT :lim
        """)
        rows = await db.execute(sql, params)
        for rank, r in enumerate(rows):
            cid = r.id
            fusion[cid] = fusion.get(cid, 0.0) + 1.0 / (K + rank + 1)
            if cid not in meta:
                meta[cid] = {"chunk_id": r.id, "doc_id": r.doc_id, "conteudo": r.conteudo,
                             "titulo": r.titulo,
                             "categoria": r.categoria, "fonte": r.fonte,
                             "confianca": r.confianca,
                             "versao": getattr(r, "versao", None),
                             "score": round(float(r.sim), 4)}
    except Exception as _e:
        logger.warning(f"Fusao lexical (RRF) falhou, mantendo semantico: {_e}")
        return semanticos
    # A-3 (auditoria IA 2026-07-17): perna FULL-TEXT (tsvector 'portuguese',
    # BM25-like) — melhor para termos raros/citações exatas (art./súmula/nº CNJ).
    # Aditiva ao RRF; OFF por default. Usa o índice GIN pré-existente
    # ix_knowledge_chunks_conteudo_fts (migration 001) — sem migration nova.
    # Falha isolada não afeta as pernas semântica/trigram.
    if getattr(settings, "RAG_FTS_ENABLED", False):
        try:
            params_f = {"q": consulta[:300], "lim": max(limite * 3, 12),
                        "restr_cats": _RESTRICTED_CATS, "scope_cli": scope_client_id or "",
                        "incl_hist": incluir_historico}
            filtro_f = ""
            if categorias:
                filtro_f = "AND kd.categoria = ANY(:cats)"
                params_f["cats"] = categorias
            sql_f = _text(f"""
                SELECT kc.id, kc.doc_id, kc.conteudo, kd.titulo, kd.categoria, kd.fonte, kd.versao,
                       {_SQL_CONFIANCA},
                       ts_rank_cd(to_tsvector('portuguese', kc.conteudo),
                                  plainto_tsquery('portuguese', :q)) AS rank
                FROM knowledge_chunks kc
                JOIN knowledge_docs kd ON kd.id = kc.doc_id
                WHERE kd.deleted_at IS NULL
                  AND to_tsvector('portuguese', kc.conteudo)
                      @@ plainto_tsquery('portuguese', :q)
                  {filtro_f}
                  {_FILTRO_ESCOPO_RAG}
                  {_FILTRO_VIGENTE_RAG}
                  {_filtros_gate_rag(incluir_ficticio)}
                ORDER BY rank DESC
                LIMIT :lim
            """)
            rows_f = await db.execute(sql_f, params_f)
            for rank, r in enumerate(rows_f):
                cid = r.id
                fusion[cid] = fusion.get(cid, 0.0) + 1.0 / (K + rank + 1)
                if cid not in meta:
                    meta[cid] = {"chunk_id": r.id, "doc_id": r.doc_id, "conteudo": r.conteudo,
                                 "titulo": r.titulo,
                                 "categoria": r.categoria, "fonte": r.fonte,
                                 "confianca": r.confianca,
                                 "versao": getattr(r, "versao", None),
                                 "score": round(float(r.rank), 4)}
        except Exception as _ef:
            logger.warning(f"Fusao FTS (RRF) falhou, ignorando esta perna: {_ef}")
    ordenados = sorted(fusion.items(), key=lambda kv: kv[1], reverse=True)
    saida = []
    for cid, _s in ordenados[:limite]:
        item = dict(meta[cid]); item["rrf"] = round(_s, 5); saida.append(item)
    return saida


async def _hyde_expandir(consulta: str) -> str:
    """HyDE (auditoria IA 2026-07-17, O-6): gera uma 'resposta hipotética' curta e
    a concatena à consulta para EMBUTIR na busca VETORIAL — melhora o recall quando
    o vocabulário do caso novo difere do registrado. Só afeta a perna densa; a
    perna lexical continua com a consulta REAL. OFF por default (RAG_HYDE_ENABLED).
    Fail-safe: desligado/erro/timeout/vazio → devolve a consulta original."""
    if not getattr(settings, "RAG_HYDE_ENABLED", False) or not (consulta or "").strip():
        return consulta
    try:
        resp = await gw_chat(
            [{"role": "system", "content": (
                "Voce e um assistente juridico. Escreva UM paragrafo curto (max. 3 frases) "
                "que responderia hipoteticamente a consulta, no vocabulario tecnico-juridico "
                "brasileiro (dispositivos, teses, termos). NAO invente numero de processo, "
                "sumula ou lei especificos — use linguagem doutrinaria generica.")},
             {"role": "user", "content": consulta[:1000]}],
            task_type="resumo",              # tier leve/barato
            temperature=0.3, max_tokens=256, nivel_inteligencia="padrao",
        )
        hipotese = (getattr(resp, "texto", "") or "").strip()
        return f"{consulta}\n{hipotese}" if hipotese else consulta
    except Exception as e:  # HyDE nunca quebra a busca
        logger.warning("HyDE indisponivel (usando consulta original): %s", str(e)[:150])
        return consulta


async def buscar_contexto_rag(
    db: AsyncSession, consulta: str, limite: int = 6,
    categorias: list[str] | None = None,
    modo_or: bool = False,
    scope_client_id: str | None = None,
    incluir_historico: bool = False,
    incluir_ficticio: bool = False,
) -> list[dict]:
    """
    Busca semântica na base de conhecimento via pgvector.
    Fallback: se não houver embeddings, usa busca textual (ILIKE) nas súmulas.

    modo_or=True: casa qualquer termo (OR) em vez de todos (AND). Útil para
    precedentes internos, onde a relevância parcial é valiosa e os textos
    raramente repetem o vocabulário exato do caso novo.

    incluir_historico=True: inclui versões não-vigentes (migration 068) —
    útil para auditoria de citações antigas ou pesquisa da evolução de uma
    tese/entendimento. Por padrão (False) só a versão vigente é retornada.

    incluir_ficticio=True: permite recuperar o corpus FICTÍCIO da Bíblia EJC
    (extra.ficticio=true — modelos de peça/referência interna). SÓ deve ser
    usado por call sites que consomem esses docs como ESTRUTURA (geração de
    peça a partir de modelo). Por padrão (False) o corpus fictício é EXCLUÍDO,
    para nunca aparecer como fundamentação em buscas amplas.

    Gate de governança (fail-closed) é aplicado a TODAS as consultas via
    _filtros_gate_rag: docs bloqueados/recusados/pendentes nunca entram; súmulas
    e corpus fictício são excluídos conforme quarentena/flags de config; norma
    REVOGADA nunca é recuperada e, sob RAG_EXIGIR_VIGENCIA_VERIFICADA (default),
    legislação com vigência não conferida também fica de fora.
    """
    # Tentativa 0: busca SEMÂNTICA via pgvector (se embeddings habilitados).
    # Usa distância de cosseno (operador <=> do pgvector). Cai no textual se
    # indisponível ou em erro. Esta é a busca "por significado" — encontra
    # precedentes mesmo quando o vocabulário do caso novo difere do registrado.
    # Reranking (Fase 1 — auditoria IA): recupera um POOL maior de candidatos e
    # reordena com um cross-encoder antes de cortar em `limite`. Desligado ou
    # indisponível → pool = limite e a ordem RRF é mantida (degradação graciosa;
    # ver ai/reranker.py). rerank(...) sempre devolve no máximo `limite` itens.
    from app.services.ai import reranker as _reranker
    _rerank_on = _reranker.disponivel()
    _n_pool = _reranker.tamanho_pool(limite) if _rerank_on else limite

    from app.services.embedding_service import disponivel as _emb_on, gerar_embeddings
    if not _emb_on():
        # Degradação AUDÍVEL: sem embeddings a busca vira ILIKE puro (recall
        # muito menor). Warning único por processo — visível no monitoramento.
        global _AVISOU_SEM_EMBEDDINGS
        if not _AVISOU_SEM_EMBEDDINGS:
            _AVISOU_SEM_EMBEDDINGS = True
            logger.warning(
                "RAG operando SEM busca semântica (EMBEDDINGS_ENABLED=false ou "
                "provider indisponível) — usando fallback textual ILIKE, com "
                "recall reduzido. Habilite embeddings em produção."
            )
    if _emb_on():
        # HyDE (O-6, OFF por default): enriquece SÓ a query densa; a lexical usa
        # a consulta real. modo="query": prefixo E5 só se o modelo for E5.
        consulta_emb = await _hyde_expandir(consulta)
        vetores = await gerar_embeddings([consulta_emb], modo="query")
        if vetores:
            vec = vetores[0]
            params_v: dict = {"vec": str(vec), "lim": _n_pool, "max_dist": _rag_max_dist(),
                              "restr_cats": _RESTRICTED_CATS, "scope_cli": scope_client_id or "",
                              "incl_hist": incluir_historico}
            filtro_cat_v = ""
            if categorias:
                filtro_cat_v = "AND kd.categoria = ANY(:cats)"
                params_v["cats"] = categorias
            sql_v = text(f"""
                SELECT kc.id, kc.doc_id, kc.conteudo, kd.titulo, kd.categoria, kd.fonte, kd.versao,
                       {_SQL_CONFIANCA},
                       (kc.embedding <=> :vec) AS dist
                FROM knowledge_chunks kc
                JOIN knowledge_docs kd ON kd.id = kc.doc_id
                WHERE kd.deleted_at IS NULL
                  AND kc.embedding IS NOT NULL
                  AND (kc.embedding <=> :vec) <= :max_dist
                  {filtro_cat_v}
                  {_FILTRO_ESCOPO_RAG}
                  {_FILTRO_VIGENTE_RAG}
                  {_filtros_gate_rag(incluir_ficticio)}
                ORDER BY kc.embedding <=> :vec
                LIMIT :lim
            """)
            # #13: com filtros seletivos (escopo por cliente, vigência, categoria)
            # o índice HNSW aproximado pode varrer poucos candidatos e sub-retornar
            # (precedentes internos somem do topo). Elevar ef_search nesta
            # transação amplia a lista de candidatos e melhora o recall sem trocar
            # o índice. SET LOCAL = escopo da transação apenas.
            try:
                await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
            except Exception:
                pass  # GUC ausente (índice não-HNSW/pgvector antigo) → segue igual
            try:
                rows_v = await db.execute(sql_v, params_v)
                resultados = [
                    {"chunk_id": r.id, "doc_id": r.doc_id, "conteudo": r.conteudo,
                     "titulo": r.titulo,
                     "categoria": r.categoria, "fonte": r.fonte,
                     "confianca": r.confianca,
                     "versao": getattr(r, "versao", None),
                     "score": round(1 - r.dist, 4)}   # cosine similarity
                    for r in rows_v
                ]
                if resultados:
                    # Funde a perna lexical (RRF) sobre o POOL, depois reranqueia
                    # e corta em `limite` (rerank off → devolve o RRF[:limite]).
                    fundidos = await _fundir_lexical(db, consulta, resultados, _n_pool, categorias,
                                                     scope_client_id, incluir_historico,
                                                     incluir_ficticio)
                    return await _reranker.rerank(consulta, fundidos, limite)
                # Sem vetores gravados ainda → cai no textual abaixo
            except Exception as e:
                logger.warning(f"Busca vetorial falhou, usando textual: {e}")

    # Tentativa 1: busca textual nos chunks (funciona sem embeddings)
    termos = [t for t in consulta.replace(",", " ").split() if len(t) >= 3][:8]
    params: dict = {"lim": _n_pool}
    cond_termos = ""
    if termos:
        partes = []
        for i, termo in enumerate(termos):
            partes.append(f"kc.conteudo ILIKE :t{i}")
            params[f"t{i}"] = f"%{termo}%"
        juntor = " OR " if modo_or else " AND "
        cond_termos = "AND (" + juntor.join(partes) + ")"
    else:
        params["q"] = f"%{consulta[:100]}%"
        cond_termos = "AND kc.conteudo ILIKE :q"

    filtro_cat = ""
    if categorias:
        filtro_cat = "AND kd.categoria = ANY(:cats)"
        params["cats"] = categorias
    params["restr_cats"] = _RESTRICTED_CATS
    params["scope_cli"] = scope_client_id or ""
    params["incl_hist"] = incluir_historico

    sql = text(f"""
        SELECT kc.id, kc.doc_id, kc.conteudo, kd.titulo, kd.categoria, kd.fonte, kd.versao,
               {_SQL_CONFIANCA}
        FROM knowledge_chunks kc
        JOIN knowledge_docs kd ON kd.id = kc.doc_id
        WHERE kd.deleted_at IS NULL
          {cond_termos}
          {filtro_cat}
          {_FILTRO_ESCOPO_RAG}
          {_FILTRO_VIGENTE_RAG}
          {_filtros_gate_rag(incluir_ficticio)}
        LIMIT :lim
    """)
    try:
        rows = await db.execute(sql, params)
        res_txt = [
            {
                "chunk_id": r.id, "doc_id": r.doc_id, "conteudo": r.conteudo,
                "titulo": r.titulo, "categoria": r.categoria, "fonte": r.fonte,
                "confianca": r.confianca,
                "versao": getattr(r, "versao", None),
            }
            for r in rows
        ]
        # Reranqueia também o fallback textual (rerank off → res_txt[:limite]).
        return await _reranker.rerank(consulta, res_txt, limite)
    except Exception as e:
        logger.warning(f"RAG search falhou: {e}")
        return []


def _formatar_fontes(fontes: list[dict]) -> str:
    if not fontes:
        return "[FONTES]\nNenhuma fonte encontrada na base de conhecimento.\n"
    linhas = ["[FONTES]"]
    for i, f in enumerate(fontes, start=1):
        linhas.append(
            f"[Fonte {i}] {f['titulo']} ({f['categoria']}"
            + (f" — {f['fonte']}" if f.get('fonte') else "")
            + f")\n{f['conteudo'][:800]}\n"
        )
    return "\n".join(linhas)


# ── Seleção de modelo por tamanho de contexto ─────────────────────────────────

def _modelo_para_prompt(prompt: str) -> str:
    """
    Groq llama3-70b-8192 tem janela de 8 192 tokens (~32 000 chars).
    Quando o prompt excede 20 000 chars, usa llama-3.1-70b-versatile
    (128k tokens) para evitar truncamento silencioso de dossiês grandes.
    Os dois modelos ficam na mesma API Groq — sem custo extra de chave.
    """
    if len(prompt) > 20_000:
        modelo = settings.GROQ_MODEL_LARGE
        logger.info(f"[IA] Prompt grande ({len(prompt)} chars) → {modelo}")
        return modelo
    return settings.GROQ_MODEL




async def _gateway_text(
    system_prompt: str,
    user_prompt: str,
    task_type: str = "analise_juridica",
    temperature: float = 0.15,
    max_tokens: int = 2048,
    nivel: str = "alto",
    model_override: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> tuple[str, GatewayResponse]:
    """Chamada centralizada ao AI Gateway, mantendo metadados para logs HITL.

    `entidades` (opcional): nomes próprios do caso para pseudonimização
    REVERSÍVEL no gateway (só surte efeito em tasks EXTERNO_PSEUDONIMIZADO). None
    (default) = só PII estrutural, sem quebrar os call sites existentes."""
    provider_override = "groq" if model_override else None
    resp = await gw_chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        task_type=task_type,
        temperature=temperature,
        max_tokens=max_tokens,
        model_override=model_override,
        provider_override=provider_override,
        nivel_inteligencia=nivel,
        entidades=entidades,
    )
    return resp.texto, resp


def _modelo_log(resp: object, fallback: str | None = None) -> str:
    modelo = getattr(resp, "modelo", None) or fallback or settings.GROQ_MODEL
    provedor = getattr(resp, "provedor", None)
    return f"{provedor}/{modelo}" if provedor else modelo


def _tokens_input(resp: object) -> int | None:
    usage = getattr(resp, "usage", None)
    if usage is not None:
        return getattr(usage, "prompt_tokens", None)
    return getattr(resp, "input_tokens", None)


def _tokens_output(resp: object) -> int | None:
    usage = getattr(resp, "usage", None)
    if usage is not None:
        return getattr(usage, "completion_tokens", None)
    return getattr(resp, "output_tokens", None)

# ── Funções principais ────────────────────────────────────────────────────────

async def analisar_caso(
    db: AsyncSession,
    user_id: str,
    descricao_fatos: str,
    area: str,
    nomes_proteger: list[str] | None = None,
    case_id: str | None = None,
) -> dict:
    """
    Análise de caso novo → sugestão de teses.
    Pipeline completo: sanitiza → RAG → Groq → log → resposta marcada como rascunho.
    """
    if not settings.AI_ENABLED:
        return {"erro": "IA desabilitada na configuração"}

    # 1. SANITIZAÇÃO LGPD (obrigatória)
    texto_limpo, houve_pii = sanitizar_pii(descricao_fatos, nomes_proteger)
    residual = validar_sem_pii(texto_limpo)
    if residual:
        # Segunda barreira: PII residual detectada → abortar
        logger.error(f"PII residual após sanitização: {residual}")
        return {
            "erro": f"Dados pessoais detectados ({', '.join(residual)}). "
                    "Remova CPF/CNPJ/nº processo do texto e tente novamente."
        }

    # Escopo de isolamento por cliente (Bloco 5): restrito ao client_id do caso.
    # None quando não há caso → RAG fail-closed (sem conteúdo restrito).
    escopo_cli = await _escopo_cliente_do_caso(db, case_id)

    # 2. RAG — recuperar contexto da base
    fontes = await buscar_contexto_rag(
        db, texto_limpo, limite=6,
        categorias=None,  # busca em todas; filtrar por área em fase 2
        scope_client_id=escopo_cli,
    )
    contexto = _formatar_fontes(fontes)

    # 2.a PRECEDENTES INTERNOS — casos já encerrados do próprio escritório.
    # Busca dedicada para garantir que a experiência acumulada da firma apareça,
    # mesmo que as fontes legais dominem o ranking textual. Restrita ao próprio
    # cliente via escopo — precedente de um cliente NUNCA aparece p/ outro.
    precedentes = await buscar_contexto_rag(
        db, texto_limpo, limite=3, categorias=["precedente_interno"],
        modo_or=True,   # relevância parcial é útil: poucos precedentes, vocabulário variado
        scope_client_id=escopo_cli,
    )
    contexto_precedentes = ""
    if precedentes:
        linhas = ["[PRECEDENTES INTERNOS DO ESCRITÓRIO — casos já encerrados]"]
        for i, p in enumerate(precedentes, start=1):
            linhas.append(f"[Precedente {i}] {p['titulo']}\n{p['conteudo'][:600]}\n")
        contexto_precedentes = "\n".join(linhas) + "\n\n"

    # 2.b INTERLIGAÇÃO — se há case_id, carregar o dossiê consolidado do caso.
    # Isso faz a IA "enxergar" todo o sistema: cliente, ramo especializado,
    # prazos, honorários, peças e histórico — já sanitizado (LGPD).
    dossie_txt = ""
    nomes_caso: list[str] = []
    if case_id:
        dossie = await montar_dossie(db, case_id, incluir_pecas=True, sanitizar=True)
        if dossie:
            dossie_txt = dossie["texto"] + "\n\n"
            nomes_caso = dossie["nomes_proteger"]
            # Re-sanitizar os fatos colados com os nomes descobertos no dossiê
            if nomes_caso:
                texto_limpo, _ = sanitizar_pii(texto_limpo, nomes_caso)

    # 3. Chamada Groq
    prompt_usuario = (
        f"ÁREA JURÍDICA: {area}\n\n"
        f"{dossie_txt}"
        f"{contexto_precedentes}"
        f"{contexto}\n\n"
        f"FATOS DO CASO (sanitizados):\n{texto_limpo}\n\n"
        f"Analise considerando TODO o contexto do dossiê acima (prazos, dados "
        f"especializados, peças já produzidas) e os precedentes internos do "
        f"escritório, e sugira as teses possíveis seguindo o formato."
    )

    modelo_usar = _modelo_para_prompt(prompt_usuario)
    modelo_override = modelo_usar if modelo_usar != settings.GROQ_MODEL else None
    try:
        resposta, resp = await _gateway_text(
            SYSTEM_ANALISE_CASO, prompt_usuario,
            task_type="estrategia", temperature=0.15, max_tokens=2600,
            nivel="alto", model_override=modelo_override,
        )
    except Exception as e:
        logger.error(f"AI Gateway falhou: {e}")
        return {"erro": f"Falha na IA: {str(e)[:200]}"}

    # 4. AI LOG (rastreabilidade LGPD + HITL)
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=_modelo_log(resp, modelo_usar),
        prompt_sanitizado=prompt_usuario[:8000],
        pii_removida=houve_pii,
        resposta=resposta,
        fontes_rag="; ".join(f["chunk_id"] for f in fontes) or None,
        tokens_input=_tokens_input(resp),
        tokens_output=_tokens_output(resp),
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    # 5. Resposta — SEMPRE marcada como rascunho
    return {
        "ai_log_id": log.id,
        "resposta": resposta,
        "fontes_usadas": len(fontes),
        "pii_removida": houve_pii,
        "aviso": "⚠️ RASCUNHO gerado por IA — revisão por advogado OBRIGATÓRIA "
                 "antes de qualquer uso (Provimento OAB 205/2021).",
        "status_hitl": "gerado",
    }


async def resumir_documento(
    db: AsyncSession, user_id: str, texto_documento: str,
    case_id: str | None = None,
) -> dict:
    """Resume documento (intimação, decisão) — mesma pipeline de segurança."""
    if not settings.AI_ENABLED:
        return {"erro": "IA desabilitada"}

    texto_limpo, houve_pii = sanitizar_pii(texto_documento[:12000])

    try:
        # FASE 1b (MAPA §5 Passo 2): task de PROSA coberto pela base central
        # ("resumo" NÃO recebe aplicar_base — legal_base._TASKS_COM_BASE).
        # "chat_rapido" mantém o tier leve (ollama chat → maritaca rápido →
        # groq) e garante a barreira anti-alucinação central. A regra inline
        # de SYSTEM_RESUMO_DOC é preservada (mudança aditiva).
        resposta, resp = await _gateway_text(
            SYSTEM_RESUMO_DOC, texto_limpo,
            task_type="chat_rapido", temperature=0.1, max_tokens=1200, nivel="alto",
        )
    except Exception as e:
        return {"erro": f"Falha na IA: {str(e)[:200]}"}

    log = AILog(
        id=str(uuid4()), user_id=user_id, case_id=case_id,
        tipo_uso=AITipoUso.resumo_documento, modelo=_modelo_log(resp),
        prompt_sanitizado=texto_limpo[:8000], pii_removida=houve_pii,
        resposta=resposta,
        tokens_input=_tokens_input(resp), tokens_output=_tokens_output(resp),
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id": log.id, "resposta": resposta,
        "aviso": "⚠️ Resumo gerado por IA — confira com o documento original.",
    }


SYSTEM_EXTRACAO_PRAZOS = """Você é um assistente jurídico brasileiro especializado em identificar PRAZOS processuais e contratuais em documentos (intimações, decisões, despachos, contratos).

REGRAS ABSOLUTAS:
- NUNCA invente prazo, data ou base legal que não esteja no texto.
- Se não houver data fatal clara (termo final) para um prazo, NÃO inclua o item.
- Responda APENAS com JSON válido, sem comentários nem texto ao redor.

FORMATO (obrigatório):
{"prazos": [{"tipo": "contestação|recurso|manifestação|...", "data_base": "descrição da data-base, se houver", "termo_final": "dd/mm/aaaa", "fatal": true, "base_legal": "dispositivo citado no texto, se houver"}]}

Sem prazos identificáveis → {"prazos": []}."""


async def extrair_prazos_ia(
    db: AsyncSession, user_id: str, texto: str,
    case_id: str | None = None,
) -> dict:
    """Extração de prazos por IA (endpoint /ai/detectar-prazos).

    Mesma pipeline de segurança do resumir_documento: sanitização LGPD →
    gateway → AILog (HITL). O parse reaproveita o caminho fail-safe do intake
    (`_parse_json`/`_prazos_extraidos` de documento_service): item sem data
    fatal parseável é DESCARTADO — a IA nunca materializa prazo inventado.
    """
    if not settings.AI_ENABLED:
        return {"erro": "IA desabilitada"}

    texto_limpo, houve_pii = sanitizar_pii(texto[:12000])

    try:
        # Fluxo JSON com task fora de _TASKS_COM_BASE ("resumo" — por design):
        # PREPENDE BASE_ESTRUTURADA no system (padrão peca_service/ia_extra
        # sugestao-honorarios) — barreira anti-alucinação sem quebrar o parse.
        resposta, resp = await _gateway_text(
            BASE_ESTRUTURADA + "\n\n" + SYSTEM_EXTRACAO_PRAZOS, texto_limpo,
            task_type="resumo", temperature=0.0, max_tokens=1500, nivel="alto",
        )
    except Exception as e:
        logger.error(f"AI Gateway (detectar-prazos) falhou: {e}")
        return {"erro": f"Falha na IA: {str(e)[:200]}"}

    from app.services.documento_service import _parse_json, _prazos_extraidos
    llm = _parse_json(resposta) or {}
    prazos = [p.model_dump() for p in _prazos_extraidos(llm)]

    log = AILog(
        id=str(uuid4()), user_id=user_id, case_id=case_id,
        tipo_uso=AITipoUso.outro, modelo=_modelo_log(resp),
        prompt_sanitizado=texto_limpo[:8000], pii_removida=houve_pii,
        resposta=resposta,
        tokens_input=_tokens_input(resp), tokens_output=_tokens_output(resp),
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id": log.id,
        "prazos": prazos,
        "total": len(prazos),
        "pii_removida": houve_pii,
        "aviso": "⚠️ Prazos extraídos por IA — RASCUNHO. Conferência e cálculo "
                 "pelo advogado responsável OBRIGATÓRIOS antes de registrar.",
        "status_hitl": "gerado",
    }


async def _log_ai(db, user_id, tipo_uso_str, prompt, resposta,
                  pii, fontes, resp_groq, case_id):
    """Helper de log para as funções ECJ — mesmo padrão do analisar_caso."""
    log = AILog(
        id=str(uuid4()), user_id=user_id, case_id=case_id,
        tipo_uso=AITipoUso(tipo_uso_str),
        modelo=_modelo_log(resp_groq),
        prompt_sanitizado=prompt[:8000],
        pii_removida=pii,
        resposta=resposta,
        fontes_rag="; ".join(f["chunk_id"] for f in fontes) or None if fontes else None,
        tokens_input=_tokens_input(resp_groq),
        tokens_output=_tokens_output(resp_groq),
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# MELHORIAS ECJ — Inteligência Jurídica (Groq llama3-70b existente)
# Todas as saídas: rascunho HITL, sanitização LGPD, fontes citadas.
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_TESES_OCULTAS = """Você é um advogado sênior brasileiro revisor de estratégia.
Sua função: identificar TESES ADICIONAIS que o advogado pode não ter percebido.

REGRAS ABSOLUTAS:
- NUNCA invente jurisprudência, súmula ou artigo de lei. Use APENAS as fontes fornecidas em [Fonte N] ou conhecimento consolidado citando o dispositivo exato.
- Se não houver fonte para uma tese, escreva "(verificar jurisprudência)".
- NUNCA prometa êxito.

FORMATO DA RESPOSTA (obrigatório):
## Teses identificadas

### 🔴 Alta relevância
- **[nome da tese]**: fundamento legal + por que se aplica + prova necessária

### 🟡 Média relevância
(mesmo formato)

### ⚪ Baixa relevância / acessórias
(mesmo formato)

## Pedidos acessórios possíveis
(lista: juros, correção, honorários sucumbenciais, tutela, etc.)

Cite [Fonte N] sempre que usar material fornecido."""

SYSTEM_AUDITOR_PECA = """Você é um auditor técnico de peças jurídicas brasileiras.
Analise a peça e produza um RELATÓRIO DE AUDITORIA.

REGRAS:
- NUNCA invente lei ou jurisprudência. Aponte ausências, não preencha com invenção.
- Seja específico: cite o trecho problemático.

FORMATO (obrigatório):
## Pontuação técnica: X/100

## ✅ Pontos fortes
## ⚠️ Omissões detectadas
(requisitos processuais, pedidos sem fundamento, fundamentos sem pedido)
## ❌ Inconsistências
(contradições internas, valores divergentes, datas conflitantes)
## 📋 Estrutura
(endereçamento, qualificação, fatos, direito, pedidos, valor da causa, provas)
## 🔧 Recomendações de correção
(lista priorizada)

Pontuação: estrutura 30pts, fundamentação 30pts, coerência 20pts, completude 20pts."""

SYSTEM_AUDIENCIA = """Você é um preparador de audiências de um escritório brasileiro.
Com base no caso fornecido, gere o KIT DE PREPARAÇÃO.

REGRAS: nunca invente fatos não fornecidos; nunca prometa resultado.

FORMATO (obrigatório):
## Resumo do caso (5 linhas)
## 💪 Pontos fortes a explorar
## ⚠️ Pontos fracos / riscos (e como mitigar)
## ❓ Perguntas sugeridas
### Para a parte contrária
### Para testemunhas
## 🚫 Perguntas a EVITAR (que abrem flanco)
## 📌 Checklist do dia
(documentos a levar, propostas de acordo: faixa sugerida se aplicável)"""


async def detectar_teses_ocultas(
    db, user_id: str, descricao_fatos: str, area: str,
    tese_principal: str | None = None,
    nomes_proteger: list[str] | None = None,
    case_id: str | None = None,
    scope_client_id: str | None = None,
) -> dict:
    """Detector de Teses Ocultas — ranking por relevância.

    scope_client_id (Bloco 5): o CHAMADOR deve verificar ownership do case_id
    e derivar o escopo (ver routers/ai.py::teses_ocultas) — esta função de
    serviço não tem acesso ao usuário autenticado para checar isso sozinha."""
    # Pseudonimização REVERSÍVEL dos nomes do caso (PR #85): com case_id, deriva
    # as ENTIDADES e deixa o gateway pseudonimizar/reidratar — as teses voltam
    # com o NOME REAL. Sem case_id (fatos livres), mantém o mascaramento
    # IRREVERSÍVEL legado via nomes_proteger. entidades_do_caso é fail-safe.
    entidades = None
    if case_id:
        from app.services.ai.entidades_caso import entidades_do_caso
        entidades = await entidades_do_caso(db, case_id) or None

    texto, pii = sanitizar_pii(descricao_fatos, (nomes_proteger or []) if not entidades else None)
    residual = validar_sem_pii(texto)
    if residual:
        return {"erro": f"Sanitização incompleta: {residual}. Revise o texto."}

    fontes = await buscar_contexto_rag(db, f"{area} {texto[:200]}", limite=6, scope_client_id=scope_client_id)
    contexto = _formatar_fontes(fontes)

    user_msg = (
        f"Área: {area}\n"
        f"Tese principal já considerada: {tese_principal or 'não informada'}\n\n"
        f"FATOS (sanitizados):\n{texto}\n\n"
        f"FONTES DA BASE INTERNA:\n{contexto}"
    )
    try:
        conteudo, resp = await _gateway_text(
            SYSTEM_TESES_OCULTAS, user_msg,
            task_type="estrategia", temperature=0.2, max_tokens=2400, nivel="alto",
            entidades=entidades,
        )
        # LGPD — AILog.prompt_sanitizado é "SEM PII". Com `entidades` o user_msg
        # tem nomes em claro (o gateway só os pseudonimiza no envio ao externo);
        # pseudonimizamos AQUI apenas o valor logado (marcadores), preservando o
        # que foi enviado e a resposta reidratada.
        prompt_log = user_msg
        if entidades:
            from app.services.ai.pseudonymizer import pseudonimizar
            prompt_log = pseudonimizar(user_msg, entidades)[0]
        await _log_ai(db, user_id, "analise_caso", prompt_log, conteudo,
                      pii, fontes, resp, case_id)
        return {
            "resposta": conteudo,
            "fontes_usadas": len(fontes),
            "pii_removida": pii,
            "aviso": "⚠️ RASCUNHO — teses exigem verificação e validação do advogado (HITL).",
        }
    except Exception as e:
        logger.error(f"Groq teses ocultas: {e}")
        return {"erro": "Serviço de IA indisponível no momento"}


async def auditar_peca(
    db, user_id: str, conteudo_peca: str, tipo_peca: str,
    case_id: str | None = None,
) -> dict:
    """Auditor de Petições — pontuação técnica + omissões."""
    texto, pii = sanitizar_pii(conteudo_peca, [])
    user_msg = f"Tipo de peça: {tipo_peca}\n\nPEÇA (sanitizada):\n{texto[:12000]}"
    try:
        conteudo, resp = await _gateway_text(
            SYSTEM_AUDITOR_PECA, user_msg,
            task_type="auditoria_peca", temperature=0.15, max_tokens=2400, nivel="alto",
        )
        await _log_ai(db, user_id, "outro", user_msg[:4000], conteudo,
                      pii, [], resp, case_id)
        return {
            "resposta": conteudo, "pii_removida": pii,
            "aviso": "⚠️ Auditoria automática — não substitui a revisão do advogado.",
        }
    except Exception as e:
        logger.error(f"Groq auditor: {e}")
        return {"erro": "Serviço de IA indisponível no momento"}


async def preparar_audiencia(
    db, user_id: str, resumo_caso: str, tipo_audiencia: str,
    nomes_proteger: list[str] | None = None,
    case_id: str | None = None,
) -> dict:
    """Assistente de Audiência — kit de preparação."""
    texto, pii = sanitizar_pii(resumo_caso, nomes_proteger or [])
    user_msg = f"Tipo de audiência: {tipo_audiencia}\n\nCASO (sanitizado):\n{texto[:8000]}"
    try:
        conteudo, resp = await _gateway_text(
            SYSTEM_AUDIENCIA, user_msg,
            task_type="estrategia", temperature=0.2, max_tokens=2400, nivel="alto",
        )
        await _log_ai(db, user_id, "outro", user_msg[:4000], conteudo,
                      pii, [], resp, case_id)
        return {
            "resposta": conteudo, "pii_removida": pii,
            "aviso": "⚠️ Material preparatório — adapte à sua estratégia.",
        }
    except Exception as e:
        logger.error(f"Groq audiência: {e}")
        return {"erro": "Serviço de IA indisponível no momento"}


SYSTEM_ANALISE_CONTRATO = """Você é um advogado contratualista brasileiro revisando uma minuta.
Produza um RELATÓRIO DE ANÁLISE CONTRATUAL para apoio à decisão do advogado.

REGRAS INVIOLÁVEIS:
- NUNCA invente dispositivo de lei, súmula ou número de artigo. Use APENAS o que
  estiver em [FONTES]; se não houver base, escreva "verificar base legal".
- Aponte riscos e lacunas; não os preencha com invenção.
- Cite o trecho/cláusula problemática ao apontar cada ponto.
- Não afirme que uma cláusula é "nula" em definitivo — diga "possivelmente
  abusiva/questionável" e remeta à análise do advogado.

FORMATO (obrigatório):
## Resumo do objeto
## ⚠️ Cláusulas de risco / possivelmente abusivas
(para cada uma: trecho, risco, e — se houver em [FONTES] — base legal)
## 🕳️ Lacunas e proteções ausentes
(garantias, multas, rescisão, foro, LGPD, reajuste, caso fortuito)
## ⚖️ Desequilíbrios entre as partes
## 🔧 Sugestões de ajuste (priorizadas)

Use exclusivamente as [FONTES] fornecidas para qualquer afirmação legal."""


SYSTEM_COMPARACAO_CONTRATOS = """Você é um advogado contratualista brasileiro comparando DUAS minutas de contrato.
Produza um RELATÓRIO DE COMPARAÇÃO CONTRATUAL, cláusula a cláusula, para apoio
à decisão do advogado.

REGRAS INVIOLÁVEIS:
- NUNCA invente dispositivo de lei, súmula ou número de artigo. Use APENAS o que
  estiver em [FONTES]; se não houver base, escreva "verificar base legal".
- Cite o trecho/cláusula de CADA contrato ao comparar cada ponto.
- NÃO prometa resultado nem afirme nulidade em definitivo — diga "possivelmente
  abusiva/questionável" e remeta à análise do advogado.

FORMATO (obrigatório):
## Resumo dos objetos (Contrato 1 × Contrato 2)
## 🔍 Comparação cláusula a cláusula
(para cada tema — objeto, preço/reajuste, prazo, rescisão, multas, garantias,
foro, LGPD, responsabilidades: qual contrato é MAIS FAVORÁVEL e POR QUÊ,
citando os trechos)
## ⚠️ Riscos exclusivos de cada contrato
## ⚖️ Conclusão comparativa
(qual minuta tende a ser mais favorável, com ressalvas — decisão final é do advogado)

Use exclusivamente as [FONTES] fornecidas para qualquer afirmação legal."""


async def analisar_contrato(
    db: AsyncSession, user_id: str, texto_contrato: str,
    tipo_contrato: str = "geral",
    nomes_proteger: list[str] | None = None,
    case_id: str | None = None,
    texto_contrato_2: str | None = None,
    modo: str | None = None,
) -> dict:
    """Análise de contrato (Bloco E) — sanitiza → RAG (CC/CDC) → Groq → log HITL.

    modo="comparacao" + texto_contrato_2: compara as duas minutas cláusula a
    cláusula (qual é mais favorável e por quê), mesmo fluxo LGPD/HITL.
    Saída é MINUTA de análise: o advogado revisa antes de qualquer uso.
    """
    if not settings.AI_ENABLED:
        return {"erro": "IA desabilitada na configuração"}

    comparacao = (modo or "").strip().lower() == "comparacao" and bool(
        (texto_contrato_2 or "").strip()
    )

    # 1) Sanitização LGPD (dupla barreira, como nas demais funções)
    texto, pii = sanitizar_pii(texto_contrato, nomes_proteger or [])
    residual = validar_sem_pii(texto)
    if residual:
        logger.error(f"PII residual após sanitização (contrato): {residual}")
        return {"erro": "Não foi possível sanitizar dados pessoais com segurança."}

    texto2 = ""
    if comparacao:
        texto2, pii2 = sanitizar_pii(texto_contrato_2 or "", nomes_proteger or [])
        residual2 = validar_sem_pii(texto2)
        if residual2:
            logger.error(f"PII residual após sanitização (contrato 2): {residual2}")
            return {"erro": "Não foi possível sanitizar dados pessoais com segurança."}
        pii = pii or pii2

    # 2) Recuperação no RAG — legislação relevante (CC, CDC) por termos do contrato
    consulta = f"{tipo_contrato} contrato cláusula abusiva rescisão multa garantia"
    fontes = await buscar_contexto_rag(
        db, consulta, limite=6, categorias=["legislacao"]
    )
    bloco_fontes = _formatar_fontes(fontes)

    if comparacao:
        user_msg = (
            f"Tipo de contrato: {tipo_contrato}\n\n{bloco_fontes}\n\n"
            f"CONTRATO 1 (sanitizado):\n{texto[:8000]}\n\n"
            f"CONTRATO 2 (sanitizado):\n{texto2[:8000]}"
        )
    else:
        user_msg = (
            f"Tipo de contrato: {tipo_contrato}\n\n{bloco_fontes}\n\n"
            f"CONTRATO (sanitizado):\n{texto[:12000]}"
        )
    system = SYSTEM_COMPARACAO_CONTRATOS if comparacao else SYSTEM_ANALISE_CONTRATO
    try:
        # FASE 1b (MAPA §5 Passo 2): "analise_contrato" está no TASK_ROUTING mas
        # FORA de legal_base._TASKS_COM_BASE (sem base central). A saída aqui é
        # PROSA (relatório de auditoria de minuta contratual) → task coberto
        # "auditoria_peca" (mesma cadeia anthropic/groq; ollama muda de
        # OLLAMA_MODEL_CONTRATO p/ OLLAMA_MODEL_PETICAO — revisão textual).
        # Não ampliamos _TASKS_COM_BASE com "analise_contrato" porque o
        # BankForensicsAgent (ai/core/orchestrator.py) usa esse task para saída
        # ESTRUTURADA — injetar a base de prosa lá arriscaria o parse.
        # As REGRAS INVIOLÁVEIS inline dos prompts são preservadas (aditivo).
        conteudo, resp = await _gateway_text(
            system, user_msg,
            task_type="auditoria_peca", temperature=0.15,
            max_tokens=3200 if comparacao else 2800, nivel="alto",
        )
        await _log_ai(db, user_id, "outro", user_msg[:4000], conteudo,
                      pii, fontes, resp, case_id)
        return {
            "resposta": conteudo,
            "pii_removida": pii,
            "modo": "comparacao" if comparacao else "analise",
            "fontes": [{"titulo": f["titulo"], "categoria": f["categoria"],
                        "fonte": f.get("fonte")} for f in fontes],
            "aviso": "⚠️ Análise automática (minuta) — não substitui a revisão "
                     "do advogado responsável. Base legal limitada às fontes citadas.",
        }
    except Exception as e:
        logger.error(f"Groq contrato: {e}")
        return {"erro": "Serviço de IA indisponível no momento"}
