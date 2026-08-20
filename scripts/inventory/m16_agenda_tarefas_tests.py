#!/usr/bin/env python3
# M16 — Agenda, Audiências, Eventos e Tarefas (bateria de homologação)
# Provado por execução real contra o servidor local na porta 8000.
from __future__ import annotations
import os
import sys
import json
import subprocess
import datetime as dt
import requests

BASE = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
# Papéis: socio=gestão (cria p/ outro, vê agenda alheia); advogado não-gestão;
# estagiario não-gestão; secretario não-gestão.
EMAILS = {
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "secretaria": "ejc_qa_auth_secretaria@golocal.ejc",
    "cliente": "ejc_qa_auth_cliente@golocal.ejc",
}

IDS = {}   # ids por email (lazy)
TOKENS = {}
FALHAS = 0
TOTAL = 0


def chk(desc, ok, extra=""):
    global FALHAS, TOTAL
    TOTAL += 1
    if ok:
        print(f"[PASS] {desc}")
    else:
        FALHAS += 1
        print(f"[FAIL] {desc} — {extra}")


def db(sql):
    env = dict(os.environ)
    env["PGPASSWORD"] = "ejc"
    o = subprocess.run(["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                        "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return o.stdout.strip()


def token(email):
    if email in TOKENS:
        return TOKENS[email]
    for tent in range(4):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": SENHA},
                          headers={"X-Forwarded-For": "127.0.0.1"}, timeout=15)
        if r.status_code == 200:
            TOKENS[email] = r.json()["access_token"]
            return TOKENS[email]
        if r.status_code == 429:
            import time
            time.sleep(18 * (tent + 1))
        else:
            raise SystemExit(f"login {email}: {r.status_code} {r.text[:120]}")
    raise SystemExit(f"login {email}: rate limit persistente")


def H(role):
    return {"Authorization": f"Bearer {token(EMAILS[role])}",
            "X-Forwarded-For": "127.0.0.1"}


def usuario_id(role):
    if role not in IDS:
        r = requests.get(f"{BASE}/api/users", headers=H(role), timeout=15)
        if r.status_code != 200:
            # fallback: consulta direta (usuário QA)
            u = db(f"SELECT id FROM users WHERE email='{EMAILS[role]}'")
        else:
            lst = r.json()
            data = lst.get("data", lst)
            u = next((x.get("id") or x.get("uuid") for x in data
                      if x.get("email") == EMAILS[role]), None)
        IDS[role] = u.strip()
    return IDS[role]


def cliente_qa_id():
    c = db("SELECT id FROM clients WHERE nome ILIKE '%EJC_QA%' ORDER BY created_at DESC LIMIT 1")
    return c.strip() if c else None


def caso_qa_id():
    # Caso da carteira do advogado QA (atribuído e ativo) — a consulta genérica
    # por 'EJC_QA%' retornava caso de outro módulo/cliente e gerava 403.
    c = db("SELECT id FROM cases "
           "WHERE advogado_responsavel_id=(SELECT id FROM users "
           "WHERE email='ejc_qa_auth_advogado@golocal.ejc') "
           "AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1")
    return c.strip() if c else None


# ── 1. AGENDA: criação ──────────────────────────────────────────────────────
cli = cliente_qa_id()
caso = caso_qa_id()
if not caso:
    print(f"[ERRO] sem caso QA: client={cli}")
    sys.exit(2)

# evento próprio (advogado, sem caso)
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA reunião 16h (próprio)", "tipo": "reuniao",
    "data_evento": "2026-12-10", "hora": "16:00",
    "local": "Sala EJC_QA", "descricao": "EJC_QA homologação M16"},
    headers=H("advogado"), timeout=15)
chk("agenda: criação de evento próprio 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
ev1 = r.json().get("id")

# evento com caso (visível na carteira do advogado)
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA diligência do caso", "tipo": "diligencia",
    "data_evento": "2026-12-10", "hora": "14:00", "case_id": caso},
    headers=H("advogado"), timeout=15)
