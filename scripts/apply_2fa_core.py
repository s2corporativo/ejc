#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path, old, new):
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"marcador inválido em {path}: {text.count(old)}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


patch(
    "backend/app/core/config.py",
    '    REQUIRE_2FA_ROLES: str = ""\n',
    '    REQUIRE_2FA_ROLES: str = "superadmin,admin,socio"\n'
    '    TWO_FACTOR_SETUP_TOKEN_EXPIRE_MINUTES: int = 15\n',
)

patch(
    "backend/app/core/security.py",
    '''def create_access_token(user_id: str, role: str,
                        must_change_password: bool = False) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.ACCESS_TOKEN_EXPIRE_HOURS
    )
    payload = {
        "sub": user_id,
        **({"pwd_change_required": True} if must_change_password else {}),
        "role": role,
''',
    '''def create_access_token(
    user_id: str,
    role: str,
    must_change_password: bool = False,
    two_factor_setup_required: bool = False,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        timedelta(minutes=expires_minutes)
        if expires_minutes is not None
        else timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    )
    payload = {
        "sub": user_id,
        **({"pwd_change_required": True} if must_change_password else {}),
        **({"two_factor_setup_required": True} if two_factor_setup_required else {}),
        "role": role,
''',
)

patch(
    "backend/app/core/auth_middleware.py",
    '''        if request.state.role == "cliente_externo":
''',
    '''        if payload.get("two_factor_setup_required") and not payload.get(
            "pwd_change_required"
        ):
            liberados_2fa = (
                "/api/auth/totp/setup",
                "/api/auth/totp/verificar",
                "/api/auth/logout",
            )
            if not any(
                _path_casa_prefixo_publico(path, prefixo)
                for prefixo in liberados_2fa
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Configure a autenticação de dois fatores para continuar.",
                        "precisa_configurar_2fa": True,
                    },
                )

        if request.state.role == "cliente_externo":
''',
)

print("core 2FA aplicado")
