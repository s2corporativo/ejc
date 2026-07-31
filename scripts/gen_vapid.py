#!/usr/bin/env python3
"""Gera par de chaves VAPID para Web Push — rodar UMA vez no deploy.
Cole as saídas no .env (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY)."""
from py_vapid import Vapid01
from cryptography.hazmat.primitives import serialization
import base64

v = Vapid01()
v.generate_keys()
priv = v.private_key.private_bytes(
    serialization.Encoding.DER,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
pub = v.public_key.public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
print("VAPID_PUBLIC_KEY=" + b64(pub))
print("VAPID_PRIVATE_KEY=" + b64(priv))
print("PUSH_ENABLED=true")
