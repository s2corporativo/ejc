from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_higiene_e_conservadora_e_identidade_vem_primeiro():
    src = (ROOT / "scripts/post_release_hygiene.sh").read_text(encoding="utf-8")
    identity = src.index("check_release_identity.py")
    branches = src.index("branch_hygiene.py")
    prune = src.index("docker container prune")
    assert identity < branches < prune
    assert "--apply" in src
    assert "--archive-old" not in src
    assert "docker volume prune" not in src
    assert "system prune --volumes" not in src
    assert "until=168h" in src
    assert "graphify update" in src


def test_higiene_registra_que_volumes_nao_sao_podados():
    src = (ROOT / "scripts/post_release_hygiene.sh").read_text(encoding="utf-8")
    assert '"docker_volumes_pruned": False' in src
    assert '"archive_old_unique": False' in src
