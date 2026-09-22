#!/usr/bin/env python3
"""Backfill explícito de quitações legadas para ``fee_payments``.

Modo padrão é somente leitura. ``--apply`` grava apenas fees que estão pagos,
com data/valor, e ainda não possuem qualquer lançamento no subledger. O script
não altera ``fees.status`` nem apaga dados: a desativação da compatibilidade só
ocorre depois da conciliação independente.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text


QUERY = text("""
SELECT f.id, f.valor, f.data_pagamento
FROM fees f
WHERE f.deleted_at IS NULL
  AND CAST(f.status AS text) = 'pago'
  AND f.data_pagamento IS NOT NULL
  AND f.valor IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM fee_payments fp WHERE fp.fee_id = f.id)
ORDER BY f.id
""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="grava o backfill; sem isso é dry-run")
    args = parser.parse_args()
    url = os.getenv("DATABASE_URL") or os.getenv("SCHEMA_CHECK_DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL ou SCHEMA_CHECK_DATABASE_URL é obrigatório")
    engine = create_engine(url.replace("postgresql+asyncpg", "postgresql+psycopg"))
    with engine.begin() as db:
        rows = list(db.execute(QUERY).mappings())
        print(f"candidatos={len(rows)} modo={'apply' if args.apply else 'dry-run'}")
        if not args.apply:
            return 0
        for row in rows:
            db.execute(
                text("""
                    INSERT INTO fee_payments
                        (id, fee_id, valor, data_pagamento, forma, created_at)
                    VALUES (:id, :fee_id, :valor, :data_pagamento, 'legado', NOW())
                    ON CONFLICT DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "fee_id": row["id"],
                    "valor": row["valor"],
                    "data_pagamento": row["data_pagamento"],
                },
            )
        print(f"inseridos={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
