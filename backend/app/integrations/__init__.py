# ── app/integrations/ ────────────────────────────────────────────────────────
# Clientes de integração com APIs/fontes públicas jurídicas e cadastrais.
# Complementam — não substituem — serviços internos com regra de negócio.
#
# Núcleo já existente:
#   • datajud_client.py          — DataJud/CNJ, consulta crua por nº de processo
#   • djen_comunica_client.py    — DJEN/Comunica, intimações por OAB/processo
#   • brasilapi_client.py        — BrasilAPI, CNPJ e CEP
#
# Onda #836:
#   • cnj_sgt_client.py          — CNJ SGT/TPU (classes, assuntos, movimentos)
#   • tcu_client.py              — TCU Dados Abertos, acórdãos
#   • ibge_localidades_client.py — IBGE Localidades/códigos oficiais
#   • ckan_public_client.py      — IBAMA, MJ/Consumidor.gov, CVM e TSE (allowlist)
#   • pgfn_open_data_client.py   — catálogo bulk da Dívida Ativa/PGFN
#   • querido_diario_client.py   — diários municipais (agregador secundário)
#   • ide_sisema_client.py       — IDE-Sisema/MG via OGC WFS
#   • inlabs_parser.py           — parser limitado de XML/ZIP do INLABS/DOU
#
# Segurança: nenhum cliente aceita host arbitrário; o gateway HTTP está em
# routers.py e exige autenticação/rate limit. INLABS não automatiza login nem
# armazena credenciais.
