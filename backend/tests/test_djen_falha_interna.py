from types import SimpleNamespace

import pytest

from app.services import djen_service


class _DBFalha:
    def __init__(self):
        self.rollback_executado = False

    async def execute(self, _query):
        raise RuntimeError("detalhe-interno-nao-deve-vazar")

    async def rollback(self):
        self.rollback_executado = True


@pytest.mark.asyncio
async def test_falha_interna_por_advogado_vira_resultado_e_nao_excecao(monkeypatch):
    djen_service.limpar_resultados_execucao()

    async def consulta_ok(_numero, _uf, dias=2):
        return djen_service.DjenConsultaResultado(
            fonte_ok=True,
            items=[{"id": "com-1", "texto": "conteudo"}],
        )

    monkeypatch.setattr(djen_service, "consultar_oab", consulta_ok)
    db = _DBFalha()
    advogado = SimpleNamespace(
        id="adv-1",
        email="sigiloso@example.com",
        djen_oab_numero="123456",
        djen_oab_uf="MG",
    )

    resultado = await djen_service.capturar_para_advogado(db, advogado)

    assert resultado.fonte_ok is False
    assert resultado.erro == "erro_interno"
    assert resultado.novas == 0
    assert db.rollback_executado is True

    resumo = djen_service.consumir_resumo_execucao()
    assert resumo["heartbeat_status"] == "erro"
    assert resumo["resultado"] == "falha_fonte"
    assert resumo["erros"] == {"erro_interno": 1}
