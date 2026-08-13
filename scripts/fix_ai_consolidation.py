"""Correções finais da consolidação ia_extra → ai.py (12/08/2026):

1. app/routers/ai.py: o bloco consolidado usa `_settings_consolidacao` mas o
   import foi declarado como `_get_settings_consolidacao` — criar o alias de
   settings (get_settings()) de forma consistente com o uso no bloco.
2. tests/test_migracao_gateway_fase1b.py: substituir chamadas
   `ia_extra.<fn>` restantes por `ia_extra_consolidado.<fn>`.
"""
import re

# ── 1. ai.py ──
p = "/home/ubuntu/ejc/backend/app/routers/ai.py"
s = open(p, encoding="utf-8").read()

# O bloco consolidado foi importado com:
#   from app.core.config import get_settings as _get_settings_consolidacao
# Precisamos expor `_settings_consolidacao` para o bloco consolidado
# (chamado com .GROQ_MODEL/.AI_ENABLED). Estratégia mínima: manter a função
# get_settings e acrescentar um alias de INSTÂNCIA obtido via proxy — como o
# código usa _settings_consolidacao.<ATTR> em tempo de execução, definimos um
# objeto proxy que chama get_settings() a cada acesso.
proxy = '''
class _SettingsProxyConslidacao:
    """Proxy: expõe os atributos de settings ao bloco consolidado,
    resolvendo get_settings() a cada acesso (mesma semântica do ia_extra
    original, que importava settings diretamente)."""

    def __getattr__(self, attr: str):
        return getattr(_get_settings_consolidacao(), attr)

_settings_consolidacao = _SettingsProxyConslidacao()
'''
if "_settings_consolidacao = _SettingsProxyConslidacao()" not in s:
    # inserir após o último import _get_settings_consolidacao (bloco consolidado)
    idx = s.rfind("from app.core.config import get_settings as _get_settings_consolidacao")
    linha_fim = s.find("\n", idx)
    s = s[:linha_fim] + "\n" + proxy + s[linha_fim:]
    open(p, "w", encoding="utf-8").write(s)
    print("ai.py: proxy _settings_consolidacao inserido")

# ── 2. test_migracao_gateway_fase1b.py ──
p = "/home/ubuntu/ejc/backend/tests/test_migracao_gateway_fase1b.py"
s = open(p, encoding="utf-8").read()
s = s.replace("ia_extra.resumir_texto", "ia_extra_consolidado.resumir_texto")
s = s.replace("ia_extra.ResumirIn", "ia_extra_consolidado.ResumirIn")
s = s.replace("ia_extra.gerar_minuta", "ia_extra_consolidado.gerar_minuta")
s = s.replace("ia_extra.MinutaIn", "ia_extra_consolidado.MinutaIn")
s = s.replace("ia_extra.pesquisar", "ia_extra_consolidado.pesquisar")
s = s.replace("ia_extra.PesquisaIn", "ia_extra_consolidado.PesquisaIn")
s = s.replace("ia_extra.sugestao_honorarios", "ia_extra_consolidado.sugestao_honorarios")
s = s.replace("ia_extra.HonorariosIn", "ia_extra_consolidado.HonorariosIn")
open(p, "w", encoding="utf-8").write(s)
print("test_migracao_gateway_fase1b.py: chamadas migradas")
