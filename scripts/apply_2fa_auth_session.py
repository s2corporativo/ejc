#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "backend/app/routers/auth.py"
text = PATH.read_text(encoding="utf-8")


def between(start, end, replacement):
    global text
    a = text.index(start)
    b = text.index(end, a)
    text = text[:a] + replacement + text[b:]


if "import io\n" not in text:
    text = text.replace("import logging\n", "import io\nimport logging\n", 1)
if "import qrcode\n" not in text:
    text = text.replace("import pyotp\n", "import pyotp\nimport qrcode\n", 1)

between(
    "    # ── 4. Login OK",
    "\n\n# ─── Refresh (rotação de token)",
    '''    # ── 4. Login OK / gate obrigatório de 2FA ───────────────────
    limpar_falhas(chave_bf)
    limpar_falhas(chave_em)

    exige_setup_2fa = _papel_exige_2fa(user.role.value) and not user.totp_enabled
    if exige_setup_2fa:
        access = create_access_token(
            user.id,
            user.role.value,
            must_change_password=user.must_change_password,
            two_factor_setup_required=True,
            expires_minutes=settings.TWO_FACTOR_SETUP_TOKEN_EXPIRE_MINUTES,
        )
        await criar_audit_log(
            db,
            user.id,
            user.role.value,
            "LOGIN_2FA_SETUP_REQUIRED",
            "users",
            user.id,
            detalhes="Sessão plena negada até ativação TOTP.",
            ip=ip,
        )
        await db.commit()
        _clear_refresh_cookie(response)
        resp = {
            "access_token": access,
            "token_type": "bearer",
            "user_id": user.id,
            "full_name": user.full_name,
            "role": user.role.value,
            "precisa_configurar_2fa": True,
        }
        if user.must_change_password:
            resp["must_change_password"] = True
            resp["detail"] = "Troque a senha antes de configurar o 2FA."
        return resp

    access = create_access_token(
        user.id,
        user.role.value,
        must_change_password=user.must_change_password,
    )
    refresh_tok, jti = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            id=str(uuid4()),
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    user.last_login_at = datetime.now(timezone.utc)
    await criar_audit_log(
        db, user.id, user.role.value, "LOGIN", "users", user.id, ip=ip
    )
    ua = request.headers.get("user-agent", "")
    await verificar_novo_dispositivo(db, user, ip, ua)
    await db.commit()
    _set_refresh_cookie(response, refresh_tok)
    resp = {
        "access_token": access,
        "refresh_token": refresh_tok,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "role": user.role.value,
    }
    if user.must_change_password:
        resp["must_change_password"] = True
        resp["detail"] = "Troca de senha obrigatória antes de continuar."
    return resp
''',
)

needle = '''    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    # Propaga o estado de troca obrigatória: sem isto, um usuário com senha
'''
replacement = '''    if not user:
        raise HTTPException(status_code=401, detail="Usuário inativo")

    if _papel_exige_2fa(user.role.value) and not user.totp_enabled:
        agora = datetime.now(timezone.utc)
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked == False,
            )
            .values(revoked=True, revoked_at=agora)
        )
        await criar_audit_log(
            db,
            user.id,
            user.role.value,
            "REFRESH_2FA_SETUP_REQUIRED",
            "users",
            user.id,
            detalhes="Refresh revogado: papel exige 2FA sem TOTP ativo.",
            ip=obter_ip_real(request),
        )
        await db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Configure a autenticação de dois fatores para continuar.",
                "precisa_configurar_2fa": True,
            },
        )

    # Propaga o estado de troca obrigatória: sem isto, um usuário com senha
'''
if text.count(needle) != 1:
    raise RuntimeError(f"marcador refresh inválido: {text.count(needle)}")
text = text.replace(needle, replacement, 1)
PATH.write_text(text, encoding="utf-8")
print("auth login/refresh 2FA aplicado")
