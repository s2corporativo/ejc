"""Endpoint /ai/detectar-prazos — extração de prazos por IA (correção F821).

O handler chamava `extrair_prazos_ia` sem que a função existisse (NameError →
500 em toda chamada real). Cobre o contrato da correção, sem rede e sem banco
(padrão test_lgpd_registros.py: handler direto + fakes + monkeypatch do
gateway):
  - prazo com data fatal parseável → item estruturado + AILog persistido (HITL);
  - item SEM data fatal → descartado (nunca inventa — mesmo fail-safe do intake);
  - resposta não-JSON da IA → degrada para lista vazia (sem 500);
  - texto curto → 422; falha do gateway → 502; resposta sempre marca rascunho.

Dados 100% fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.ai_log import AILog
from app.models.user import User, UserRole
from app.routers.ai import detectar_prazos
from app.schemas.ai import ResumirDocRequest


class _FakeDB:
    def __init__(self):
        self.added: list = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _user() -> User:
    return User(id="u-adv-1", role=UserRole.advogado)


def _gateway_fake(texto_resposta: str):
    async def fake(system_prompt, user_prompt, **kw):
        resp = SimpleNamespace(
            texto=texto_resposta, modelo="llama-fake", provedor="groq",
            fallback_ativado=False, usage=None, input_tokens=10, output_tokens=20,
        )
        return texto_resposta, resp
    return fake


TEXTO_INTIMACAO = (
    "Intimação fictícia: fica a parte ré intimada para apresentar contestação "
    "no prazo de 15 dias úteis, com termo final em 20/08/2026, nos termos do "
    "art. 335 do CPC. Documento de teste, sem dados reais."
)



async def test_detectar_prazos_extrai_prazo_com_data_fatal(monkeypatch):
    import app.services.ai_service as svc
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)
    monkeypatch.setattr(svc, "_gateway_text", _gateway_fake(
        '{"prazos": [{"tipo": "contestação", "data_base": "intimação", '
        '"termo_final": "20/08/2026", "fatal": true, "base_legal": "art. 335 CPC"}]}'
    ))

    db = _FakeDB()
    r = await detectar_prazos(ResumirDocRequest(texto=TEXTO_INTIMACAO), db=db, cu=_user())

    assert r["total"] == 1
    prazo = r["prazos"][0]
    assert prazo["tipo"] == "contestação"
    assert prazo["termo_final"] == "2026-08-20"  # normalizado ISO (padrão intake)
    assert prazo["fatal"] is True
    assert "RASCUNHO" in r["aviso"]
    assert r["status_hitl"] == "gerado"
    # Governança: AILog persistido
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1 and db.commits == 1
    assert r["ai_log_id"] == logs[0].id



async def test_detectar_prazos_descarta_item_sem_data_fatal(monkeypatch):
    import app.services.ai_service as svc
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)
    monkeypatch.setattr(svc, "_gateway_text", _gateway_fake(
        '{"prazos": [{"tipo": "recurso", "data_base": "publicação", "fatal": true}]}'
    ))

    db = _FakeDB()
    r = await detectar_prazos(ResumirDocRequest(texto=TEXTO_INTIMACAO), db=db, cu=_user())
    assert r["total"] == 0 and r["prazos"] == []  # nunca inventa data



async def test_detectar_prazos_resposta_nao_json_degrada_sem_500(monkeypatch):
    import app.services.ai_service as svc
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)
    monkeypatch.setattr(svc, "_gateway_text", _gateway_fake("desculpe, não entendi"))

    db = _FakeDB()
    r = await detectar_prazos(ResumirDocRequest(texto=TEXTO_INTIMACAO), db=db, cu=_user())
    assert r["prazos"] == [] and "ai_log_id" in r



async def test_detectar_prazos_texto_curto_422():
    with pytest.raises(HTTPException) as exc:
        await detectar_prazos(ResumirDocRequest(texto="curto"), db=_FakeDB(), cu=_user())
    assert exc.value.status_code == 422



async def test_detectar_prazos_gateway_indisponivel_502(monkeypatch):
    import app.services.ai_service as svc
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)

    async def boom(*a, **kw):
        raise RuntimeError("provider fora")
    monkeypatch.setattr(svc, "_gateway_text", boom)

    with pytest.raises(HTTPException) as exc:
        await detectar_prazos(ResumirDocRequest(texto=TEXTO_INTIMACAO), db=_FakeDB(), cu=_user())
    assert exc.value.status_code == 502
