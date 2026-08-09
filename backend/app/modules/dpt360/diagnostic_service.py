from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.schemas import (
    DptDiagnosticAreaReadiness,
    DptDiagnosticEvidence,
    DptDiagnosticKind,
    DptDiagnosticReadiness,
)

DIAGNOSTIC_AREAS: dict[DptDiagnosticKind, list[str]] = {
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
    """Sinais factuais com aderência setorial conhecida.

    A contagem global de documentos do cliente NÃO é usada como evidência de
    uma área: sem classificação/vínculo semântico, um PDF trabalhista não pode
    "preencher" prontidão tributária e vice-versa.
    """
    cases = set(profile.areas_com_casos)
    return {
        "tributario": [
            {
                "tipo": "casos_tributarios",
                "presente": "tributario" in cases,
                "quantidade": 1 if "tributario" in cases else 0,
            },
        ],
        "ambiental": [
            {
                "tipo": "casos_ambientais",
                "presente": "ambiental" in cases,
                "quantidade": 1 if "ambiental" in cases else 0,
            },
            {
                "tipo": "autos_ambientais",
                "presente": profile.autos_ambientais > 0,
                "quantidade": profile.autos_ambientais,
            },
        ],
        "administrativo": [
            {
                "tipo": "casos_administrativos_licitacoes",
                "presente": "administrativo" in cases or "licitacoes" in cases,
                "quantidade": (
                    1 if "administrativo" in cases or "licitacoes" in cases else 0
                ),
            },
        ],
        "trabalhista": [
            {
                "tipo": "casos_trabalhistas",
                "presente": "trabalhista" in cases,
                "quantidade": 1 if "trabalhista" in cases else 0,
            },
        ],
        "contratual": [
            {
                "tipo": "casos_contratuais_empresariais",
                "presente": "contratual" in cases or "empresarial" in cases,
                "quantidade": (
                    1 if "contratual" in cases or "empresarial" in cases else 0
                ),
            },
            {
                "tipo": "estrutura_societaria",
                "presente": profile.sociedades > 0,
                "quantidade": profile.sociedades,
            },
        ],
        "lgpd": [
            {
                "tipo": "ropa",
                "presente": profile.operacoes_lgpd > 0,
                "quantidade": profile.operacoes_lgpd,
            },
        ],
        "governanca_ia": [
            {"tipo": "inventario_ia", "presente": False, "quantidade": 0},
        ],
    }


async def build_diagnostic_readiness(
    db: AsyncSession,
    user: User,
    client_id: str,
    kind: DptDiagnosticKind = "completo",
) -> DptDiagnosticReadiness | None:
    if kind not in DIAGNOSTIC_AREAS:
        # Defesa para chamadas internas fora do FastAPI. A rota pública já usa
        # Literal e devolve 422 antes de chegar aqui.
        raise ValueError(f"Tipo de diagnóstico DPT inválido: {kind}")

    profile = await get_company_profile(db, user, client_id)
    if profile is None:
        return None

    evidences = _evidence_map(profile)
    areas: list[DptDiagnosticAreaReadiness] = []
    for area in DIAGNOSTIC_AREAS[kind]:
        area_evidence = evidences[area]
        present = [
            DptDiagnosticEvidence.model_validate(item)
            for item in area_evidence
            if item["presente"]
        ]
        gaps = [item["tipo"] for item in area_evidence if not item["presente"]]
        areas.append(
            DptDiagnosticAreaReadiness(
                area=area,
                estado="com_evidencias" if present else "nao_avaliado",
                evidencias_disponiveis=present,
                lacunas_preliminares=gaps,
                regra="lacuna de registro não equivale a irregularidade nem a regularidade",
            )
        )

    return DptDiagnosticReadiness(
        client_id=client_id,
        tipo=kind,
        generated_at=datetime.now(timezone.utc),
        areas=areas,
        pode_iniciar_analise=True,
        persistencia="nao_habilitada_nesta_pilha",
        motivo_persistencia=(
            "A governança Alembic do EJC exige que migration nova parta diretamente do head canônico da main; "
            "esta entrega não cria migration concorrente."
        ),
        hitl="obrigatorio",
    )