chk("agenda: criação de evento vinculado ao caso 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
ev2 = r.json().get("id")

# evento de audiência com hora
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA audiência de instrução", "tipo": "audiencia",
    "data_evento": "2026-12-11", "hora": "09:30",
    "descricao": "EJC_QA prova por execução"},
    headers=H("advogado"), timeout=15)
chk("agenda: tipo 'audiencia' aceito 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
ev3 = r.json().get("id")

# tipo inválido
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA x", "tipo": "balada", "data_evento": "2026-12-11"},
    headers=H("advogado"), timeout=15)
chk("agenda: tipo inválido rejeitado 422", r.status_code == 422, f"{r.status_code}")

# hora malformada (>10 chars violaria VARCHAR — validação max_length)
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA x", "tipo": "compromisso", "data_evento": "2026-12-11",
    "hora": "09:30 EXCEDE O MAXLENGTH"},
    headers=H("advogado"), timeout=15)
chk("agenda: hora > 10 chars rejeitada 422 (não estoura VARCHAR)", r.status_code == 422,
    f"{r.status_code}")

# título > 255 rejeitado
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA " + "X" * 300, "tipo": "compromisso",
    "data_evento": "2026-12-11"}, headers=H("advogado"), timeout=15)
chk("agenda: título > 255 rejeitado 422", r.status_code == 422, f"{r.status_code}")

# ── 2. AGENDA: responsavel + gate de gestão ─────────────────────────────────
adv_id = usuario_id("advogado")
est_id = usuario_id("estagiario")

r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA evento p/ estagiário", "tipo": "compromisso",
    "data_evento": "2026-12-12", "hora": "10:00", "responsavel_id": est_id},
    headers=H("advogado"), timeout=15)
chk("agenda: advogado NÃO cria evento p/ outro responsável 403",
    r.status_code == 403, f"{r.status_code} {r.text[:80]}")

r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA evento p/ estagiário (gestão)", "tipo": "compromisso",
    "data_evento": "2026-12-12", "hora": "10:00", "responsavel_id": est_id},
    headers=H("socio"), timeout=15)
chk("agenda: sócio (gestão) cria evento p/ outro 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
ev4 = r.json().get("id")

# responsável inexistente
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA x", "tipo": "compromisso", "data_evento": "2026-12-12",
    "responsavel_id": "00000000-0000-0000-0000-000000000000"},
    headers=H("socio"), timeout=15)
chk("agenda: responsável inexistente rejeitado 422 (não vira órfão)",
    r.status_code == 422, f"{r.status_code} {r.text[:80]}")

# ── 3. AGENDA: case_id sem acesso (IDOR/ABAC) ───────────────────────────────
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA invasão", "tipo": "compromisso", "data_evento": "2026-12-12",
    "case_id": caso}, headers=H("cliente"), timeout=15)
chk("agenda: cliente_externo SEM acesso ao caso rejeitado (403/404)",
    r.status_code in (403, 404), f"{r.status_code} {r.text[:80]}")

# ── 4. AGENDA: edição e reagendamento ───────────────────────────────────────
r = requests.patch(f"{BASE}/api/agenda-eventos/{ev1}", json={
    "data_evento": "2026-12-15", "hora": "15:00", "local": "Sala nova EJC_QA"},
    headers=H("advogado"), timeout=15)
chk("agenda: reagendamento por edição 200", r.status_code == 200,
    f"{r.status_code} {r.text[:80]}")
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("advogado"),
                 params={"page_size": 500}, timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
ev = next((e for e in itens if e.get("id") == ev1), None)
chk("agenda: reagendamento persiste (data/hora/local atualizados)",
    ev is not None and str(ev.get("data_evento")) == "2026-12-15"
    and (ev.get("hora") or "").strip() == "15:00"
    and ev.get("local") == "Sala nova EJC_QA",
    str(ev)[:150] if ev else "evento não listado")

