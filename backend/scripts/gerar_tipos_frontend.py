"""Gera `frontend/src/types/gerado.ts` a partir dos enums canônicos do backend.

S1 (relatório E2E 2026-09-03, §9.3): "gerar, não copiar". Os tipos TS de
área do direito, status de caso/peça/prazo, origem de prazo e papéis de
usuário eram escritos à mão e divergiam do backend (ex.: `Deadline.origem`
com 4 valores reais contra 3 declarados). Este script é a única fonte do
arquivo TS; o teste `tests/test_tipos_frontend_gerados.py` regenera em
memória e falha quando o arquivo commitado envelhece.

Uso (do diretório `backend/`):

    APP_ENV=development python scripts/gerar_tipos_frontend.py            # grava
    APP_ENV=development python scripts/gerar_tipos_frontend.py --stdout   # imprime
    APP_ENV=development python scripts/gerar_tipos_frontend.py --check    # só compara

Atalho pelo frontend: `npm run types:gerar`.
"""

from __future__ import annotations

import argparse
import enum
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
DESTINO = RAIZ / "frontend" / "src" / "types" / "gerado.ts"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.taxonomia import AREAS_CANONICAS  # noqa: E402
from app.models.ai_log import AIStatusHITL  # noqa: E402
from app.models.case import (  # noqa: E402
    CaseArea,
    CaseFase,
    CasePrioridade,
    CaseStatus,
)
from app.models.deadline import (  # noqa: E402
    DeadlinePrioridade,
    DeadlineStatus,
    DeadlineTipo,
)
from app.models.legal_doc import PecaStatus, PecaTipo  # noqa: E402
from app.models.user import UserRole  # noqa: E402

# `Deadline.origem` é String(20) sem enum no backend (models/deadline.py:65-68);
# os valores reais gravados são estes quatro (entrada_service grava
# `entrada_unica`, importação de documento grava `importacao_ia`). Mantido
# aqui — e não copiado no frontend — até virar enum no model.
DEADLINE_ORIGENS: tuple[str, ...] = (
    "manual",
    "datajud",
    "importacao_ia",
    "entrada_unica",
)

# `core/taxonomia.py` não carrega rótulos; `peca_service.AREAS_DIREITO_LABEL`
# cobre só 17 áreas. Rótulos pt-BR completos ficam aqui e o script REPROVA
# quando uma área nova do enum não tiver rótulo (fonte única, sem cópia).
ROTULOS_AREA: dict[str, str] = {
    "civil": "Cível",
    "trabalhista": "Trabalhista",
    "consumidor": "Consumidor",
    "familia": "Família",
    "ambiental": "Ambiental",
    "criminal": "Criminal",
    "previdenciario": "Previdenciário",
    "empresarial": "Empresarial",
    "tributario": "Tributário",
    "administrativo": "Administrativo",
    "bancario": "Bancário",
    "imobiliario": "Imobiliário",
    "sucessoes": "Sucessões",
    "constitucional": "Constitucional",
    "digital_lgpd": "Digital e LGPD",
    "transito": "Trânsito",
    "saude": "Saúde",
    "medico": "Médico",
    "agrario": "Agrário",
    "agronegocio": "Agronegócio",
    "eleitoral": "Eleitoral",
    "internacional": "Internacional",
    "contratual": "Contratual",
    "societario": "Societário",
    "licitacoes": "Licitações",
}

# Áreas em destaque no menu "Ramos" (Bloco 4 do plano V3: os casos reais são
# consumidor e cível).
AREAS_DESTAQUE: tuple[str, ...] = ("consumidor", "civil")

CABECALHO = """// ARQUIVO GERADO — não edite.
// Fonte: backend/scripts/gerar_tipos_frontend.py (enums de app/models e
// app/core/taxonomia). Regenerar: `npm run types:gerar` (frontend) ou
// `APP_ENV=development python scripts/gerar_tipos_frontend.py` (backend).
// O teste backend/tests/test_tipos_frontend_gerados.py falha quando este
// arquivo diverge do backend.
"""


def _valores(e: type[enum.Enum]) -> list[str]:
    return [str(m.value) for m in e]


def _uniao(nome_const: str, nome_tipo: str, valores: list[str], doc: str) -> str:
    itens = "\n".join(f'  "{v}",' for v in valores)
    return (
        f"/** {doc} */\n"
        f"export const {nome_const} = [\n{itens}\n] as const;\n"
        f"export type {nome_tipo} = (typeof {nome_const})[number];\n"
    )


