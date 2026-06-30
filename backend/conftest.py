# Garante que o pacote `app` seja importável ao rodar pytest a partir de backend/
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_ENV", "development")
