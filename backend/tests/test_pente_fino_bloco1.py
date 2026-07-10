# ── tests/test_pente_fino_bloco1.py ──────────────────────────────────────────
# Pente fino (main @ a11f938) — Bloco 1 (segurança/sigilo). Trava os invariantes
# dos fixes: SSRF do Web Push, precedência normativa da taxonomia RAG (P3),
# anti-lockout entre pares no PATCH /users (P4) e RBAC nas leituras do Drive.
import pathlib
from types import SimpleNamespace

import pytest

from app.services.notification_service import endpoint_push_valido
from app.services.google_drive_taxonomy import classificar_drive_file
from app.routers.users import _validar_alvo


# ── SSRF: allowlist de endpoints Web Push ─────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://android.googleapis.com/gcm/x",
    "https://updates.push.services.mozilla.com/wpush/v2/x",
    "https://web.push.apple.com/xyz",
    "https://sub.notify.windows.com/w",
])
def test_endpoint_push_permitido(url):
    assert endpoint_push_valido(url) is True


@pytest.mark.parametrize("url", [
    "http://fcm.googleapis.com/x",                 # sem https
    "https://169.254.169.254/latest/meta-data/",   # metadata interno
    "https://localhost:8000/internal",             # loopback
    "https://attacker.example/collect",            # host arbitrario
    "https://fcm.googleapis.com.evil.com/x",        # sufixo forjado
    "", "not-a-url",
])
def test_endpoint_push_bloqueado(url):
    assert endpoint_push_valido(url) is False


# ── P3: taxonomia RAG — token de exclusão só no nome + precedência normativa ───
def test_p3_sumula_em_pasta_backup_nao_e_excluida():
    d = classificar_drive_file("Sumula 7 STJ.docx", caminho="Conhecimento/Backup 2023")
    assert d.excluir is False and d.categoria.startswith("sumula")


def test_p3_lei_com_antigo_no_caminho_nao_e_excluida():
    d = classificar_drive_file("Lei 8112.pdf", caminho="Legislacao/Antigo")
    assert d.excluir is False


def test_p3_backup_real_no_nome_ainda_e_excluido():
    d = classificar_drive_file("backup_dump_2023.txt", caminho="qualquer")
    assert d.excluir is True and d.categoria == "nao_indexar"


# ── P4: anti-lockout entre pares no _validar_alvo ─────────────────────────────
def _u(role, uid="x"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def test_p4_admin_nao_gerencia_outro_admin():
    with pytest.raises(Exception) as exc:
        _validar_alvo(_u("admin", "a"), _u("admin", "b"))
    assert getattr(exc.value, "status_code", None) == 403


def test_p4_superadmin_gerencia_admin():
    _validar_alvo(_u("superadmin", "s"), _u("admin", "a"))  # não levanta


# ── RBAC nas leituras do Google Drive (achado 19) ─────────────────────────────
def test_leituras_drive_exigem_papel_gestor():
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app" / "routers" / "google_drive_knowledge.py"
    ).read_text(encoding="utf-8")
    # get_current_user não pode mais ser o único gate (as 3 leituras migraram para require_roles)
    assert "get_current_user" not in src, "leituras do Drive não devem usar get_current_user solto"
    assert src.count("require_roles([\"superadmin\", \"admin\", \"socio\"])") >= 7