def gerar() -> str:
    areas = list(AREAS_CANONICAS)
    faltantes = [a for a in areas if a not in ROTULOS_AREA]
    if faltantes:
        raise SystemExit(
            "Área(s) do enum CaseArea sem rótulo em ROTULOS_AREA: "
            + ", ".join(faltantes)
        )
    sobrando = [a for a in ROTULOS_AREA if a not in areas]
    if sobrando:
        raise SystemExit(
            "Rótulo sem área correspondente no enum CaseArea: " + ", ".join(sobrando)
        )
    if list(_valores(CaseArea)) != areas:
        raise SystemExit("AREAS_CANONICAS divergiu do enum CaseArea")
    destaque_invalido = [a for a in AREAS_DESTAQUE if a not in areas]
    if destaque_invalido:
        raise SystemExit("AREAS_DESTAQUE fora do enum: " + ", ".join(destaque_invalido))

    partes: list[str] = [CABECALHO]

    partes.append(
        _uniao(
            "AREAS_CANONICAS",
            "CaseArea",
            areas,
            "Áreas do direito (enum CaseArea / core.taxonomia.AREAS_CANONICAS).",
        )
    )
    rotulos = "\n".join(f'  {a}: "{ROTULOS_AREA[a]}",' for a in areas)
    partes.append(
        "/** Rótulo pt-BR de cada área canônica. */\n"
        f"export const ROTULO_AREA: Record<CaseArea, string> = {{\n{rotulos}\n}};\n"
    )
    destaque = "\n".join(f'  "{a}",' for a in AREAS_DESTAQUE)
    partes.append(
        "/** Áreas em destaque no menu de ramos (casos reais do escritório). */\n"
        f"export const AREAS_DESTAQUE: readonly CaseArea[] = [\n{destaque}\n];\n"
    )

    partes.append(
        _uniao("CASE_STATUS", "CaseStatus", _valores(CaseStatus), "Status do caso (enum CaseStatus).")
    )
    partes.append(_uniao("CASE_FASE", "CaseFase", _valores(CaseFase), "Fase do caso (enum CaseFase)."))
    partes.append(
        _uniao(
            "CASE_PRIORIDADE",
            "CasePrioridade",
            _valores(CasePrioridade),
            "Prioridade do caso (enum CasePrioridade).",
        )
    )
    partes.append(
        _uniao("DEADLINE_TIPO", "DeadlineTipo", _valores(DeadlineTipo), "Tipo de prazo (enum DeadlineTipo).")
    )
    partes.append(
        _uniao(
            "DEADLINE_STATUS",
            "DeadlineStatus",
            _valores(DeadlineStatus),
            "Status de prazo (enum DeadlineStatus).",
        )
    )
    partes.append(
        _uniao(
            "DEADLINE_PRIORIDADE",
            "DeadlinePrioridade",
            _valores(DeadlinePrioridade),
            "Prioridade de prazo (enum DeadlinePrioridade).",
        )
    )
    partes.append(
        _uniao(
            "DEADLINE_ORIGEM",
            "DeadlineOrigem",
            list(DEADLINE_ORIGENS),
            "Origem do prazo (coluna deadlines.origem — valores reais gravados).",
        )
    )
    partes.append(_uniao("USER_ROLE", "UserRole", _valores(UserRole), "Papéis de usuário (enum UserRole)."))
    partes.append(_uniao("PECA_STATUS", "PecaStatus", _valores(PecaStatus), "Status de peça (enum PecaStatus)."))
    partes.append(_uniao("PECA_TIPO", "PecaTipo", _valores(PecaTipo), "Tipo de peça (enum PecaTipo)."))
    partes.append(
        _uniao(
            "AI_STATUS_HITL",
            "AIStatusHITL",
            _valores(AIStatusHITL),
            "Status de revisão humana de output de IA (enum AIStatusHITL).",
        )
    )
    return "\n".join(partes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--stdout", action="store_true", help="imprime em vez de gravar")
    grupo.add_argument("--check", action="store_true", help="compara com o arquivo commitado")
    args = parser.parse_args(argv)

    conteudo = gerar()
    if args.stdout:
        sys.stdout.write(conteudo)
        return 0
    if args.check:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != conteudo:
            sys.stderr.write(f"{DESTINO} desatualizado — rode o script sem --check.\n")
            return 1
        print(f"{DESTINO} em dia.")
        return 0
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(conteudo, encoding="utf-8")
    print(f"gerado: {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
