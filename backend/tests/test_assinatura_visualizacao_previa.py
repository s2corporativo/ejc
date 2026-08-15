"""Regressão ASS-01 (Issue #1081): `POST /signatures/{id}/assinar` exige que
o documento tenha sido visualizado ANTES de aceitar a assinatura — o gate
antigo vivia só no frontend (PortalAssinaturas.tsx) e qualquer chamada direta
(curl/devtools) a assinava sem consentimento informado (MP 2.200-2/2001,
art. 10 §2º).

Source-inspection (sem DB/rede), mesmo padrão de `test_signatures_ownership.py`:
trava o INCONVIANTE no código — um teste comportamental completo exigiria o
full-stack do portal, e o invariante aqui é exatamente a presença das duas
verificações server-side.
"""
from __future__ import annotations

import inspect

from app.routers import signatures as sig


def _corpo(fn):
    return inspect.getsource(fn)


def test_assinar_exige_visualizacao_previa_registrada():
    """O POST /assinar DEVE recusar (422) quando `documento_visualizado_em`
    ainda é NULL — a coluna é gravada apenas pelo GET /documento (1ª
    visualização). A mensagem de erro menciona o endpoint de visualização,
    para que o cliente do portal saiba o próximo passo legítimo."""
    src = _corpo(sig.assinar)
    assert "sr.documento_visualizado_em is None" in src
    assert "status_code=422" in src
    assert "documento ainda não foi" in src or "visualizado" in src


def test_assinar_repoe_visualizacao_no_comprovante():
    """O comprovante da assinatura DEVE devolver o timestamp da visualização
    prévia — é a evidência de consentimento informado que respalda a MP
    2.200-2/2001, art. 10 §2º (a própria issue #1081 pede que a assinatura
    seja PROVAR que o signatário viu o documento antes)."""
    src = _corpo(sig.assinar)
    assert "documento_visualizado_em" in src
    assert "sr.documento_visualizado_em.isoformat()" in src


def test_visualizar_documento_grava_1a_visualizacao():
    """O GET /documento DEVE gravar `documento_visualizado_em` na PRIMEIRA
    visualização (só quando é None) — repetições do GET não podem forjar uma
    visualização véspera da assinatura reescrevendo o timestamp."""
    src = _corpo(sig.visualizar_documento)
    assert "sr.documento_visualizado_em is None" in src
    assert "sr.documento_visualizado_em = " in src
    assert "datetime.now(timezone.utc)" in src
