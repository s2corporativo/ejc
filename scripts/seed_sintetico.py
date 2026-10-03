#!/usr/bin/env python3
"""Seed do dataset sintético de performance (doc. performance/ejc-entrada-caso-hoje-baseline.md §2).

Reproduz o perfil documentado do baseline (PR #1945), cujo executor citado
(`scripts/seed_sintetico.py`) não foi versionado — este arquivo fecha essa
lacuna para que as medições sejam reproduzíveis:

  8 usuários (socio, admin, A1, A2, auxA1, auxA2, secretaria, cliente externo)
  · 80 clientes · 120 casos (2 carteiras de 60; empates de created_at;
  ~5 sem próxima ação) · 600 prazos (40 datas empatadas; vencidos/hoje/
  críticos/futuro; avulsos e vinculados) · 400 tarefas (empatadas; avulsas)
  · 500 eventos de agenda · 300 intimações DJEN · 8 suspensões ·
  300 documentos (60 por nível de confidencialidade; OCR longo; %/_ em
  título e OCR) · 40 peças (30 em revisão/corrigida) · 150 fees.

Guardas anti-produção (ambas obrigatórias):
  1. A URL de conexão (SEED_DATABASE_URL, fallback DATABASE_URL) precisa
     conter o marcador `sintetico` (ex.: banco `ejc_sintetico`).
  2. A variável SEED_PERF=1 precisa estar afirmada.

Pré-requisitos: migrations no HEAD (`alembic upgrade head` é do ambiente);
PostgreSQL dedicado NUNCA apontando para produção.

Idempotência: IDs uuid5 do namespace `perf.ejc.sintetico` + ON CONFLICT DO
NOTHING — reexecuções não duplicam.

Distribuições determinísticas documentadas (para reproduzir as contagens por
rota do baseline, os p95 dependem ainda do hardware — os VOLUMES e as
distribuições abaixo são o contrato):
  · prazos: 10% vencidos (0-30d atrás), 10% hoje, 20% críticos (1-3d),
    60% futuros (4-90d); 40 com a MESMA data; 20% avulsos (sem caso,
    responsável direto = dono da carteira);
  · tarefas: 30% concluídas, resto a_fazer; data_limite: 20% vencidas,
    20% hoje, 60% futuras/NULL; 40 empatadas em data_limite; 60 avulsas;
  · documentos: 60 por nível (normal, interno, restrito, confidencial,
    segredo_justica); OCR com ~2.000 chars e termo canário com % _ ;
  · peças: 30 em revisão/corrigida (HITL), 10 aprovadas.

Uso:
  SEED_PERF=1 \\
  SEED_DATABASE_URL=postgresql+asyncpg://user:pass@host/ejc_sintetico \\
  python3 scripts/seed_sintetico.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta

# ── Guardas anti-produção ────────────────────────────────────────────────────
MARKER = "sintetico"
ENV_FLAG = "SEED_PERF"


def _url() -> str:
    url = os.getenv("SEED_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if MARKER not in url:
        sys.exit(
            f"[seed-sintetico] RECUSADO: a URL precisa conter '{MARKER}' "
            "(banco dedicado ejc_sintetico — nunca produção)."
        )
    return url


def _guard() -> None:
    if os.getenv(ENV_FLAG) != "1":
        sys.exit(
            f"[seed-sintetico] RECUSADO: defina {ENV_FLAG}=1 para confirmar "
            "que o alvo é o banco sintético dedicado."
        )
    _url()


NS = uuid.uuid5(uuid.NAMESPACE_URL, "perf.ejc.sintetico")


def uid(chave: str) -> str:
    return str(uuid.uuid5(NS, chave))


HOJE = date.today()

N_CLIENTS = 80
N_CASES_POR_CARTEIRA = 60      # 120 casos: A1 60 + A2 60
N_SEM_PROXIMA_ACAO = 5         # ~5 casos sem próxima ação
N_DEADLINES = 600
N_DEADLINES_EMPATADAS = 40
N_TASKS = 400
N_TASKS_EMPATADAS = 40
N_TASKS_AVULSAS = 60
N_AGENDA = 500
N_DJEN = 300
N_SUSPENSOES = 8
N_DOCS_POR_NIVEL = 60          # 5 níveis × 60 = 300
N_LEGAL_DOCS = 40
N_LEGAL_FILA = 30              # em_revisao/corrigida (HITL)
N_FEES = 150

ATORES = [
    ("perf-socio", "socio"),
    ("perf-admin", "admin"),
    ("perf-a1", "advogado"),
    ("perf-a2", "advogado"),
    ("perf-auxa1", "advogado_auxiliar"),
    ("perf-auxa2", "advogado_auxiliar"),
    ("perf-secretaria", "secretaria"),
    ("perf-cext", "cliente_externo"),
]

NIVEIS_CONF = ("normal", "interno", "restrito", "confidencial", "segredo_justica")
_OCR_LONGO = (
    "Lorem jurídico sintético para exercitar ILIKE sobre ocr_text. "
    "Termo canário: canario%ocr_xk42 — percentuais e underscores precisam "
    "de escape no GED. " * 25
)


def _lote(sql: str, linhas: list[dict], conn) -> None:
    if not linhas:
        return
    from sqlalchemy import text

    conn.execute(text(sql), linhas)


async def seed() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_url(), pool_pre_ping=True)
    async with engine.begin() as conn:
        ancora = (
            await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE email = :e"),
                {"e": "perf-a1@sintetico.local"},
            )
        ).scalar()
        if ancora:
            print("[seed-sintetico] dataset já presente — nada a fazer.")
            await _registro(conn)
            await engine.dispose()
            return

        # ── Users (8) ────────────────────────────────────────────────────
        _lote(
            """INSERT INTO users (id, email, hashed_password, full_name, role,
                is_active, created_at, updated_at)
               VALUES (:id, :email, 'x', :nome, :role::userrole, true, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            [{"id": uid(f"user:{e}"), "email": f"{e}@sintetico.local",
              "role": r, "nome": r.replace("_", " ").title()}
             for e, r in ATORES],
            conn,
        )
        A1 = uid("user:perf-a1")
        A2 = uid("user:perf-a2")
        AUX1 = uid("user:perf-auxa1")

        # ── Clients (80; 40 por carteira) ────────────────────────────────
        clientes = []
        for i in range(N_CLIENTS):
            clientes.append({
                "id": uid(f"client:{i}"), "tipo": "PF",
                "nome": f"Cliente Sintetico {i:03d}",
                "email": f"cliente{i:03d}@sintetico.local",
                "status": "ativo", "resp": A1 if i < N_CLIENTS // 2 else A2,
            })
        clientes.append({
            "id": uid("client:cext"), "tipo": "PF", "nome": "Cliente Portal Sintetico",
            "email": "cext@sintetico.local", "status": "ativo", "resp": A1,
        })
        _lote(
            """INSERT INTO clients (id, tipo, nome, email, status,
                responsavel_id, created_at, updated_at)
               VALUES (:id, :tipo::clienttipo, :nome, :email,
                :status::clientstatus, :resp, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            clientes, conn,
        )
        CLIENT_CEXT = uid("client:cext")

        # Hash cego do CPF sintático do cliente do portal (busca exata).
        if os.getenv("PII_HASH_KEY"):
            from app.services.pii_crypto import hash_documento, normalizar_documento

            dig = normalizar_documento("11144477735")  # CPF sintático válido
            _lote(
                "UPDATE clients SET cpf_hash = :h WHERE id = :i",
                [{"h": hash_documento(dig), "i": CLIENT_CEXT}], conn,
            )
        else:
            print("[seed-sintetico] AVISO: PII_HASH_KEY ausente — cliente portal sem cpf_hash.")

        # ── Cases (120: 60 por carteira; empates de created_at; 5 sem
        #    próxima ação; 1 de risco crítico e 1 de risco alto por carteira)
        casos = []
        for n in range(N_CASES_POR_CARTEIRA * 2):
            dono = A1 if n < N_CASES_POR_CARTEIRA else A2
            local = n % N_CASES_POR_CARTEIRA
            status = "aberto" if local % 4 else "em_instrucao"
            casos.append({
                "id": uid(f"case:{n}"), "titulo": f"Processo Sintetico {n:03d}",
                "status": status, "client_id": uid(f"client:{n % N_CLIENTS}"),
                "resp": dono,
                "aux": AUX1 if (dono == A1 and local == 1) else None,
                "proxima": None if local < N_SEM_PROXIMA_ACAO // 2 + (
                    1 if dono == A2 and local == 2 else 0)
                else f"Atuar no caso {n:03d}",
                "prazo_acao": HOJE + timedelta(days=(n % 40) - 5) if n % 2 else None,
                "prioridade": ("urgente" if n % 10 == 0
                               else "alta" if n % 5 == 0 else "media"),
                "risco": ("critico" if local == 3
                          else "alto" if local == 7 else "baixo"),
            })
        _lote(
            """INSERT INTO cases (id, titulo, area, status, client_id,
                advogado_responsavel_id, advogado_auxiliar_id, proxima_acao,
                proxima_acao_prazo, prioridade, risco, created_at, updated_at)
               VALUES (:id, :titulo, 'civil'::casearea, :status::casestatus,
                :client_id, :resp, :aux, :proxima, :prazo_acao,
                :prioridade::caseprioridade, :risco, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            casos, conn,
        )
        CASE_A1_0 = uid("case:0")

        # ── Deadlines (600; 40 empatadas; avulsas e vinculadas) ──────────
        prazos = []
        for i in range(N_DEADLINES - N_DEADLINES_EMPATADAS):
            avulso = i % 5 == 0
            if i % 10 < 1:      # 10% vencidos
                dp, st = HOJE - timedelta(days=1 + (i % 30)), "pendente"
            elif i % 10 < 2:    # 10% hoje
                dp, st = HOJE, "pendente"
            elif i % 10 < 4:    # 20% críticos (1-3d)
                dp, st = HOJE + timedelta(days=1 + (i % 3)), "pendente"
            else:               # 60% futuros
                dp, st = HOJE + timedelta(days=4 + (i % 87)), "pendente"
            prazos.append({
                "id": uid(f"dl:{i}"), "t": f"Prazo Sintetico {i:04d}",
                "dp": dp, "st": st,
                "case_id": None if avulso else uid(f"case:{i % 120}"),
                "resp": A1 if i % 2 == 0 else A2,
            })
        dp_tie = HOJE + timedelta(days=3)
        for i in range(N_DEADLINES_EMPATADAS):  # 40 com a MESMA data
            prazos.append({
                "id": uid(f"dl:tie:{i}"), "t": f"Prazo Empatado {i:02d}",
                "dp": dp_tie, "st": "pendente",
                "case_id": CASE_A1_0, "resp": A1,
            })
        _lote(
            """INSERT INTO deadlines (id, titulo, tipo, prioridade, status,
                data_prazo, case_id, responsavel_id, created_at, updated_at)
               VALUES (:id, :t, 'processual'::deadlinetipo, 'media',
                :st::deadlinestatus, :dp, :case_id, :resp, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            prazos, conn,
        )

        # ── Tasks (400; 40 empatadas; 60 avulsas) ────────────────────────
        tarefas = []
        for i in range(N_TASKS - N_TASKS_EMPATADAS):
            avulsa = i < N_TASKS_AVULSAS
            if i % 5 == 0:
                st, dl = "concluida", HOJE - timedelta(days=i % 20)
            elif i % 5 == 1:
                st, dl = "a_fazer", HOJE - timedelta(days=i % 10)
            elif i % 5 == 2:
                st, dl = "a_fazer", HOJE
            elif i % 5 == 3:
                st, dl = "a_fazer", None
            else:
                st, dl = "a_fazer", HOJE + timedelta(days=1 + (i % 45))
            tarefas.append({
                "id": uid(f"tk:{i}"), "t": f"Tarefa Sintetica {i:04d}",
                "st": st, "dl": dl,
                "case_id": None if avulsa else uid(f"case:{i % 120}"),
                "resp": A1 if i % 2 == 0 else A2, "criador": A1,
            })
        for i in range(N_TASKS_EMPATADAS):  # 40 com a MESMA data_limite
            tarefas.append({
                "id": uid(f"tk:tie:{i}"), "t": f"Tarefa Empatada {i:02d}",
                "st": "a_fazer", "dl": HOJE,
                "case_id": uid("case:2"), "resp": A1, "criador": A1,
            })
        _lote(
            """INSERT INTO tasks (id, titulo, status, prioridade, data_limite,
                case_id, responsavel_id, criado_por, created_at, updated_at)
               VALUES (:id, :t, :st::taskstatus, 'media', :dl, :case_id,
                :resp, :criador, now(), now()) ON CONFLICT (id) DO NOTHING""",
            tarefas, conn,
        )

        # ── Agenda (500) ─────────────────────────────────────────────────
        agenda = []
        for i in range(N_AGENDA):
            agenda.append({
                "id": uid(f"ag:{i}"), "t": f"Evento Sintetico {i:04d}",
                "tipo": "audiencia" if i % 4 == 0 else "compromisso",
                "de": HOJE + timedelta(days=(i % 60) - 10),
                "case_id": uid(f"case:{i % 120}"),
                "resp": A1 if i % 2 == 0 else A2,
                "concluido": i % 3 == 0,
            })
        _lote(
            """INSERT INTO agenda_eventos (id, titulo, tipo, data_evento,
                case_id, responsavel_id, concluido, created_by, created_at,
                updated_at)
               VALUES (:id, :t, :tipo, :de, :case_id, :resp, :concluido,
                :resp, now(), now()) ON CONFLICT (id) DO NOTHING""",
            agenda, conn,
        )

        # ── DJEN (300) ───────────────────────────────────────────────────
        djen = []
        for i in range(N_DJEN):
            djen.append({
                "id": uid(f"dj:{i}"), "ext": f"SINT-{i:06d}",
                "adv": A1 if i % 2 == 0 else A2,
                "dd": HOJE - timedelta(days=i % 90),
                "proc": i % 3 == 0,
                "case_id": uid(f"case:{i % 120}") if i % 3 == 0 else None,
            })
        _lote(
            """INSERT INTO djen_comunicacoes (id, comunicacao_id_externo,
                advogado_id, data_disponibilizacao, processada, case_id,
                tipo_comunicacao, texto_resumo, created_at, updated_at)
               VALUES (:id, :ext, :adv, :dd, :proc, :case_id, 'intimacao',
                'Resumo sintético da comunicação', now(), now())
               ON CONFLICT (id) DO NOTHING""",
            djen, conn,
        )

        # ── Suspensões (8) ───────────────────────────────────────────────
        _lote(
            """INSERT INTO suspensoes_tribunal (id, tribunal, data_inicio,
                data_fim, motivo, created_by, created_at)
               VALUES (:id, :tribunal, :di, :df, :motivo, :by, now())
               ON CONFLICT (id) DO NOTHING""",
            [{
                "id": uid(f"susp:{i}"),
                "tribunal": ("TJMG" if i % 2 == 0 else "TRT3"),
                "di": HOJE + timedelta(days=30 + i * 5),
                "df": HOJE + timedelta(days=50 + i * 5),
                "motivo": f"Recesso/feriados sintético {i}",
                "by": A1,
            } for i in range(N_SUSPENSOES)],
            conn,
        )

        # ── Documents (300: 60 por nível; OCR longo; % _ em título/OCR) ──
        docs = []
        for n, nivel in enumerate(NIVEIS_CONF):
            for i in range(N_DOCS_POR_NIVEL):
                k = n * N_DOCS_POR_NIVEL + i
                docs.append({
                    "id": uid(f"doc:{k}"),
                    "t": f"Documento Sintetico {k:03d} 100%_concluido"
                    if k % 17 == 0 else f"Documento Sintetico {k:03d}",
                    "fn": f"doc-{k:03d}.pdf", "fp": f"/uploads/sint/doc-{k:03d}.pdf",
                    "conf": nivel,
                    "case_id": uid(f"case:{k % 120}"),
                    "client_id": uid(f"client:{k % N_CLIENTS}"),
                    "up": A1 if k % 2 == 0 else A2,
                    "ocr": _OCR_LONGO if k % 7 == 0 else "lorem jurídico sintético",
                })
        _lote(
            """INSERT INTO documents (id, titulo, filename, filepath,
                confidencialidade, case_id, client_id, uploaded_by, ocr_text,
                created_at, updated_at)
               VALUES (:id, :t, :fn, :fp, :conf::docconfidencialidade,
                :case_id, :client_id, :up, :ocr, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            docs, conn,
        )

        # ── Legal docs (40; 30 em revisão/corrigida) ─────────────────────
        pecas = []
        for i in range(N_LEGAL_DOCS):
            fila = i < N_LEGAL_FILA
            pecas.append({
                "id": uid(f"ld:{i}"), "t": f"Peça Sintetica {i:03d}",
                "st": ("em_revisao" if i % 2 == 0 else "corrigida") if fila
                else "aprovada",
                "case_id": uid(f"case:{i % 120}"),
            })
        _lote(
            """INSERT INTO legal_docs (id, titulo, tipo_peca, status, case_id,
                conteudo, ai_generated, human_reviewed, created_at, updated_at)
               VALUES (:id, :t, 'peticao_inicial'::pecatipo, :st::pecastatus,
                :case_id, '# Peça sintética', true, false, now(), now())
               ON CONFLICT (id) DO NOTHING""",
            pecas, conn,
        )

        # ── Fees (150) ───────────────────────────────────────────────────
        fees = []
        for i in range(N_FEES):
            fees.append({
                "id": uid(f"fee:{i}"), "desc": f"Honorários Sintetico {i:04d}",
                "client_id": uid(f"client:{i % N_CLIENTS}"),
                "case_id": uid(f"case:{i % 120}"),
                "status": ("pago" if i % 3 == 0
                           else "pendente" if i % 3 == 1 else "atrasado"),
                "valor": 1500 + (i % 7) * 250,
            })
        _lote(
            """INSERT INTO fees (id, descricao, client_id, case_id, status,
                valor, created_at, updated_at)
               VALUES (:id, :desc, :client_id, :case_id, :status::feestatus,
                :valor, now(), now()) ON CONFLICT (id) DO NOTHING""",
            fees, conn,
        )

        await _registro(conn)
    await engine.dispose()


async def _registro(conn) -> None:
    """Registro obrigatório (baseline §2): contagens por tabela."""
    from sqlalchemy import text

    print("[seed-sintetico] ── Registro do dataset ──")
    head = (
        await conn.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar()
    print(f"  alembic HEAD: {head}")
    esperado = {
        "users": 8, "clients": N_CLIENTS + 1, "cases": N_CASES_POR_CARTEIRA * 2,
        "deadlines": N_DEADLINES, "tasks": N_TASKS, "agenda_eventos": N_AGENDA,
        "djen_comunicacoes": N_DJEN, "suspensoes_tribunal": N_SUSPENSOES,
        "documents": N_DOCS_POR_NIVEL * len(NIVEIS_CONF),
        "legal_docs": N_LEGAL_DOCS, "fees": N_FEES,
    }
    for tabela, alvo in esperado.items():
        try:
            n = (await conn.execute(
                text(f"SELECT COUNT(*) FROM {tabela}")
            )).scalar()
            marca = "OK" if n >= alvo else "ABAIXO DO ESPERADO"
            print(f"  {tabela}: {n} (esperado ≥ {alvo}) {marca}")
        except Exception as exc:
            print(f"  {tabela}: ERRO {exc}")
    print("  Executor: scripts/seed_sintetico.py (uuid5 determinístico; "
          "namespace perf.ejc.sintetico)")


async def _assercoes() -> None:
    """Aserções que bloqueiam o uso do dataset se o perfil divergir."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_url())
    erros: list[str] = []
    async with engine.connect() as conn:
        A1 = uid("user:perf-a1")
        A2 = uid("user:perf-a2")

        async def um(sql: str, **kw):
            return (await conn.execute(text(sql), kw)).scalar()

        # 1. Visibilidade por ator difere (carteiras disjuntas)
        async def prazos_de(ator):
            return await um(
                """SELECT COUNT(*) FROM deadlines d WHERE d.deleted_at IS NULL AND (
                     (d.case_id IS NOT NULL AND d.case_id IN (
                        SELECT c.id FROM cases c WHERE c.deleted_at IS NULL AND
                          (c.advogado_responsavel_id = :a
                           OR c.advogado_auxiliar_id = :a)))
                     OR (d.case_id IS NULL AND d.responsavel_id = :a))""",
                a=ator,
            )
        va, vb = await prazos_de(A1), await prazos_de(A2)
        if not (va > 0 and vb > 0 and va != vb):
            erros.append(f"visibilidade por ator suspeita: A1={va} A2={vb}")
        # 2. Prazos empatados presentes (prova de desempate)
        ties = await um(
            "SELECT MAX(cnt) FROM (SELECT data_prazo, COUNT(*) cnt FROM deadlines"
            " GROUP BY data_prazo) t"
        )
        if (ties or 0) < N_DEADLINES_EMPATADAS:
            erros.append(f"empate máximo {ties} < {N_DEADLINES_EMPATADAS}")
        # 3. 60 documentos por nível de confidencialidade
        for nivel in NIVEIS_CONF:
            n = await um(
                "SELECT COUNT(*) FROM documents WHERE confidencialidade = :c",
                c=nivel,
            )
            if n < N_DOCS_POR_NIVEL:
                erros.append(f"{nivel}: {n} < {N_DOCS_POR_NIVEL}")
        # 4. Fila HITL = 30
        fila = await um(
            "SELECT COUNT(*) FROM legal_docs WHERE status IN"
            " ('em_revisao','corrigida') AND ai_generated IS TRUE"
            " AND human_reviewed IS FALSE"
        )
        if fila != N_LEGAL_FILA:
            erros.append(f"fila HITL {fila} != {N_LEGAL_FILA}")
        # 5. Casos sem próxima ação presentes (G1 edge do baseline)
        sem_acao = await um(
            "SELECT COUNT(*) FROM cases WHERE deleted_at IS NULL"
            " AND proxima_acao IS NULL"
        )
        if sem_acao < 1:
            erros.append("faltam casos sem proxima_acao")
    await engine.dispose()
    if erros:
        for e in erros:
            print(f"[seed-sintetico] FALHA DE ASERÇÃO: {e}")
        sys.exit(1)
    print("[seed-sintetico] asserções pós-carga: OK")


if __name__ == "__main__":
    _guard()
    asyncio.run(seed())
    asyncio.run(_assercoes())
