from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = ROOT / "scripts" / "ci-local.sh"


def test_venv_e_identificado_por_python_e_requirements_hash():
    src = CI_LOCAL.read_text(encoding="utf-8")

    assert 'VENV_DIR_OVERRIDE="${VENV_DIR:-}"' in src
    assert 'hashlib.sha256(pathlib.Path("backend/requirements.txt").read_bytes())' in src
    assert "python_runtime_key" in src
    assert 'VENV_DIR="$STATE_ROOT/venv-py${py_key}-${req_hash}"' in src


def test_venv_e_construido_sob_lock_e_promovido_atomicamente():
    src = CI_LOCAL.read_text(encoding="utf-8")
    ensure = src[src.index("ensure_venv() {") : src.index("ensure_pip_audit() {")]

    assert 'lock_file="$VENV_DIR.lock"' in ensure
    assert 'flock "$venv_lock_fd"' in ensure
    assert 'build_dir="${VENV_DIR}.build.$$.$RANDOM"' in ensure
    assert '"$build_dir/bin/python" -m pip check' in ensure
    assert '> "$build_dir/.ejc-ready"' in ensure
    assert 'mv "$build_dir" "$VENV_DIR"' in ensure
    # Localiza a ÚLTIMA ocorrência de flock -u em ensure
    last_unlock = ensure.rfind('flock -u "$venv_lock_fd"')
    mv_pos = ensure.index('mv "$build_dir" "$VENV_DIR"')
    assert mv_pos < last_unlock


def test_skip_pip_exige_venv_pronto_e_nao_cria_ambiente_parcial():
    src = CI_LOCAL.read_text(encoding="utf-8")
    ensure = src[src.index("ensure_venv() {") : src.index("ensure_pip_audit() {")]

    assert 'CI_SKIP_PIP:-0}" = "1"' in ensure
    assert "venv hermético pronto não existe" in ensure
    assert ensure.index("CI_SKIP_PIP=1 solicitado") < ensure.index('"$PYTHON_BIN" -m venv')
    assert '[ -x "$VENV_DIR/bin/python" ] && [ -s "$ready" ]' in ensure


def test_pip_audit_nao_muta_venv_da_aplicacao():
    src = CI_LOCAL.read_text(encoding="utf-8")
    audit = src[src.index("ensure_pip_audit() {") : src.index("check_node() {")]
    backend = src[src.index("run_backend() {") : src.index("run_eval() {")]

    assert 'tool_dir="$STATE_ROOT/tools/pip-audit-${PIP_AUDIT_VERSION}-py${py_key}"' in audit
    assert '"$build_dir/bin/python" -m pip install -q "pip-audit==$PIP_AUDIT_VERSION"' in audit
    assert 'PIP_AUDIT_BIN="$tool_dir/bin/pip-audit"' in audit
    assert 'ensure_venv; ensure_pip_audit; start_pg' in backend
    assert '"$PIP_AUDIT_BIN" -r requirements.txt --desc' in backend
    assert '"$PY" -m pip install -q' not in backend


def test_mudanca_de_requirements_separa_ambiente_python():
    src = CI_LOCAL.read_text(encoding="utf-8")

    assert 'VENV_DIR="${VENV_DIR:-$STATE_ROOT/venv-py311}"' not in src
    assert "resolve_venv_dir" in src


def test_pgvector_image_exige_referencia_fixada_com_digest():
    src = CI_LOCAL.read_text(encoding="utf-8")
    start_pg = src[src.index("start_pg() {") : src.index("pick_pg_port")]

    assert "PGVECTOR_IMAGE" in src
    assert "@sha256:" in src
    assert "PGVECTOR_IMAGE deve usar referência fixada com @sha256:" in start_pg
    assert 'case "$PGVECTOR_IMAGE"' in start_pg
    assert "*@sha256:*" in start_pg
