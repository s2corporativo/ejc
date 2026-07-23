"""Rubrica auditavel do validador juridico — controle de qualidade FORMAL.

Contexto (auditoria): `validador_juridico_service._calcular_metricas` calcula o
score que GATEIA o protocolo (legal_docs: score >= 75 para aprovar/finalizar/
protocolar). A heuristica de regex foi refatorada numa RUBRICA por secao —
criterios rotulados, com peso documentado e detalhamento {criterio, rotulo,
secao, peso, atendido, pontua, deducao, observacao} para o HITL/UI.

TRAVA DE SEGURANCA (inegociavel): a rubrica NUNCA pode ser mais permissiva que a
heuristica historica. Esta suite fixa o invariante `score_rubrica <=
score_heuristico_legado` para toda entrada (nenhuma peca hoje barrada passa a
ser aprovada) e prova que, nesta versao, o score e IDENTICO (refatoracao
transparente) — os criterios das novas secoes sao informativos (nao pontuam).

Sem Postgres: exercita apenas funcoes puras do service + os parsers do gate.
Dados 100% ficticios.
"""
from __future__ import annotations

import itertools

import pytest

from app.services import validador_juridico_service as V
from app.services.validador_juridico_service import _calcular_metricas, _formatar_metricas
from app.routers.legal_docs import _parse_score, _parse_veredito, VALIDACAO_SCORE_MINIMO


# ── Oraculo: copia EXATA da heuristica historica (o teto que a rubrica nao fura) ─

def _score_heuristico_legado(texto: str, documentos: list[str] | None) -> int:
    """Replica byte-a-byte as deducoes da heuristica anterior a rubrica, usando
    os MESMOS detectores do service (a fidelidade esta na logica de score)."""
    artigos = V._uniq(V._ARTIGO_RE.findall(texto))
    leis = V._uniq(V._LEI_RE.findall(texto))
    jurisprudencia = V._uniq(V._JURIS_RE.findall(texto))
    provas = V._uniq(V._PROVA_RE.findall(texto))
    pedidos = V._uniq(V._PEDIDO_RE.findall(texto))
    jur_pendente = [
        j for j in jurisprudencia
        if not V._NUM_PROC_RE.search(j) and "tema" not in j.lower() and "sum" not in j.lower()
    ]
    score = 100
    if len(texto) < 1500:
        score -= 12
    if not artigos and not leis:
        score -= 22
    if not pedidos:
        score -= 14
    if not provas and not documentos:
        score -= 18
    if jur_pendente:
        score -= min(20, 6 * len(jur_pendente))
    if "verificar fonte" in texto.lower():
        score -= 8
    if "[dado nao informado]" in texto.lower() or "[verificar]" in texto.lower():
        score -= 10
    return max(0, min(100, score))


# ── Builder de rascunhos: cada flag liga UMA deducao da heuristica ─────────────

_FILLER = "texto de preenchimento processual neutro "  # sem art/lei/pedido/prova/sum/tema


def _draft(*, longo=False, art=False, ped=False, prov=False, jurp=False,
           vf=False, lac=False) -> str:
    partes: list[str] = []
    if art:
        partes.append("Nos termos do art. 5o da CF e da Lei 8.078 de 1990,")
    if ped:
        partes.append("assim, requer a procedencia total.")
    if prov:
        partes.append("conforme o documento anexo juntado.")
    if jurp:
        # STJ sem numero CNJ, sem 'tema', sem 'sum' -> pendente de verificacao.
        partes.append("vide STJ em julgado recente confirmando a tese.")
    if vf:
        partes.append("(verificar fonte)")
    if lac:
        partes.append("[verificar]")
    corpo = " ".join(partes) or "peca minima de teste."
    if longo:
        corpo = corpo + " " + (_FILLER * 45)  # ultrapassa 1500 chars
    return corpo


_FLAGS = ("longo", "art", "ped", "prov", "jurp", "vf", "lac")
_DOCS = (None, [], ["LEGAL_DOC_ID:x"])


def _todas_combinacoes():
    for bits in itertools.product((False, True), repeat=len(_FLAGS)):
        kwargs = dict(zip(_FLAGS, bits))
        for docs in _DOCS:
            yield kwargs, docs


