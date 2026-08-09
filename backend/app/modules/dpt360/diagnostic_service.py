from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile

DIAGNOSTIC_AREAS = {
    "completo": [
        "tributario",
        "ambiental",
        "administrativo",
        "trabalhista",
        "contratual",
        "lgpd",
        "governanca_ia",
    ],
    "tributario": ["tributario"],
    "ambiental": ["ambiental"],
    "administrativo": ["administrativo"],
    "trabalhista": ["trabalhista"],
    "contratual": ["contratual"],
    "lgpd": ["lgpd"],
    "governanca_ia": ["governanca_ia"],
}


def _evidence_map(profile) -> dict[str, list[dict[str, Any]]]:
    cases = set(profile.areas_com_casos)
    return {
        "tributario": [
            {"tipo": "casos", "presente": "tributario" in cases, "quantidade": None},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "ambiental": [
            {"tipo": "casos", "presente": "ambiental" in cases, "quantidade": None},
            {"tipo": "autos_ambientais", "presente": profile.autos_ambientais > 0, "quantidade": profile.autos_ambientais},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "administrativo": [
            {"tipo": "casos", "presente": "administrativo" in cases or "licitacoes" in cases, "quantidade": None},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "trabalhista": [
            {"tipo": "casos", "presente": "trabalhista" in cases, "quantidade": None},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "contratual": [
            {"tipo": "casos", "presente": "contratual" in cases or "empresarial" in cases, "quantidade": None},
            {"tipo": "societario", "presente": profile.sociedades > 0, "quantidade": profile.sociedades},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "lgpd": [
            {"tipo": "ropa", "presente": profile.operacoes_lgpd > 0, "quantidade": profile.operacoes_lgpd},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
        "governanca_ia": [
            {"tipo": "inventario_ia", "presente": False, "quantidade": 0},
            {"tipo": "documentos", "presente": profile.documentos > 0, "quantidade": profile.documentos},
        ],
    }


async def build_diagnostic_readiness(
    db: AsyncSession,
    user: User,
    client_id: str,
    kind: str = "completo",
) -> dict[str, Any] | None:
    profile = await get_company_profile(db, user, client_id)
    if profile is None:
        return None
    normalized = kind if kind in DIAGNOSTIC_AREAS else "completo"
    evidences = _evidence_map(profile)
    areas: list[dict[str, Any]] = []
    for area in DIAGNOSTIC_AREAS[normalized]:
        area_evidence = evidences[area]
        present = [item for item in area_evidence if item["presente"]]
        gaps = [item["tipo"] for item in area_evidence if not item["presente"]]
        areas.append(
            {
                "area": area,
                "estado": "com_evidencias" if present else "nao_avaliado",
                "evidencias_disponiveis": present,
                "lacunas_preliminares": gaps,
                "regra": "lacuna documental não equivale a irregularidade",
            }
        )
    return {
        "client_id": client_id,
        "tipo": normalized,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "areas": areas,
        "pode_iniciar_analise": True,
        "persistencia": "nao_habilitada_nesta_pilha",
        "motivo_persistencia": (
            "A governança Alembic do EJC exige que migration nova parta diretamente do head canônico da main; "
            "esta Onda está empilhada e não cria migration concorrente."
        ),
        "hitl": "obrigatorio",
    }
