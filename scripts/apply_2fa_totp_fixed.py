#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "backend/app/routers/auth.py"
t = p.read_text(encoding="utf-8")
if "import io\n" not in t:
    t = t.replace("import logging\n", "import io\nimport logging\n", 1)
if "import qrcode\n" not in t:
    t = t.replace("import pyotp\n", "import pyotp\nimport qrcode\n", 1)

old = '    uri = totp.provisioning_uri(name=user.email, issuer_name="EJC — De Paula Teixeira")\n    return {"secret": secret, "uri": uri, "aviso": "Use /totp/verificar com o primeiro código para ativar."}\n'
new = '''    uri = totp.provisioning_uri(
        name=user.email, issuer_name="EJC — De Paula Teixeira"
    )
    qr_buffer = io.BytesIO()
    qrcode.make(uri).save(qr_buffer, format="PNG")
    qr_data_url = "data:image/png;base64," + base64.b64encode(
        qr_buffer.getvalue()
    ).decode("ascii")
    return {
        "secret": secret,
        "uri": uri,
        "qr_data_url": qr_data_url,
        "aviso": "Use /totp/verificar com o primeiro código para ativar.",
    }
'''
if t.count(old) != 1:
    raise RuntimeError("retorno setup não encontrado")
t = t.replace(old, new, 1)

old_sig = '''async def totp_verificar(
    req: TOTPVerificarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
'''
new_sig = '''async def totp_verificar(
    req: TOTPVerificarRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
'''
if t.count(old_sig) != 1:
    raise RuntimeError("assinatura verificar não encontrada")
t = t.replace(old_sig, new_sig, 1)

func = t.index("async def totp_verificar")
a = t.index("    _recifrar_totp_legado(user, secret, legado)", func)
b = t.index("\n\n@router.post(\"/totp/desativar\")", a)
novo = '''    _recifrar_totp_legado(user, secret, legado)
    user.totp_enabled = True
    await criar_audit_log(
        db, user.id, user.role.value, "TOTP_ATIVADO", "users", user.id,
        ip=obter_ip_real(request),
    )
    if payload.get("two_factor_setup_required"):
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        access = create_access_token(user.id, user.role.value)
        refresh_tok, jti = create_refresh_token(user.id)
        db.add(RefreshToken(
            id=str(uuid4()), user_id=user.id, jti=jti,
            expires_at=datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        ))
        user.last_login_at = datetime.now(timezone.utc)
        await criar_audit_log(
            db, user.id, user.role.value, "LOGIN_2FA_CONCLUIDO", "users", user.id,
            detalhes="TOTP ativado; sessão plena emitida.",
            ip=obter_ip_real(request),
        )
        await db.commit()
        _set_refresh_cookie(response, refresh_tok)
        return {
            "detail": "TOTP ativado com sucesso.",
            "access_token": access,
            "refresh_token": refresh_tok,
            "token_type": "bearer",
            "user_id": user.id,
            "full_name": user.full_name,
            "role": user.role.value,
        }
    await db.commit()
    return {"detail": "TOTP ativado com sucesso. Guarde o segredo em lugar seguro."}
'''
p.write_text(t[:a] + novo + t[b:], encoding="utf-8")
print("patch TOTP aplicado com âncora correta")