# ── 1. TRAVA DE SEGURANCA: rubrica nunca mais permissiva que a heuristica ──────

def test_rubrica_nunca_mais_permissiva_que_heuristica():
    """Para TODA entrada: score da rubrica <= score da heuristica legada.
    Consequencia direta no gate: nenhuma peca barrada hoje passa a ser aprovada."""
    for kwargs, docs in _todas_combinacoes():
        texto = _draft(**kwargs)
        rub = _calcular_metricas(texto, docs)["score_confianca"]
        leg = _score_heuristico_legado(texto, docs)
        assert rub <= leg, (kwargs, docs, rub, leg)


def test_rubrica_nao_resgata_peca_barrada_no_gate():
    """Em termos do GATE (>= {min}): se a heuristica barra (score < min), a
    rubrica tambem barra. A rubrica jamais 'resgata' peca reprovada."""
    for kwargs, docs in _todas_combinacoes():
        texto = _draft(**kwargs)
        rub = _calcular_metricas(texto, docs)["score_confianca"]
        leg = _score_heuristico_legado(texto, docs)
        if leg < VALIDACAO_SCORE_MINIMO:
            assert rub < VALIDACAO_SCORE_MINIMO, (kwargs, docs, rub, leg)


# ── 2. Refatoracao transparente: score IDENTICO nesta versao ──────────────────

def test_rubrica_reproduz_score_da_heuristica():
    """v1 e refatoracao transparente: score da rubrica == heuristica para toda
    entrada (os criterios das novas secoes sao informativos e nao pontuam).
    Se um dia um criterio informativo virar pontuante, ESTE teste deve ser
    atualizado conscientemente — o de seguranca (<=) permanece intocado."""
    for kwargs, docs in _todas_combinacoes():
        texto = _draft(**kwargs)
        rub = _calcular_metricas(texto, docs)["score_confianca"]
        leg = _score_heuristico_legado(texto, docs)
        assert rub == leg, (kwargs, docs, rub, leg)


def test_score_bate_com_soma_das_deducoes_pontuantes():
    for kwargs, docs in _todas_combinacoes():
        m = _calcular_metricas(_draft(**kwargs), docs)
        ded = sum(c["deducao"] for c in m["rubrica"] if c["pontua"])
        assert m["score_confianca"] == max(0, min(100, 100 - ded)), (kwargs, docs)


# ── 3. Detalhamento estruturado por secao ─────────────────────────────────────

_CHAVES = {"criterio", "rotulo", "secao", "peso", "atendido", "pontua", "deducao", "observacao"}
_SECOES_OBRIGATORIAS = {
    "enderecamento_competencia", "fatos", "fundamentacao_legal", "pedidos",
    "provas_documentos", "valor_causa", "marcadores_qualidade", "citacoes_validadas",
}


def test_rubrica_itens_bem_formados():
    m = _calcular_metricas(_draft(longo=True, art=True, ped=True, prov=True), None)
    rub = m["rubrica"]
    assert isinstance(rub, list) and rub
    for c in rub:
        assert set(c) == _CHAVES, c
        assert isinstance(c["criterio"], str) and c["criterio"]
        assert isinstance(c["rotulo"], str) and c["rotulo"]
        assert isinstance(c["observacao"], str) and c["observacao"]
        assert isinstance(c["atendido"], bool) and isinstance(c["pontua"], bool)
        assert c["deducao"] >= 0 and c["peso"] >= 0
        # Criterio informativo nunca deduz; criterio atendido nunca deduz.
        if not c["pontua"] or c["atendido"]:
            assert c["deducao"] == 0, c


def test_rubrica_cobre_todas_as_secoes_obrigatorias():
    m = _calcular_metricas(_draft(), None)
    secoes = {c["secao"] for c in m["rubrica"]}
    assert _SECOES_OBRIGATORIAS <= secoes, _SECOES_OBRIGATORIAS - secoes


def test_rubrica_marca_natureza_formal_nao_preditiva():
    m = _calcular_metricas(_draft(), None)
    assert m["score_metodo"] == "rubrica_formal_v1"
    assert m["score_base"] == 100
    natureza = m["natureza"].upper()
    assert "FORMAL" in natureza and "NAO E PREDICAO" in natureza


