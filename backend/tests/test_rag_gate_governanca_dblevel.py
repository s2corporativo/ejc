"""Auditoria RAG — validação ROW-LEVEL (Postgres real) dos gates de governança,
quarentena de súmulas, exclusão do corpus fictício e do versionamento de
`chave_origem` (migration 092).

Fecha os bloqueadores P0 apontados na auditoria:
  * documento explicitamente BLOQUEADO/RECUSADO/PENDENTE nunca é recuperado;
  * súmulas do seed (fonte='sumula' / chave 'sumula:%') ficam em QUARENTENA;
  * corpus FICTÍCIO (extra.ficticio=true) é excluído das buscas amplas e só
    entra com incluir_ficticio=True (geração de peça a partir de modelos);
  * reingerir a MESMA `chave_origem` com conteúdo novo cria nova versão vigente
    sem colidir com o índice único parcial (antes: IntegrityError);
  * SITUAÇÃO JURÍDICA (Issue #636): norma REVOGADA nunca é recuperada (com ou
    sem flag) e legislação com vigência não conferida segue
    RAG_EXIGIR_VIGENCIA_VERIFICADA — sem alcançar o que não é legislação.

Requer Postgres com pg_trgm + pgvector e migrations aplicadas. Roda só quando
RUN_DB_TESTS=1 (job de CI `db-validation`); caso contrário, pula. Determinístico:
usa o caminho TEXTUAL (ILIKE) de buscar_contexto_rag (embeddings desligados).
"""
from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste(monkeypatch):
    """Descarta o pool do engine singleton no MESMO event loop que o usou —
    ver justificativa detalhada em test_rag_isolation_dblevel.py."""
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import engine
    await engine.dispose()


async def _ins(db, *, titulo, categoria, conteudo, chave_origem, fonte=None, extra=None,
               vigente=True):
    """Insere doc + 1 chunk textual (caminho ILIKE, sem embeddings)."""
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO knowledge_docs (id, titulo, categoria, fonte, chave_origem, "
            "vigente, status_indexacao, extra) "
            "VALUES (:id,:t,:c,:f,:k, :vig, 'indexado', CAST(:e AS jsonb))"
        ),
        {"id": doc_id, "t": titulo, "c": categoria, "f": fonte, "k": chave_origem,
         "vig": vigente, "e": json.dumps(extra or {})},
    )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, 0, :cont)"
        ),
        {"id": str(uuid4()), "doc": doc_id, "cont": conteudo},
    )
    return doc_id


async def test_gate_bloqueado_e_pendente_nao_recuperados():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzgate{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        # O documento de CONTROLE é legislação corretamente ingerida no mundo
        # pós-P0.1: aprovado na curadoria E com vigência 'vigente' COM
        # proveniência positiva completa (origem, data de verificação e SEM
        # carimbo de inferência). Sem isso sairia pelo gate de vigência estrito.
        await _ins(db, titulo="GATE_OK", categoria="legislacao",
                   conteudo=f"norma valida {termo}", chave_origem=f"n:{uuid4()}",
                   extra={"rag_status": "aprovado", "legal_status": "vigente",
                          "legal_status_origem": "planalto:texto_compilado",
                          "legal_status_verificado_em": "2026-08-01T10:00:00Z"})
        await _ins(db, titulo="GATE_BLOQUEADO", categoria="legislacao",
                   conteudo=f"norma bloqueada {termo}", chave_origem=f"b:{uuid4()}",
                   extra={"confidence_level": "bloqueado"})
        await _ins(db, titulo="GATE_RECUSADO", categoria="legislacao",
                   conteudo=f"norma recusada {termo}", chave_origem=f"r:{uuid4()}",
                   extra={"rag_status": "recusado"})
        await _ins(db, titulo="GATE_PENDENTE", categoria="legislacao",
                   conteudo=f"norma pendente {termo}", chave_origem=f"p:{uuid4()}",
                   extra={"rag_status": "pendente"})
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "GATE_OK" in titulos, "doc aprovado/legado deveria ser recuperado"
            assert "GATE_BLOQUEADO" not in titulos, "VAZAMENTO: doc bloqueado recuperado"
            assert "GATE_RECUSADO" not in titulos, "VAZAMENTO: doc recusado recuperado"
            assert "GATE_PENDENTE" not in titulos, "VAZAMENTO: doc pendente recuperado"
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'GATE_%'"))
            await db.commit()


async def test_sumulas_em_quarentena_nao_recuperadas():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzsum{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        # marcador 1: fonte='sumula'; marcador 2: chave_origem 'sumula:%'
        await _ins(db, titulo="SUMULA_FONTE", categoria="trabalhista",
                   conteudo=f"verbete sumular {termo}", chave_origem=f"x:{uuid4()}",
                   fonte="sumula")
        await _ins(db, titulo="SUMULA_CHAVE", categoria="trabalhista",
                   conteudo=f"outro verbete {termo}", chave_origem=f"sumula:{uuid4()}")
        await _ins(db, titulo="NAO_SUMULA", categoria="trabalhista",
                   conteudo=f"jurisprudencia comum {termo}", chave_origem=f"j:{uuid4()}",
                   extra={"rag_status": "aprovado"})
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "NAO_SUMULA" in titulos
            assert "SUMULA_FONTE" not in titulos, "quarentena falhou (fonte=sumula)"
            assert "SUMULA_CHAVE" not in titulos, "quarentena falhou (chave sumula:)"
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE titulo IN "
                "('SUMULA_FONTE','SUMULA_CHAVE','NAO_SUMULA')"))
            await db.commit()