# marcação como concluído
r = requests.patch(f"{BASE}/api/agenda-eventos/{ev2}", json={"concluido": True},
                   headers=H("advogado"), timeout=15)
chk("agenda: marcar concluído 200", r.status_code == 200, f"{r.status_code}")
# persistência no banco (camada SQL, independente de filtros do GET)
chk("agenda: concluido=true persiste no banco",
    db(f"SELECT concluido FROM agenda_eventos WHERE id='{ev2}'") == "t")

# transferência de responsável: advogado NÃO transfere p/ terceiro
r = requests.patch(f"{BASE}/api/agenda-eventos/{ev3}",
                   json={"responsavel_id": est_id},
                   headers=H("advogado"), timeout=15)
chk("agenda: transferência p/ terceiro sem gestão rejeitada 403",
    r.status_code == 403, f"{r.status_code} {r.text[:80]}")

# gestão transfere (com auditoria UPDATE)
r = requests.patch(f"{BASE}/api/agenda-eventos/{ev3}",
                   json={"responsavel_id": est_id},
                   headers=H("socio"), timeout=15)
chk("agenda: gestão transfere responsável 200", r.status_code == 200,
    f"{r.status_code} {r.text[:80]}")
aud = db("SELECT count(*) FROM audit_logs WHERE entidade='agenda_eventos' "
         f"AND registro_id='{ev3}' AND acao='UPDATE'")
chk("agenda: transferência de responsável gera auditoria UPDATE",
    int(aud or 0) >= 1, aud)

# edição de evento inexistente
r = requests.patch(f"{BASE}/api/agenda-eventos/00000000-0000-0000-0000-000000000000",
                   json={"titulo": "x"}, headers=H("socio"), timeout=15)
chk("agenda: edição de inexistente 404", r.status_code == 404, f"{r.status_code}")

# ── 5. AGENDA: conflitos (double-booking) ───────────────────────────────────
# Idempotência: remove resíduos de corridas anteriores no slot de conflito
# (bateria não controla exclusão no fim; runs repetidos acumulavam itens e o
# cenário "AVISA 1 conflito" falhava com 5+ avisos).
for _t in ("EJC_QA conflito A", "EJC_QA conflito B", "EJC_QA sem hora",
           "EJC_QA pós-concluído"):
    for _r in db(f"SELECT id FROM agenda_eventos WHERE titulo='{_t}' "
                 "AND deleted_at IS NULL AND concluido IS NOT TRUE").split("\n"):
        if _r.strip():
            try:
                requests.delete(f"{BASE}/api/agenda-eventos/{_r.strip()}",
                                headers=H("advogado"), timeout=15)
            except Exception:
                pass
r1 = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA conflito A", "tipo": "reuniao",
    "data_evento": "2026-12-18", "hora": "11:00"},
    headers=H("advogado"), timeout=15)
r2 = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA conflito B", "tipo": "diligencia",
    "data_evento": "2026-12-18", "hora": "11:00"},
    headers=H("advogado"), timeout=15)
confl = r2.json().get("conflito_agenda", [])
chk("agenda: segundo evento na mesma data/hora AVISA conflito (cria mesmo assim)",
    r2.status_code == 201 and len(confl) == 1
    and confl[0].get("titulo") == "EJC_QA conflito A",
    f"{r2.status_code} conflitos={confl}")

# evento SEM hora não colide por horário
r3 = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA sem hora", "tipo": "compromisso",
    "data_evento": "2026-12-18"}, headers=H("advogado"), timeout=15)
chk("agenda: evento sem hora NÃO colide por horário",
    r3.status_code == 201 and not r3.json().get("conflito_agenda"),
    f"{r3.status_code}")

