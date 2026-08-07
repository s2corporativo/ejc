"""As migrations REAIS do repositório precisam passar no gate de deploy.

`scripts/check_migration_compatibility.py` só roda no `deploy-vps.yml`, na etapa
"Classificar migrations pendentes" — **não** roda na CI. O efeito é que uma
migration que reprova no gate passa por todos os checks do PR, entra na `main` e
só se manifesta depois do merge, derrubando o deploy. E, como o deploy dispara
por `workflow_run` a cada push na `main`, todo merge seguinte repete a falha até
alguém corrigir a migration.

Foi o que aconteceu com `132_processo_eletronico_mni.py` (PR #763): o seed do
catálogo de tribunais usava `op.bulk_insert` sobre `sa.table()`, o gate reprovou
("estrutura dinâmica Assign" + "op.bulk_insert não está na allowlist") e o deploy
de 2026-08-07 12:08 UTC saiu com exit 1, deixando produção em
`131_audit_logs_worm`.

`test_migration_compatibility_gate.py` e `test_additive_backfill_policy.py` já
cobrem o classificador — mas com migrations sintéticas em `tmp_path`. Nenhum dos
dois olha para `backend/alembic/versions/`. Este arquivo fecha essa lacuna.

**Por que uma catraca e não "todas as migrations".** O gate foi introduzido em
2026-07-26, muito depois do início do projeto: 86 das 125 migrations existentes
reprovam nele. Elas são inofensivas na prática porque já foram aplicadas em
produção — o gate só classifica o que está *pendente*. Exigir que todas passem
significaria reescrever migrations já aplicadas, o que a regra 6 do `CLAUDE.md`
proíbe. Então a trava é para a frente: da `PRIMEIRA_REVISAO_SOB_A_CATRACA` em
diante, ninguém entra sujo.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_migration_compatibility.py"
VERSIONS = ROOT / "backend" / "alembic" / "versions"

SPEC = importlib.util.spec_from_file_location("migration_gate_real", SCRIPT)
assert SPEC and SPEC.loader
_modulo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = _modulo
SPEC.loader.exec_module(_modulo)

# Migrations numeradas a partir daqui precisam passar no gate. O número é o da
# primeira migration escrita depois desta trava existir — abaixo dele está o
# histórico já aplicado em produção, que não se reescreve.
PRIMEIRA_REVISAO_SOB_A_CATRACA = 132


def _numeradas() -> list[tuple[int, Path]]:
    saida: list[tuple[int, Path]] = []
    for caminho in sorted(VERSIONS.glob("*.py")):
        casa = re.match(r"(\d+)_", caminho.name)
        if casa:
            saida.append((int(casa.group(1)), caminho))
    return saida


def test_a_catraca_alcanca_alguma_migration():
    """Guarda do guarda: catraca acima do topo não trava nada."""
    numeros = [n for n, _ in _numeradas()]
    assert numeros, "nenhuma migration numerada encontrada — glob errado?"
    assert max(numeros) >= PRIMEIRA_REVISAO_SOB_A_CATRACA, (
        f"a catraca está em {PRIMEIRA_REVISAO_SOB_A_CATRACA}, acima da maior "
        f"migration ({max(numeros)}) — o teste passaria por vacuidade"
    )


def test_migrations_novas_passam_no_gate_de_deploy():
    """Migration que reprova no gate derruba o deploy DEPOIS do merge.

    O custo de deixar passar não é um teste vermelho: é a `main` implantando
    com erro a cada push até alguém diagnosticar.
    """
    revisoes = {rev.path: rev for rev in _modulo._load_revisions(VERSIONS).values()}

    reprovadas: list[str] = []
    conferidas = 0
    for numero, caminho in _numeradas():
        if numero < PRIMEIRA_REVISAO_SOB_A_CATRACA:
            continue
        revisao = revisoes.get(caminho)
        assert revisao is not None, f"{caminho.name} não foi carregada pelo gate"
        conferidas += 1
        achados, _politica = _modulo._classify(revisao)
        if achados:
            reprovadas.append(f"{caminho.name}: {'; '.join(achados)}")

    assert conferidas, "nenhuma migration sob a catraca — ver teste anterior"
    assert not reprovadas, (
        "migration reprovada pelo gate de deploy — o merge na `main` vai "
        "derrubar o Deploy VPS na etapa 'Classificar migrations pendentes':\n  "
        + "\n  ".join(reprovadas)
    )


def test_seed_de_tribunais_e_idempotente_por_construcao():
    """Regressão direta do defeito: o seed do 132 não pode voltar a bulk_insert.

    O gate já reprovaria, mas a asserção aqui nomeia a propriedade que importa —
    reaplicar o seed não pode violar `uq_tribunais_codigo_grau`.

    Afirmado sobre a AST, não sobre o texto: o comentário da própria migration
    explica por que `op.bulk_insert` saiu, e um grep no arquivo cru acharia a
    explicação em vez da chamada.
    """
    caminho = VERSIONS / "132_processo_eletronico_mni.py"
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))

    chamadas = {
        _modulo._op_call_name(no)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
    }
    assert "bulk_insert" not in chamadas, (
        "op.bulk_insert voltou ao 132 — o gate de deploy reprova e a `main` "
        "para de implantar"
    )

    nomes = {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)}
    assert "uuid4" not in nomes, (
        "id sorteado em tempo de migration faz produção, homologação e CI "
        "divergirem na identidade da mesma linha"
    )

    sql = " ".join(
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
    ).upper()
    assert "INSERT INTO TRIBUNAIS" in sql, "o seed do catálogo sumiu"
    assert "NOT EXISTS" in sql, "o seed perdeu a prova de idempotência"

    assert _modulo._assignment(arvore, "deployment_policy") == "additive_data_backfill"
    assert _modulo._assignment(arvore, "data_backfill_targets") == ("tribunais",)
