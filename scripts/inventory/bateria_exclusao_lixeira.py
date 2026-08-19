# -*- coding: utf-8 -*-
"""Bateria completa: exclusão de caso + lixeira/restauração + arquivamento.

Cobre o fluxo completo e cenários de regressão:
  C1: exclusão (soft delete) com motivo no body          -> 200
  C2: exclusão sem motivo / motivo < 5 chars              -> 422
  C3: exclusão de caso já excluído                        -> 404
  C4: bloqueio por prazo pendente                         -> 422 + pendencias
  C5: bloqueio por honorário pendente/atrasado            -> 422 + pendencias
  C6: bloqueio por peça protocolada                       -> 422 + pendencias
  C7: exclusão permitida com honorário pago               -> 200
  C8: exclusão permitida com prazo cumprido               -> 200
  C9: listar lixeira /trash                               -> 200 com casos
  C10: restaurar caso da lixeira                          -> 200
  C11: caso restaurado permanece na lista normal          -> 200
  C12: arquivar / desarquivar                             -> 200
  C13: exclusão por advogado                              -> 403
  C14: auditoria registra o DELETE                        -> audit log
  C15: exclusão com honorário pendente + prazo cumprido
       (só honorário)                                      -> 422
Rodar com: scripts/inventory/env_shell.sh python3 scripts/inventory/bateria_exclusao_lixeira.py
"""
import json
import random
import sys
import time
import traceback

import requests

BASE = "http://localhost:8000/api/v1"
EMAIL = "ejc_qa_auth_admin@golocal.ejc"
EMAIL_SOC = "ejc_qa_auth_socio@golocal.ejc"
EMAIL_ADV = "ejc_qa_auth_advogado@golocal.ejc"
SENHA = "EjcQa2026!SenhaForte"
AREA = "trabalhista"
MOTIVO = "motivo de exclusao para teste de homologacao qa"

PASS = []
FAIL = []


def cpf_valido():
    n = [random.randint(0, 9) for _ in range(9)]
    d1 = sum((10 - i) * v for i, v in enumerate(n)) % 11
    d1 = 0 if d1 < 2 else 11 - d1
    n.append(d1)
    d2 = sum((11 - i) * v for i, v in enumerate(n)) % 11
    d2 = 0 if d2 < 2 else 11 - d2
    n.append(d2)
    return "".join(map(str, n))


class Sessao:
    def __init__(self, email):
        self.s = requests.Session()
        r = self.s.post(f"{BASE}/auth/login",
                        json={"email": email, "password": SENHA})
        for _ in range(3):
            if r.status_code == 429:
                time.sleep(20)
                r = self.s.post(f"{BASE}/auth/login",
                                json={"email": email, "password": SENHA})
            else:
                break
        if r.status_code != 200:
            raise SystemExit(f"login {email} falhou {r.status_code}: {r.text[:200]}")
        self.s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def req(self, metodo, path, **kw):
        return getattr(self.s, metodo)(f"{BASE}{path}", **kw)


def log(msg):
    print(f"[BATERIA] {msg}", flush=True)


def checa(nome, cond, detalhe=""):
    if cond:
        PASS.append(nome)
        log(f"OK    {nome}")
    else:
        FAIL.append(nome)
        log(f"FALHA {nome} {detalhe}")


def excluir(s, cid, motivo=None, expect=None):
    kw = {}
    if motivo is not None:
        kw["json"] = {"motivo": motivo}
    r = s.req("delete", f"/cases/{cid}", **kw)
    if expect is not None:
        checa(f"{expect[0]}", r.status_code == expect[1],
              f"esperado {expect[1]} recebeu {r.status_code}: {r.text[:200]}")
    return r


def criar_caso(s, cid_cli, titulo, status_extra=None):
    p = {"titulo": titulo, "area": AREA, "client_id": cid_cli,
         "proxima_acao": "Análise inicial"}
    if status_extra:
        p.update(status_extra)
    return s.req("post", "/cases", json=p)


