#!/usr/bin/env python3
"""Carrega o .env do repositório (dotenv) no ambiente e executa o comando dado.

Uso: python3 scripts/env_run.py <cmd> [args...]
Ex.: python3 scripts/env_run.py python3 -m pytest tests -q
"""
import os
import subprocess
import sys
from dotenv import load_dotenv

if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(repo_root, ".env"), override=False)
    sys.exit(subprocess.call(sys.argv[1:]))
