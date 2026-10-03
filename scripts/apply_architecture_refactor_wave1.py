#!/usr/bin/env python3
"""Entrada compatível da onda histórica de refatoração.

Fonte congelada em archive/apply_architecture_refactor_wave1.py.gz (base 049fd6c).
A implementação atual vive em backend/app/core, routers e frontend/src/config.
O arquivo arquivado preserva os usos históricos, inclusive --check; este não
é um gerador da arquitetura corrente. --check mantém o contrato histórico e
pode apontar divergência legítima em árvores que evoluíram após a onda.
"""
from pathlib import Path as _ArchivePath
import gzip as _archive_gzip

_archive = _ArchivePath(__file__).resolve().parent / "archive" / "apply_architecture_refactor_wave1.py.gz"
# __file__ continua sendo o entrypoint: ROOT histórico permanece correto.
exec(compile(_archive_gzip.decompress(_archive.read_bytes()), str(_archive), "exec"), globals())
