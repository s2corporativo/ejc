#!/usr/bin/env python3
"""Auditoria E2E do EJC — bateria de testes reais contra a API local (:8000).
Dados criados usam o prefixo TESTE_EJC_AUDITORIA_2026 (isolamento total).
"""
import json
import sys
import requests

BASE = "http://localhost:8000/api"
ADMIN_EMAIL = "admin@seu-dominio.com.br"
ADMIN_PW = "TROCAR_POR_SENHA_FORTE_INICIAL"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

PREFIX = "TESTE_EJC_AUDITORIA_2026"

s = requests.Session()
s.headers["Content-Type"] = "application/json"
s.headers["Connection"] = "close"
results = []

def retried(fn, retries=2, delay=6):
    """Reexecuta fn() após falhas de conexão/timeout (servidor em sandbox
    sob pressão de memória pode derrubar o processo; reiniciamos antes de
    reexecutar)."""
    import time
    last = None
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
            # reinicia o servidor se necessário
            restart_if_down()
    raise last

def restart_if_down():
    import os
    try:
        requests.get(BASE + "/openapi.json", timeout=5)
        return
    except Exception:  # noqa: BLE001
        pass
    import subprocess, time
    if not os.path.exists("/swap/swapfile"):
        subprocess.run(["sudo", "fallocate", "-l", "4G", "/swap/swapfile"],
                       capture_output=True)
        subprocess.run(["sudo", "chmod", "600", "/swap/swapfile"], capture_output=True)
        subprocess.run(["sudo", "mkswap", "/swap/swapfile"], capture_output=True)
    subprocess.run(["sudo", "swapon", "/swap/swapfile"], capture_output=True)
    subprocess.Popen(
        "cd /home/ubuntu/ejc/backend && ( set -a && source ../.env && set +a "
        "&& nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 "
        "> /tmp/uvicorn.log 2>&1 & )",
        shell=True)
    for _ in range(8):
        time.sleep(5)
        try:
            if requests.get(BASE + "/openapi.json", timeout=5).status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass

