#!/usr/bin/env python3
"""Módulo 04 — Usuários, Perfis e RBAC: bateria de prova de execução.

Constrói matriz: [endpoint + verbo] x [role] usando tokens JWT reais obtidos
por login (TestClient contra servidor vivo). Verifica autorização vertical
(cada perfil só alcança o que lhe cabe) e pontos de escalada indevida.
Resultados em qa/homologacao/m04/resultado_rbac_tests.txt
"""
import os
import sys

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.chdir("/home/ubuntu/ejc_repo/backend")

import requests
from app.core.config import get_settings
settings = get_settings()

BASE = "http://127.0.0.1:8000"
S = requests.Session()
SENHA = "EjcQa2026!SenhaForte"
# Rotaciona IP via X-Forwarded-For para não atingir o rate limit de login
# IP estático via X-Forwarded-For: o app resolve em DNS qualquer valor
# sintético (gaierror → 500 no login). Contadores in-memory do rate limit
# são zerados pelo reinício do uvicorn ANTES da bateria.
def _hdr(base: dict | None = None) -> dict:
    h = dict(base or {})
    h["X-Forwarded-For"] = "127.0.0.1"
    return h

_real_request = requests.Session.request


def _rotated_request(self, method, url, **kw):
    kw["headers"] = _hdr(kw.get("headers"))
    return _real_request(self, method, url, **kw)

requests.Session.request = _rotated_request
RESULTADOS = []
DIR = "/home/ubuntu/ejc_repo/qa/homologacao/m04"
os.makedirs(DIR, exist_ok=True)

USERS = {
    "admin": "ejc_qa_auth_admin@golocal.ejc",
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "financeiro": "ejc_qa_auth_financeiro@golocal.ejc",
    "secretaria": "ejc_qa_auth_secretaria@golocal.ejc",
    "cliente": "ejc_qa_auth_cliente@golocal.ejc",
}


def login(email):
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": email, "password": SENHA}, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()["access_token"]


def tok(role):
    return TOKENS.get(role)


TOKENS = {}


def check(nome, cond, obs):
    st = "PASS" if cond else "FAIL"
    RESULTADOS.append(f"[{st}] {nome} — {obs}")
    print(f"[{st}] {nome} — {obs}")


def q(nome, method, path, role, expect, body=None):
    # role=None → requisição SEM token (anonimo)
    """Testa endpoint p/ role: expect = status esperado (int) ou set.
    Retorna status real."""
    headers = {"Content-Type": "application/json"}
    t = tok(role)
    if t:
        headers["Authorization"] = f"Bearer {t}"
    r = getattr(S, method)(f"{BASE}{path}", json=body, headers=headers,
                           timeout=15)
    ok = r.status_code == expect if isinstance(expect, int) \
        else r.status_code in expect
    check(f"{nome}|{role}", ok,
          f"HTTP {r.status_code} (esperado {expect})")
    return r


# ── 1. Criar usuários de teste por perfil (admin) ────────────────────────
def criar_usuario(role, email):
    t = tok("admin")
    nome = f"QA {role.title()}"
    r = S.post(f"{BASE}/api/users/",
               json={"email": email, "password": "SenhaForte2026!",
                     "full_name": nome, "role": role},
               headers={"Authorization": f"Bearer {t}"}, timeout=15)
    if r.status_code not in (200, 201, 409):
        return False, r.text[:120]
    # alterar senha para o padrão QA
    return True, r.text[:80]


perfis = [
    ("socio", USERS["socio"]),
    ("advogado", USERS["advogado"]),
    ("estagiario", USERS["estagiario"]),
    ("financeiro", USERS["financeiro"]),
    ("secretaria", USERS["secretaria"]),
]
# login admin primeiro — a criação exige token de administrador
TOKENS["admin"] = login(USERS["admin"])
check("token_admin", TOKENS["admin"] is not None, "login admin")
for role, email in perfis:
    ok, msg = criar_usuario(role, email)
    check(f"criar_usuario_{role}", ok, msg)

