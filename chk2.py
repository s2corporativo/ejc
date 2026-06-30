import subprocess, sys

checks = [
    # (arquivo no container, string que deve existir, descricao)
    ('/app/app/routers/auth.py', 'import pyotp', 'TOTP import em auth.py'),
    ('/app/app/models/user.py', 'totp_enabled', 'TOTP columns em user.py'),
    ('/app/app/services/pdf_service.py', 'DejaVu Sans', 'Font DejaVu em pdf_service.py'),
    ('/app/app/services/pdf_service.py', '@page', 'Numeracao pagina em pdf_service.py'),
    ('/app/app/routers/produtividade.py', 'roi-por-area', 'ROI endpoint em produtividade.py'),
    ('/app/app/services/scheduler.py', '_purgar_dados_lgpd', 'LGPD purge em scheduler.py'),
    ('/app/app/services/rentabilidade.py', 'ranking_por_area', 'ROI service em rentabilidade.py'),
    ('/app/app/routers/rag.py', 'ingerir-ai-log', 'RAG destilacao em rag.py'),
    ('/app/app/routers/sumulas.py', 'verificar-conflito', 'Conflito endpoint em sumulas.py'),
    ('/app/app/services/sumulas_ingestion.py', 'SUMULAS_SEED', 'Sumulas seed service'),
    ('/app/app/services/conflito_interesses.py', 'EOAB', 'Conflito service com base legal'),
    ('/app/app/main.py', 'sumulas_router', 'Sumulas router registrado em main.py'),
]

ok = 0
fail = 0
for path, search, desc in checks:
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
        if search in content:
            print(f'  OK  {desc}')
            ok += 1
        else:
            print(f'  FAIL {desc} — string nao encontrada: {search!r}')
            fail += 1
    except FileNotFoundError:
        print(f'  MISSING arquivo nao existe: {path}')
        fail += 1

print(f'\nTotal: {ok} OK / {fail} FAIL')