"""Primitivas dos diagnósticos históricos de QA.

Sessões, caches, contadores, callbacks e credenciais são parâmetros explícitos.
Não abre banco, não autentica e não lê a senha no import. As variantes mantêm
seus contratos históricos de retry, falha, saída e atualização de sessão.
"""

from __future__ import annotations

LOCAL_API = "http://127.0.0.1:8000"


def qa_email(role):
    return f"ejc_qa_auth_{role}@golocal.ejc"


def qa_emails(roles):
    return {role: qa_email(role) for role in roles}


def qa_credentials(password, roles):
    return {role: (qa_email(role), password) for role in roles}


def qa_headers(*, content_type=False):
    headers = {"X-Forwarded-For": "127.0.0.1"}
    if content_type:
        headers = {"Content-Type": "application/json", **headers}
    return headers


def qa_password(name: str) -> str:
    import os

    v = os.environ.get("EJC_QA_PASSWORD")
    if not v:
        raise RuntimeError(
            f"Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}"
        )
    return v


def valid_cnj(*, random):
    n = f"{random.randint(1000000, 9999999)}"
    ano = "2026"
    j, tr, oo = ("8", "01", "0001")
    corpo = int(f"{n}{ano}{j}{tr}{oo}00")
    dv = (1 - corpo) % 97
    return f"{n}-{dv:02d}.{ano}.{j}.{tr}.{oo}"


def valid_cpf(*, random) -> str:
    n = [random.randint(0, 9) for _ in range(9)]
    s = sum(((10 - i) * d for i, d in enumerate(n)))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    s = sum(((11 - i) * d for i, d in enumerate(n)))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    d = "".join((str(x) for x in n))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def check_ok(nome, ok, detalhe="", *, OK, TOTAL):
    TOTAL += 1
    OK += int(ok)
    print(f"{('PASS' if ok else 'FAIL')} {nome}" + (f" — {detalhe}" if not ok else ""))
    return (OK, TOTAL)


def cached_auth_headers(email, *, BASE, PWD, S, _TOKENS, time):
    if email in _TOKENS:
        return _TOKENS[email]
    time.sleep(18)
    for _ in range(6):
        r = S.post(
            f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=10
        )
        if r.status_code == 200:
            _TOKENS[email] = {"Authorization": f"Bearer {r.json()['access_token']}"}
            return _TOKENS[email]
        time.sleep(45)
    raise SystemExit(f"login falhou para {email}")


def check_totals(nome, ok, motivo="", *, ok_total, total):
    total += 1
    ok = bool(ok)
    ok_total += ok
    print("PASS" if ok else "FAIL", f"{nome} — {motivo or ''}")
    return (ok_total, total, ok)


def check_failures(desc, ok, extra="", *, FALHAS, TOTAL):
    TOTAL += 1
    if ok:
        print(f"[PASS] {desc}")
    else:
        FALHAS += 1
        print(f"[FAIL] {desc} — {extra}")
    return (FALHAS, TOTAL)


def cached_token(email, *, BASE, SENHA, TOKENS, requests, time):
    if email in TOKENS:
        return TOKENS[email]
    for tent in range(4):
        r = requests.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": SENHA},
            headers={"X-Forwarded-For": "127.0.0.1"},
            timeout=15,
        )
        if r.status_code == 200:
            TOKENS[email] = r.json()["access_token"]
            return TOKENS[email]
        if r.status_code == 429:
            time.sleep(18 * (tent + 1))
        else:
            raise SystemExit(f"login {email}: {r.status_code} {r.text[:120]}")
    raise SystemExit(f"login {email}: rate limit persistente")


def role_headers(role, *, EMAILS, tok):
    return {
        "Authorization": f"Bearer {tok(EMAILS[role])}",
        "X-Forwarded-For": "127.0.0.1",
    }


def login_rag(email: str, *, BASE, S, SENHA, TOKENS, time) -> str:
    if email in TOKENS:
        return TOKENS[email]
    for _ in range(2):
        r = S.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": SENHA},
            headers={"X-Forwarded-For": "127.0.0.1"},
            timeout=15,
        )
        if r.status_code == 429:
            time.sleep(45)
            continue
        r.raise_for_status()
        TOKENS[email] = r.json()["access_token"]
        return TOKENS[email]
    raise SystemExit("login falhou (rate limit persistente)")


def email_headers(email: str, *, login) -> dict:
    return {"Authorization": f"Bearer {login(email)}", "X-Forwarded-For": "127.0.0.1"}


