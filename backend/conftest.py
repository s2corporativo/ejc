# conftest.py — garante ambiente de teste (dev: SECRET_KEY efêmera, sem .env).
# Estar na raiz do backend coloca `app` no sys.path (import mode prepend do pytest).
#
# Blindagem contra backend/.env local: pydantic-settings LÊ o .env se ele
# existir, e a suíte assume os defaults do código (ex.: os testes de
# test_feriados_brasilapi.py assumem FERIADOS_BRASILAPI_ENABLED=true, o
# default de Settings). Como variável de ambiente REAL tem precedência sobre
# o .env no pydantic-settings, fixamos aqui (via setdefault — quem exporta
# explicitamente no shell/CI continua mandando) as envs críticas cujos
# valores num .env de dev contaminariam os testes.
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FERIADOS_BRASILAPI_ENABLED", "true")