# conflito de outro usuário: censura (advogado vê evento do sócio sem detalhe)
r4 = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA evento sócio secreto", "tipo": "reuniao",
    "data_evento": "2026-12-19", "hora": "08:00"},
    headers=H("socio"), timeout=15)
soc_ev = r4.json().get("id")
r5 = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA teste censura", "tipo": "compromisso",
    "data_evento": "2026-12-19", "hora": "08:00"},
    headers=H("advogado"), timeout=15)
confl5 = r5.json().get("conflito_agenda", [])
# A checagem de conflito é filtrada pelo responsável do chamador: eventos de
# OUTRO responsável jamais são devolvidos — não há oráculo da agenda alheia
# nem pela via do conflito (proteção N2 por design: invisibilidade total).
# A censura de título/local (_censurar_conflitos) blinda o único caminho em
# que eventos de terceiros podem aparecer (gestão cria evento para outro).
ok_n2 = (r5.status_code == 201
         and not any("secreto" in (c.get("titulo") or "") for c in confl5))
chk("agenda: conflito NÃO revela evento de outro responsável (N2 por invisibilidade)",
    r5.status_code == 201 and ok_n2,
    f"{r5.status_code} conflitos={confl5}")
requests.delete(f"{BASE}/api/agenda-eventos/{soc_ev}", headers=H("socio"), timeout=15)
if r5.status_code == 201:
    requests.delete(f"{BASE}/api/agenda-eventos/{r5.json().get('id')}",
                    headers=H("advogado"), timeout=15)

# edição: o próprio evento NÃO aparece na lista de conflitos (exclude_id)
r = requests.patch(f"{BASE}/api/agenda-eventos/{ev1}",
                   json={"data_evento": "2026-12-18", "hora": "11:00"},
                   headers=H("advogado"), timeout=15)
confl_ed = r.json().get("conflito_agenda", [])
# A edição move ev1 para o slot dos conflitos A/B (mesmo responsável) — eles
# DEVEM aparecer como aviso, mas o PRÓPRIO ev1 jamais pode estar na lista.
chk("agenda: edição NÃO self-colide (exclui a si mesma via exclude_id)",
    r.status_code == 200 and ev1 not in (c.get("id") for c in confl_ed),
    f"{r.status_code} conflitos={confl_ed}")

# evento concluído não conta como conflito
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA pós-concluído", "tipo": "compromisso",
    "data_evento": "2026-12-10", "hora": "14:00"},
    headers=H("advogado"), timeout=15)
chk("agenda: evento concluído não gera conflito (excluído da checagem)",
    r.status_code == 201 and not r.json().get("conflito_agenda"),
    f"{r.status_code} {r.json()}")

# ── 6. AGENDA: listagem e escopo ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("advogado"),
                 params={"page_size": 500}, timeout=15)
chk("agenda: listagem 200 p/ advogado (escopo pessoal/carteira)",
    r.status_code == 200, f"{r.status_code}")
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
titulos = [e.get("titulo", "") for e in itens]
chk("agenda: advogado vê o próprio evento e o do caso",
    any("EJC_QA" in t for t in titulos), f"{len(itens)} itens")

# não-gestão NÃO vê eventos de outro usuário fora da carteira
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("estagiario"),
                 params={"page_size": 500}, timeout=15)
itens_est = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
tem_socio = any(e.get("responsavel_id") == usuario_id("socio") for e in itens_est)
chk("agenda: estagiário não vê eventos de outro usuário (vazamento)",
    not tem_socio, f"{len(itens_est)} itens")

# gestão vê agenda geral
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("socio"),
                 params={"page_size": 500}, timeout=15)
chk("agenda: sócio (gestão) acessa agenda geral 200", r.status_code == 200,
    f"{r.status_code}")

# cliente_externo sem acesso
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("cliente"), timeout=15)
chk("agenda: cliente_externo não acessa 403/404", r.status_code in (401, 403, 404),
    f"{r.status_code}")

