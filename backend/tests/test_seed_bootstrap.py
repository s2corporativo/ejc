"""Bootstrap de seeds (itens 4.3/5.6) — a wiring dos catálogos idempotentes no
seed_all deve ser BEST-EFFORT: uma falha de um seed não pode abortar o deploy.

Os seeds síncronos chamam `sys.exit(1)` em má-configuração (SystemExit, que é
BaseException) — por isso `_rodar_seed_sync` precisa capturar Exception E
SystemExit, senão o processo de bootstrap abortaria.
"""
import sys
from pathlib import Path

# backend/ no path para importar o pacote `seeds` (rodado como script no deploy).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seeds.seed_all import _rodar_seed_sync


async def test_rodar_seed_sync_engole_systemexit():
    def cai_com_sys_exit():
        sys.exit(1)

    # Não deve propagar (senão o bootstrap abortaria).
    await _rodar_seed_sync("seed-sysexit", cai_com_sys_exit)


async def test_rodar_seed_sync_engole_exception():
    def cai_com_excecao():
        raise RuntimeError("driver ausente")

    await _rodar_seed_sync("seed-exc", cai_com_excecao)


async def test_rodar_seed_sync_ok_nao_interfere():
    marcas = []
    await _rodar_seed_sync("seed-ok", lambda: marcas.append(1))
    assert marcas == [1]


# ── SEED_ON_BOOT (DB-13, auditoria de camadas 06/09/2026) ───────────────────

def test_seed_on_boot_interpreta_valores(monkeypatch):
    from seeds.seed_all import seed_on_boot_ativo

    for ligado in ("1", "true", "yes", "", "qualquer-coisa"):
        assert seed_on_boot_ativo(ligado) is True, ligado
    for desligado in ("0", "false", "FALSE", " no ", "off"):
        assert seed_on_boot_ativo(desligado) is False, desligado

    monkeypatch.delenv("SEED_ON_BOOT", raising=False)
    assert seed_on_boot_ativo() is True  # default: tudo roda (dev/CI)
    monkeypatch.setenv("SEED_ON_BOOT", "0")
    assert seed_on_boot_ativo() is False


async def test_main_com_seed_on_boot_desligado_roda_so_o_admin(monkeypatch):
    """Com SEED_ON_BOOT=0, main() semeia o admin e PARA antes de importar
    qualquer outro seed (document_types, skills, base jurídica, reembed)."""
    import seeds.seed_all as seed_all

    chamadas = []

    async def _admin_fake():
        chamadas.append("admin")

    async def _nunca(*_a, **_k):
        raise AssertionError("seed além do admin rodou com SEED_ON_BOOT=0")

    monkeypatch.setattr(seed_all, "seed_admin", _admin_fake)
    monkeypatch.setattr(seed_all, "_rodar_seed_sync", _nunca)
    monkeypatch.setattr(seed_all, "_rodar_seed_async", _nunca)
    monkeypatch.setenv("SEED_ON_BOOT", "0")

    await seed_all.main()
    assert chamadas == ["admin"]
