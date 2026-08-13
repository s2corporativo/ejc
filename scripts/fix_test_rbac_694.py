"""Migra os testes de RBAC do router morto jurimetria_extra para o módulo
consolidado (jurimetria.py) e retira teses_v4 (arquivado em _dead_code)
das listas de verificação. 12/08/2026."""
p = "/home/ubuntu/ejc/backend/tests/test_rbac_equipe_juridica_694.py"
s = open(p, encoding="utf-8").read()

# 1. seção jurimetria_extra → consolidate (mesmos _req_staff/_req_socio no prelude)
s = s.replace("def test_jurimetria_extra_req_staff_financeiro_403():\n"
              "    from app.routers.jurimetria_extra import _req_staff",
              "def test_jurimetria_consolidado_req_staff_financeiro_403():\n"
              "    from app.routers.jurimetria import _req_staff")
s = s.replace("def test_jurimetria_extra_req_staff_estagiario_passa():\n"
              "    from app.routers.jurimetria_extra import _req_staff",
              "def test_jurimetria_consolidado_req_staff_estagiario_passa():\n"
              "    from app.routers.jurimetria import _req_staff")

# 2. remover teses_v4 do _HELPERS_BOOL (router arquivado)
s = s.replace('    ("app.routers.teses_v4", "_is_staff"),\n', "")

# 3. remover teses_v4.py / jurimetria_extra.py dos "arquivos corrigidos"
# (não existem mais em app/routers; a trava do grandfather não precisa citá-los)
s = s.replace('        "advogado_estilo.py", "teses.py", "teses_v4.py",\n',
              '        "advogado_estilo.py", "teses.py",\n')
s = s.replace('        "precedentes_jurisprudencia.py", "jurimetria.py", "jurimetria_extra.py",\n',
              '        "precedentes_jurisprudencia.py", "jurimetria.py",\n')

open(p, "w", encoding="utf-8").write(s)
print("test_rbac_equipe_juridica_694.py migrado")
