from scripts.check_release_identity import validate_identity

SHA = "a" * 40

def test_identidade_canonicamente_alinhada():
    assert validate_identity(
        expected=SHA, marker=SHA, local_commit=SHA, public_commit=SHA
    ) == []

def test_divergencia_de_qualquer_fonte_bloqueia():
    errors = validate_identity(
        expected=SHA, marker="b" * 40, local_commit=SHA, public_commit="c" * 40
    )
    assert any(".deployed_sha divergente" in e for e in errors)
    assert any("health público divergente" in e for e in errors)

def test_pre_marker_valida_runtime_sem_exigir_arquivo():
    assert validate_identity(
        expected=SHA, marker=None, local_commit=SHA, public_commit=SHA,
        require_marker=False,
    ) == []