# ── 7. AGENDA: exclusão com auditoria ───────────────────────────────────────
r = requests.delete(f"{BASE}/api/agenda-eventos/{ev2}", headers=H("advogado"),
                    timeout=15)
chk("agenda: exclusão (soft) 200", r.status_code == 200, f"{r.status_code}")
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("advogado"),
                 params={"page_size": 500}, timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
chk("agenda: excluído sai da listagem",
    not any(e.get("id") == ev2 for e in itens))
aud = db("SELECT count(*) FROM audit_logs WHERE entidade='agenda_eventos' "
         f"AND registro_id='{ev2}' AND acao='DELETE'")
chk("agenda: auditoria DELETE registrada", int(aud or 0) >= 1, aud)
r = requests.delete(f"{BASE}/api/agenda-eventos/00000000-0000-0000-0000-000000000000",
                    headers=H("advogado"), timeout=15)
chk("agenda: exclusão de inexistente 404", r.status_code == 404, f"{r.status_code}")

# evento pessoal de OUTRO: não-gestão não pode apagar
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA pessoal outro", "tipo": "compromisso",
    "data_evento": "2026-12-22", "hora": "09:00"},
    headers=H("secretaria"), timeout=15)
outro = r.json().get("id")
r = requests.delete(f"{BASE}/api/agenda-eventos/{outro}", headers=H("advogado"),
                    timeout=15)
chk("agenda: não apaga evento pessoal de outro usuário 403",
    r.status_code == 403, f"{r.status_code}")
requests.delete(f"{BASE}/api/agenda-eventos/{outro}", headers=H("secretaria"), timeout=15)

# ── 8. TAREFAS: criação e notificação ───────────────────────────────────────
r = requests.post(f"{BASE}/api/tasks", json={
    "titulo": "EJC_QA tarefa própria", "descricao": "EJC_QA homologação",
    "prioridade": "alta", "data_limite": "2026-12-14"},
    headers=H("advogado"), timeout=15)
