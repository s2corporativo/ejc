# ── tests/test_peca_analise_validacao_hitl.py ────────────────────────────────
# Dívida 5.2 / P1-9 (auditoria de IA 2026-08-18, #1150): as DUAS saídas de
# maior valor jurídico — a minuta de peça e a análise estratégica — nasciam
# fora da validação canônica do núcleo. Rodavam só o citation_check, sem
# detecção de promessa de resultado (vedação OAB), sem a marca "SEM BASE
# VERIFICÁVEL" e sem o carimbo HITL que o orquestrador aplica a todo o resto.
#
# Contrato testado aqui:
#   • peça e análise passam por response_validator.validar (exige_fonte=True);
#   • promessa de resultado no texto vira ALERTA + revisão obrigatória, nunca
#     reescrita silenciosa;
#   • peça sem NENHUMA âncora (sem fonte RAG, sem citação confirmada) é
#     entregue E PERSISTIDA com o prefixo "SEM BASE VERIFICÁVEL";
#   • falha da validação não derruba a entrega — vira alerta ao revisor;
#   • ambas carregam o carimbo HITL canônico (is_rascunho/requer_revisao/
#     status_hitl/aviso_hitl).
#
# Padrão dos testes de IA do projeto (sem Postgres/IA real): fakes locais,
# pipeline REAL com dependências monkeypatched e a IA substituída por recorder.
from __future__ import annotations

import json
from types import SimpleNamespace

import app.services.peca_service as ps
from app.models.ai_log import AILog
from app.models.legal_doc import LegalDoc
from app.services.ai.core.hitl_policy import AVISO_HITL
from app.services.ai.core.response_validator import PREFIXO_SEM_BASE

# Texto longo o bastante para sobreviver à padronização da peça.
_CORPO = "Texto ficticio da minuta para exercitar a validacao canonica. " * 12
PECA_COM_PROMESSA = (
    "DOS FATOS\n" + _CORPO + "\nO exito e garantido nesta demanda.\n"
)
PECA_NEUTRA = "DOS FATOS\n" + _CORPO


class _PipeDB:
    """Sem case_id o pipeline não consulta o banco — só add()/commit() no fim."""

    def __init__(self):
        self.added: list = []

    def add(self, obj, *a, **k):
        self.added.append(obj)

    async def commit(self):
        return None


async def _rodar_peca(monkeypatch, *, texto_peca: str = PECA_NEUTRA,
                      citacoes: dict | None = None,
                      validar_raises: bool = False):
    """Roda gerar_peca_pipeline com IA/RAG/citações fakes; devolve o estado."""
    calls: list[dict] = []

    async def fake_gw(messages, task_type, temperature=None, max_tokens=None, **kw):
        calls.append({"task_type": task_type})
        # A 6ª chamada é a etapa 7 (redação da peça); as demais são auxiliares.
        return SimpleNamespace(
            texto=texto_peca if len(calls) == 6 else "resposta simulada",
            modelo="fake-model", provedor="fake", input_tokens=1, output_tokens=1,
        )

    async def rag_vazio(*a, **k):
        return []

    async def cit_fake(db, material, **kw):
        if validar_raises:
            raise RuntimeError("citation_check indisponivel")
        return citacoes if citacoes is not None else {"confirmadas": 0, "total": 0}

    async def grounding_fake(db, texto, **kw):
        return {"contagem_status": {}, "score": 100}

    async def sem_codigo(db, area):
        return None

    monkeypatch.setattr(ps, "gw_chat", fake_gw)
    monkeypatch.setattr(ps, "buscar_contexto_rag", rag_vazio)
    monkeypatch.setattr(ps, "get_settings", lambda: SimpleNamespace(
        PECAS_RAG_MODELOS_ENABLED=False, PECAS_RAG_MODELOS_TOPK=3,
        PECAS_AUTOCRITICA_ENABLED=False,
    ))
    import app.services.citation_check as citation_check
    import app.services.peca_numeracao as peca_numeracao
    import app.services.verificador_jurisprudencia as vj
    monkeypatch.setattr(citation_check, "verificar_citacoes", cit_fake)
    monkeypatch.setattr(vj, "verificar_jurisprudencia", grounding_fake)
    monkeypatch.setattr(peca_numeracao, "proximo_codigo_peca", sem_codigo)

    db = _PipeDB()
    eventos: list[str] = []
    async for ev in ps.gerar_peca_pipeline(
        db=db, user_id="u1", tipo_peca="contestacao", area_direito="civil",
        descricao_fatos="Fatos ficticios de teste da validacao canonica.",
        pedidos="Pedidos ficticios.", nomes_proteger=[], case_id=None,
        instrucoes_adicionais=None,
    ):
        eventos.append(ev)

    conclusao = [
        json.loads(ev.split("data: ", 1)[1].strip())
        for ev in eventos if ev.startswith("event: concluido")
    ]
    log = next(o for o in db.added if isinstance(o, AILog))
    doc = next(o for o in db.added if isinstance(o, LegalDoc))
    return SimpleNamespace(conclusao=conclusao[0], log=log, doc=doc, eventos=eventos)


# ══════════════════════════════════════════════════════════════════════════════
# Peça
# ══════════════════════════════════════════════════════════════════════════════

