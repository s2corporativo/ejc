# ── tests/test_middleware_auth_invariant.py ──────────────────────────────────
# Item 8 (defesa em profundidade): o AuthMiddleware valida a ASSINATURA/exp do
# JWT mas, por ser propositalmente sem DB, NÃO checa is_active/revogação — quem
# barra um usuário desativado/removido é o get_current_user (query no banco).
#
# O invariante que sustenta a segurança: NENHUM endpoint pode decidir autorização
# a partir de request.state.user_id/role (populados pelo middleware) — isso
# pularia o gate de is_active. Todo endpoint protegido deve usar
# Depends(get_current_user). Este teste trava esse invariante: se um router
# passar a ler request.state.user_id/role, ele falha e obriga a usar
# get_current_user (ou a reforçar o middleware conscientemente).
import pathlib
import re

from app.core.auth_middleware import _is_publica

_ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"
_PADRAO = re.compile(r"request\.state\.(user_id|role)\b")


def test_data_room_acesso_por_token_e_publico():
    # Item 11: o link externo do Data Room (token de 48 bytes na URL) precisa ser
    # público — senão o cliente externo (sem JWT) toma 401 e o compartilhamento
    # não funciona. Só o subpath /acesso/ é público.
    assert _is_publica("/api/data-rooms/acesso/abc123token") is True


def test_gestao_data_room_continua_protegida():
    # A gestão do Data Room (criar/listar/revogar links) NÃO pode ser pública.
    assert _is_publica("/api/data-rooms/algum-id/links") is False
    assert _is_publica("/api/data-rooms") is False


def test_calendar_feed_assinado_e_publico():
    # O feed ICS é uma capability URL: o token HMAC no próprio path substitui
    # JWT somente para a leitura do calendário. Compatibilidade /api/v1 também
    # precisa continuar sujeita à mesma regra após normalização.
    token = "a" * 32
    assert _is_publica(f"/api/calendar/user-123/{token}.ics") is True
    assert _is_publica(f"/api/v1/calendar/user-123/{token}.ics") is True


def test_gestao_calendar_continua_protegida():
    # A whitelist antiga liberava a subárvore inteira /calendar/, fazendo estas
    # rotas autenticadas escaparem dos gates globais de senha, 2FA e Portal.
    assert _is_publica("/api/calendar/me/url") is False
    assert _is_publica("/api/calendar/me/rotate") is False
    # Tokens com shape diferente não podem ampliar a exceção pública.
    assert _is_publica("/api/calendar/user-123/token-curto.ics") is False
    assert _is_publica("/api/calendar/user-123/" + ("a" * 32) + ".ics/extra") is False


def test_routers_nao_autorizam_por_request_state():
    infratores = []
    for arq in _ROUTERS.glob("*.py"):
        texto = arq.read_text(encoding="utf-8")
        for m in _PADRAO.finditer(texto):
            linha = texto[: m.start()].count("\n") + 1
            infratores.append(f"{arq.name}:{linha} usa request.state.{m.group(1)}")
    assert not infratores, (
        "Endpoint decidindo autorização por request.state (do middleware, que NÃO "
        "checa is_active) — use Depends(get_current_user):\n  " + "\n  ".join(infratores)
    )
