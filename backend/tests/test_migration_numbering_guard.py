"""Guarda genérica da numeração e do encadeamento das migrations.

Motivo (2026-07-27): os PRs #495 e #497 reservaram o MESMO número 122 para
migrations diferentes, com o mesmo `down_revision`. Nada no repositório
detectava isso — `test_alembic_single_head.py` fixa o head canônico à mão e
precisa ser editado a cada migration nova, o que fez com que os dois PRs
editassem o mesmo arquivo e entrassem em conflito.

Esta suíte é **genérica**: não conhece nenhuma migration específica e não
precisa ser atualizada quando uma nova entra. Ela lê o diretório e cobra os
invariantes que a governança exige (docs/GOVERNANCA_IA.md, seção 8):

- número de prefixo único por migration;
- todo `down_revision` aponta para uma revisão existente;
- o número do filho é sempre maior que o do pai (sem reuso nem retrocesso);
- head único;
- nenhuma revisão de merge nova (duas cabeças reconciliadas à mão).

As duas exceções legadas — o prefixo 101 duplicado e a revisão de merge 104 —
são allowlist explícita: existem na `main` desde antes desta guarda e ficam
registradas aqui para que qualquer caso NOVO falhe.
"""
from __future__ import annotations

import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Divergência histórica já reconciliada pela revisão de merge 104 — ver
# test_alembic_single_head.py. Nenhum prefixo novo pode se repetir.
PREFIXOS_DUPLICADOS_LEGADOS = {101}
# Única revisão de merge aceita. Merge novo significa que duas frentes criaram
# migrations em paralelo — o que a reserva de numeração existe para impedir.
MERGES_LEGADOS = {"104_merge_entrada_orquestrador"}

_RE_REVISION = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.M)
_RE_DOWN = re.compile(r"^down_revision\s*=\s*(None|\(.*?\)|\[.*?\]|[\"'][^\"']+[\"'])", re.M | re.S)
_RE_STR = re.compile(r"[\"']([^\"']+)[\"']")


def _numero(nome_do_arquivo: str) -> int | None:
    """A sequência mora no NOME do arquivo.

    O identificador interno nem sempre é numérico: as migrations mais antigas
    usam hash (`revision = 'a1b2c3d4e5f6'`) com o arquivo numerado por fora.
    """
    correspondencia = re.match(r"^(\d+)_", nome_do_arquivo)
    return int(correspondencia.group(1)) if correspondencia else None


def _carregar() -> dict[str, dict]:
    """Mapa revisão → {pais, arquivo, numero}, lido do fonte das migrations."""
    migrations: dict[str, dict] = {}
    for arquivo in sorted(VERSIONS_DIR.glob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        revisao = _RE_REVISION.search(fonte)
        assert revisao, f"{arquivo.name}: não declara `revision = \"...\"`"
        bruto = _RE_DOWN.search(fonte)
        assert bruto, f"{arquivo.name}: não declara `down_revision`"
        texto = bruto.group(1).strip()
        pais = () if texto == "None" else tuple(_RE_STR.findall(texto))
        identificador = revisao.group(1)
        assert identificador not in migrations, (
            f"identificador de revisão duplicado: {identificador} "
            f"({arquivo.name} e {migrations[identificador]['arquivo']})"
        )
        migrations[identificador] = {
            "pais": pais,
            "arquivo": arquivo.name,
            "numero": _numero(arquivo.name),
        }
    assert migrations, "nenhuma migration encontrada em alembic/versions"
    return migrations


def test_todo_arquivo_tem_prefixo_numerico():
    sem_prefixo = [
        dados["arquivo"] for dados in _carregar().values() if dados["numero"] is None
    ]
    assert not sem_prefixo, (
        "migration sem prefixo numérico sequencial: "
        f"{sem_prefixo} — a numeração é o que permite reservar o próximo número "
        "em backend/alembic/MIGRATION_RESERVATIONS.md"
    )


def test_nenhum_numero_de_migration_e_reutilizado():
    """Duas migrations com o mesmo número = duas frentes reservaram o mesmo slot."""
    migrations = _carregar()
    por_numero: dict[int, list[str]] = {}
    for dados in migrations.values():
        por_numero.setdefault(dados["numero"], []).append(dados["arquivo"])

    colisoes = {
        numero: sorted(arquivos)
        for numero, arquivos in por_numero.items()
        if len(arquivos) > 1 and numero not in PREFIXOS_DUPLICADOS_LEGADOS
    }
    assert not colisoes, (
        f"número de migration reutilizado: {colisoes}. Reserve o próximo número em "
        "backend/alembic/MIGRATION_RESERVATIONS.md antes de criar a migration "
        "(docs/GOVERNANCA_IA.md, seção 8)."
    )


def test_todo_down_revision_aponta_para_revisao_existente():
    migrations = _carregar()
    orfas = {
        revisao: [pai for pai in dados["pais"] if pai not in migrations]
        for revisao, dados in migrations.items()
    }
    orfas = {revisao: pais for revisao, pais in orfas.items() if pais}
    assert not orfas, f"down_revision aponta para revisão inexistente: {orfas}"


def test_numero_do_filho_e_maior_que_o_do_pai():
    """Impede retrocesso e reuso de número dentro da própria cadeia."""
    migrations = _carregar()
    invertidas = []
    for revisao, dados in migrations.items():
        for pai in dados["pais"]:
            numero_pai = migrations[pai]["numero"]
            if numero_pai is not None and dados["numero"] is not None:
                if numero_pai >= dados["numero"]:
                    invertidas.append(f"{revisao} encadeia após {pai}")
    assert not invertidas, (
        f"encadeamento fora de ordem numérica: {invertidas} — a migration nova "
        "sempre parte do head atual e recebe um número maior."
    )


def test_existe_um_unico_head():
    """Sem depender de um identificador fixo: head = revisão que ninguém referencia."""
    migrations = _carregar()
    referenciadas = {pai for dados in migrations.values() for pai in dados["pais"]}
    heads = sorted(set(migrations) - referenciadas)
    assert len(heads) == 1, (
        f"o repositório tem {len(heads)} heads de migration ({heads}). Duas frentes "
        "criaram migrations em paralelo — consolide a cadeia antes do merge."
    )


def test_nenhuma_revisao_de_merge_nova():
    migrations = _carregar()
    merges = sorted(
        revisao
        for revisao, dados in migrations.items()
        if len(dados["pais"]) > 1 and revisao not in MERGES_LEGADOS
    )
    assert not merges, (
        f"revisão de merge nova: {merges}. Merge de migrations significa que duas "
        "branches criaram migrations concorrentes — a reserva de numeração existe "
        "para impedir isso (docs/GOVERNANCA_IA.md, seção 8)."
    )
