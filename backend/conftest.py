# conftest.py — garante ambiente de teste (dev: SECRET_KEY efêmera, sem .env).
# Estar na raiz do backend coloca `app` no sys.path (import mode prepend do pytest).
import os

os.environ.setdefault("APP_ENV", "development")