async def test_ficticio_excluido_por_padrao_incluido_sob_demanda():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzfic{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="FIC_MODELO", categoria="modelo_documento_juridico",
                   conteudo=f"modelo ficticio {termo}", chave_origem=f"f:{uuid4()}",
                   extra={"ficticio": True, "rag_status": "aprovado"})
        await db.commit()
        try:
            # busca ampla (fundamentação) → fictício NÃO aparece
            amplo = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "FIC_MODELO" not in {r["titulo"] for r in amplo}, (
                "corpus fictício vazou em busca ampla (fundamentação)")
            # geração de peça (opt-in) → fictício disponível como estrutura
            modelos = await buscar_contexto_rag(
                db, termo, limite=20, modo_or=True,
                categorias=["modelo_documento_juridico"], incluir_ficticio=True)
            assert "FIC_MODELO" in {r["titulo"] for r in modelos}, (
                "incluir_ficticio=True deveria liberar o corpus de modelos")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo = 'FIC_MODELO'"))
            await db.commit()


async def test_regime_estrito_exclui_documento_legado_sem_aprovacao():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzlegacy{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="LEGADO_SEM_CURADORIA", categoria="legislacao",
                   conteudo=f"norma antiga {termo}", chave_origem=f"legacy:{uuid4()}")
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            assert "LEGADO_SEM_CURADORIA" not in {r["titulo"] for r in res}
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE titulo='LEGADO_SEM_CURADORIA'"))
            await db.commit()


async def test_norma_revogada_nao_e_recuperada(monkeypatch):
    """Issue #636: curadoria e vigência são campos DISTINTOS — um documento
    'aprovado' e revogado ao mesmo tempo não pode voltar como fundamentação."""
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service
    from app.services.ai_service import buscar_contexto_rag

    # flag OFF de propósito: a exclusão do revogado NÃO depende dela
    monkeypatch.setattr(ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", False)
    termo = f"zzrevog{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="VIG_VIGENTE", categoria="legislacao",
                   conteudo=f"norma em vigor {termo}", chave_origem=f"v:{uuid4()}",
                   extra={"rag_status": "aprovado", "legal_status": "vigente"})
        await _ins(db, titulo="VIG_REVOGADA", categoria="legislacao",
                   conteudo=f"norma revogada {termo}", chave_origem=f"rv:{uuid4()}",
                   extra={"rag_status": "aprovado", "legal_status": "revogada"})
        await _ins(db, titulo="VIG_REVOGADA_ALIAS", categoria="legislacao",
                   conteudo=f"norma revogada alias {termo}", chave_origem=f"ra:{uuid4()}",
                   extra={"rag_status": "aprovado", "situacao_normativa": " REVOGADA "})
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, termo, limite=20, modo_or=True)
            titulos = {r["titulo"] for r in res}
            assert "VIG_VIGENTE" in titulos, "norma vigente deveria ser recuperada"
            assert "VIG_REVOGADA" not in titulos, "VAZAMENTO: norma revogada recuperada"
            assert "VIG_REVOGADA_ALIAS" not in titulos, (
                "VAZAMENTO: revogação declarada em situacao_normativa ignorada")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'VIG_%'"))
            await db.commit()


