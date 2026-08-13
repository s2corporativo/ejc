"""Reescreve o proxy _settings_consolidacao em app/routers/ai.py para ser
resolvido via módulo app.core.config (honra monkeypatch de cfg.get_settings
usado pelos testes da migração). 12/08/2026."""
import importlib

p = "/home/ubuntu/ejc/backend/app/routers/ai.py"
s = open(p, encoding="utf-8").read()

antigo = '''class _SettingsProxyConslidacao:
    """Proxy: expõe os atributos de settings ao bloco consolidado,
    resolvendo get_settings() a cada acesso (mesma semântica do ia_extra
    original, que importava settings diretamente)."""

    def __getattr__(self, attr: str):
        return getattr(_get_settings_consolidacao(), attr)

_settings_consolidacao = _SettingsProxyConslidacao()'''

novo = '''class _SettingsProxyConslidacao:
    """Proxy: expõe os atributos de settings ao bloco consolidado.
    Resolve get_settings() via lookup de módulo a cada acesso, para que os
    testes possam aplicar monkeypatch em app.core.config.get_settings."""

    def __getattr__(self, attr: str):
        _cfg = importlib.import_module("app.core.config")
        return getattr(_cfg.get_settings(), attr)

_settings_consolidacao = _SettingsProxyConslidacao()'''

if antigo in s:
    s = s.replace(antigo, novo)
    open(p, "w", encoding="utf-8").write(s)
    print("proxy reescrito (module lookup)")
else:
    raise SystemExit("padrão do proxy não encontrado em ai.py")