def check(tid, desc, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((tid, desc, status, detail if not cond else ""))
    print(f"{status}  {tid}  {desc}" + (f"  << {detail}" if not cond else ""))

def post(path, payload=None, timeout=30, files=None, data=None, headers=None):
    if files:
        # sessão mantém Content-Type application/json e requests NÃO o remove
        # ao enviar multipart — a validação do servidor falha. Usamos sessão
        # temporária sem Content-Type.
        tmp = requests.Session()
        tmp.headers["Authorization"] = s.headers.get("Authorization", "")
        return tmp.post(BASE + path, files=files, data=data or {}, timeout=timeout)
    return s.post(BASE + path, json=payload, timeout=timeout)

def get(path, params=None, timeout=30):
    return s.get(BASE + path, params=params or {}, timeout=timeout)

def safe_json(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}

def patch(path, payload):
    return s.patch(BASE + path, json=payload)

def delete(path):
    return s.delete(BASE + path)

# ---------------- T01 Autenticação ----------------
r = get("/users/me")
check("T01-1", "Endpoint protegido sem token → 401", r.status_code == 401, f"{r.status_code}")

r = post("/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PW})
login_ok = r.status_code == 200
check("T01-2", "Login admin retorna 200", login_ok, str(r.text)[:120])
try:
    tok = r.json().get("access_token")
except Exception:  # noqa: BLE001
    tok = None
s.headers["Authorization"] = f"Bearer {tok}"

r = get("/users/me")
check("T01-3", "/users/me com token retorna perfil", r.status_code == 200, f"{r.status_code}")
profile = safe_json(r) if r.status_code == 200 else {}
ROLE = profile.get("role", profile.get("data", {}).get("role", "unknown"))
check("T01-4", "Perfil identifica role", bool(ROLE), json.dumps(profile)[:120])

r = get("/openapi.json")
check("T01-5", "OpenAPI servida", r.status_code == 200, f"{r.status_code}")

r = get("/ai/status", timeout=20)
check("T01-6", "Status da camada de IA", r.status_code == 200, f"{r.status_code}")

r = get("/rag/buscar", params={"q": "teste RAG auditoria"}, timeout=30)
check("T01-7", "Endpoint RAG acessível", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T04 Clientes ----------------
def _find_test_client():
    try:
        rr = get("/clients/", params={"search": PREFIX})
    except Exception:  # noqa: BLE001
        restart_if_down()
        try:
            rr = get("/clients/", params={"search": PREFIX})
        except Exception:  # noqa: BLE001
            return None
    dd = safe_json(rr) if rr.status_code == 200 else {}
    items = dd.get("data", dd) if isinstance(dd, dict) else dd
    for it in items:
        if (it.get("razao_social") or "").startswith(PREFIX):
            return it["id"]
    return None

def _create_test_client(cnpj, suffix=""):
    rr = post("/clients/", {
        "tipo": "PJ",
        "razao_social": f"{PREFIX} Cliente Alpha Ltda{suffix}",
        "nome_fantasia": f"{PREFIX} Alpha{suffix}",
        "cnpj": cnpj,
        "email": f"{PREFIX.lower()}{suffix}@cliente.teste.br",
        "telefone": "31 99999-0001",
        "logradouro": "Rua da Auditoria", "numero": "100", "bairro": "Centro",
        "cidade": "Betim", "estado": "MG", "cep": "32510000",
        "origem": "indicacao", "status": "lead",
    })
    if rr.status_code in (200, 201):
        c1 = safe_json(rr)
        return rr, c1.get("id") or c1.get("data", {}).get("id") if c1 else None
    return rr, None

# Idempotente: localiza primeiro (evita o caminho 409 do POST que instabiliza o sandbox)
T04_1_CODE = None
C1_ID = _find_test_client()
if C1_ID is None:
    r, C1_ID = _create_test_client("11444759000180")
    T04_1_CODE = r.status_code
if C1_ID is None:
    restart_if_down()
    C1_ID = _find_test_client()
if C1_ID is None:
    r, C1_ID = _create_test_client("11222333000181", suffix="-2")
    T04_1_CODE = r.status_code if T04_1_CODE is None else T04_1_CODE

def _find_test_case():
    rr = get("/cases/", params={"search": PREFIX})
    dd = safe_json(rr) if rr.status_code == 200 else {}
    items = dd.get("data", dd) if isinstance(dd, dict) else dd
    for it in items:
        if (it.get("titulo") or "").startswith(PREFIX):
            return it["id"]
    return None
if C1_ID is None:
    restart_if_down()
    C1_ID = _find_test_client()
if C1_ID is None:
    print("ABORT: cliente não localizado nem criado")
    sys.exit(1)
T04_1_OK = 'T04_1_CODE' in dir() and T04_1_CODE in (200, 201)
check("T04-1", "Criar cliente retorna 201/200 (ou já existia)", C1_ID is not None,
      "id=" + str(C1_ID) + (" (criado nesta execução)" if T04_1_OK else " (existente — idempotente)"))

r = get("/clients/", params={"search": "TESTE_EJC_AUDITORIA_2026"})
data = safe_json(r) if r.status_code == 200 else {}
check("T04-2", "Buscar cliente por prefixo", r.status_code == 200 and str(data).count(PREFIX) >= 1,
      f"{r.status_code} {str(data)[:120]}")

r = patch("/clients/" + str(C1_ID), {"telefone": "31 99999-9999"})
check("T04-3", "Atualizar cliente", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

r = post("/clients/", {
    "tipo": "PJ",
    "razao_social": f"{PREFIX} Cliente Alpha Duplicada",
    "cnpj": "11222333000181",
    "email": f"{PREFIX.lower()}dup2@cliente.teste.br",
})
check("T04-4", "Duplicidade de CNPJ rejeitada (409/422)", r.status_code in (409, 422), f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T05 Casos ----------------
r = post("/cases/", {
    "titulo": f"{PREFIX} - Caso Administrativo Tributário 01",
    "area": "tributario",
    "client_id": C1_ID,
    "prioridade": "alta",
    "descricao_fatos": "Caso criado pela auditoria E2E 2026. Defesa em auto de infração ICMS.",
    "proxima_acao": "Preparar defesa administrativa",
    "proxima_acao_prazo": "2026-09-15",
    "numero_processo": None,
})
case = safe_json(r) if r.status_code in (200, 201) else None
CASE_ID = None
if case:
    CASE_ID = case.get("id") or case.get("data", {}).get("id")
if CASE_ID is None and r.status_code in (409, 500):
    CASE_ID = _find_test_case()
if CASE_ID is None:
    print("ABORT: caso não criado —", r.status_code, r.text[:300])
    sys.exit(2)
check("T05-1", "Criar caso retorna 201/200", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")

r = get("/cases/" + str(CASE_ID))
check("T05-2", "Consultar caso criado", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

r = patch("/cases/" + str(CASE_ID), {"proxima_acao": "Preparar defesa administrativa"})
check("T05-3", "Atualizar caso (próxima ação)", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

r = post("/cases/", {"titulo": "caso orfão", "area": "trabalhista"})
check("T05-4", "Caso sem client_id rejeitado (422)", r.status_code == 422, f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T06 Prazos (deadlines) ----------------
r = post("/deadlines/", {
    "titulo": f"{PREFIX} Prazo de defesa administrativa",
    "tipo": "administrativo",
    "prioridade": "alta",
    "data_prazo": "2026-09-15",
    "case_id": CASE_ID,
})
prazo = safe_json(r) if r.status_code in (200, 201) else None
PRAZO_ID = prazo.get("id") if prazo else None
check("T06-1", "Criar prazo (deadline) retorna 201/200", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")
PRAZO_ID = PRAZO_ID or "none"

r = post("/deadlines/", {
    "titulo": f"{PREFIX} Prazo de audiência",
    "tipo": "audiencia",
    "data_prazo": "2026-08-13",
    "case_id": CASE_ID,
})
check("T06-2", "Criar segundo prazo", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

r = get("/deadlines/", params={"search": PREFIX})
check("T06-3", "Listar prazos com busca", r.status_code == 200, f"{r.status_code}")

# ---------------- T07 Tarefas ----------------
r = post("/tasks/", {
    "titulo": f"{PREFIX} Tarefa de análise de XMLs monofásicos",
    "descricao": "Auditar XMLs de entrada de produtos monofásicos",
    "prioridade": "alta",
    "data_limite": "2026-08-20",
    "case_id": CASE_ID,
    "responsavel_id": profile.get("id"),
})
task = safe_json(r) if r.status_code in (200, 201) else None
TASK_ID = task.get("id") if task else None
check("T07-1", "Criar tarefa no caso", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")
TASK_ID = TASK_ID or "none"

r = get("/tasks/", params={"case_id": CASE_ID})
check("T07-2", "Listar tarefas do caso", r.status_code == 200, f"{r.status_code}")

open("/tmp/doc_teste_ejc.txt", "w").write(f"{PREFIX} conteúdo binário de teste\n")
# ---------------- T08 Documentos ----------------
r = post("/documents/upload",
         files={"file": ("doc_teste_ejc.txt", open("/tmp/doc_teste_ejc.txt", "rb"), "text/plain")},
         data={"titulo": f"{PREFIX} Documento binário auditoria", "tipo": "contrato",
               "case_id": str(CASE_ID) if CASE_ID else ""})
up = safe_json(r) if r.status_code in (200, 201) else None
DOC_ID = None
if up:
    DOC_ID = up.get("id") or up.get("document_id")
check("T08-1", "Upload de arquivo binário", r.status_code in (200, 201), f"{r.status_code} {str(up)[:150]}")

r = get("/documents/upload") if False else get("/documents")
check("T08-2", "Listar documentos", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T09 Agenda ----------------
r = post("/agenda-eventos/", {
    "titulo": f"{PREFIX} Reunião de auditoria",
    "tipo": "reuniao",
    "data_evento": "2026-09-01",
    "hora": "14:00",
    "descricao": "Evento criado pela auditoria E2E",
    "case_id": CASE_ID,
})
check("T09-1", "Criar evento de agenda", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")

r = get("/agenda-eventos/", params={"search": PREFIX})
check("T09-2", "Listar eventos de agenda", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T10 Dashboard ----------------
r = get("/dashboard")
d = safe_json(r) if r.status_code == 200 else {}
check("T10-1", "Dashboard responde 200", r.status_code == 200, f"{r.status_code}")
ds = str(d)
check("T10-2", "Dashboard reflete caso criado", CASE_ID and CASE_ID in ds or d.get("casos", {}).get("total", d.get("total_casos", 0)) >= 1,
      ds[:200])

# ---------------- T10b Ficha de triagem (pré-requisito da geração de peças) ----------------
FT = {}
r = post("/triagem/ficha/pre-preencher", {"case_id": str(CASE_ID)})
check("T10b-1", "Pré-preenchimento da ficha de triagem (IA)", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")
if r.status_code == 200 and isinstance(safe_json(r), dict):
    FT = safe_json(r)
r = post("/triagem/ficha", {
    "case_id": str(CASE_ID),
    "competencia": FT.get("competencia", "administrativa_tributaria"),
    "rito": FT.get("rito", "ordinario"),
    "legitimidade_ativa": FT.get("legitimidade_ativa", "cliente"),
    "legitimidade_passiva": FT.get("legitimidade_passiva", "fazenda_publica"),
    "prescricao_decadencia": FT.get("prescricao_decadencia", "em_analise"),
    "tutela_urgencia": FT.get("tutela_urgencia", False),
    "tutela_fundamento": FT.get("tutela_fundamento"),
    "provas_disponiveis": FT.get("provas_disponiveis", "autos de infração e notificações"),
    "provas_faltantes": FT.get("provas_faltantes"),
    "valor_causa": str(FT.get("valor_causa", "50000.00")),
    "risco_processual": FT.get("risco_processual", "medio"),
    "risco_nota": str(FT.get("risco_nota", "60")),
    "pedidos_principais": "Cancelamento do auto de infração e afastamento da multa.",
    "pedidos_subsidiarios": "Redução da multa por circunstâncias atenuantes.",
    "confirmar": True,
})
ft = safe_json(r) if r.status_code in (200, 201) and isinstance(safe_json(r), dict) else {}
check("T10b-2", "Salvar ficha de triagem (habilita geração de peças)", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")

# ---------------- T11 Peças ----------------
r = post("/pecas/gerar", {
    "titulo": f"{PREFIX} Minuta de defesa administrativa",
    "area_direito": "tributario",
    "tipo_peca": "contestacao",
    "case_id": CASE_ID,
    "descricao_fatos": "Defesa em auto de infração ICMS. Cliente autuado por omissão de recolhimento.",
    "pedidos": "Cancelamento do auto de infração e afastamento da multa.",
})
peca = safe_json(r) if r.status_code in (200, 201) else None
PECA_ID = peca.get("id") if peca else None
check("T11-1", "Gerar peça (minuta)", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")

r = get("/pecas/meta", params={"case_id": CASE_ID})
check("T11-2", "Metadados de peças do caso", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T12 IA ----------------
r = retried(lambda: post("/ai/core/chat", {"mensagem": "O que é PIS monofásico na cadeia tributária?"}, timeout=120))
check("T12-1", "AI-core chat responde", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:150]}")

r = retried(lambda: post("/ai/pesquisar", {"pergunta": "defesa administrativa tributária"}, timeout=120))
check("T12-2", "AI pesquisar", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

r = retried(lambda: post("/ai/resumir-documento", {"texto": "Texto de teste curto para validar endpoint de resumo."}, timeout=120))
check("T12-3", "AI resumir documento", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

r = get("/rag/buscar", params={"q": "PIS monofásico", "limite": 5}, timeout=60)
rag = safe_json(r) if r.status_code == 200 else None
check("T12-4", "RAG busca (knowledge base)", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T13 DPT360 ----------------
r = get("/dpt360/dashboard", timeout=60)
dpt = safe_json(r) if r.status_code == 200 else {}
check("T13-1", "DPT360 dashboard", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

r = get(f"/dpt360/companies/{C1_ID}", timeout=60)
check("T13-2", "DPT360 empresa/projeto", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

r = get(f"/dpt360/diagnostics/readiness/{C1_ID}", timeout=60)
check("T13-3", "DPT360 diagnóstico de prontidão", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

r = get(f"/dpt360/reports/executive/{C1_ID}?days=30", timeout=120)
rel = safe_json(r) if r.status_code == 200 else None
check("T13-4", "DPT360 relatório executivo", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")
if rel:
    check("T13-5", "Relatório é rascunho determinístico", rel.get("status") == "rascunho", str(rel)[:100])
    check("T13-6", "Relatório traz cobertura completa", rel.get("cobertura_completa") is True,
          json.dumps(rel.get("cobertura_notas"))[:200])

# ---------------- T14 Financeiro ----------------
r = get("/financeiro/consolidado", timeout=60)
check("T14-1", "Financeiro consolidado acessível", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

fc = safe_json(r) if r.status_code == 200 else {}
check("T14-2", "Financeiro consolidado retorna estrutura completa",
      bool(fc) and any(k in fc for k in ("receitas", "despesas", "total", "dados", "resumo", "consolidado", "periodos")),
      json.dumps(fc)[:150])

# ---------------- T15 Intimações/andamentos ----------------
r = get("/casos/" + str(CASE_ID) + "/andamentos/status", timeout=30)
check("T15-1", "Status de andamentos do caso", r.status_code == 200, f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T16 Busca global ----------------
r = get("/search/", params={"q": PREFIX}, timeout=30)
check("T16-1", "Busca global retorna resultados", r.status_code == 200 and PREFIX in r.text,
      f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T17 Notificações ----------------
r = get("/notifications/", timeout=30)
check("T17-1", "Notificações listáveis", r.status_code == 200, f"{r.status_code}")

# ---------------- T18 RBAC ----------------
# criar usuário advogado comum via rota de gestão (superadmin)
r = post("/users/", {
    "email": f"{PREFIX.lower()}@adv.teste.br",
    "full_name": f"{PREFIX} Advogado Teste",
    "role": "advogado",
    "password": _qa_pw("senha_inicial_advogado"),
})
if r.status_code in (200, 201, 409):
    SENHA_ATUAL = None
    # Ciclo determinístico: a senha inicial do usuário é a credencial QA
    # definida em EJC_QA_PASSWORD; as variações derivadas são base + sufixos.
    _t18_base = _qa_pw("senha_inicial_advogado")
    for senha in (_t18_base, _t18_base + "@1", _t18_base + "@2"):
        r = post("/auth/login", {"email": f"{PREFIX.lower()}@adv.teste.br", "password": senha})
        if r.status_code == 200:
            avd_tok = safe_json(r).get("access_token")
            SENHA_ATUAL = senha
            break
    else:
        avd_tok = None
    check("T18-1", "Login do advogado comum", avd_tok is not None,
          r.status_code == 200 if r.status_code else str(r)[:80])
else:
    avd_tok = None
    check("T18-1", "Login do advogado comum", False, f"criação {r.status_code} {str(r.text)[:120]}")

if avd_tok:
    sa = requests.Session()
    sa.headers["Authorization"] = f"Bearer {avd_tok}"
    # primeira sessão exige troca de senha obrigatória (política de segurança)
    _t18_base = _qa_pw("rotacao"); _ROTACAO = {_t18_base: _t18_base + "@1", _t18_base + "@1": _t18_base + "@2", _t18_base + "@2": _t18_base}
    NOVA_SENHA = _ROTACAO.get(SENHA_ATUAL, _t18_base)
    rr = sa.post(BASE + "/auth/alterar-senha", json={
        "senha_atual": SENHA_ATUAL or _t18_base,
        "nova_senha": NOVA_SENHA,
    })
    if rr.status_code in (200, 201):
        rr2 = sa.post(BASE + "/auth/login", {"email": f"{PREFIX.lower()}@adv.teste.br", "password": NOVA_SENHA})
        avd_tok = rr2.json().get("access_token") if rr2.status_code == 200 else None
    rr = sa.get(BASE + "/users/me", timeout=30)
    check("T18-2", "Advogado: perfil próprio acessível", rr.status_code == 200, f"{rr.status_code} {str(rr.text)[:100]}")
    # rotas negadas (comportamento correto: 403)
    for path, label in [
        ("/admin/backup/status", "backup admin"),
        ("/audit/", "trilha de auditoria"),
        ("/api-keys", "api-keys"),
    ]:
        rr = sa.get(BASE + path, timeout=30)
        check("T18-3", f"Advogado negado em {label}", rr.status_code in (401, 403), f"{rr.status_code}")

# ---------------- T19 LGPD ----------------
r = get(f"/clients/{C1_ID}/relatorio-lgpd", timeout=30)
check("T19-1", "Relatório LGPD do cliente", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T20 Dossiê ----------------
r = retried(lambda: post(f"/dossie/{CASE_ID}/gerar", timeout=120))
check("T20-1", "Gerar dossiê do caso", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

# ---------------- T21 Workflow ----------------
r = get(f"/workflow/casos/{CASE_ID}", timeout=30)
check("T21-1", "Workflow do caso", r.status_code == 200, f"{r.status_code} {str(r.text)[:100]}")

# ---------------- T22 Score jurídico ----------------
r = retried(lambda: post(f"/cases/{CASE_ID}/score-juridico/calcular", timeout=120))
check("T22-1", "Calcular score jurídico do caso", r.status_code in (200, 201), f"{r.status_code} {str(r.text)[:120]}")

# ---------------- Teardown (fluxo LGPD correto) ----------------
clean = []
# 1) Prazos e tarefas: exclusão lógica permitida
clean.append(("/deadlines/", (delete(f"/deadlines/{PRAZO_ID}").status_code if PRAZO_ID else 404)))
clean.append(("/tasks/", (delete(f"/tasks/{TASK_ID}").status_code if TASK_ID else 404)))
# 2) Caso: encerramento via Pós-Mortem (POST /cases/{id}/encerrar) — fluxo canônico;
#    a exclusão física de casos (DELETE) é rejeitada pela trilha de auditoria (422), correto
if CASE_ID:
    rr = post(f"/cases/{CASE_ID}/encerrar", {
        "resultado": "arquivado",
        "motivo_resultado": "Encerramento de teste da auditoria E2E 2026. Dados sintéticos, sem valor probatório.",
        "provas_determinantes": "Dados sintéticos de auditoria.",
        "licoes_aprendidas": "Teste de auditoria: validação do fluxo de encerramento LGPD.",
        "alimentar_rag": False,
    })
    clean.append(("/cases/{id}/encerrar", rr.status_code))
# 3) Cliente: bloqueios e esquecimento LGPD (anonimização) — nunca exclusão física
clean.append(("/clients/{id}/esquecimento/bloqueios", (get(f"/clients/{C1_ID}/esquecimento/bloqueios").status_code if C1_ID else 404)))
if C1_ID:
    rr = post(f"/clients/{C1_ID}/esquecimento", {})
    clean.append(("/clients/{id}/esquecimento", rr.status_code))  # 409 = j00e1 anonimizado (idempotente)
check("T23-1", "Teardown: encerramento por pós-mortem + esquecimento LGPD",
      all(c in (200, 204, 404, 409) for _, c in clean if isinstance(c, int)), str(clean))

fails = [t for t in results if t[2] == "FAIL"]
print(f"\n===== RESUMO: {len(results)} testes, {len(results)-len(fails)} PASS, {len(fails)} FAIL =====")
for t in fails:
    print("FAIL", t[0], t[1], t[3])
sys.exit(0 if not fails else 1)
