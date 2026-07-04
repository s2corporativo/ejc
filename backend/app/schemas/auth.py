# ── app/schemas/auth.py ──────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    role: str

class RefreshRequest(BaseModel):
    refresh_token: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "advogado"
    phone: Optional[str] = None
    oab_number: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    oab_number: Optional[str] = None
    is_active: Optional[bool] = None
    djen_oab_numero: Optional[str] = None   # captura de intimações
    djen_oab_uf: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    oab_number: Optional[str] = None
    # Path da API que serve a foto de perfil (ex.: /users/{id}/avatar).
    # O frontend monta a URL final com o baseURL do axios (/api) + este path.
    avatar_url: Optional[str] = None
    is_active: bool
    djen_oab_numero: Optional[str] = None
    djen_oab_uf: Optional[str] = None
    class Config:
        from_attributes = True

class PasswordChange(BaseModel):
    senha_atual: str
    senha_nova: str