async def test_vigencia_nao_verificada_segue_a_flag_sem_esvaziar_a_base(monkeypatch):
    """Com RAG_EXIGIR_VIGENCIA_VERIFICADA ligada, legislação sem vigência
    declarada sai da recuperação; desligada, volta. Em NENHUM dos dois casos o
    filtro alcança documento que não é legislação (a governança devolve
    'nao_aplicavel' para esses, que permite fundamentação)."""
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzverif{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="VER_LEG_SEM_STATUS", categoria="legislacao",
                   conteudo=f"norma sem vigencia declarada {termo}",
                   chave_origem=f"ns:{uuid4()}", extra={"rag_status": "aprovado"})
        await _ins(db, titulo="VER_LEG_DECLARADA", categoria="legislacao",
                   conteudo=f"norma com vigencia declarada {termo}",
                   chave_origem=f"cd:{uuid4()}",
                   extra={"rag_status": "aprovado", "legal_status": "vigente",
                          "legal_status_origem": "planalto:texto_compilado",
                          "legal_status_verificado_em": "2026-08-01T10:00:00Z"})
        await _ins(db, titulo="VER_JURIS_COMUM", categoria="jurisprudencia",
                   conteudo=f"acordao comum sem vigencia {termo}",
                   chave_origem=f"jc:{uuid4()}", extra={"rag_status": "aprovado"})
        await db.commit()
        try:
            monkeypatch.setattr(
                ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", True)
            estrito = {r["titulo"] for r in
                       await buscar_contexto_rag(db, termo, limite=20, modo_or=True)}
            assert "VER_LEG_SEM_STATUS" not in estrito, (
                "VAZAMENTO: legislação com vigência não conferida recuperada")
            assert "VER_LEG_DECLARADA" in estrito
            assert "VER_JURIS_COMUM" in estrito, (
                "efeito colateral: o filtro esvaziou conteúdo que não é legislação")

            monkeypatch.setattr(
                ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", False)
            frouxo = {r["titulo"] for r in
                      await buscar_contexto_rag(db, termo, limite=20, modo_or=True)}
            assert "VER_LEG_SEM_STATUS" in frouxo, (
                "com a flag desligada o acervo não conferido deve voltar")
            assert {"VER_LEG_DECLARADA", "VER_JURIS_COMUM"} <= frouxo
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'VER_%'"))
            await db.commit()


async def test_proposicao_legislativa_fica_fora_por_decisao_e_nao_por_acidente():
    """O recorte `categoria LIKE '%legisl%'` também alcança
    `proposicao_legislativa` (ingestores da Câmara e do Senado), que NÃO grava
    `legal_status`. A exclusão é INTENCIONAL e PERMANENTE — projeto em
    tramitação não pode fundamentar peça como lei em vigor — e está registrada
    no `.env.example` e no comentário do filtro. Este teste existe para que a
    decisão fique medida: se alguém trocar o recorte por uma lista fechada de
    categorias, a proposição volta ao RAG e o teste avisa."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    termo = f"zzprop{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="PROP_TRAMITACAO", categoria="proposicao_legislativa",
                   conteudo=f"projeto de lei em tramitacao {termo}",
                   chave_origem=f"pl:{uuid4()}", extra={"rag_status": "aprovado"})
        await _ins(db, titulo="PROP_JURIS_CONTROLE", categoria="jurisprudencia",
                   conteudo=f"acordao de controle {termo}",
                   chave_origem=f"jx:{uuid4()}", extra={"rag_status": "aprovado"})
        await db.commit()
        try:
            titulos = {r["titulo"] for r in
                       await buscar_contexto_rag(db, termo, limite=20, modo_or=True)}
            assert "PROP_TRAMITACAO" not in titulos, (
                "proposição em tramitação não é lei vigente e não pode voltar "
                "como fundamentação")
            assert "PROP_JURIS_CONTROLE" in titulos, (
                "o recorte vazou para fora da faixa de legislação")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'PROP_%'"))
            await db.commit()


async def test_versao_historica_de_legislacao_nao_e_tratada_como_nao_verificada():
    """`inferir_situacao_juridica` testa `vigente` ANTES do extra e devolve
    'historica' — situação DECLARADA — para qualquer versão não vigente. O
    espelho SQL precisa reproduzir esse ramo: sem isso, o acervo histórico de
    legislação sem `legal_status` sumia, e com ele o aviso "possivelmente
    desatualizada" de `_artigo_superado`/`_sumula_superada`, que consultam
    `vigente = FALSE` justamente para produzi-lo."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag
    from app.services.knowledge_governance import inferir_situacao_juridica
    from app.models.rag import KnowledgeDoc

    # o que a governança diz sobre este documento — a referência do espelho
    situacao = inferir_situacao_juridica(
        KnowledgeDoc(titulo="x", categoria="legislacao", extra={}, vigente=False))
    assert situacao["code"] == "historica"

    termo = f"zzhist{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="HIST_LEG_SEM_STATUS", categoria="legislacao",
                   conteudo=f"redacao anterior da norma {termo}",
                   chave_origem=f"h:{uuid4()}", extra={"rag_status": "aprovado"},
                   vigente=False)
        await _ins(db, titulo="HIST_LEG_REVOGADA", categoria="legislacao",
                   conteudo=f"redacao anterior de norma revogada {termo}",
                   chave_origem=f"hr:{uuid4()}", vigente=False,
                   extra={"rag_status": "aprovado", "legal_status": "revogada"})
        await db.commit()
        try:
            titulos = {r["titulo"] for r in await buscar_contexto_rag(
                db, termo, limite=20, modo_or=True, incluir_historico=True)}
            assert "HIST_LEG_SEM_STATUS" in titulos, (
                "versão histórica é 'historica' na governança, não "
                "'vigencia_nao_verificada' — o gate de vigência não pode "
                "removê-la da auditoria de citações antigas")
            assert "HIST_LEG_REVOGADA" not in titulos, (
                "VAZAMENTO: revogação declarada vale também no histórico — o "
                "filtro do revogado lê o extra INDEPENDENTE de kd.vigente")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE titulo LIKE 'HIST_%'"))
            await db.commit()


async def test_verificador_citacao_usa_mesmos_gates_do_rag():
    from app.core.database import AsyncSessionLocal
    from app.services.citation_check import _existe_sumula

    async with AsyncSessionLocal() as db:
        await _ins(db, titulo="Súmula STJ nº 997", categoria="sumula_stj",
                   conteudo="verbete oficial aprovado para teste de citação",
                   chave_origem="sumula:stj:997",
                   extra={"rag_status": "aprovado", "conferido": True})
        await _ins(db, titulo="Súmula STJ nº 998", categoria="sumula_stj",
                   conteudo="verbete ainda pendente para teste de citação",
                   chave_origem="sumula:stj:998",
                   extra={"rag_status": "pendente", "conferido": True})
        await db.commit()
        try:
            assert await _existe_sumula(db, "997", "STJ") == "Súmula STJ nº 997"
            assert await _existe_sumula(db, "998", "STJ") is None
        finally:
            await db.execute(text(
                "DELETE FROM knowledge_docs WHERE chave_origem IN "
                "('sumula:stj:997','sumula:stj:998')"))
            await db.commit()


async def test_refeed_do_ingestor_nao_reverte_vigencia_decidida_por_curador():
    """Review de segurança do PR #642, provado no banco: o curador marca o
    diploma como 'revogada' no painel; o job semanal do Planalto reingere o
    MESMO conteúdo (atalho 'inalterado', que também mescla `extra`) trazendo
    'vigente'. A decisão humana tem de sobreviver — senão a norma revogada volta
    à recuperação sozinha, com `governance_updated_by` ainda apontando para o
    curador, isto é, PARECENDO decisão dele."""
    from app.core.database import AsyncSessionLocal
    from app.services.ingestion_service import upsert_documento

    k = f"lei:vigencia:{uuid4()}"
    txt = ("Texto compilado da norma de teste, com tamanho suficiente para "
           "ultrapassar o minimo de cinquenta caracteres exigido pelo upsert.")
    extra_ingestor = {
        "rag_status": "aprovado",
        "legal_status": "vigente",
        "legal_status_origem": "planalto:texto_compilado",
        "legal_status_inferido_em": "2026-08-02T00:00:00+00:00",
    }
    async with AsyncSessionLocal() as db:
        await upsert_documento(db, titulo="VIGC v1", categoria="legislacao",
                               conteudo=txt, fonte="http://x", chave_origem=k,
                               extra=dict(extra_ingestor), embutir_vetores=False)
        await db.commit()

    # Curador decide pelo painel: mesma gravação de rag_governance.PATCH —
    # carimba origem/conferência e REMOVE `legal_status_inferido_em`, que
    # pertencia à leitura automática que ele acaba de substituir.
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE knowledge_docs SET extra = "
            "(extra - 'legal_status_inferido_em') || CAST(:e AS jsonb) "
            "WHERE chave_origem = :k"),
            {"k": k, "e": json.dumps({
                "legal_status": "revogada",
                "legal_status_origem": "curadoria:u-teste",
                "legal_status_verificado_em": "2026-08-02T12:00:00+00:00",
                "governance_updated_by": "u-teste",
            })})
        await db.commit()

    # Re-feed com CONTEÚDO DIFERENTE → caminho de versionamento (não "inalterado")
    txt_v2 = txt + " Texto adicional para forcar nova versao do diploma."
    async with AsyncSessionLocal() as db:
        await upsert_documento(db, titulo="VIGC v2", categoria="legislacao",
                               conteudo=txt_v2, fonte="http://x", chave_origem=k,
                               extra=dict(extra_ingestor), embutir_vetores=False)
        await db.commit()

    async with AsyncSessionLocal() as db:
        try:
            # Deve haver DUAS versões: a anterior (vigente=false) e a nova (vigente=true)
            linhas = (await db.execute(text(
                "SELECT versao, vigente, extra FROM knowledge_docs "
                "WHERE chave_origem = :k ORDER BY versao"),
                {"k": k})).fetchall()
            assert len(linhas) == 2, "deveria ter criado nova versão"
            v1, vig1, extra1 = linhas[0]
            v2, vig2, extra2 = linhas[1]
            assert v1 == 1 and not vig1, "versão 1 deveria estar desativada"
            assert v2 == 2 and vig2, "versão 2 deveria estar vigente"
            # A NOVA versão (v2) deve preservar a curadoria da v1
            assert extra2["legal_status"] == "revogada", (
                "versionamento perdeu a vigência decidida pelo curador")
            assert extra2["legal_status_origem"] == "curadoria:u-teste"
            assert extra2["legal_status_verificado_em"] == "2026-08-02T12:00:00+00:00"
            assert "legal_status_inferido_em" not in extra2, (
                "carimbo do ingestor sobrando ao lado do status do curador — o "
                "registro afirmaria uma leitura que não vale para este valor")
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()


