"""Endpoint de coleta do TJMG sob demanda (POST /ia-governanca/fontes/tjmg/coletar).

Valida, sem HTTP/banco, chamando a função do endpoint diretamente:
1) admin/sócio → 202 + agenda executar_ingestao(slug="tjmg") em background;
2) papel sem permissão → 403. Com o gate estrutural da Fase 8 (onda 1), a
   checagem vive na dependency `_req_admin_socio` — o 403 acontece ANTES do
   handler ser alcançado, então o teste nega chamando a dependency direto
   (mesma função que o FastAPI resolve na montagem da rota).
"""
from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, HTTPException

import app.routers.ia_governanca as gov
from app.services.ingestion_service import executar_ingestao


class _User:
    def __init__(self, role: str):
        self.role = role


async def test_coletar_tjmg_admin_agenda_background():
    bg = BackgroundTasks()
    res = await gov.coletar_tjmg_agora(bg, _User("socio"))
    assert res["status"] == "coleta_iniciada"
    # agendou exatamente 1 task de ingestão da fonte 'tjmg'
    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    assert task.func is executar_ingestao
    assert task.args[0] == "tjmg"                 # slug
    assert task.args[2] == "jurisprudencia"       # categoria_rag


async def test_coletar_tjmg_nao_admin_403_na_dependency():
    # Gate estrutural (Fase 8): `_req_admin_socio` nega ANTES do handler —
    # nenhum task de ingestão pode ser agendado para papel sem permissão.
    with pytest.raises(HTTPException) as ei:
        await gov._req_admin_socio(_User("advogado"))
    assert ei.value.status_code == 403
