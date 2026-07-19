# ── app/integrations/ ────────────────────────────────────────────────────────
# Clientes de integração com APIs públicas jurídicas/cadastrais expostos sob
# /api/integracoes/* (routers.py). Complementam — não substituem — os serviços
# internos já existentes que usam as mesmas fontes com regras de negócio
# próprias (services/datajud_service.py, services/djen_service.py,
# services/feriados_service.py, routers/utils.py):
#
#   • datajud_client.py       — DataJud/CNJ, consulta crua por nº de processo
#   • djen_comunica_client.py — DJEN/Comunica, intimações por OAB/processo
#   • brasilapi_client.py     — BrasilAPI, CNPJ e CEP
#   • conecta_gov_client.py   — Conecta gov.br (SCAFFOLD, inativo até
#                               credenciamento institucional — router NÃO
#                               registrado em main.py)
