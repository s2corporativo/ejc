# ── tests/test_configurar_oab_djen.py ────────────────────────────────────────
# `scripts/configurar_oab_djen.py` grava o vínculo advogado↔OAB que o job
# diário de intimações usa para saber de quem monitorar publicações. Erro aqui
# não falha ruidosamente: grava a inscrição de outro advogado, ou não grava
# nada, e o job segue "verde" capturando zero. Os testes abaixo travam
# justamente as recusas — ambiguidade, conflito e divergência cadastral —
# porque é delas que depende a segurança do script.
from __future__ import annotations

import pytest

from app.models.user import User
from scripts.configurar_oab_djen import (
    EntradaInvalida,
    localizar,
    montar_plano,
    parse_definicao,
)


def _user(uid: str, nome: str, email: str, *, djen=None, uf=None, oab=None) -> User:
    u = User()
    u.id = uid
    u.full_name = nome
    u.email = email
    u.djen_oab_numero = djen
    u.djen_oab_uf = uf
    u.oab_number = oab
    return u


# ── parse dos argumentos ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "bruto,numero,uf",
    [
        ("Guilherme=252599/MG", "252599", "MG"),
        ("Joao Pedro=251174/MG", "251174", "MG"),
        ("x=252599 MG", "252599", "MG"),
        ("x=OAB/MG 252599", "252599", "MG"),
        ("x=252599-mg", "252599", "MG"),
    ],
)
def test_parse_aceita_formatos_usuais(bruto, numero, uf):
    d = parse_definicao(bruto)
    assert (d.numero, d.uf) == (numero, uf)


@pytest.mark.parametrize(
    "bruto",
    [
        "Guilherme",             # sem '='
        "=252599/MG",            # identificador vazio
        "x=252599",              # sem UF — jamais deduzir
        "x=252599/XX",           # UF inexistente
        "x=MG",                  # sem número
        "x=12/MG",               # número curto demais
        "x=12345678901/MG",      # não cabe em String(10)
        "x=252599/MG 251174/SP",  # dois números
    ],
)
def test_parse_recusa_entrada_ambigua_ou_invalida(bruto):
    with pytest.raises(EntradaInvalida):
        parse_definicao(bruto)


def test_parse_nao_deduz_uf_a_partir_do_escritorio():
    """Número sem UF é ambíguo no país inteiro: recusar é o comportamento
    correto, porque supor a UF monitoraria a inscrição de outro advogado."""
    with pytest.raises(EntradaInvalida) as exc:
        parse_definicao("Guilherme=252599")
    assert "NUNCA é deduzida" in str(exc.value)


# ── casamento do identificador ───────────────────────────────────────────────

def test_localizar_por_email_e_exato():
    us = [
        _user("1", "Guilherme Teixeira", "guilherme@x.adv.br"),
        _user("2", "Guilherme Souza", "guilherme.souza@x.adv.br"),
    ]
    assert [u.id for u in localizar(us, "GUILHERME@X.ADV.BR")] == ["1"]


def test_localizar_por_fragmento_ignora_acento_e_caixa():
    us = [_user("1", "João Pedro de Paula", "jp@x.adv.br")]
    assert [u.id for u in localizar(us, "joao pedro")] == ["1"]


# ── plano: gravações válidas ─────────────────────────────────────────────────

def test_plano_grava_os_dois_socios():
    us = [
        _user("1", "Guilherme Teixeira", "g@x.adv.br"),
        _user("2", "João Pedro de Paula", "jp@x.adv.br"),
    ]
    plano, erros = montar_plano(
        us,
        [parse_definicao("Guilherme=252599/MG"), parse_definicao("Joao Pedro=251174/MG")],
    )
    assert erros == []
    assert [(i.user_id, i.definicao.numero, i.definicao.uf) for i in plano] == [
        ("1", "252599", "MG"),
        ("2", "251174", "MG"),
    ]
    # O script NÃO escreve `oab_number`: esse campo assina as peças geradas.
    # Só sinaliza que o perfil está vazio, para o advogado preencher lá.
    assert all(i.perfil_vazio for i in plano)


def test_plano_e_idempotente():
    us = [_user("1", "Guilherme", "g@x.adv.br", djen="252599", uf="MG", oab="252599/MG")]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert erros == []
    assert plano[0].ja_configurado is True


def test_plano_aceita_perfil_coerente_e_nao_o_reescreve():
    us = [_user("1", "Guilherme", "g@x.adv.br", oab="OAB/MG 252599")]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert erros == []
    assert plano[0].perfil_vazio is False
    assert plano[0].ja_configurado is False  # djen_* continua vazio


