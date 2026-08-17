#!/usr/bin/env python3
"""Resume o output de `alembic check` em categorias acionáveis."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/alembic_check.txt"
t = open(path).read()

print("== remove_column (coluna existe no BANCO mas NÃO no ORM) ==")
for m in re.finditer(r"remove_column', None, '(\w+)', Column\('(\w+)'\w*\)", t):
    print(f"  tabela={m.group(1)} coluna={m.group(2)}")

print("== add_column (coluna existe no ORM mas NÃO no BANCO) ==")
for m in re.finditer(r"add_column', None, '(\w+)', Column\('(\w+)'", t):
    print(f"  tabela={m.group(1)} coluna={m.group(2)}")

print("== modify_type ==")
for m in re.finditer(r"modify_type', None, '(\w+)', '(\w+)'.{0,40}", t):
    print(f"  {m.group(0)[:130]}")

print("== remove_constraint ==")
for m in re.finditer(r"remove_constraint', [^)]{0,100}", t):
    print(f"  {m.group(0)[:130]}")

print("== add_constraint ==")
for m in re.finditer(r"add_constraint', [^)]{0,100}", t):
    print(f"  {m.group(0)[:130]}")

# index renames: remove ix_X + add ix_Y for same table/columns = apenas rename
print("== índices (remove->add) — candidatos a rename ==")
rem = re.findall(r"remove_index', Index\('(\w+)', Column\('(\w+)'(?:, NullType\(\))?[^)]*\), table=<(\w+)>", t)
add = re.findall(r"add_index', Index\('(\w+)', Column\('(\w+)'\w*\), table=<(\w+)>", t)
adds = {(tbl, col): idx for idx, col, tbl in add}
for idx, col, tbl in rem:
    novo = adds.get((tbl, col))
    if novo and novo != idx:
        print(f"  rename: {idx} -> {novo} (tabela {tbl}, coluna {col})")
    elif not novo:
        print(f"  remove SEM add: {idx} (tabela {tbl})")
print("== add_index sem remove correspondente ==")
rems = {(tbl, col): idx for idx, col, tbl in rem}
for idx, col, tbl in add:
    if (tbl, col) not in rems or rems[(tbl, col)] == idx:
        print(f"  add puro: {idx} (tabela {tbl}, coluna {col})")
