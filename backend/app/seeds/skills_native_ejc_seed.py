"""Seed idempotente das skills nativas por ramo e módulo do EJC."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.ai.core.ejc_skill_catalog import (
    native_skill_coverage,
    native_skill_specs,
)


_FIELDS = (
    "display_name",
    "description",
    "system_prompt",
    "engine",
    "area",
    "active",
    "requires_case",
    "requires_human_review",
    "oab_restricted",
)


def _sync_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Variável DATABASE_URL não configurada.")
    if "+asyncpg" in database_url:
        return database_url.replace("+asyncpg", "+psycopg2")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if database_url.startswith("postgresql://") and "+" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return database_url


def _payload(spec) -> dict:
    return {
        "name": spec.name,
        "display_name": spec.display_name,
        "description": spec.description,
        "system_prompt": spec.system_prompt,
        "engine": "groq",
        "area": spec.area,
        "active": True,
        "requires_case": spec.requires_case,
        "requires_human_review": True,
        "oab_restricted": spec.oab_restricted,
    }


def seed() -> None:
    coverage = native_skill_coverage()
    # PORTÃO = `estrutura_ok`, não `complete`. Com `complete` (que exige método
    # de ramo para as 25 áreas canônicas), este seed levantava SEMPRE — faltam
    # 11 métodos, e escrevê-los "exige advogado, não se inventa aqui". O efeito
    # era que as 48 skills nativas VÁLIDAS nunca chegavam a `ejc_skills`: em
    # `seed_all` a exceção é engolida como "não-fatal", então o catálogo ficava
    # mentindo em silêncio (os endpoints de cobertura e `/system-modules/mapa`
    # reportavam 48 skills que a tabela não tinha). O método seguia aplicado por
    # outro caminho — `orchestrator` injeta os blocos de prompt —, o que tornava
    # a divergência ainda mais difícil de perceber.
    #
    # Lacuna de CONTEÚDO (área sem método) não pode bloquear o que já está
    # pronto; defeito de ESTRUTURA (módulo sem método, área fora do enum) pode.
    if not coverage["estrutura_ok"]:
        raise RuntimeError(f"Catálogo nativo estruturalmente inválido: {coverage}")

    faltando = coverage["legal_areas"]["missing"]
    if faltando:
        print(
            f"[skills_native_ejc] AVISO: {len(faltando)} área(s) canônica(s) "
            f"sem método de ramo — {', '.join(faltando)}. As demais são "
            "semeadas normalmente; escrever esses métodos exige advogado."
        )

    engine = create_engine(_sync_database_url())
    inserted = updated = unchanged = 0
    select_sql = text(
        """
        SELECT display_name, description, system_prompt, engine, area, active,
               requires_case, requires_human_review, oab_restricted, version
          FROM ejc_skills
         WHERE name = :name
        """
    )
    insert_sql = text(
        """
        INSERT INTO ejc_skills (
            id, name, display_name, description, system_prompt, engine, area,
            active, requires_case, requires_human_review, oab_restricted,
            version, created_at, updated_at
        ) VALUES (
            :id, :name, :display_name, :description, :system_prompt, :engine,
            :area, :active, :requires_case, :requires_human_review,
            :oab_restricted, 1, :now, :now
        )
        """
    )
    update_sql = text(
        """
        UPDATE ejc_skills
           SET display_name = :display_name,
               description = :description,
               system_prompt = :system_prompt,
               engine = :engine,
               area = :area,
               active = :active,
               requires_case = :requires_case,
               requires_human_review = :requires_human_review,
               oab_restricted = :oab_restricted,
               version = :version,
               updated_at = :now
         WHERE name = :name
        """
    )

    try:
        with Session(engine) as session:
            for spec in native_skill_specs():
                data = _payload(spec)
                row = session.execute(select_sql, {"name": spec.name}).fetchone()
                now = datetime.now(timezone.utc)
                if row is None:
                    session.execute(
                        insert_sql,
                        {**data, "id": str(uuid4()), "now": now},
                    )
                    inserted += 1
                    continue

                current = dict(row._mapping)
                changed = any(current[field] != data[field] for field in _FIELDS)
                if not changed:
                    unchanged += 1
                    continue

                session.execute(
                    update_sql,
                    {
                        **data,
                        "version": int(current["version"] or 1) + 1,
                        "now": now,
                    },
                )
                updated += 1
            session.commit()
    finally:
        engine.dispose()

    print(
        "[seed] skills nativas EJC: "
        f"{inserted} inseridas, {updated} atualizadas, "
        f"{unchanged} inalteradas; cobertura={coverage['total_native_skills']}."
    )


if __name__ == "__main__":
    seed()