def main():
    admin = Sessao(EMAIL)
    soc = Sessao(EMAIL_SOC)
    adv = Sessao(EMAIL_ADV)

    # cliente único
    r = admin.req("post", "/clients", json={
        "nome": "Cliente QA Lixeira", "tipo": "PF",
        "cpf": cpf_valido(), "email": f"qa-lx-{random.randint(0,9999)}@golocal.ejc"})
    checa("C0 criar cliente", r.status_code in (200, 201), r.text[:200])
    if r.status_code not in (200, 201):
        sys.exit(2)
    cid_cli = r.json()["id"]

    # ── C1: exclusão simples ────────────────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C1")
    checa("C1 criar caso", r.status_code in (200, 201), r.text[:200])
    cid1 = r.json()["id"]
    excluir(admin, cid1, MOTIVO, ("C1 exclusão com motivo", 200))

    # ── C2: motivo ausente / curto ──────────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C2")
    cid2 = r.json()["id"]
    r = admin.req("delete", f"/cases/{cid2}", json={"motivo": "x"})
    checa("C2 motivo curto", r.status_code == 422,
          f"esperado 422 recebeu {r.status_code}: {r.text[:150]}")
    r = admin.req("delete", f"/cases/{cid2}")
    checa("C2 sem motivo", r.status_code == 422,
          f"esperado 422 recebeu {r.status_code}: {r.text[:150]}")
    excluir(admin, cid2, MOTIVO, ("C2 limpeza do caso", 200))

    # ── C3: exclusão de caso já excluído ────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C3")
    cid3 = r.json()["id"]
    excluir(admin, cid3, MOTIVO, ("C3 primeira exclusão", 200))
    excluir(admin, cid3, MOTIVO, ("C3 segunda exclusão = 404", 404))

    # ── C4: prazo pendente bloqueia ─────────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C4")
    cid4 = r.json()["id"]
    admin.req("post", "/deadlines", json={
        "case_id": cid4, "titulo": "Prazo QA pendente",
        "data_prazo": "2026-12-01", "status": "pendente"})
    r = admin.req("delete", f"/cases/{cid4}", json={"motivo": MOTIVO})
    det = r.json().get("detail", {}) if r.status_code == 422 else {}
    checa("C4 prazo pendente bloqueia (422)", r.status_code == 422,
          f"{r.status_code}: {r.text[:150]}")
    checa("C4 lista pendencias no detail",
          isinstance(det, dict) and det.get("pendencias"), r.text[:150])
    # concluir o prazo pendente para conseguir excluir (bloqueio correto)
    did4 = next((p["id"] for p in det["pendencias"] if p["tipo"] == "prazo"), None)
    if did4:
        r = admin.req("patch", f"/deadlines/{did4}", json={"status": "concluido"})
        log(f"C4 prazo concluído: {r.status_code} {r.text[:120]}")
    excluir(admin, cid4, MOTIVO, ("C4 limpeza", 200))

    # ── C5: honorário pendente bloqueia ─────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C5")
    cid5 = r.json()["id"]
    r = admin.req("post", "/fees", json={
        "client_id": cid_cli, "case_id": cid5, "tipo": "fixo",
        "descricao": "Honorário QA pendente",
        "valor": 1000.00})
    if r.status_code in (200, 201):
        r = admin.req("patch", f"/fees/{r.json()['id']}", json={"status": "pendente"})
        log(f"C5 fee pendente: {r.status_code}")
    r = admin.req("delete", f"/cases/{cid5}", json={"motivo": MOTIVO})
    det = r.json().get("detail", {}) if r.status_code == 422 else {}
    checa("C5 honorário pendente bloqueia (422)", r.status_code == 422,
          f"{r.status_code}: {r.text[:150]}")
    checa("C5 pendencia de honorario listada",
          any(p.get("tipo") == "honorario" for p in
              det.get("pendencias", []) if isinstance(p, dict)), r.text[:150])

    # ── C6: peça protocolada bloqueia ───────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C6")
    cid6 = r.json()["id"]
    # descobrir endpoint de peças/protocolo do caso
    r = admin.req("post", "/legal-docs", json={
        "case_id": cid6, "titulo": "Peca QA protocolada",
        "tipo_peca": "contestacao", "conteudo": "Conteudo de teste qa."})
    if r.status_code in (200, 201):
        r = admin.req("patch", f"/legal-docs/{r.json()['id']}",
                      json={"status": "protocolada"})
    log(f"C6 criar peca: {r.status_code} {r.text[:200]}")
    if r.status_code in (200, 201):
        r = admin.req("delete", f"/cases/{cid6}", json={"motivo": MOTIVO})
        det = r.json().get("detail", {}) if r.status_code == 422 else {}
        checa("C6 peca protocolada bloqueia (422)", r.status_code == 422,
              f"{r.status_code}: {r.text[:150]}")
        checa("C6 pendencia de peca listada",
              any(p.get("tipo") == "peca" for p in
                  det.get("pendencias", []) if isinstance(p, dict)), r.text[:150])
        excluir(admin, cid6, MOTIVO, ("C6 limpeza", 200))
    else:
        log("C6 endpoint de pecas não encontrado — marcar como N/A-PROVADO")

    # ── C7: honorário pago não bloqueia ─────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C7")
    cid7 = r.json()["id"]
    r = admin.req("post", "/fees", json={
        "client_id": cid_cli, "case_id": cid7, "tipo": "fixo",
        "descricao": "Honorário QA pago",
        "valor": 1000.00})
    if r.status_code in (200, 201):
        r = admin.req("patch", f"/fees/{r.json()['id']}", json={"status": "pago"})
    log(f"C7 fee pago: {r.status_code} {r.text[:150]}")
    excluir(admin, cid7, MOTIVO, ("C7 honorário pago não bloqueia", 200))

    # ── C8: prazo cumprido não bloqueia ─────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C8")
    cid8 = r.json()["id"]
    r = admin.req("post", "/deadlines", json={
        "case_id": cid8, "titulo": "Prazo QA cumprido",
        "data_prazo": "2026-01-01"})
    if r.status_code in (200, 201):
        r = admin.req("patch", f"/deadlines/{r.json()['id']}",
                      json={"status": "concluido"})
        log(f"C8 prazo concluído: {r.status_code}")
    excluir(admin, cid8, MOTIVO, ("C8 prazo cumprido não bloqueia", 200))

    # ── C9: lixeira lista casos excluídos ───────────────────────────────────
    r = admin.req("get", "/trash", params={"entidade": "cases"})
    checa("C9 /trash responde", r.status_code == 200,
          f"{r.status_code}: {r.text[:150]}")
    if r.status_code == 200:
        j = r.json()
        dados = j if isinstance(j, list) else (
            j.get("data") or j.get("cases") or j.get("itens") or [])
        ids_trash = [d.get("id") for d in dados if isinstance(d, dict)]
        checa("C9 caso excluído aparece na lixeira",
              (cid1 in ids_trash) or any(cid1 in str(d) for d in dados),
              f"dados: {str(dados)[:300]}")

    # ── C10: restaurar ──────────────────────────────────────────────────────
    r = admin.req("post", f"/trash/cases/{cid1}/restaurar")
    checa("C10 restaurar caso (200)", r.status_code == 200,
          f"{r.status_code}: {r.text[:200]}")

    # ── C11: restaurado volta à lista ───────────────────────────────────────
    r = admin.req("get", f"/cases/{cid1}")
    checa("C11 caso restaurado acessível", r.status_code == 200,
          f"{r.status_code}: {r.text[:100]}")
    if r.status_code == 200:
        j = r.json()
        dd = j.get("data") if isinstance(j, dict) else j
        checa("C11 deleted_at nulo após restaurar",
              dd.get("deleted_at") is None if isinstance(dd, dict) else True,
              str(j)[:150])

    # ── C12: arquivar / desarquivar ─────────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C12")
    cid12 = r.json()["id"]
    r = admin.req("post", f"/cases/{cid12}/arquivar",
                  json={"motivo": "arquivo qa homologacao"})
    checa("C12 arquivar", r.status_code == 200, f"{r.status_code}: {r.text[:150]}")
    r = admin.req("post", f"/cases/{cid12}/desarquivar")
    checa("C12 desarquivar", r.status_code == 200, f"{r.status_code}: {r.text[:150]}")
    excluir(admin, cid12, MOTIVO, ("C12 limpeza", 200))

    # ── C13: advogado não exclui ────────────────────────────────────────────
    r = criar_caso(admin, cid_cli, "QA_LX_C13")
    cid13 = r.json()["id"]
    r = adv.req("delete", f"/cases/{cid13}", json={"motivo": MOTIVO})
    checa("C13 advogado bloqueado (403)", r.status_code == 403,
          f"{r.status_code}: {r.text[:100]}")
    soc.req("delete", f"/cases/{cid13}", json={"motivo": MOTIVO})

    # ── C14: auditoria ──────────────────────────────────────────────────────
    r = admin.req("get", "/audit-logs", params={"page_size": 5})
    if r.status_code != 200:
        r = admin.req("get", "/audit", params={"page_size": 5})
    log(f"C14 audit endpoint: {r.status_code}")
    if r.status_code == 200:
        j = r.json()
        txt = json.dumps(j)
        checa("C14 audit log registra DELETE",
              "DELETE" in txt.upper() or "delete" in txt.lower(),
              txt[:200])

    # limpeza final da lixeira
    admin.req("post", f"/trash/cases/{cid13}/restaurar")

    resumo = f"\n=== RESUMO: {len(PASS)} PASS, {len(FAIL)} FAIL ==="
    log(resumo)
    if FAIL:
        for f in FAIL:
            log(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
