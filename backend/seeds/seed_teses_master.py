"""seeds/seed_teses_master.py — seed manual do lote inicial de teses candidatas.

Importa `backend/data/legal/theses_master.jsonl` para a tabela `teses`, todas
com `status_validacao="descoberta"` (ver app/services/teses_seed_importador.py
para o pipeline normalizar→validar→dedup→persistir e as invariantes de
governança). Idempotente — rodar de novo não duplica nem sobrescreve.

NÃO roda no boot (diferente de seeds/seed_all.py) — é um lote editorial único,
disparado manualmente pelo titular ou por quem estiver curando o Banco de
Teses. Uso (dentro do container, WORKDIR /app): python seeds/seed_teses_master.py
"""
from __future__ import annotations

import asyncio

from app.core.database import AsyncSessionLocal
from app.services.teses_seed_importador import importar_theses_master


async def main() -> None:
    async with AsyncSessionLocal() as db:
        resumo = await importar_theses_master(db)
    print(
        f"[seed_teses_master] lidos={resumo['lidos']} "
        f"importados={resumo['importados']} "
        f"ja_existentes={resumo['ja_existentes']} "
        f"duplicados_no_arquivo={resumo['duplicados_no_arquivo']}"
    )
    if resumo["codigos_criados"]:
        print(f"[seed_teses_master] códigos novos: {', '.join(resumo['codigos_criados'])}")


if __name__ == "__main__":
    asyncio.run(main())
