"""Teto de tamanho nos campos de texto de IA (auditoria de segurança 18/08).

Nada em ai_gateway.py valida o tamanho de `messages` antes de chamar o
provedor; AI_LONG_DOCUMENT_MAX_CHARS só é aplicado por ai_skill_service.py —
quem chama o gateway direto (a maioria dos endpoints de app/routers/ai.py)
ignorava o teto. Payload sem limite chega inteiro ao provedor externo: custo
sem controle e superfície de negação de serviço. VerificarCitacoesRequest já
usa max_length=200_000; replicado aqui por consistência interna, sem inventar
um teto novo.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ai import AnalisarCasoRequest, ResumirDocRequest

_MUITO_GRANDE = "a" * 200_001
_NO_LIMITE = "a" * 200_000


def test_analisar_caso_rejeita_texto_acima_do_teto():
    with pytest.raises(ValidationError):
        AnalisarCasoRequest(descricao_fatos=_MUITO_GRANDE, area="civel")


def test_analisar_caso_aceita_texto_no_teto():
    req = AnalisarCasoRequest(descricao_fatos=_NO_LIMITE, area="civel")
    assert len(req.descricao_fatos) == 200_000


def test_resumir_documento_rejeita_texto_acima_do_teto():
    with pytest.raises(ValidationError):
        ResumirDocRequest(texto=_MUITO_GRANDE)


def test_teses_ocultas_e_afins_tem_teto(monkeypatch):
    """Schemas locais de app/routers/ai.py (não vivem em schemas/ai.py)."""
    from app.routers.ai import (
        AnaliseContratoReq,
        AudienciaReq,
        AuditarPecaReq,
        TesesOcultasReq,
    )

    with pytest.raises(ValidationError):
        TesesOcultasReq(descricao_fatos=_MUITO_GRANDE, area="civel")
    with pytest.raises(ValidationError):
        AuditarPecaReq(conteudo=_MUITO_GRANDE, tipo_peca="contestacao")
    with pytest.raises(ValidationError):
        AudienciaReq(resumo_caso=_MUITO_GRANDE)
    with pytest.raises(ValidationError):
        AnaliseContratoReq(texto_contrato=_MUITO_GRANDE)
    with pytest.raises(ValidationError):
        AnaliseContratoReq(texto_contrato="minuta curta", texto_contrato_2=_MUITO_GRANDE)
