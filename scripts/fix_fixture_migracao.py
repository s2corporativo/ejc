"""Substitui o monkeypatch do fixture ia_extra_consolidado (o módulo ai.py
consolidado não expõe `settings`; o settings é lido por get_settings() em
cada endpoint). 12/08/2026."""
p = "/home/ubuntu/ejc/backend/tests/test_migracao_gateway_fase1b.py"
s = open(p, encoding="utf-8").read()
linhas = s.splitlines(True)
for i, linha in enumerate(linhas):
    if linha.strip() == "def ia_extra_consolidado(monkeypatch):":
        # substitui as 4 linhas seguintes
        j = i + 1
        novo = [
            "    import app.routers.ai as mod\n",
            "    import app.core.config as cfg\n",
            "    _st = type(\"Settings\", (), {\"AI_ENABLED\": True, \"GROQ_MODEL\": \"\"})()\n",
            "    monkeypatch.setattr(cfg, \"get_settings\", lambda: _st)\n",
            "    monkeypatch.setattr(mod, \"buscar_contexto_rag\", _rag_vazio)\n",
            "    return mod\n",
        ]
        # encontrar o fim do fixture (linha "return mod")
        k = j
        while k < len(linhas) and not linhas[k].strip() == "return mod":
            k += 1
        linhas[j:k + 1] = novo
        break
else:
    raise SystemExit("fixture não encontrada")
open(p, "w", encoding="utf-8").write("".join(linhas))
print("fixture corrigida")
