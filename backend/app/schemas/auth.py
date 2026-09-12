# ── app/schemas/auth.py ──────────────────────────────────────────────────────
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional

from app.core.ufs import UFS_BRASIL

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
    cpf: Optional[str] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    oab_number: Optional[str] = None
    cpf: Optional[str] = None
    is_active: Optional[bool] = None
    djen_oab_numero: Optional[str] = None   # captura de intimações
    djen_oab_uf: Optional[str] = None

    # A OAB da captura DJEN não é texto livre: o job das 06h30 consulta o CNJ
    # com exatamente o que estiver aqui. Número com lixo ou UF inexistente
    # significa monitorar ninguém (ou a inscrição de outro advogado) sem que
    # nada falhe visivelmente. String vazia é normalizada para NULL — o modo
    # explícito de DESLIGAR o monitoramento — e a coerência do par
    # número↔UF é checada no router, que enxerga o valor já gravado.
    @field_validator("djen_oab_numero")
    @classmethod
    def _validar_oab_numero(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        limpo = v.strip()
        if not limpo:
            return None
        # `str.isdigit()` e `\d` do `re` são Unicode-aware: "²²²²²²" e
        # "٢٥٢٥٩٩" passariam, e depois `oab_para_captura` (que faz
        # `re.sub(r"\D", "", ...)`) devolveria vazio — o campo ficaria não-nulo,
        # o job selecionaria o advogado e a captura resolveria
        # `oab_nao_configurada` em silêncio. Classe explícita [0-9] fecha isso.
        if not re.fullmatch(r"[0-9]{1,10}", limpo):
            raise ValueError(
                "Número da OAB deve ter de 1 a 10 dígitos (0-9), sem "
                "pontuação ou letras."
            )
        return limpo

    @field_validator("djen_oab_uf")
    @classmethod
    def _validar_oab_uf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        limpo = v.strip().upper()
        if not limpo:
            return None
        if limpo not in UFS_BRASIL:
            raise ValueError(
                "UF da OAB inválida — use a sigla de uma das 27 unidades "
                "federativas (ex.: MG)."
            )
        return limpo

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    oab_number: Optional[str] = None
    cpf_mascarado: Optional[str] = None
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