def check_pass_fail(
    nome: str, cond: bool, extra: str = "", *, FAIL, PASS
) -> tuple[int, int]:
    if cond:
        PASS += 1
        print(f"[PASS] {nome}")
    else:
        FAIL += 1
        print(f"[FAIL] {nome} — {extra}")
    return (FAIL, PASS)


def record_pass(msg, *, PASS):
    PASS.append(msg)
    print(f"[PASS] {msg}")


def record_fail(msg, *, FAIL):
    FAIL.append(msg)
    print(f"[FAIL] {msg}")


def record_unavailable(msg, *, NA):
    NA.append(msg)
    print(f"[N/A-PROVADO] {msg}")


def authed_credentials(role, *, API, CRED, S, _TOKENS, _fail, sys, time):
    if role in _TOKENS:
        return _TOKENS[role]
    email, senha = CRED[role]
    time.sleep(16)
    r = S.post(
        f"{API}/api/auth/login", json={"email": email, "password": senha}, timeout=30
    )
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(
            f"{API}/api/auth/login",
            json={"email": email, "password": senha},
            timeout=30,
        )
    if r.status_code != 200:
        _fail(f"login {role}: HTTP {r.status_code}")
        sys.exit(1)
    tok = r.json()["access_token"]
    S.headers["Authorization"] = f"Bearer {tok}"
    _TOKENS[role] = tok
    return tok


def qa_client_id(*, API, S, _CLIENTE_ID, _fail, authed) -> str | None:
    if _CLIENTE_ID[0]:
        return _CLIENTE_ID[0]
    authed("socio")
    r = S.get(f"{API}/api/clients", timeout=30)
    d = r.json() if r.status_code == 200 else {}
    items = (
        d
        if isinstance(d, list)
        else d.get("data") or d.get("clientes") or d.get("items") or []
    )
    for it in items:
        cid = it.get("id")
        nome = it.get("nome") or it.get("razao_social") or ""
        if nome.startswith("EJC_QA"):
            _CLIENTE_ID[0] = cid
            return cid
    _fail("nenhum cliente EJC_QA encontrado p/ criar casos")
    return None


def record_detailed_pass(t, d="", *, PASS):
    PASS.append((t, d))
    print(f"  [PASS] {t} — {d}"[:200])


def record_detailed_fail(t, d="", *, FAIL):
    FAIL.append((t, d))
    print(f"  [FAIL] {t} — {d}"[:200])


def record_detailed_unavailable(t, d="", *, NA):
    NA.append((t, d))
    print(f"  [N/A]  {t} — {d}"[:200])


def authed_role(nome, *, API, S, SENHA, _TOKENS, time):
    if nome in _TOKENS:
        S.headers["Authorization"] = "Bearer " + _TOKENS[nome]
        return
    time.sleep(18)
    r = S.post(
        f"{API}/api/auth/login",
        json={
            "email": qa_email(nome if nome != "cliente_externo" else "cliente"),
            "password": SENHA,
        },
        timeout=20,
    )
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(
            f"{API}/api/auth/login",
            json={
                "email": qa_email(nome if nome != "cliente_externo" else "cliente"),
                "password": SENHA,
            },
            timeout=20,
        )
    assert r.status_code == 200, f"login {nome} falhou: {r.status_code} {r.text[:150]}"
    tk = r.json().get("access_token") or r.json().get("token") or r.json().get("access")
    assert tk, f"login {nome} sem token: {r.text[:200]}"
    _TOKENS[nome] = tk
    S.headers["Authorization"] = "Bearer " + tk


def get_with_retry(url, *, S, time, **kw):
    for _ in range(3):
        r = S.get(url, timeout=20, **kw)
        if r.status_code != 429:
            return r
        time.sleep(12)
    return r


def query_local(sql, *, runner, environ):
    result = runner(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        env={**environ, "PGPASSWORD": "ejc"},
    )
    return result.stdout.strip()


def login_headers(email, *, BASE, HEADERS, SENHA, TOKENS, requests, time):
    if email not in TOKENS:
        time.sleep(18)
        r = requests.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": SENHA},
            headers=HEADERS,
            timeout=15,
        )
        if r.status_code == 429:
            time.sleep(45)
            r = requests.post(
                f"{BASE}/api/auth/login",
                json={"email": email, "password": SENHA},
                headers=HEADERS,
                timeout=15,
            )
        TOKENS[email] = r.json()["access_token"]
    return {**HEADERS, "Authorization": f"Bearer {TOKENS[email]}"}
