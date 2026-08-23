import time, json, requests


def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v


SENHA = _qa_pw('_probe_cases')
B = "http://127.0.0.1:8000"
S = requests.Session()
for email in ("ejc_qa_auth_socio@golocal.ejc", "ejc_qa_auth_advogado@golocal.ejc"):
    time.sleep(18)
    r = S.post(f"{B}/api/auth/login", json={"email": email, "password": SENHA}, timeout=30)
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{B}/api/auth/login", json={"email": email, "password": SENHA}, timeout=30)
    print(email, r.status_code)
    if r.status_code == 200:
        break
tok = r.json()["access_token"]
r = S.get(f"{B}/api/cases", params={"page": 1, "page_size": 5}, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
j = r.json()
print("keys:", list(j.keys()) if isinstance(j, dict) else f"list len={len(j)}")
itens = j if isinstance(j, list) else j.get("itens", j.get("cases", j.get("data", [])))
if itens:
    print(json.dumps(itens[0], ensure_ascii=False)[:1200])
