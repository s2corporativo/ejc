"""
Victory Vault — repositório das teses vitoriosas e modelos de documentos do
escritório. Persistência REAL em PostgreSQL (tabelas teses_vitoriosas e
modelos_documentos, migration 054).

Histórico: até a auditoria de 28/06/2026 isto era um store in-memory (lista
Python carregada de JSON mock) — todo POST se perdia no restart e o caminho do
mock era um absoluto /home/ubuntu inexistente no container. Agora grava no banco;
o JSON mock é usado apenas como seed inicial (1ª vez que a tabela está vazia),
preservando o conteúdo de demonstração.

As assinaturas dos métodos foram mantidas (sem `db` no parâmetro) para não quebrar
os chamadores existentes (victory_vault_router, core/veredito_ia). Cada método
abre sua própria AsyncSession via AsyncSessionLocal.
"""
from typing import List, Optional
import json
import os
import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.schemas.victory_vault_schema import (
    TeseVitoriosaCreate, TeseVitoriosa,
    ModeloDocumentoCreate, ModeloDocumento,
)

logger = logging.getLogger("ejc.victory_vault")

_MOCK_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "mock_db")


class VictoryVault:
    # Flag de processo: garante que o auto-seed tenta rodar só uma vez.
    _seed_tentado = False

    async def _ensure_seeded(self, db) -> None:
        """Se a tabela de teses estiver vazia, popula a partir do JSON mock.
        Idempotente: roda no máximo uma vez por processo e só quando vazia."""
        if VictoryVault._seed_tentado:
            return
        VictoryVault._seed_tentado = True
        # Auditoria 04/07/2026: o seed vem de JSON MOCK (conteúdo de demonstração)
        # e NUNCA deve rodar em produção — dado fake em sistema jurídico é
        # inaceitável. Em produção a tabela começa/permanece como estiver.
        from app.core.config import get_settings
        if get_settings().APP_ENV == "production":
            return
        try:
            count = (await db.execute(text("SELECT COUNT(*) FROM teses_vitoriosas WHERE deleted_at IS NULL"))).scalar()
            if count and count > 0:
                return
            teses_path = os.path.join(_MOCK_DIR, "teses_vitoriosas.json")
            if not os.path.exists(teses_path):
                return
            with open(teses_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                # Usa só os campos do schema (o mock tem extras que ignoramos).
                t = TeseVitoriosaCreate(
                    titulo=item.get("titulo", ""),
                    ementa=item.get("ementa", ""),
                    area_juridica=item.get("area_juridica", ""),
                    data_vitoria=str(item.get("data_vitoria", "")),
                    link=item.get("link"),
                )
                await db.execute(text("""
                    INSERT INTO teses_vitoriosas (id, titulo, ementa, area_juridica, data_vitoria, link)
                    VALUES (:id, :titulo, :ementa, :area, :data, :link)
                    ON CONFLICT (id) DO NOTHING
                """), {
                    "id": str(item.get("id")) if item.get("id") is not None else None,
                    "titulo": t.titulo, "ementa": t.ementa, "area": t.area_juridica,
                    "data": t.data_vitoria, "link": t.link,
                })
            await db.commit()
            logger.info("Victory Vault: seed inicial de teses_vitoriosas aplicado.")
        except Exception as e:
            logger.warning(f"Victory Vault: falha no auto-seed (ignorado): {e}")

    # ── Teses vitoriosas ─────────────────────────────────────────────────────
    async def create_tese_vitoriosa(self, tese: TeseVitoriosaCreate) -> TeseVitoriosa:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                INSERT INTO teses_vitoriosas (titulo, ementa, area_juridica, data_vitoria, link)
                VALUES (:titulo, :ementa, :area, :data, :link)
                RETURNING id
            """), {
                "titulo": tese.titulo, "ementa": tese.ementa, "area": tese.area_juridica,
                "data": tese.data_vitoria, "link": tese.link,
            })).first()
            await db.commit()
            return TeseVitoriosa(id=row[0], **tese.dict())

    async def get_teses_vitoriosas(self, area_juridica: Optional[str] = None,
                                   query: Optional[str] = None) -> List[TeseVitoriosa]:
        async with AsyncSessionLocal() as db:
            await self._ensure_seeded(db)
            sql = ("SELECT id, titulo, ementa, area_juridica, data_vitoria, link "
                   "FROM teses_vitoriosas WHERE deleted_at IS NULL")
            params: dict = {}
            if area_juridica:
                sql += " AND lower(area_juridica) = lower(:area)"
                params["area"] = area_juridica
            if query:
                sql += " AND (titulo ILIKE :q OR ementa ILIKE :q)"
                params["q"] = f"%{query}%"
            sql += " ORDER BY created_at DESC"
            rows = (await db.execute(text(sql), params)).mappings().all()
            return [TeseVitoriosa(**dict(r)) for r in rows]

    # ── Modelos de documentos ────────────────────────────────────────────────
    async def create_modelo_documento(self, modelo: ModeloDocumentoCreate) -> ModeloDocumento:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                INSERT INTO modelos_documentos (tipo_documento, area_juridica, conteudo_template, descricao)
                VALUES (:tipo, :area, :conteudo, :descricao)
                RETURNING id
            """), {
                "tipo": modelo.tipo_documento, "area": modelo.area_juridica,
                "conteudo": modelo.conteudo_template, "descricao": modelo.descricao,
            })).first()
            await db.commit()
            return ModeloDocumento(id=row[0], **modelo.dict())

    async def get_modelos_documentos(self, tipo_documento: Optional[str] = None,
                                     area_juridica: Optional[str] = None,
                                     query: Optional[str] = None) -> List[ModeloDocumento]:
        async with AsyncSessionLocal() as db:
            sql = ("SELECT id, tipo_documento, area_juridica, conteudo_template, descricao "
                   "FROM modelos_documentos WHERE deleted_at IS NULL")
            params: dict = {}
            if tipo_documento:
                sql += " AND lower(tipo_documento) = lower(:tipo)"
                params["tipo"] = tipo_documento
            if area_juridica:
                sql += " AND lower(area_juridica) = lower(:area)"
                params["area"] = area_juridica
            if query:
                sql += " AND (conteudo_template ILIKE :q OR coalesce(descricao,'') ILIKE :q)"
                params["q"] = f"%{query}%"
            sql += " ORDER BY created_at DESC"
            rows = (await db.execute(text(sql), params)).mappings().all()
            return [ModeloDocumento(**dict(r)) for r in rows]

    async def get_modelo_por_id(self, modelo_id: str) -> Optional[ModeloDocumento]:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT id, tipo_documento, area_juridica, conteudo_template, descricao "
                "FROM modelos_documentos WHERE id = :id AND deleted_at IS NULL"
            ), {"id": modelo_id})).mappings().first()
            return ModeloDocumento(**dict(row)) if row else None

    # Alias usado por core/document_template_engine — evita AttributeError.
    async def buscar_modelos(self, query: Optional[str] = None,
                             area_juridica: Optional[str] = None) -> List[ModeloDocumento]:
        return await self.get_modelos_documentos(area_juridica=area_juridica, query=query)


# Instância de módulo (compat: document_template_engine importa `vault`).
vault = VictoryVault()