def test_criterios_novas_secoes_sao_informativos():
    """endereEcamento, narrativa explicita e valor da causa NAO pontuam nesta
    versao (nao mexem no gate) — sao expostos so para o HITL/UI."""
    m = _calcular_metricas(_draft(), None)
    por_id = {c["criterio"]: c for c in m["rubrica"]}
    for cid in ("enderecamento_competencia", "narrativa_fatica_explicita", "valor_da_causa"):
        assert por_id[cid]["pontua"] is False, cid
        assert por_id[cid]["peso"] == 0 and por_id[cid]["deducao"] == 0, cid


def test_deteccao_das_novas_secoes():
    texto = (
        "EXCELENTISSIMO SENHOR DOUTOR JUIZ DE DIREITO DA VARA CIVEL DA COMARCA. "
        "DOS FATOS: narrativa. Da-se a causa o valor de R$ 10.000,00."
    )
    por_id = {c["criterio"]: c for c in _calcular_metricas(texto, None)["rubrica"]}
    assert por_id["enderecamento_competencia"]["atendido"] is True
    assert por_id["narrativa_fatica_explicita"]["atendido"] is True
    assert por_id["valor_da_causa"]["atendido"] is True
    # Peca sem esses marcadores: informativos ficam nao atendidos, sem punir score.
    por_id2 = {c["criterio"]: c for c in _calcular_metricas("peca sem cabecalho.", None)["rubrica"]}
    assert por_id2["enderecamento_competencia"]["atendido"] is False
    assert por_id2["valor_da_causa"]["atendido"] is False


def test_criterios_reprovados_lista_apenas_pontuantes_nao_atendidos():
    m = _calcular_metricas(_draft(), None)  # peca minima: reprova varios pontuantes
    reprovados = set(m["criterios_reprovados"])
    por_id = {c["criterio"]: c for c in m["rubrica"]}
    assert reprovados
    for cid in reprovados:
        assert por_id[cid]["pontua"] is True and por_id[cid]["atendido"] is False
    # Nenhum informativo entra na lista de reprovados.
    assert "enderecamento_competencia" not in reprovados


# ── 4. Contrato do GATE preservado: score/veredito seguem parseaveis ──────────

def test_formatar_metricas_preserva_score_e_veredito_para_o_gate():
    """Prova de que o gate (legal_docs._parse_score/_parse_veredito) le do prompt
    formatado exatamente o score/veredito da rubrica — o bloqueio de protocolo
    continua ancorado no mesmo numero."""
    for kwargs, docs in _todas_combinacoes():
        m = _calcular_metricas(_draft(**kwargs), docs)
        texto = _formatar_metricas(m)
        assert _parse_score(texto) == m["score_confianca"], (kwargs, docs, texto[:200])
        assert _parse_veredito(texto) == m["veredito"], (kwargs, docs)


def test_gate_barra_peca_fraca_e_libera_peca_completa():
    # Peca vazia/curta: score baixo -> abaixo do minimo -> gate barra.
    m_fraca = _calcular_metricas(_draft(), None)
    assert _parse_score(_formatar_metricas(m_fraca)) < VALIDACAO_SCORE_MINIMO
    # Peca longa, com fundamentacao, pedidos e provas, sem pendencias/marcadores.
    m_forte = _calcular_metricas(_draft(longo=True, art=True, ped=True, prov=True),
                                 ["LEGAL_DOC_ID:x"])
    assert m_forte["score_confianca"] == 100
    assert _parse_score(_formatar_metricas(m_forte)) >= VALIDACAO_SCORE_MINIMO


def test_formatar_metricas_nao_emite_score_confianca_espurio_antes_do_real():
    """A rubrica no prompt nao pode injetar um 'score_confianca: NN' anterior que
    o regex do gate (primeira ocorrencia) capturaria por engano."""
    m = _calcular_metricas(_draft(vf=True, lac=True, jurp=True), None)
    texto = _formatar_metricas(m)
    assert texto.count("score_confianca") == 1  # so a chave de topo