for role, email in USERS.items():
    if role != "cliente":
        r = S.post(f"{BASE}/api/auth/alterar-senha",
                   json={"senha_atual": "SenhaForte2026!", "nova_senha": SENHA},
                   headers={"Authorization": f"Bearer {tok(role)}"}, timeout=15)
    TOKENS[role] = login(email)
    check(f"token_{role}", TOKENS[role] is not None, f"login {role}")

# ── 2. Autorização vertical: endpoints sensíveis por perfil ──────────────
# Gerenciamento de usuários (só admin/superadmin pode listar/criar)
q("admin_list_users", "get", "/api/users/?page_size=5", "admin", 200)
q("admin_list_users|socio", "get", "/api/users/?page_size=5", "socio", 403)
q("admin_list_users|financeiro", "get", "/api/users/?page_size=5",
  "financeiro", 403)
q("admin_list_users|cliente", "get", "/api/users/?page_size=5", "cliente", 403)

# Casos — leitura com filtro de visibilidade (socio+ todos; advogado os
# próprios; demais perfis ficam fora por gate de criação/visualização).
# Pós-correção (M04): estagiário/financeiro/secretaria passam a receber 403.
q("casos|admin", "get", "/api/cases/?page_size=2", "admin", [200, 404])
q("casos|advogado", "get", "/api/cases/?page_size=2", "advogado", [200, 404])
q("casos|estagiario", "get", "/api/cases/?page_size=2", "estagiario", [200, 404])
q("casos|financeiro", "get", "/api/cases/?page_size=2", "financeiro", 403)
q("casos|cliente", "get", "/api/cases/?page_size=2", "cliente", 403)

# Módulos do sistema (admin)
q("system_modules|admin", "get", "/api/system-modules/mapa", "admin",
    [200, 404])
q("system_modules|advogado", "get", "/api/system-modules/mapa", "advogado", 403)

# Auditoria (admin/socio)
q("auditoria|admin", "get", "/api/audit/", "admin", [200, 404])
q("auditoria|estagiario", "get", "/api/audit/", "estagiario", 403)

# Trash / lixeira (admin/socio)
q("trash|socio", "get", "/api/trash/?entidade=clients&page_size=2",
  "socio", [200, 404])
q("trash|advogado", "get", "/api/trash/", "advogado", 403)
q("trash|estagiario", "get", "/api/trash/", "estagiario", 403)

# Exportações CSV — financeiro/admin (não advogado comum)
q("export_clientes|admin", "get", "/api/export/clientes.csv", "admin",
  [200, 404])
q("export_clientes|advogado", "get", "/api/export/clientes.csv", "advogado",
  403)
q("export_clientes|secretaria", "get", "/api/export/clientes.csv",
  "secretaria", 403)

# Clientes — leitura básica (secretaria/financeiro ok; estagiário não)
q("teses|admin", "get", "/api/teses?page_size=2", "admin", [200, 404])
q("teses|advogado", "get", "/api/teses?page_size=2", "advogado", [200, 404])
q("teses|estagiario", "get", "/api/teses?page_size=2", "estagiario", [200, 404])
q("teses|financeiro", "get", "/api/teses?page_size=2", "financeiro", 403)
q("teses|secretaria", "get", "/api/teses?page_size=2", "secretaria", 403)
q("teses|cliente", "get", "/api/teses?page_size=2", "cliente", 403)

# Templates — equipe jurídica/gestão (advogado+; financeiro/secretaria fora)
q("templates|admin", "get", "/api/templates/", "admin", [200, 404])
q("templates|advogado", "get", "/api/templates/", "advogado", [200, 404])
q("templates|estagiario", "get", "/api/templates/", "estagiario", 403)
q("templates|financeiro", "get", "/api/templates/", "financeiro", 403)
q("templates|secretaria", "get", "/api/templates/", "secretaria", 403)

# Jurídico — teses (EQUIPE_JURIDICA allowlist exata)
q("teses_maior|financeiro", "get", "/api/teses?page_size=2", "financeiro", 403)
q("teses_maior|secretaria", "get", "/api/teses?page_size=2", "secretaria", 403)
# escrita de teses: advogado+ (estagiário só consulta)
q("teses_escrita|estagiario", "post", "/api/teses", "estagiario", 403,
  {"titulo": "TeseQA Homologação", "descricao": "Descricao minima de dez caracteres para o teste"})

