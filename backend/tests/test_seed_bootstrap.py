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
