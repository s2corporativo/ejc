"""Migra as referências restantes a app.routers.ia_extra em
tests/test_migracao_gateway_fase1b.py para o módulo consolidado
app.routers.ai (consolidação 12/08/2026)."""
p = "/home/ubuntu/ejc/backend/tests/test_migracao_gateway_fase1b.py"
s = open(p, encoding="utf-8").read()
s = s.replace("import app.routers.ia_extra as extra", "import app.routers.ai as extra")
# A verificação "get_groq não existe em ia_extra" continua válida para ai.py,
# pois ai.py também não exporta get_groq.
open(p, "w", encoding="utf-8").write(s)
print("ok")