def test_plano_aceita_perfil_sem_uf_mas_com_o_mesmo_numero():
    """`oab_number` livre ("252599") não resolve par nenhum; com o MESMO
    número não há divergência, só dado incompleto."""
    us = [_user("1", "Guilherme", "g@x.adv.br", oab="252599")]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert erros == []
    assert plano[0].perfil_vazio is False


def test_recusa_perfil_sem_uf_com_numero_diferente():
    """A guarda de divergência falhava ABERTO aqui: "111111" resolve para
    ("", ""), que era lido como "sem divergência", e o script gravava outra
    inscrição ao lado — o dano exato que ele existe para impedir."""
    us = [_user("1", "Guilherme", "g@x.adv.br", oab="111111")]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert plano == []
    assert "Divergência de dado cadastral" in erros[0]


# ── plano: recusas ───────────────────────────────────────────────────────────

def test_recusa_fragmento_ambiguo_sem_gravar_nada():
    us = [
        _user("1", "Guilherme Teixeira", "g1@x.adv.br"),
        _user("2", "Guilherme Souza", "g2@x.adv.br"),
    ]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert plano == []
    assert len(erros) == 1 and "Ambíguo" in erros[0]


def test_recusa_identificador_sem_correspondencia():
    us = [_user("1", "Guilherme", "g@x.adv.br")]
    plano, erros = montar_plano(us, [parse_definicao("Fulano=252599/MG")])
    assert plano == []
    assert "nenhum usuário ativo" in erros[0]


def test_recusa_oab_ja_vinculada_a_outro_usuario():
    """Reatribuir uma OAB em uso faria dois usuários receberem a mesma
    intimação — ou pior, moveria o monitoramento sem aviso."""
    us = [
        _user("1", "Guilherme", "g@x.adv.br"),
        _user("2", "Outro Advogado", "o@x.adv.br", djen="252599", uf="MG"),
    ]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert plano == []
    assert "já está vinculada" in erros[0]


def test_recusa_divergencia_com_a_oab_do_perfil():
    us = [_user("1", "Guilherme", "g@x.adv.br", oab="111111/SP")]
    plano, erros = montar_plano(us, [parse_definicao("Guilherme=252599/MG")])
    assert plano == []
    assert "Divergência de dado cadastral" in erros[0]


def test_recusa_dois_identificadores_para_o_mesmo_usuario():
    us = [_user("1", "Guilherme Teixeira", "g@x.adv.br")]
    plano, erros = montar_plano(
        us,
        [parse_definicao("Guilherme=252599/MG"), parse_definicao("Teixeira=251174/MG")],
    )
    assert plano == []
    assert "mesmo" in erros[0]


def test_um_erro_aborta_o_lote_inteiro():
    """Meio plano aplicado é pior que nenhum: parece configurado."""
    us = [
        _user("1", "Guilherme Teixeira", "g@x.adv.br"),
        _user("2", "João Pedro", "jp@x.adv.br"),
    ]
    plano, erros = montar_plano(
        us,
        [parse_definicao("Joao Pedro=251174/MG"), parse_definicao("Inexistente=252599/MG")],
    )
    assert erros  # o chamador (executar) devolve 2 e não grava nada
    assert [i.user_id for i in plano] == ["2"]


# ── CLI: modos somente-leitura não se misturam com gravação ──────────────────

def test_cli_recusa_verificar_junto_com_definir():
    from scripts.configurar_oab_djen import main

    assert main(["--verificar", "--definir", "Guilherme=252599/MG"]) == 2


def test_cli_recusa_testar_fonte_junto_com_definir():
    from scripts.configurar_oab_djen import main

    assert main(["--testar-fonte", "--definir", "Guilherme=252599/MG"]) == 2


def test_cli_recusa_dois_modos_de_leitura_ao_mesmo_tempo():
    from scripts.configurar_oab_djen import main

    assert main(["--verificar", "--testar-fonte"]) == 2


def test_cli_sem_argumento_nao_grava_nada():
    from scripts.configurar_oab_djen import main

    assert main([]) == 2


def test_cli_recusa_definicao_invalida_antes_de_abrir_o_banco():
    """O parser roda antes de qualquer conexão: entrada errada não chega a
    tocar o banco nem a pedir confirmação."""
    from scripts.configurar_oab_djen import main

    assert main(["--definir", "Guilherme=252599", "--aplicar"]) == 2


def test_cli_aplicar_exige_operador_declarado():
    """Sem ator, o AuditLog não distingue alteração por shell de ação
    automática do sistema (LGPD art. 37)."""
    from scripts.configurar_oab_djen import main

    assert main(["--definir", "Silva=123456/MG", "--aplicar"]) == 2


def test_uf_precisa_ser_token_inteiro():
    """"SEP" (typo de SP) casava o pedaço "SE" e gravava uma inscrição em
    Sergipe sem acusar nada."""
    with pytest.raises(EntradaInvalida):
        parse_definicao("Silva=123456/SEP")
