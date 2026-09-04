"""seeds/seed_demo.py — dados fictícios de DEMONSTRAÇÃO (dev/homologação).

Cria um conjunto pequeno e coerente de dados de demonstração — clientes (PF e
PJ), casos em áreas variadas e prazos (futuros e um vencido) vinculados —
para que um ambiente recém-provisionado tenha o que mostrar numa demo sem
depender de dados reais. Pente fino E2E de 30/08/2026, §7.4.

Contratos (mesmos de seeds/seed_all.py):
  - conexão pelo engine ASYNC do app (`AsyncSessionLocal` — asyncpg, lê
    DATABASE_URL do ambiente/.env como o próprio backend);
  - IDEMPOTENTE: rodar N vezes não duplica nem sobrescreve (cada registro é
    localizado por uma chave estável antes de criar);
  - uso: `python seeds/seed_demo.py` (WORKDIR backend/).

Guardas:
  - RECUSA rodar com APP_ENV=production — dado fictício não entra em produção;
  - todo registro carrega o marcador "DEMO-FICTICIO" no nome/título (fácil de
    localizar e de limpar);
  - e-mails fictícios só em @example.com (domínio reservado, RFC 2606);
  - CPFs/CNPJs são SINTÉTICOS com dígitos verificadores calculados (o cadastro
    real valida DV; um documento inválido quebraria fluxos de demo), cifrados
    pelo mesmo `pii_crypto` que o cadastro usa (Fernet + hash cego).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Executável de qualquer cwd: `python seeds/seed_demo.py` fora do container
# não tem `backend/` no sys.path (no container, WORKDIR /app resolve via
# PYTHONPATH). Não afeta o import quando o pacote `app` já é resolvível.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

MARCADOR = "DEMO-FICTICIO"


def _abortar_se_producao() -> None:
    app_env = (os.environ.get("APP_ENV") or "").strip().lower()
    if app_env == "production":
        raise SystemExit(
            "[seed_demo] RECUSADO: APP_ENV=production — este seed cria dados "
            "FICTÍCIOS de demonstração e não pode rodar em produção. "
            "Use um ambiente de desenvolvimento/homologação."
        )


# ── Documentos sintéticos com DV válido ──────────────────────────────────────


def cpf_valido(base9: str) -> str:
    """Completa 9 dígitos com os 2 DVs do CPF (módulo 11)."""
    digitos = [int(c) for c in base9]
    assert len(digitos) == 9 and len(set(digitos)) > 1
    for _ in range(2):
        soma = sum(d * p for d, p in zip(digitos, range(len(digitos) + 1, 1, -1)))
        resto = (soma * 10) % 11
        digitos.append(0 if resto == 10 else resto)
    return "".join(str(d) for d in digitos)


def cnpj_valido(base8: str) -> str:
    """Completa raiz de 8 dígitos + filial 0001 com os 2 DVs do CNPJ."""
    digitos = [int(c) for c in base8] + [0, 0, 0, 1]
    assert len(digitos) == 12

    def dv(ds: list[int], pesos: list[int]) -> int:
        resto = sum(d * p for d, p in zip(ds, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(digitos, pesos1)
    d2 = dv(digitos + [d1], [6] + pesos1)
    return "".join(str(d) for d in digitos + [d1, d2])


# ── Massa de demonstração (determinística — chave estável p/ idempotência) ───

CLIENTES_DEMO: list[dict] = [
    {
        "tipo": "PF",
        "nome": f"{MARCADOR} Ana Beatriz Exemplo",
        "cpf": cpf_valido("123456780"),
        "email": "ana.demo@example.com",
        "telefone": "31988880001",
        "cidade": "Betim",
        "estado": "MG",
    },
    {
        "tipo": "PF",
        "nome": f"{MARCADOR} Carlos Eduardo Modelo",
        "cpf": cpf_valido("987654320"),
        "email": "carlos.demo@example.com",
        "telefone": "31988880002",
        "cidade": "Contagem",
        "estado": "MG",
    },
    {
        "tipo": "PJ",
        "razao_social": f"{MARCADOR} Padaria Pão Quente Ltda",
        "nome_fantasia": "Pão Quente (demo)",
        "cnpj": cnpj_valido("12345678"),
        "email": "padaria.demo@example.com",
        "telefone": "3135550001",
        "cidade": "Betim",
        "estado": "MG",
    },
    {
        "tipo": "PJ",
        "razao_social": f"{MARCADOR} Transportadora Horizonte S.A.",
        "nome_fantasia": "Horizonte Log (demo)",
        "cnpj": cnpj_valido("87654321"),
        "email": "transportadora.demo@example.com",
        "telefone": "3135550002",
        "cidade": "Belo Horizonte",
        "estado": "MG",
    },
]

# cliente_idx aponta para CLIENTES_DEMO; numero_interno é a chave idempotente
# (índice único parcial de cases cobre só ativos — o prefixo DEMO- não colide
# com a numeração real DPT-AAAA-NNNN de services/case_numeracao.py).
CASOS_DEMO: list[dict] = [
    {
        "numero_interno": "DEMO-2026-0001",
        "titulo": f"{MARCADOR} Reclamação trabalhista — verbas rescisórias",
        "area": "trabalhista",
        "cliente_idx": 0,
        "comarca": "Betim",
        "valor_causa": Decimal("25000.00"),
        "proxima_acao": "Elaborar reclamação trabalhista com pedido de verbas rescisórias",
    },
    {
        "numero_interno": "DEMO-2026-0002",
        "titulo": f"{MARCADOR} Cobrança indevida de telefonia",
        "area": "consumidor",
        "cliente_idx": 0,
        "comarca": "Betim",
        "valor_causa": Decimal("8000.00"),
        "proxima_acao": "Reunir faturas e protocolos para a petição inicial no JEC",
    },
    {
        "numero_interno": "DEMO-2026-0003",
        "titulo": f"{MARCADOR} Revisão de benefício previdenciário",
        "area": "previdenciario",
        "cliente_idx": 1,
        "comarca": "Contagem",
        "valor_causa": Decimal("42000.00"),
        "proxima_acao": "Solicitar CNIS atualizado e simular regras de transição",
    },
    {
        "numero_interno": "DEMO-2026-0004",
        "titulo": f"{MARCADOR} Ação de indenização por acidente de trânsito",
        "area": "civil",
        "cliente_idx": 1,
        "comarca": "Contagem",
        "valor_causa": Decimal("15000.00"),
        "proxima_acao": "Notificar seguradora e juntar boletim de ocorrência",
    },
    {
        "numero_interno": "DEMO-2026-0005",
        "titulo": f"{MARCADOR} Recuperação de crédito — contratos de fornecimento",
        "area": "empresarial",
        "cliente_idx": 2,
        "comarca": "Betim",
        "valor_causa": Decimal("120000.00"),
        "proxima_acao": "Enviar notificação extrajudicial aos devedores",
    },
    {
        "numero_interno": "DEMO-2026-0006",
        "titulo": f"{MARCADOR} Defesa em auto de infração fiscal (ICMS)",
        "area": "tributario",
        "cliente_idx": 3,
        "comarca": "Belo Horizonte",
        "valor_causa": Decimal("310000.00"),
        "proxima_acao": "Protocolar impugnação administrativa dentro do prazo legal",
    },
]

# caso_idx aponta para CASOS_DEMO; dias é relativo a hoje (negativo = vencido).
PRAZOS_DEMO: list[dict] = [
    {"titulo": f"{MARCADOR} Audiência inicial trabalhista", "caso_idx": 0,
     "dias": 15, "tipo": "audiencia", "prioridade": "alta"},
    {"titulo": f"{MARCADOR} Protocolo da inicial no JEC", "caso_idx": 1,
     "dias": 7, "tipo": "processual", "prioridade": "alta"},
    {"titulo": f"{MARCADOR} Juntada do CNIS atualizado", "caso_idx": 2,
     "dias": 30, "tipo": "interno", "prioridade": "media"},
    {"titulo": f"{MARCADOR} Resposta da seguradora (acompanhar)", "caso_idx": 3,
     "dias": 45, "tipo": "interno", "prioridade": "baixa"},
    {"titulo": f"{MARCADOR} Prazo de impugnação fiscal", "caso_idx": 5,
     "dias": 20, "tipo": "administrativo", "prioridade": "critica"},
    # Um prazo VENCIDO de propósito: demos de dashboard/alerta precisam de um.
    {"titulo": f"{MARCADOR} Notificação extrajudicial (vencido)", "caso_idx": 4,
     "dias": -10, "tipo": "interno", "prioridade": "alta", "status": "vencido"},
]


async def seed_demo() -> dict[str, dict[str, int]]:
    _abortar_se_producao()

    # Imports tardios: exigem settings/engine prontos (mesmo padrão do app).
    from app.core.database import AsyncSessionLocal
    from app.models.case import Case, CaseArea, CasePrioridade, CaseStatus
    from app.models.client import Client, ClientTipo
    from app.models.deadline import (
        Deadline,
        DeadlinePrioridade,
        DeadlineStatus,
        DeadlineTipo,
    )
    from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento

    contagem = {k: {"criados": 0, "existentes": 0} for k in ("clientes", "casos", "prazos")}

    async with AsyncSessionLocal() as db:
        # ── Clientes (chave idempotente: e-mail fictício) ────────────────────
        clientes: list[Client] = []
        for dados in CLIENTES_DEMO:
            existente = (
                await db.execute(
                    select(Client).where(
                        Client.email == dados["email"], Client.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            if existente:
                clientes.append(existente)
                contagem["clientes"]["existentes"] += 1
                continue
            eh_pf = dados["tipo"] == "PF"
            doc = normalizar_documento(dados.get("cpf") if eh_pf else dados.get("cnpj"))
            cliente = Client(
                id=str(uuid4()),
                tipo=ClientTipo.PF if eh_pf else ClientTipo.PJ,
                nome=dados.get("nome"),
                razao_social=dados.get("razao_social"),
                nome_fantasia=dados.get("nome_fantasia"),
                cpf_enc=encrypt(doc) if eh_pf else None,
                cnpj_enc=encrypt(doc) if not eh_pf else None,
                cpf_hash=hash_documento(doc) if eh_pf else None,
                cnpj_hash=hash_documento(doc) if not eh_pf else None,
                email=dados["email"],
                telefone=dados["telefone"],
                cidade=dados["cidade"],
                estado=dados["estado"],
                observacoes=f"{MARCADOR}: registro de demonstração criado por seeds/seed_demo.py.",
            )
            db.add(cliente)
            clientes.append(cliente)
            contagem["clientes"]["criados"] += 1
        await db.flush()

        # ── Casos (chave idempotente: numero_interno DEMO-…) ─────────────────
        casos: list[Case] = []
        for dados in CASOS_DEMO:
            existente = (
                await db.execute(
                    select(Case).where(
                        Case.numero_interno == dados["numero_interno"],
                        Case.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existente:
                casos.append(existente)
                contagem["casos"]["existentes"] += 1
                continue
            caso = Case(
                id=str(uuid4()),
                numero_interno=dados["numero_interno"],
                titulo=dados["titulo"],
                area=CaseArea(dados["area"]),
                status=CaseStatus.aberto,
                prioridade=CasePrioridade.media,
                comarca=dados["comarca"],
                valor_causa=dados["valor_causa"],
                # Obrigatória por regra de negócio para caso aberto (G1 — o
                # router exige; via model não passa pelo router, mas o dado de
                # demo respeita a mesma invariante).
                proxima_acao=dados["proxima_acao"],
                descricao_fatos=f"{MARCADOR}: fatos fictícios para demonstração.",
                client_id=clientes[dados["cliente_idx"]].id,
            )
            db.add(caso)
            casos.append(caso)
            contagem["casos"]["criados"] += 1
        await db.flush()

        # ── Prazos (chave idempotente: título + caso) ────────────────────────
        hoje = date.today()
        for dados in PRAZOS_DEMO:
            caso = casos[dados["caso_idx"]]
            existente = (
                await db.execute(
                    select(Deadline).where(
                        Deadline.titulo == dados["titulo"],
                        Deadline.case_id == caso.id,
                        Deadline.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existente:
                contagem["prazos"]["existentes"] += 1
                continue
            vencido = dados.get("status") == "vencido"
            db.add(
                Deadline(
                    id=str(uuid4()),
                    titulo=dados["titulo"],
                    descricao=f"{MARCADOR}: prazo fictício de demonstração.",
                    tipo=DeadlineTipo(dados["tipo"]),
                    prioridade=DeadlinePrioridade(dados["prioridade"]),
                    status=DeadlineStatus.vencido if vencido else DeadlineStatus.pendente,
                    data_prazo=hoje + timedelta(days=dados["dias"]),
                    data_intimacao=hoje + timedelta(days=dados["dias"] - 15),
                    case_id=caso.id,
                    observacoes=f"{MARCADOR} seeds/seed_demo.py em "
                    f"{datetime.now(timezone.utc).date().isoformat()}",
                )
            )
            contagem["prazos"]["criados"] += 1

        await db.commit()

    for entidade, c in contagem.items():
        print(f"[seed_demo] {entidade}: {c['criados']} criado(s), "
              f"{c['existentes']} já existente(s).")
    print(f"[seed_demo] concluído — todos os registros carregam o marcador '{MARCADOR}'.")
    return contagem


if __name__ == "__main__":
    asyncio.run(seed_demo())
