#!/usr/bin/env python3
"""Diagnóstico de criação de cliente."""
import requests

BASE = "http://localhost:8000/api"
s = requests.Session()
s.headers.update({"Content-Type": "application/json"})
r = s.post(BASE + "/auth/login", json={
    "email": "admin@seu-dominio.com.br",
    "password": "TROCAR_POR_SENHA_FORTE_INICIAL",
})
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

r = s.post(BASE + "/clients/", json={
    "tipo": "PJ",
    "razao_social": "TESTE_EJC_AUDITORIA_2026 Cliente Beta Ltda",
    "nome_fantasia": "Beta",
    "cnpj": "11223344000155",
    "email": "beta@teste.br",
    "telefone": "31 99999-0002",
    "logradouro": "Rua Beta", "numero": "200", "bairro": "Centro",
    "cidade": "Betim", "estado": "MG", "cep": "32510000",
    "origem": "indicacao", "status": "lead",
})
print("STATUS:", r.status_code)
print(r.text[:800])
