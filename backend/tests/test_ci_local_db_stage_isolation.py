from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def _block(src: str, start: str, end: str) -> str:
    return src[src.index(start) : src.index(end)]


def test_backend_e_continuidade_encerram_seus_bancos_efemeros():
    src = CI_LOCAL.read_text(encoding="utf-8")
    backend = _block(src, "run_backend() {", "run_eval() {")
    continuity = _block(src, "run_continuity() {", "run_ui_extra() {")

    assert "ensure_venv; start_pg" in backend
    assert "stop_pg" in backend
    assert backend.index("start_pg") < backend.index("stop_pg")

    assert "ensure_venv; start_pg" in continuity
    assert "stop_pg" in continuity
    assert continuity.index("start_pg") < continuity.index("stop_pg")


def test_stop_pg_reseta_estado_e_porta_dinamica_entre_estagios():
    src = CI_LOCAL.read_text(encoding="utf-8")
    stop = _block(src, "stop_pg() {", "_cleanup() {")

    assert 'PG_MODE=""' in stop
    assert 'PGBIN=""' in stop
    assert '[ -n "$PG_PORT_OVERRIDE" ] || PG_PORT=""' in stop

    # Quando o usuário não fixa PG_PORT, o próximo start_pg precisa escolher
    # outra porta livre; isso impede backend e restore de reutilizarem o mesmo
    # servidor apenas por estarem no mesmo processo `full`.
    assert 'PG_PORT_OVERRIDE="${PG_PORT:-}"' in src
    assert 'PG_PORT="$PG_PORT_OVERRIDE"' in src
    assert 's.bind(("127.0.0.1", 0))' in src


def test_full_executa_backend_antes_de_continuidade_com_ciclo_independente():
    src = CI_LOCAL.read_text(encoding="utf-8")
    case = src[src.index('case "$MODE" in') :]
    full_line = next(line for line in case.splitlines() if line.strip().startswith("full)"))

    assert "run_backend" in full_line
    assert "run_continuity" in full_line
    assert full_line.index("run_backend") < full_line.index("run_continuity")
    assert "run_backend; run_eval; run_frontend; run_p0; run_architecture; run_continuity" in full_line