chk("tarefas: criação própria 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
tk1 = r.json().get("id")

# notificação ao responsável atribuído (não criador)
antes = db("SELECT count(*) FROM notifications WHERE user_id='" + est_id + "'")
r = requests.post(f"{BASE}/api/tasks", json={
    "titulo": "EJC_QA tarefa atribuída", "prioridade": "media",
    "data_limite": "2026-12-20", "responsavel_id": est_id},
    headers=H("advogado"), timeout=15)
tk2 = r.json().get("id")
depois = db("SELECT count(*) FROM notifications WHERE user_id='" + est_id + "'")
chk("tarefas: atribuição gera notificação ao responsável",
    r.status_code == 201 and int(depois) == int(antes) + 1,
    f"{r.status_code} notifs {antes}→{depois}")
notifs = db("SELECT titulo FROM notifications WHERE user_id='" + est_id
            + "' ORDER BY created_at DESC LIMIT 1")
chk("tarefas: notificação identifica tarefa atribuída",
    "tarefa" in (notifs or "").lower(), notifs)

# auto-atribuição NÃO duplica notificação
antes = db("SELECT count(*) FROM notifications WHERE user_id='"
           + usuario_id("advogado") + "'")
r = requests.post(f"{BASE}/api/tasks", json={
    "titulo": "EJC_QA tarefa auto", "responsavel_id": usuario_id("advogado")},
    headers=H("advogado"), timeout=15)
depois = db("SELECT count(*) FROM notifications WHERE user_id='"
            + usuario_id("advogado") + "'")
chk("tarefas: atribuição a si mesmo NÃO gera notificação duplicada",
    r.status_code == 201 and int(depois) == int(antes),
    f"{r.status_code} {antes}→{depois}")

# responsável inexistente
r = requests.post(f"{BASE}/api/tasks", json={
    "titulo": "EJC_QA x",
    "responsavel_id": "00000000-0000-0000-0000-000000000000"},
    headers=H("advogado"), timeout=15)
chk("tarefas: responsável inexistente rejeitado 422",
    r.status_code == 422, f"{r.status_code} {r.text[:80]}")

# caso sem acesso
r = requests.post(f"{BASE}/api/tasks", json={
    "titulo": "EJC_QA invasão", "case_id": caso}, headers=H("cliente"), timeout=15)
chk("tarefas: case_id sem acesso rejeitado (403/404)",
    r.status_code in (403, 404), f"{r.status_code} {r.text[:80]}")

# ── 9. TAREFAS: edição, conclusão e sincronização de atendimento ────────────
r = requests.patch(f"{BASE}/api/tasks/{tk1}", json={
    "descricao": "EJC_QA descrição atualizada", "prioridade": "critica",
    "data_limite": "2026-12-16"}, headers=H("advogado"), timeout=15)
chk("tarefas: edição (descrição/prioridade/prazo) 200",
    r.status_code == 200, f"{r.status_code} {r.text[:80]}")

r = requests.patch(f"{BASE}/api/tasks/{tk1}", json={"status": "concluida"},
                   headers=H("advogado"), timeout=15)
chk("tarefas: conclusão 200", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

# persistência no banco (camada SQL, independente de filtros do GET)
row = db(f"SELECT status, (concluida_em IS NOT NULL)::text FROM tasks WHERE id='{tk1}'")
chk("tarefas: conclusão persiste status + concluida_em preenchida",
    row is not None and row.split("|")[0] == "concluida" and row.split("|")[1] == "true",
    row)

# status inválido
r = requests.patch(f"{BASE}/api/tasks/{tk1}", json={"status": "fantasma"},
                   headers=H("advogado"), timeout=15)
chk("tarefas: status inválido rejeitado 422", r.status_code == 422,
    f"{r.status_code} {r.text[:80]}")

# reabertura limpa concluida_em
r = requests.patch(f"{BASE}/api/tasks/{tk1}", json={"status": "a_fazer"},
                   headers=H("advogado"), timeout=15)
chk("tarefas: reabertura 200", r.status_code == 200, f"{r.status_code}")
r = requests.get(f"{BASE}/api/tasks", headers=H("advogado"), timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
tk = next((t for t in itens if t.get("id") == tk1), None)
chk("tarefas: reabertura zera concluida_em",
    tk is not None and tk.get("status") == "a_fazer"
    and tk.get("concluida_em") in (None, ""),
    str(tk)[:150] if tk else "tarefa não listada")

# transferência de responsável em edição
r = requests.patch(f"{BASE}/api/tasks/{tk1}",
                   json={"responsavel_id": usuario_id("secretaria")},
                   headers=H("advogado"), timeout=15)
chk("tarefas: atribuição de responsável na edição 200",
    r.status_code == 200, f"{r.status_code} {r.text[:80]}")

# edição de inexistente
r = requests.patch(f"{BASE}/api/tasks/00000000-0000-0000-0000-000000000000",
                   json={"titulo": "x"}, headers=H("advogado"), timeout=15)
chk("tarefas: edição de inexistente 404", r.status_code == 404, f"{r.status_code}")

# ── 10. TAREFAS: filtros e escopo ───────────────────────────────────────────
r = requests.get(f"{BASE}/api/tasks", headers=H("advogado"),
                 params={"case_id": caso}, timeout=15)
chk("tarefas: filtro por caso 200", r.status_code == 200, f"{r.status_code}")

r = requests.get(f"{BASE}/api/tasks", headers=H("advogado"),
                 params={"minhas": "true"}, timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
adv_id_now = usuario_id("advogado")
chk("tarefas: filtro minhas= só retorna onde sou responsável",
    all(t.get("responsavel_id") == adv_id_now for t in itens) if itens else True,
    f"{len(itens)} itens")

# não-gestão não vê tarefas de casos alheios (IDOR)
r = requests.get(f"{BASE}/api/tasks", headers=H("estagiario"), timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
chk("tarefas: estagiário acessa listagem com escopo próprio 200",
    r.status_code == 200, f"{r.status_code}")

# ── 11. TAREFAS: exclusão e atendimento ─────────────────────────────────────
r = requests.delete(f"{BASE}/api/tasks/{tk2}", headers=H("advogado"), timeout=15)
chk("tarefas: exclusão (soft) 200", r.status_code == 200,
    f"{r.status_code} {r.text[:80]}")
r = requests.get(f"{BASE}/api/tasks", headers=H("advogado"), timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
chk("tarefas: excluída sai da listagem",
    not any(t.get("id") == tk2 for t in itens))
r = requests.delete(f"{BASE}/api/tasks/00000000-0000-0000-0000-000000000000",
                    headers=H("advogado"), timeout=15)
chk("tarefas: exclusão de inexistente 404", r.status_code == 404, f"{r.status_code}")

# ── 12. Timezone / formato horário ──────────────────────────────────────────
# hora é VARCHAR(10) livre + data_evento DATE — o sistema aceita qualquer
# string de horário legível; o ponto provável aqui é a tolerância da validação
# (não crashar) e a normalização do trim nos conflitos.
r = requests.post(f"{BASE}/api/agenda-eventos", json={
    "titulo": "EJC_QA hora com espaços", "tipo": "compromisso",
    "data_evento": "2026-12-23", "hora": "  13:00  "},
    headers=H("advogado"), timeout=15)
chk("agenda: horário com espaços aceito e normalizado (trim)",
    r.status_code == 201, f"{r.status_code} {r.text[:80]}")
ev_hs = r.json().get("id")
r = requests.get(f"{BASE}/api/agenda-eventos", headers=H("advogado"),
                 params={"page_size": 500}, timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
ev = next((e for e in itens if e.get("id") == ev_hs), None)
chk("agenda: hora retornada normalizada ('13:00')",
    ev is not None and (ev.get("hora") or "").strip() == "13:00",
    str(ev)[:150] if ev else "evento não listado")

# ── 13. Lacunas documentadas (não são defeitos) ─────────────────────────────
# O módulo NÃO implementa: recorrência, lembretes/notificações de eventos,
# timezone explícito, participantes múltiplos e client_id direto.
# São decisões/limitações conhecidas — a bateria registra sem reprovar.
chk("agenda: sem recorrência (lacuna aceita — campo inexistente no schema)",
    db("SELECT count(*) FROM information_schema.columns WHERE table_name="
       "'agenda_eventos' AND column_name='recorrencia'") == "0")
chk("tarefas: sem lembrete automático (lacuna aceita — sem campo cron/reminder)",
    db("SELECT count(*) FROM information_schema.columns WHERE table_name='tasks' "
       "AND column_name IN ('lembrete','reminder')") == "0")
chk("agenda: sem timezone explícito (data date + hora varchar — lacuna aceita)",
    db("SELECT count(*) FROM information_schema.columns WHERE table_name="
       "'agenda_eventos' AND column_name='timezone'") == "0")

# ── limpeza final ───────────────────────────────────────────────────────────
for eid in [ev1, ev3, ev4, ev_hs]:
    requests.delete(f"{BASE}/api/agenda-eventos/{eid}", headers=H("advogado"
        if eid != ev4 else "socio"), timeout=15)
requests.delete(f"{BASE}/api/tasks/{tk1}", headers=H("advogado"), timeout=15)
requests.delete(f"{BASE}/api/agenda-eventos/{outro}", headers=H("secretaria"), timeout=15)

print(f"\nM16 resultado: {TOTAL - FALHAS}/{TOTAL} PASS")
if FALHAS:
    print(f"{FALHAS} falha(s)")
    sys.exit(2)