async def test_reingestao_versiona_sem_colidir_indice_unico():
    """Bug P0: reingerir a MESMA chave_origem com conteúdo novo colidia com o
    índice único (não considerava `vigente`). Após a migration 092 + flush
    ordenado do upsert, cria nova versão vigente e preserva o histórico."""
    from app.core.database import AsyncSessionLocal
    from app.services.ingestion_service import upsert_documento

    k = f"lei:teste:{uuid4()}"
    txt1 = ("Redacao ORIGINAL da norma de teste, com tamanho suficiente para "
            "ultrapassar o minimo de cinquenta caracteres exigido pelo upsert.")
    txt2 = ("Redacao ATUALIZADA da mesma norma apos alteracao legislativa, "
            "tambem com mais de cinquenta caracteres para valer a reingestao.")
    async with AsyncSessionLocal() as db:
        r1 = await upsert_documento(db, titulo="VER v1", categoria="legislacao",
                                    conteudo=txt1, fonte="http://x", chave_origem=k,
                                    embutir_vetores=False)
        await db.commit()
    async with AsyncSessionLocal() as db:
        # NÃO pode lançar IntegrityError (era o bug)
        r2 = await upsert_documento(db, titulo="VER v2", categoria="legislacao",
                                    conteudo=txt2, fonte="http://x", chave_origem=k,
                                    embutir_vetores=False)
        await db.commit()
    async with AsyncSessionLocal() as db:
        try:
            assert r1 == "novo" and r2 == "atualizado", (r1, r2)
            rows = (await db.execute(text(
                "SELECT titulo, versao, vigente FROM knowledge_docs "
                "WHERE chave_origem=:k ORDER BY versao"), {"k": k})).all()
            assert len(rows) == 2, "as duas versões devem coexistir (histórico)"
            vig = [r for r in rows if r.vigente]
            assert len(vig) == 1, "exatamente UMA versão vigente por chave"
            assert vig[0].titulo == "VER v2", "a versão vigente deve ser a mais nova"
        finally:
            await db.execute(text("DELETE FROM knowledge_docs WHERE chave_origem=:k"), {"k": k})
            await db.commit()
