"""Testes de unidade do dispatch unificado `notificar` (P1: preferências
deixam de ser inertes).

Mocka os canais (sino/push/email/whatsapp) e as consultas de preferência/
disponibilidade via monkeypatch no namespace de notification_service, sem
tocar banco nem rede.
"""
from datetime import time
from types import SimpleNamespace

from app.services import notification_service as ns


def _availability(push=True, email=True, whatsapp=True):
    return SimpleNamespace(push=push, email=email, whatsapp=whatsapp)


def _pref(**over):
    base = dict(
        prazos_enabled=True,
        tarefas_enabled=True,
        financeiro_enabled=True,
        push_enabled=True,
        email_enabled=True,
        whatsapp_enabled=True,
        timezone="America/Sao_Paulo",
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _spy(monkeypatch):
    calls = {"sino": [], "push": [], "email": [], "whatsapp": []}

    async def fake_sino(db, user_id, titulo, mensagem, tipo="sistema", link=None):
        calls["sino"].append({"user_id": user_id, "tipo": tipo})
        return SimpleNamespace(id="n1")

    async def fake_push(db, user_id, titulo, mensagem, link="/"):
        calls["push"].append({"user_id": user_id, "link": link})

    async def fake_email(destinatario, assunto, corpo):
        calls["email"].append({"to": destinatario, "assunto": assunto})
        return True

    async def fake_whatsapp(telefone, mensagem):
        calls["whatsapp"].append({"telefone": telefone, "mensagem": mensagem})
        return True

    monkeypatch.setattr(ns, "criar_notificacao_interna", fake_sino)
    monkeypatch.setattr(ns, "enviar_push", fake_push)
    monkeypatch.setattr(ns, "enviar_email", fake_email)
    monkeypatch.setattr(ns, "enviar_whatsapp", fake_whatsapp)
    return calls


def _patch(monkeypatch, pref, avail):
    async def fake_get(db, user_id):
        return pref

    monkeypatch.setattr(ns, "get_notification_preference", fake_get)
    monkeypatch.setattr(ns, "channel_availability", lambda settings=None: avail)


async def test_pref_none_segue_os_defaults_declarados(monkeypatch):
    """Usuário SEM linha de preferências recebe o que o default declara.

    Regressão do achado P1: `pref is None` liberava TODOS os canais externos,
    embora DEFAULT_PREFERENCES declare `whatsapp_enabled=False` e
    `email_enabled=False` (e seja isso que a API mostra ao usuário em
    /notificacoes/preferencias). Efeito: bastaria habilitar o canal no
    ambiente para todo usuário que nunca abriu a tela passar a receber
    WhatsApp externo sem ter optado. Push (default True) continua saindo.
    """
    spy = _spy(monkeypatch)
    _patch(monkeypatch, None, _availability())
    await ns.notificar(
        None, "u1", "T", "M", tipo="tarefa",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert len(spy["push"]) == 1          # DEFAULT_PREFERENCES: push ligado
    assert spy["email"] == []             # DEFAULT_PREFERENCES: e-mail off
    assert spy["whatsapp"] == []          # DEFAULT_PREFERENCES: whatsapp off


async def test_pref_none_nao_manda_whatsapp_nem_em_tipo_mandatorio(monkeypatch):
    """Nem alerta mandatório abre canal externo sem opt-in do usuário.

    `prazo` ignora a categoria (o sino é obrigatório), mas não pode driblar o
    default do CANAL: sem preferência gravada, WhatsApp/e-mail seguem fechados.
    """
    spy = _spy(monkeypatch)
    _patch(monkeypatch, None, _availability())
    await ns.notificar(
        None, "u1", "Prazo", "vence amanhã", tipo="prazo",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert spy["whatsapp"] == []
    assert spy["email"] == []


async def test_opt_in_explicito_libera_whatsapp(monkeypatch):
    """Contraprova: com opt-in gravado, o canal dispara normalmente."""
    spy = _spy(monkeypatch)
    _patch(monkeypatch, _pref(whatsapp_enabled=True), _availability())
    await ns.notificar(
        None, "u1", "T", "M", tipo="tarefa",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["whatsapp"]) == 1


async def test_categoria_desativada_nao_mandatorio_suprime_tudo(monkeypatch):
    spy = _spy(monkeypatch)
    _patch(monkeypatch, _pref(financeiro_enabled=False), _availability())
    await ns.notificar(
        None, "u1", "T", "M", tipo="financeiro",
        email="a@x.com", telefone="5531999999999",
    )
    assert spy["sino"] == []
    assert spy["push"] == []
    assert spy["email"] == []
    assert spy["whatsapp"] == []


async def test_mandatorio_com_categoria_off_cria_sino_e_permite_canais(monkeypatch):
    spy = _spy(monkeypatch)
    # prazo é mandatório: mesmo com prazos_enabled=False o sino é criado.
    _patch(monkeypatch, _pref(prazos_enabled=False), _availability())
    await ns.notificar(
        None, "u1", "Prazo", "vence", tipo="prazo",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert spy["sino"][0]["tipo"] == "prazo"
    assert len(spy["push"]) == 1
    assert len(spy["email"]) == 1
    assert len(spy["whatsapp"]) == 1


async def test_quiet_hours_mantem_sino_e_suprime_canais_externos(monkeypatch):
    spy = _spy(monkeypatch)
    _patch(
        monkeypatch,
        _pref(quiet_hours_start=time(22), quiet_hours_end=time(7)),
        _availability(),
    )
    # Força janela silenciosa independentemente da hora real do runner.
    monkeypatch.setattr(ns, "is_quiet_hours", lambda *a, **k: True)
    await ns.notificar(
        None, "u1", "T", "M", tipo="tarefa",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert spy["push"] == []
    assert spy["email"] == []
    assert spy["whatsapp"] == []


async def test_push_off_email_on_apenas_email(monkeypatch):
    spy = _spy(monkeypatch)
    _patch(
        monkeypatch,
        _pref(push_enabled=False, email_enabled=True, whatsapp_enabled=False),
        _availability(),
    )
    await ns.notificar(
        None, "u1", "T", "M", tipo="tarefa",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert spy["push"] == []
    assert len(spy["email"]) == 1
    assert spy["whatsapp"] == []


async def test_forcar_sino_cria_sino_mas_nao_abre_canais_com_categoria_off(monkeypatch):
    # Régua de cobrança: item de trabalho operacional. Mesmo com a categoria
    # financeiro desativada, o sino é registrado (senão o nível seria marcado
    # como notificado sem entrega, suprimindo a cobrança permanentemente); os
    # canais externos seguem gateados pela categoria (aqui, suprimidos).
    spy = _spy(monkeypatch)
    _patch(monkeypatch, _pref(financeiro_enabled=False), _availability())
    await ns.notificar(
        None, "u1", "Cobrança", "em atraso", tipo="financeiro",
        email="a@x.com", telefone="5531999999999", forcar_sino=True,
    )
    assert len(spy["sino"]) == 1
    assert spy["push"] == []
    assert spy["email"] == []
    assert spy["whatsapp"] == []


async def test_forcar_sino_com_categoria_on_dispara_canais(monkeypatch):
    # Com a categoria ativa, forcar_sino não interfere nos canais externos.
    spy = _spy(monkeypatch)
    _patch(monkeypatch, _pref(financeiro_enabled=True), _availability())
    await ns.notificar(
        None, "u1", "Cobrança", "em atraso", tipo="financeiro",
        email="a@x.com", telefone="5531999999999", forcar_sino=True,
    )
    assert len(spy["sino"]) == 1
    assert len(spy["push"]) == 1
    assert len(spy["email"]) == 1
    assert len(spy["whatsapp"]) == 1


async def test_canal_indisponivel_bloqueia_push_mesmo_habilitado(monkeypatch):
    spy = _spy(monkeypatch)
    _patch(monkeypatch, _pref(push_enabled=True), _availability(push=False))
    await ns.notificar(
        None, "u1", "T", "M", tipo="tarefa",
        email="a@x.com", telefone="5531999999999",
    )
    assert len(spy["sino"]) == 1
    assert spy["push"] == []
    assert len(spy["email"]) == 1
    assert len(spy["whatsapp"]) == 1