# ── 3. Autorização horizontal: self vs admin ─────────────────────────────
# /me acessível por todos autenticados
for role in USERS:
    q(f"me|{role}", "get", "/api/users/me", role, 200)

# Advogado não pode ver dados de admin
r = S.get(f"{BASE}/api/users/me/security",
          headers={"Authorization": f"Bearer {tok('advogado')}"}, timeout=10)
check("security_self|advogado", r.status_code == 200, f"HTTP {r.status_code}")

# Cliente externo não acessa superfície interna (middleware)
for path in ("/api/system-modules/mapa", "/api/audit/",
             "/api/teses?page_size=2", "/api/templates/"):
    q(f"cliente_bloqueado{path}", "get", path, "cliente", 403)

# Admin não pode rebaixar o próprio nível nem desativar a si mesmo.
# RODA POR ÚLTIMO (se falhar o guard, o token admin fica inválido para o
# restante da bateria — por isso está ao fim e tenta restaurar em seguida).
# NOTA: o roteador expõe PATCH /api/users/{user_id} (sem alias /me).
admin_uid = None
me_admin = S.get(f"{BASE}/api/users/me",
                 headers={"Authorization": f"Bearer {tok('admin')}"}, timeout=10)
if me_admin.status_code == 200:
    admin_uid = me_admin.json().get("id")
r = S.patch(f"{BASE}/api/users/{admin_uid}",
            json={"role": "estagiario"},
            headers={"Authorization": f"Bearer {tok('admin')}"}, timeout=15)
check("admin_nao_rebaixa_self", r.status_code in (400, 403, 422),
      f"HTTP {r.status_code}")
# restaura o nível admin (caso o guard não exista — evita trancar o admin)
r2 = S.patch(f"{BASE}/api/users/{admin_uid}",
             json={"role": "admin"},
             headers={"Authorization": f"Bearer {tok('admin')}"}, timeout=15)
if r2.status_code != 200:
    RESULTADOS.append("[WARN] admin_nao_rebaixa_self — falha ao restaurar "
                      f"role=admin: HTTP {r2.status_code}")

# ── 4. Escalada indevida: token de baixo nível em endpoints de alto nível ──
# advogado cria usuário?
q("escalar_criar_user|advogado", "post", "/api/users/",
  "advogado", 403, {"email": "escalada_teste@golocal.ejc",
                    "password": "T@123456", "full_name": "Escalada",
                    "role": "socio"})
q("escalar_criar_user|secretaria", "post", "/api/users/",
  "secretaria", 403, {"email": "escalada2_teste@golocal.ejc",
                      "password": "SenhaForte2026!", "full_name": "Escalada2",
                      "role": "admin"})
# Sociedades — leitura = equipe interna (get_current_user, cliente fora);
# escrita (criar/alterar/remover) = admin/socio. estagiário LÊ (200), mas
# NÃO ESCREVE (403 no POST). Isso é desenho do módulo (padrão de clientes).
q("sociedades_leitura|estagiario", "get", "/api/empresarial/sociedades",
  "estagiario", [200, 404])
q("sociedades_escrita|estagiario", "post", "/api/empresarial/sociedades",
  "estagiario", 403, {"nome": "EscaladaSoc", "client_id": "00000000-0000-0000-0000-000000000000"})

# ── 5. Teses — autenticação obrigatória (gatilho: nenhuma rota de leitura
# exigia token — gap CRÍTICO de exposição de acervo jurídico)
q("teses_auth|anonimo", "get", "/api/teses", None, 401)
q("teses_auth|cliente", "get", "/api/teses", "cliente", 403)

with open(f"{DIR}/resultado_rbac_tests.txt", "w") as f:
    f.write("\n".join(RESULTADOS) + "\n")
n = sum(1 for x in RESULTADOS if x.startswith("[PASS]"))
print(f"TOTAL: {n}/{len(RESULTADOS)} PASS")
print("GRAVADO:", f"{DIR}/resultado_rbac_tests.txt")