async def test_peca_carimba_hitl_canonico(monkeypatch):
    """A minuta é rascunho com a MESMA semântica do orquestrador."""
    r = await _rodar_peca(monkeypatch)
    assert r.conclusao["is_rascunho"] is True
    assert r.conclusao["status_hitl"] == "gerado"
    assert r.conclusao["aviso_hitl"] == AVISO_HITL
    assert r.conclusao["requer_revisao"] is True


async def test_peca_alerta_promessa_de_resultado(monkeypatch):
    """Vedação OAB: a promessa é ALERTADA ao revisor, nunca reescrita."""
    r = await _rodar_peca(monkeypatch, texto_peca=PECA_COM_PROMESSA)
    assert "minuta para exercitar" in r.conclusao["documento"]  # é mesmo a peça
    alertas = " ".join(r.conclusao["alertas"])
    assert "promessa de resultado" in alertas.lower()
    assert r.conclusao["revisao_obrigatoria"] is True
    # O teor NÃO é reescrito — o revisor precisa ver o que o modelo escreveu.
    assert "garantido" in r.conclusao["documento"]


async def test_peca_sem_ancora_e_entregue_marcada(monkeypatch):
    """Sem fonte RAG e sem citação confirmada, a marca vai no CORPO e no banco."""
    r = await _rodar_peca(monkeypatch)
    assert r.conclusao["sem_base_verificavel"] is True
    assert r.conclusao["documento"].startswith(PREFIXO_SEM_BASE)
    assert r.doc.conteudo.startswith(PREFIXO_SEM_BASE)
    assert r.log.resposta.startswith(PREFIXO_SEM_BASE)


async def test_peca_com_citacao_confirmada_nao_e_marcada(monkeypatch):
    """Citação confirmada na base oficial já é âncora verificável."""
    r = await _rodar_peca(
        monkeypatch, citacoes={"confirmadas": 2, "total": 2, "citacoes": []},
    )
    assert r.conclusao["sem_base_verificavel"] is False
    assert not r.conclusao["documento"].startswith(PREFIXO_SEM_BASE)
    assert r.conclusao["verificacao_citacoes"]["confirmadas"] == 2


async def test_peca_entregue_mesmo_com_validacao_indisponivel(monkeypatch):
    """Fail-safe: a validação falhar não pode impedir a entrega da minuta."""
    r = await _rodar_peca(monkeypatch, validar_raises=True)
    assert r.conclusao["documento"]
    assert r.conclusao["revisao_obrigatoria"] is True
    alertas = " ".join(r.conclusao["alertas"]).lower()
    assert "manualmente" in alertas


# ══════════════════════════════════════════════════════════════════════════════
# Análise estratégica
# ══════════════════════════════════════════════════════════════════════════════

class _AnaliseDB:
    """A análise só usa o db para RAG/validação, ambos monkeypatched aqui."""


async def _rodar_analise(monkeypatch, resposta: str, *, com_db: bool = True):
    async def fake_chat(*, messages, **kw):
        return SimpleNamespace(texto=resposta)

    async def rag_vazio(*a, **k):
        return []

    async def cit_fake(db, material, **kw):
        return {"confirmadas": 0, "total": 0}

    async def grounding_fake(db, texto, **kw):
        return {"contagem_status": {}, "score": 100}

    import app.services.verificador_jurisprudencia as vj
    import app.services.citation_check as citation_check
    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)
    monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag_vazio)
    monkeypatch.setattr(citation_check, "verificar_citacoes", cit_fake)
    monkeypatch.setattr(vj, "verificar_jurisprudencia", grounding_fake)

    from app.services.analise_estrategica import analisar_caso

    return await analisar_caso(
        titulo="Caso ficticio de teste",
        fatos="Fatos ficticios suficientes para a analise estrategica.",
        db=_AnaliseDB() if com_db else None,
    )


async def test_analise_carimba_hitl_canonico(monkeypatch):
    res = await _rodar_analise(monkeypatch, '{"ramo":"Civel","alertas":[]}')
    assert res["is_rascunho"] is True
    assert res["status_hitl"] == "gerado"
    assert res["aviso_hitl"] == AVISO_HITL


async def test_analise_alerta_promessa_de_resultado(monkeypatch):
    res = await _rodar_analise(
        monkeypatch,
        '{"ramo":"Civel","alertas":["alerta do modelo"],'
        '"observacoes_finais":"O exito e garantido nesta demanda."}',
    )
    alertas = " ".join(res["alertas"]).lower()
    assert "alerta do modelo" in alertas          # o alerta do modelo é preservado
    assert "promessa de resultado" in alertas     # e o do validador é somado
    assert res["revisao_obrigatoria"] is True
    assert res["requer_revisao"] is True


async def test_analise_sem_ancora_e_sinalizada(monkeypatch):
    res = await _rodar_analise(monkeypatch, '{"ramo":"Civel"}')
    assert res["sem_base_verificavel"] is True
    assert res["_verificacao_citacoes"] == {"confirmadas": 0, "total": 0}


async def test_analise_sem_db_ainda_nasce_rascunho(monkeypatch):
    """Sem banco não há validação possível — o carimbo HITL continua valendo."""
    res = await _rodar_analise(monkeypatch, '{"ramo":"Civel"}', com_db=False)
    assert res["is_rascunho"] is True
    assert res["aviso_hitl"] == AVISO_HITL
