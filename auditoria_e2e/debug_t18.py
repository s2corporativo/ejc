import requests
BASE = "http://localhost:8000/api"
PREFIX = "TESTE_EJC_AUDITORIA_2026"
s = requests.Session()
s.headers["Content-Type"] = "application/json"
r = s.post(BASE + "/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
email = f"{PREFIX.lower()}@adv.teste.br"
r = s.post(BASE + "/users/", json={"email": email, "full_name": f"{PREFIX} Advogado Teste", "role": "advogado", "password": "SenhaForte@2026"})
print("create user:", r.status_code, r.text[:120])
for senha in ("SenhaForte@2026", "SenhaNova@2026!"):
    r = s.post(BASE + "/auth/login", json={"email": email, "password": senha})
    print("login", senha, r.status_code, r.text[:120])
    if r.status_code == 200:
        sa = requests.Session()
        sa.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        rr = sa.post(BASE + "/auth/alterar-senha", json={"senha_atual": "SenhaForte@2026", "nova_senha": "SenhaNova@2026!"})
        print("altera-senha:", rr.status_code, rr.text[:150])
        if rr.status_code in (200, 201):
            rr2 = sa.post(BASE + "/auth/login", json={"email": email, "password": "SenhaNova@2026!"})
            print("relogin:", rr2.status_code, rr2.text[:120])
        rr = sa.get(BASE + "/users/me")
        print("users/me:", rr.status_code, rr.text[:120])
