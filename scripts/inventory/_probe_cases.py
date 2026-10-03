
if __package__:
    from . import _shared
else:  # Execução direta: python scripts/inventory/<script>.py
    import _shared

import time, json, requests


def _qa_pw(name: str) -> str:
    return _shared.qa_password(name)


SENHA = _qa_pw('_probe_cases')
B = _shared.LOCAL_API
S = requests.Session()
for email in (_shared.qa_email('socio'), _shared.qa_email('advogado')):
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
