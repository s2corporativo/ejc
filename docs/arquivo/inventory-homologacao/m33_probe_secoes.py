"""Probe: executa secao_previdenciario / secao_empresarial / secao_fontes_hitl isoladamente."""
import sys
sys.path.insert(0, "/home/ubuntu/ejc_repo/scripts/inventory")
import importlib.util
spec = importlib.util.spec_from_file_location("m33", "/home/ubuntu/ejc_repo/scripts/inventory/m33_verticais_tests.py")
m33 = importlib.util.module_from_spec(spec)
# Intercept main guard
import types
spec.loader.exec_module(m33)
print("secoes registradas:", hasattr(m33, "secao_previdenciario"),
      hasattr(m33, "secao_empresarial"), hasattr(m33, "secao_fontes_hitl"))
for nome in ("secao_previdenciario", "secao_empresarial", "secao_fontes_hitl"):
    print(f"\n== executando {nome} ==")
    try:
        getattr(m33, nome)()
        print(f"{nome}: OK sem excecao")
    except SystemExit as e:
        print(f"{nome}: SystemExit {e.code}")
    except Exception as e:  # noqa
        print(f"{nome}: EXCEPTION {type(e).__name__}: {e}")
print("\nPASS:", len(m33.PASS), "FAIL:", len(m33.FAIL))
