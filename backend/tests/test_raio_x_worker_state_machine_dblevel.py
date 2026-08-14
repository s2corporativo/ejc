"""Máquina de estados concorrente do worker Raio-X em PostgreSQL real."""
from __future__ import annotations

import asyncio
import os
from app.core.config import Settings
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.raio_x import RaioXAnalise, RaioXDocumento
from app.tasks import raio_x_tasks

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL e concorrência real (RUN_DB_TESTS=1)",
)


async def _semear(tmp_path) -> tuple[str, str, str]:
    async with AsyncSessionLocal() as db:
        user_id = str(uuid4())
        analise_id = str(uuid4())
        documento_id = str(uuid4())
        rel = f"raio-x/{analise_id}/documento.txt"
        full = tmp_path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("conteúdo jurídico de teste", encoding="utf-8")

        await db.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                "VALUES (:id, :email, 'x', 'Advogado Worker', 'advogado', true)"
            ),
            {"id": user_id, "email": f"worker-{user_id[:8]}@teste.local"},
        )
        db.add(
            RaioXAnalise(
                id=analise_id,
                titulo="Análise concorrente do worker",
                status="fila",
                created_by=user_id,
                relatorio={},
            )
        )
        db.add(
            RaioXDocumento(
                id=documento_id,
                analise_id=analise_id,
                nome_original="documento.txt",
                filepath=rel,
                mimetype="text/plain",
                size_bytes=10,
                sha256="b" * 64,
                resultado_analise={},
                uploaded_by=user_id,
            )
        )
        await db.commit()
        return user_id, analise_id, documento_id


@pytest.mark.anyio
async def test_arquivamento_humano_durante_ocr_prevalece(monkeypatch, tmp_path):
    user_id, analise_id, documento_id = await _semear(tmp_path)
    iniciou_extracao = asyncio.Event()
    liberar_extracao = asyncio.Event()

    _settings_reais = Settings()
    _settings_reais.UPLOAD_DIR = str(tmp_path)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: _settings_reais,
    )

    async def _extrair(*args, **kwargs):
        iniciou_extracao.set()
        await liberar_extracao.wait()
        return {
            "ok": True,
            "intake_result": {"tipo_documento": {"valor": "peticao"}},
            "tokens_total": 7,
            "_texto_sanitizado": "não deve persistir neste fluxo",
        }

    monkeypatch.setattr(
        "app.services.documento_service.extrair_e_analisar",
        _extrair,
    )

    worker = asyncio.create_task(
        raio_x_tasks.processar_analise(
            analise_id,
            user_id,
            "advogado",
            [documento_id],
            False,
            AsyncSessionLocal,
        )
    )
    await asyncio.wait_for(iniciou_extracao.wait(), timeout=5)

    async with AsyncSessionLocal() as db_humano:
        analise = (
            await db_humano.execute(
                select(RaioXAnalise)
                .where(RaioXAnalise.id == analise_id)
                .with_for_update()
            )
        ).scalar_one()
        assert analise.status == "em_processamento"
        analise.status = "arquivado"
        await db_humano.commit()

    liberar_extracao.set()
    resultado = await asyncio.wait_for(worker, timeout=10)
    assert resultado == "cancelada_por_estado"

    async with AsyncSessionLocal() as db_check:
        analise = await db_check.get(RaioXAnalise, analise_id)
        documento = await db_check.get(RaioXDocumento, documento_id)

    assert analise.status == "arquivado"
    assert analise.relatorio == {}
    assert documento.resultado_analise == {}, (
        "resultado de OCR/IA foi commitado apesar de ação humana concorrente"
    )


@pytest.mark.anyio
async def test_marcar_erro_nao_sobrescreve_analise_arquivada(tmp_path):
    _user_id, analise_id, _documento_id = await _semear(tmp_path)
    async with AsyncSessionLocal() as db:
        analise = await db.get(RaioXAnalise, analise_id)
        analise.status = "arquivado"
        await db.commit()

    await raio_x_tasks._marcar_erro(
        analise_id,
        "erro tardio do worker",
        AsyncSessionLocal,
    )

    async with AsyncSessionLocal() as db_check:
        analise = await db_check.get(RaioXAnalise, analise_id)

    assert analise.status == "arquivado"
    assert "erro_processamento" not in (analise.relatorio or {})
