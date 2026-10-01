#!/usr/bin/env python3
"""Seed do dataset sintético de performance — cadeia Entrada → Caso → Hoje.

Plano completo: docs/performance/ejc-entrada-caso-hoje-baseline.md §7.

Executor do dataset em banco de homolog ISOLADO. NUNCA apontar para produção.

Guardas anti-produção (ambas obrigatórias):
  1. A URL de conexão (SEED_DATABASE_URL, com fallback DATABASE_URL) precisa
     conter o marcador `homolog_perf` no nome do banco.
  2. A variável SEED_HOMOLOG_PERF=1 precisa estar afirmada no ambiente.

Pré-requisitos: migrations aplicadas até o HEAD (`alembic upgrade head` é
responsabilidade do ambiente — o seed NÃO roda migrations).

Idempotência: todos os IDs são uuid5 determinísticos do namespace
`perf.ejc.homolog`; reexecutar refaz `ON CONFLICT DO NOTHING` e termina com as
mesmas contagens (sem duplicar).

Uso:
  SEED_HOMOLOG_PERF=1 \
  SEED_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ejc_homolog_perf \
  python3 scripts/perf/seed_homolog.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta

# ── Guardas anti-produção ────────────────────────────────────────────────────
MARKER = "homolog_perf"
ENV_FLAG = "SEED_HOMOLOG_PERF"


def _url() -> str:
    url = os.getenv("SEED_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if MARKER not in url:
        sys.exit(
            f"[seed-perf] RECUSADO: a URL precisa conter '{MARKER}'. "
            "Este dataset é exclusivo de homolog isolado."
        )
    return url


def _guard() -> None:
    if os.getenv(ENV_FLAG) != "1":
        sys.exit(
            f"[seed-perf] RECUSADO: defina {ENV_FLAG}=1 para confirmar "
            "que o alvo é homolog isolado (nunca produção)."
        )
    _url()


NS = uuid.uuid5(uuid.NAMESPACE_URL, "perf.ejc.homolog")


def uid(chave: str) -> str:
    return str(uuid.uuid5(NS, chave))


HOJE = date.today()

# ── Atores (baseline §7.2) ───────────────────────────────────────────────────
ATORES = [
    ("perf-superadmin", "superadmin"),
    ("perf-socio", "socio"),
    ("perf-advogado-a", "advogado"),
    ("perf-advogado-b", "advogado"),
    ("perf-auxiliar-a", "advogado_auxiliar"),
    ("perf-estagiario", "estagiario"),
    ("perf-secretaria", "secretaria"),
    ("perf-cliente-x", "cliente_externo"),
]

N_CLIENTS_A, N_CLIENTS_B, N_CLIENTS_N = 60, 60, 80
N_CASES_A, N_CASES_B, N_CASES_ORFAOS = 25, 25, 10
N_DEADLINES = 1500
N_DEADLINES_ANTIGAS = 12000
N_TASKS = 800
N_AGENDA = 2000
N_DJEN = 1200
N_DOCS = 3000
N_DOCS_RESTRITOS = 10
N_FEES = 300
N_LEGAL_DOCS = 40
N_LEGAL_FILA = 15  # em_revisao/corrigida (fila HITL > amostra de 30 do browser)


def _lote(sql: str, linhas: list[dict], conn) -> int:
    if not linhas:
        return 0
    from sqlalchemy import text

    r = conn.execute(text(sql), linhas)
    return r.rowcount or 0


async def seed() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_url(), pool_pre_ping=True)
    async with engine.begin() as conn:
        # Idempotência por âncora: se o sócio âncora existe, termina cedo.
        ancora = (
            await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE email = :e"),
                {"e": "perf-socio@homolog.local"},
            )
        ).scalar()
        if ancora:
            print("[seed-perf] dataset já presente (âncora encontrada) — nada a fazer.")
            await _registro(conn)
            await engine.dispose()
            return

        # ── Users ────────────────────────────────────────────────────────
        _lote(
            """INSERT INTO users (id, email, hashed_password, full_name, role,
                is_active, created_at, updated_at)
               VALUES (:id, :email, 'x', :nome, :role::userrole, true, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            [
                {"id": uid(f"user:{e}"), "email": f"{e}@homolog.local", "role": r,
                 "nome": r.replace("_", " ").title()}
                for e, r in ATORES
            ],
            conn,
        )
        A = uid("user:perf-advogado-a")
        B = uid("user:perf-advogado-b")
        AUX = uid("user:perf-auxiliar-a")
        SOC = uid("user:perf-socio")
        CLI_X_USER = uid("user:perf-cliente-x")

        # ── Clients (60 carteira A, 60 B, 80 neutros + cliente X) ────────
        clientes: list[dict] = []
        for i in range(N_CLIENTS_A + N_CLIENTS_B + N_CLIENTS_N):
            dono = A if i < N_CLIENTS_A else (B if i < N_CLIENTS_A + N_CLIENTS_B else SOC)
            clientes.append({
                "id": uid(f"client:{i}"), "tipo": "PF",
                "nome": f"Cliente Perf {i:03d}",
                "email": f"cliente{i:03d}@homolog.local",
                "status": "ativo", "responsavel_id": dono,
            })
        clientes.append({
            "id": uid("client:X"), "tipo": "PF", "nome": "Cliente Portal X",
            "email": "clientex@homolog.local", "status": "ativo",
            "responsavel_id": A,
        })
        _lote(
            """INSERT INTO clients (id, tipo, nome, email, status,
                responsavel_id, created_at, updated_at)
               VALUES (:id, :tipo::clienttipo, :nome, :email,
                :status::clientstatus, :responsavel_id, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            clientes, conn,
        )
        CLIENT_X = uid("client:X")

        # Hash cego do CPF sintático do cliente X (busca exata da matriz).
        # Exige PII_HASH_KEY no ambiente; sem a chave, a célula de busca por
        # CPF fica sem hash e o seed segue (registrado no log).
        cpf_x = "11144477735"  # CPF sintático válido (dígito verificador ok)
        if os.getenv("PII_HASH_KEY"):
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
            from app.services.pii_crypto import hash_documento, normalizar_documento

            dig = normalizar_documento(cpf_x)
            _lote(
                "UPDATE clients SET cpf_hash = :h WHERE id = :i",
                [{"h": hash_documento(dig), "i": CLIENT_X}], conn,
            )
            print("[seed-perf] cpf_hash do cliente X semeado.")
        else:
            print("[seed-perf] AVISO: PII_HASH_KEY ausente — cliente X sem cpf_hash.")

        # ── Cases (25 A, 25 B, 10 órfãos; A1 = caso do auxiliar) ─────────
        casos: list[dict] = []

        def _caso(n: int, resp: str | None, aux: str | None) -> dict:
            status = "aberto" if n % 4 else "em_instrucao"
            prazo = HOJE + timedelta(days=(n % 40) - 5)
            return {
                "id": uid(f"case:{n}"), "titulo": f"Caso Perf {n:03d}",
                "area": "civil", "status": status, "client_id": uid(f"client:{n % 200}"),
                "advogado_responsavel_id": resp, "advogado_auxiliar_id": aux,
                "proxima_acao": f"Atuar no caso {n:03d}",
                "proxima_acao_prazo": prazo if n % 2 else None,
                "prioridade": ("urgente" if n % 10 == 0 else "alta" if n % 5 == 0 else "media"),
                "risco": ("alto" if n % 7 == 0 else "critico" if n % 23 == 0 else "baixo"),
            }

        for n in range(N_CASES_A):
            casos.append(_caso(n, A, AUX if n == 1 else None))
        for n in range(N_CASES_A, N_CASES_A + N_CASES_B):
            casos.append(_caso(n, B, None))
        for n in range(N_CASES_A + N_CASES_B, N_CASES_A + N_CASES_B + N_CASES_ORFAOS):
            c = _caso(n, None, None)
            c["status"] = "aberto"
            casos.append(c)
        _lote(
            """INSERT INTO cases (id, titulo, area, status, client_id,
                advogado_responsavel_id, advogado_auxiliar_id, proxima_acao,
                proxima_acao_prazo, prioridade, risco, created_at, updated_at)
               VALUES (:id, :titulo, :area::casearea, :status::casestatus,
                :client_id, :advogado_responsavel_id, :advogado_auxiliar_id,
                :proxima_acao, :proxima_acao_prazo, :prioridade::caseprioridade,
                :risco, now(), now()) ON CONFLICT (id) DO NOTHING""",
            casos, conn,
        )
        CASE_A1 = uid("case:1")

        # ── Deadlines (1.500 + 12.000 antigas; 20 empatadas) ─────────────
        prazos: list[dict] = []
        for i in range(N_DEADLINES):
            dono_caso = i % 3 == 0
            prazos.append({
                "id": uid(f"dl:{i}"), "titulo": f"Prazo Perf {i:04d}",
                "tipo": "processual", "prioridade": "media",
                "status": ("pendente" if i % 3 else "vencido" if i % 7 == 0 else "concluido"),
                "dp": HOJE + timedelta(days=(i % 45) - 15),
                "case_id": uid(f"case:{i % 50}") if dono_caso else None,
                "resp": A if i % 2 else B if not dono_caso and i % 5 == 0 else (A if dono_caso else SOC),
            })
        # 20 prazos com data idêntica (prova de tie/desempate do cursor)
        tie = HOJE + timedelta(days=3)
        for i in range(20):
            prazos.append({
                "id": uid(f"dl:tie:{i}"), "titulo": f"Prazo Empatado {i:02d}",
                "tipo": "processual", "prioridade": "alta", "status": "pendente",
                "dp": tie, "case_id": uid("case:0"), "resp": A,
            })
        _lote(
            """INSERT INTO deadlines (id, titulo, tipo, prioridade, status,
                data_prazo, case_id, responsavel_id, created_at, updated_at)
               VALUES (:id, :titulo, :tipo::deadlinetipo,
                :prioridade::deadlineprioridade, :status::deadlinestatus,
                :dp, :case_id, :resp, now(), now()) ON CONFLICT (id) DO NOTHING""",
            prazos, conn,
        )
        antigas: list[dict] = []
        for i in range(N_DEADLINES_ANTIGAS):
            antigas.append({
                "id": uid(f"dl:old:{i}"), "titulo": f"Prazo Arquivado {i:05d}",
                "status": "concluido", "dp": HOJE - timedelta(days=60 + (i % 900)),
                "case_id": uid(f"case:{i % 50}"), "resp": A if i % 2 else B,
            })
        _lote(
            """INSERT INTO deadlines (id, titulo, tipo, prioridade, status,
                data_prazo, case_id, responsavel_id, created_at, updated_at)
               VALUES (:id, :titulo, 'processual'::deadlinetipo, 'baixa',
                :status::deadlinestatus, :dp, :case_id, :resp, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            antigas, conn,
        )

        # ── Tasks (800; 30 caseless; 20 empatadas) ───────────────────────
        tarefas: list[dict] = []
        for i in range(N_TASKS):
            caseless = i < 30
            tarefas.append({
                "id": uid(f"tk:{i}"), "titulo": f"Tarefa Perf {i:04d}",
                "status": ("concluida" if i % 5 == 0 else "a_fazer"),
                "prioridade": ("urgente" if i % 11 == 0 else "alta" if i % 7 == 0 else "media"),
                "dl": None if caseless and i % 3 == 0 else HOJE + timedelta(days=(i % 30) - 10),
                "case_id": None if caseless else uid(f"case:{i % 50}"),
                "resp": A if i % 2 else B, "criador": A,
            })
        tiet = HOJE
        for i in range(20):
            tarefas.append({
                "id": uid(f"tk:tie:{i}"), "titulo": f"Tarefa Empatada {i:02d}",
                "status": "a_fazer", "prioridade": "alta", "dl": tiet,
                "case_id": uid("case:2"), "resp": A, "criador": A,
            })
        _lote(
            """INSERT INTO tasks (id, titulo, status, prioridade, data_limite,
                case_id, responsavel_id, criado_por, created_at, updated_at)
               VALUES (:id, :titulo, :status::taskstatus, :prioridade, :dl,
                :case_id, :resp, :criador, now(), now()) ON CONFLICT (id) DO NOTHING""",
            tarefas, conn,
        )

        # ── Agenda (2.000; 500 futuros pendentes) ────────────────────────
        agenda: list[dict] = []
        for i in range(N_AGENDA):
            futuro = i < 500
            agenda.append({
                "id": uid(f"ag:{i}"), "titulo": f"Evento Perf {i:04d}",
                "tipo": "audiencia" if i % 4 == 0 else "compromisso",
                "de": HOJE + timedelta(days=(i % 60) - 10 if futuro else -(i % 200) - 10),
                "case_id": uid(f"case:{i % 50}"),
                "resp": A if i % 2 else B, "concluido": not futuro and i % 3 == 0,
            })
        _lote(
            """INSERT INTO agenda_eventos (id, titulo, tipo, data_evento,
                case_id, responsavel_id, concluido, created_by, created_at, updated_at)
               VALUES (:id, :titulo, :tipo, :de, :case_id, :resp, :concluido,
                :resp, now(), now()) ON CONFLICT (id) DO NOTHING""",
            agenda, conn,
        )

        # ── DJEN (1.200; 400 não processadas) ────────────────────────────
        djen: list[dict] = []
        for i in range(N_DJEN):
            djen.append({
                "id": uid(f"dj:{i}"),
                "ext": f"PERF-{i:06d}",
                "adv": A if i % 2 else B,
                "dd": HOJE - timedelta(days=i % 120),
                "proc": i >= 400,
                "case_id": uid(f"case:{i % 50}") if i % 3 == 0 else None,
            })
        _lote(
            """INSERT INTO djen_comunicacoes (id, comunicacao_id_externo,
                advogado_id, data_disponibilizacao, processada, case_id,
                tipo_comunicacao, texto_resumo, created_at, updated_at)
               VALUES (:id, :ext, :adv, :dd, :proc, :case_id, 'intimacao',
                'Resumo sintético da comunicação PERF', now(), now())
               ON CONFLICT (id) DO NOTHING""",
            djen, conn,
        )

        # ── Documents (3.000; 10 restritos no caso A; termo canário OCR) ─
        docs: list[dict] = []
        for i in range(N_DOCS):
            restrito = i < N_DOCS_RESTRITOS
            docs.append({
                "id": uid(f"doc:{i}"), "titulo": f"Documento Perf {i:05d}",
                "fn": f"perf-{i:05d}.pdf", "fp": f"/uploads/perf/{i:05d}.pdf",
                "conf": "restrito" if restrito else ("interno" if i % 5 == 0 else "normal"),
                "case_id": uid(f"case:{i % 50}"),
                "client_id": uid(f"client:{i % 200}"),
                "up": A if i % 2 else B,
                "ocr": "lorem jurídico canario-ocr-xk42 presente no texto" if i % 97 == 0 else "lorem jurídico",
            })
        _lote(
            """INSERT INTO documents (id, titulo, filename, filepath,
                confidencialidade, case_id, client_id, uploaded_by, ocr_text,
                created_at, updated_at)
               VALUES (:id, :titulo, :fn, :fp, :conf::docconfidencialidade,
                :case_id, :client_id, :up, :ocr, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            docs, conn,
        )

        # ── Fees (300) ───────────────────────────────────────────────────
        fees: list[dict] = []
        for i in range(N_FEES):
            fees.append({
                "id": uid(f"fee:{i}"), "desc": f"Honorários Perf {i:04d}",
                "client_id": uid(f"client:{i % 200}"),
                "case_id": uid(f"case:{i % 50}"),
                "status": ("pago" if i % 3 == 0 else "pendente" if i % 3 == 1 else "atrasado"),
                "valor": 1500 + (i % 7) * 250,
            })
        _lote(
            """INSERT INTO fees (id, descricao, client_id, case_id, status,
                valor, created_at, updated_at)
               VALUES (:id, :desc, :client_id, :case_id, :status::feestatus,
                :valor, now(), now()) ON CONFLICT (id) DO NOTHING""",
            fees, conn,
        )

        # ── Legal docs (40; 15 em_revisao/corrigida) ─────────────────────
        pecas: list[dict] = []
        for i in range(N_LEGAL_DOCS):
            fila = i < N_LEGAL_FILA
            pecas.append({
                "id": uid(f"ld:{i}"), "titulo": f"Peça Perf {i:03d}",
                "tipo": "peticao_inicial",
                "status": ("em_revisao" if i % 2 else "corrigida") if fila else "aprovada",
                "case_id": uid(f"case:{i % 50}"),
            })
        _lote(
            """INSERT INTO legal_docs (id, titulo, tipo_peca, status, case_id,
                conteudo, created_at, updated_at)
               VALUES (:id, :titulo, :tipo::pecatipo, :status::pecastatus,
                :case_id, '# Peça sintética', now(), now())
               ON CONFLICT (id) DO NOTHING""",
            pecas, conn,
        )

        await _registro(conn)
    await engine.dispose()


async def _registro(conn) -> None:
    """Registro obrigatório (baseline §7.4): contagens por tabela."""
    from sqlalchemy import text

    print("[seed-perf] ── Registro do dataset ──")
    head = (
        await conn.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar()
    print(f"  alembic HEAD: {head}")
    for tabela in ("users", "clients", "cases", "deadlines", "tasks",
                   "agenda_eventos", "djen_comunicacoes", "documents",
                   "fees", "legal_docs"):
        try:
            n = (await conn.execute(
                text(f"SELECT COUNT(*) FROM {tabela}")
            )).scalar()
            print(f"  {tabela}: {n}")
        except Exception as exc:  # tabela pode não existir em variantes antigas
            print(f"  {tabela}: ERRO {exc}")
    print("  Gerador: scripts/perf/seed_homolog.py (uuid5 determinístico, namespace perf.ejc.homolog)")


async def _assercoes() -> None:
    """Aserções pós-carga (baseline §7.4). Falhar aqui bloqueia o uso do dataset."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_url())
    erros: list[str] = []
    async with engine.connect() as conn:
        A = uid("user:perf-advogado-a")
        B = uid("user:perf-advogado-b")

        async def um(sql: str, **kw):
            return (await conn.execute(text(sql), kw)).scalar()

        # 1. Visibilidade por ator (prazos: case na carteira OU avulso próprio)
        va = await um(
            """SELECT COUNT(*) FROM deadlines d WHERE d.deleted_at IS NULL AND (
                 (d.case_id IS NOT NULL AND d.case_id IN (
                    SELECT c.id FROM cases c WHERE c.deleted_at IS NULL AND
                      (c.advogado_responsavel_id = :a OR c.advogado_auxiliar_id = :a)))
                 OR (d.case_id IS NULL AND d.responsavel_id = :a))""",
            a=A,
        )
        vb = await um(
            """SELECT COUNT(*) FROM deadlines d WHERE d.deleted_at IS NULL AND (
                 (d.case_id IS NOT NULL AND d.case_id IN (
                    SELECT c.id FROM cases c WHERE c.deleted_at IS NULL AND
                      (c.advogado_responsavel_id = :a OR c.advogado_auxiliar_id = :a)))
                 OR (d.case_id IS NULL AND d.responsavel_id = :a))""",
            a=B,
        )
        if not (va > 0 and vb > 0 and va != vb):
            erros.append(f"visibilidade por ator suspeita: A={va} B={vb}")
        # 2. Órfãos fora do alcance dos advogados
        orf = await um(
            "SELECT COUNT(*) FROM cases WHERE deleted_at IS NULL "
            "AND advogado_responsavel_id IS NULL AND advogado_auxiliar_id IS NULL"
        )
        if orf != N_CASES_ORFAOS:
            erros.append(f"órfãos esperados {N_CASES_ORFAOS}, achados {orf}")
        # 3. Documentos restritos existem e estão no caso A
        restr = await um(
            "SELECT COUNT(*) FROM documents WHERE confidencialidade = 'restrito'"
        )
        if restr < N_DOCS_RESTRITOS:
            erros.append(f"restritos esperados ≥{N_DOCS_RESTRITOS}, achados {restr}")
        # 4. Empates presentes (tie test)
        ties = await um(
            "SELECT COUNT(*) FROM (SELECT data_prazo FROM deadlines "
            "GROUP BY data_prazo HAVING COUNT(*) >= 20) t"
        )
        if ties < 1:
            erros.append("faltam prazos empatados p/ prova de desempate")
        # 5. Fila HITL acima da amostra do browser
        fila = await um(
            "SELECT COUNT(*) FROM legal_docs WHERE status IN ('em_revisao','corrigida')"
        )
        if fila < N_LEGAL_FILA:
            erros.append(f"fila HITL esperada ≥{N_LEGAL_FILA}, achada {fila}")
    await engine.dispose()
    if erros:
        for e in erros:
            print(f"[seed-perf] FALHA DE ASERÇÃO: {e}")
        sys.exit(1)
    print("[seed-perf] asserções pós-carga: OK")


if __name__ == "__main__":
    _guard()
    asyncio.run(seed())
    asyncio.run(_assercoes())
