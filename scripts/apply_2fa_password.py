#!/usr/bin/env python3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "backend/app/routers/auth.py"
t = p.read_text(encoding="utf-8")
a = t.index("    # Revogar TODAS as outras sessões")
b = t.index("\n\n# ─── Recuperação de senha (público)", a)
novo = '''    # Revogar TODAS as outras sessões após a troca.
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked == False)
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )

    exige_setup_2fa = _papel_exige_2fa(user.role.value) and not user.totp_enabled
    if exige_setup_2fa:
        access = create_access_token(
            user.id,
            user.role.value,
            two_factor_setup_required=True,
            expires_minutes=settings.TWO_FACTOR_SETUP_TOKEN_EXPIRE_MINUTES,
        )
        await criar_audit_log(
            db, user.id, user.role.value, "TROCA_SENHA", "users", user.id,
            detalhes="Senha alterada; sessão plena retida até ativação 2FA.",
            ip=obter_ip_real(request),
        )
        await db.commit()
        _clear_refresh_cookie(response)
        return {
            "detail": "Senha alterada. Agora configure o 2FA.",
            "access_token": access,
            "token_type": "bearer",
            "user_id": user.id,
            "full_name": user.full_name,
            "role": user.role.value,
            "must_change_password": False,
            "precisa_configurar_2fa": True,
        }

    access = create_access_token(user.id, user.role.value)
    refresh_tok, jti = create_refresh_token(user.id)
    db.add(RefreshToken(
        id=str(uuid4()), user_id=user.id, jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await criar_audit_log(
        db, user.id, user.role.value, "TROCA_SENHA", "users", user.id,
        ip=obter_ip_real(request),
    )
    await db.commit()
    _set_refresh_cookie(response, refresh_tok)
    return {
        "detail": "Senha alterada com sucesso.",
        "access_token": access,
        "refresh_token": refresh_tok,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "role": user.role.value,
        "must_change_password": False,
    }
'''
p.write_text(t[:a] + novo + t[b:], encoding="utf-8")
print("gate pós-senha aplicado")
