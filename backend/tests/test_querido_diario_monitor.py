"""Monitor periódico de diários oficiais municipais (Querido Diário).

O risco deste job não é errar a consulta — é passar por saudável sem entregar
nada. Por isso os testes cobrem, além do caminho feliz, os três modos de
"rodou mas não produziu": integração desligada, configuração incompleta e
falha de consulta. Nos três, o resultado tem de carregar `erros`, que é o que
faz o heartbeat registrar `erro` em vez de `ok` (achado V2-3.1: monitorar
resultado, não execução).

Sem rede: o cliente do Querido Diário é substituído por um dublê, e a ingestão
por um espião — nenhum teste aqui toca a API pública nem o banco.
"""
from __future__ import annotations

import pytest

from app.services import querido_diario_monitor as monitor


class _ClienteFake:
    """Dublê do QueridoDiarioClient: devolve payload fixo ou levanta erro."""

    def __init__(self, payload=None, erro=None):
        self._payload = payload or {"gazettes": []}
        self._erro = erro
        self.chamadas: list[dict] = []

    async def buscar(self, **kwargs):
        self.chamadas.append(kwargs)
        if self._erro:
            raise self._erro
        return self._payload


class _DbFake:
    """Sessão mínima: `begin_nested` como contexto e `commit` no-op."""

    def begin_nested(self):
        class _Ctx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()

    async def commit(self):
        return None


def _payload(url="https://diario.betim.mg.gov.br/ed/123.pdf", excerto="obra pública"):
    return {
        "gazettes": [
            {
                "url": url,
                "date": "2026-09-03",
                "territory_name": "Betim",
                "state_code": "MG",
                "excerpts": [excerto],
            }
        ]
    }


@pytest.fixture
def _sem_pausa(monkeypatch):
    """Remove a pausa entre chamadas — o teste não precisa esperar 1,1 s."""
    monkeypatch.setattr(monitor, "_PAUSA_ENTRE_CHAMADAS_S", 0)


def _configurar(monkeypatch, *, municipios="3106705", termos="licitação",
                integracao_ligada=True):
    from app.core.config import get_settings
    from app.integrations import feature_flags

    st = get_settings()
    monkeypatch.setattr(st, "QUERIDO_DIARIO_MONITOR_MUNICIPIOS", municipios,
                        raising=False)
    monkeypatch.setattr(st, "QUERIDO_DIARIO_MONITOR_TERMOS", termos, raising=False)
    monkeypatch.setattr(st, "QUERIDO_DIARIO_MONITOR_JANELA_DIAS", 2, raising=False)
    monkeypatch.setattr(feature_flags, "enabled",
                        lambda fonte: integracao_ligada, raising=False)


def _espionar_ingestao(monkeypatch, estado="novo"):
    from app.services import ingestion_service

    recebidos: list[dict] = []

    async def _fake_upsert(db, **kwargs):
        recebidos.append(kwargs)
        return estado

    monkeypatch.setattr(ingestion_service, "upsert_documento", _fake_upsert)
    return recebidos


# ── projeção do documento ────────────────────────────────────────────────────

def test_documento_carrega_origem_e_marca_conferencia_obrigatoria():
    """Agregador não autentica ato: a URL de origem e o marcador são o que
    permitem a conferência humana depois."""
    doc = monitor._montar_documento("3106705", "licitação",
                                    _payload()["gazettes"][0])
    assert doc is not None
    assert doc["fonte"] == "https://diario.betim.mg.gov.br/ed/123.pdf"
    assert doc["extra"]["conferencia_original_obrigatoria"] is True
    assert doc["extra"]["natureza"] == "agregador_secundario"


def test_documento_nasce_pendente_de_curadoria():
    """Nada entra aprovado no RAG por captura automática."""
    doc = monitor._montar_documento("3106705", "licitação",
                                    _payload()["gazettes"][0])
    assert doc["extra"]["rag_status"] == "pendente"


def test_item_sem_url_ou_sem_texto_e_descartado():
    """Documento sem origem conferível não entra na base."""
    sem_url = {"date": "2026-09-03", "excerpts": ["texto"]}
    sem_texto = {"url": "https://x/y.pdf", "excerpts": []}
    assert monitor._montar_documento("3106705", "t", sem_url) is None
    assert monitor._montar_documento("3106705", "t", sem_texto) is None


def test_chave_de_dedup_usa_a_url_da_edicao():
    """A mesma edição achada por dois termos diferentes tem de colapsar."""
    item = _payload()["gazettes"][0]
    a = monitor._montar_documento("3106705", "licitação", item)["chave_origem"]
    b = monitor._montar_documento("3106705", "desapropriação", item)["chave_origem"]
    assert a == b


# ── varredura ────────────────────────────────────────────────────────────────

async def test_varredura_ingere_achado_e_conta_resultado(monkeypatch, _sem_pausa):
    _configurar(monkeypatch)
    recebidos = _espionar_ingestao(monkeypatch)

    import app.integrations.querido_diario_client as qd_mod
    monkeypatch.setattr(qd_mod, "QueridoDiarioClient",
                        lambda *a, **k: _ClienteFake(_payload()))

    r = await monitor.executar_monitoramento(_DbFake())

    assert r["consultas"] == 1
    assert r["achados"] == 1
    assert r["novos"] == 1
    assert not r["erros"]
    assert len(recebidos) == 1
    # Vetorização adiada: o job horário de reembed completa (mesmo padrão DJEN).
    assert recebidos[0]["embutir_vetores"] is False


async def test_achado_entra_como_conhecimento_publico_sem_vinculo_forjado(
    monkeypatch, _sem_pausa
):
    """Vincular diário a caso por heurística seria pior que não vincular."""
    _configurar(monkeypatch)
    recebidos = _espionar_ingestao(monkeypatch)
    import app.integrations.querido_diario_client as qd_mod
    monkeypatch.setattr(qd_mod, "QueridoDiarioClient",
                        lambda *a, **k: _ClienteFake(_payload()))

    await monitor.executar_monitoramento(_DbFake())

    assert recebidos[0].get("client_id") is None
    assert recebidos[0].get("case_id") is None


# ── os três modos de "rodou e não entregou" ──────────────────────────────────

async def test_integracao_desligada_vira_erro_nao_sucesso_vazio(monkeypatch):
    _configurar(monkeypatch, integracao_ligada=False)
    r = await monitor.executar_monitoramento(_DbFake())
    assert r["erros"] == {"integracao_desabilitada": 1}
    assert r["consultas"] == 0


@pytest.mark.parametrize("municipios,termos", [("", "licitação"), ("3106705", "")])
async def test_configuracao_incompleta_vira_erro(monkeypatch, municipios, termos):
    """Monitor sem município ou sem termo nunca consultaria nada — e um painel
    verde para isso é exatamente o defeito que o heartbeat existe para pegar."""
    _configurar(monkeypatch, municipios=municipios, termos=termos)
    r = await monitor.executar_monitoramento(_DbFake())
    assert r["erros"] == {"configuracao_incompleta": 1}


async def test_falha_de_consulta_e_contada_e_nao_derruba_a_varredura(
    monkeypatch, _sem_pausa
):
    _configurar(monkeypatch, municipios="3106705,3106200")
    _espionar_ingestao(monkeypatch)
    from app.integrations.querido_diario_client import QueridoDiarioError
    import app.integrations.querido_diario_client as qd_mod
    monkeypatch.setattr(
        qd_mod, "QueridoDiarioClient",
        lambda *a, **k: _ClienteFake(erro=QueridoDiarioError("indisponível")),
    )

    r = await monitor.executar_monitoramento(_DbFake())

    assert r["consultas"] == 2, "a segunda consulta tem de acontecer mesmo assim"
    assert r["erros"].get("QueridoDiarioError") == 2


async def test_varre_o_produto_municipios_x_termos(monkeypatch, _sem_pausa):
    _configurar(monkeypatch, municipios="3106705,3106200", termos="a,b,c")
    _espionar_ingestao(monkeypatch)
    cliente = _ClienteFake({"gazettes": []})
    import app.integrations.querido_diario_client as qd_mod
    monkeypatch.setattr(qd_mod, "QueridoDiarioClient", lambda *a, **k: cliente)

    r = await monitor.executar_monitoramento(_DbFake())

    assert r["consultas"] == 6
    assert len(cliente.chamadas) == 6


# ── radar vinculado a clientes ───────────────────────────────────────────────

class _ClientesFake:
    """Sessão que devolve linhas de cliente para `_alvos_de_clientes`."""

    def __init__(self, linhas):
        self._linhas = linhas
        self.filtros_tipo = None

    async def execute(self, stmt):
        # Guarda os VALORES vinculados do WHERE (o `IN` vira placeholder na
        # string compilada, então checar `str(stmt)` não provaria nada).
        self.filtros_tipo = list(stmt.compile().params.values())

        class _R:
            def __init__(self, linhas):
                self._l = linhas

            def all(self_inner):
                return self_inner._l

        return _R(self._linhas)


def _ligar_radar(monkeypatch, *, incluir_pf=False, ibge_ligado=True):
    from app.core.config import get_settings
    from app.integrations import feature_flags

    st = get_settings()
    monkeypatch.setattr(st, "QUERIDO_DIARIO_RADAR_CLIENTES_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(st, "QUERIDO_DIARIO_RADAR_INCLUI_PF", incluir_pf,
                        raising=False)
    monkeypatch.setattr(
        feature_flags, "enabled",
        lambda fonte: ibge_ligado if fonte == "ibge" else True,
        raising=False,
    )


def _fake_ibge(monkeypatch, codigo="3106705"):
    import app.integrations.ibge_localidades_client as ibge_mod

    class _Fake:
        async def canonicalizar(self, nome, uf):
            return {"id": codigo, "nome": nome} if codigo else None

    monkeypatch.setattr(ibge_mod, "IbgeLocalidadesClient", lambda *a, **k: _Fake())


async def test_radar_gera_alvo_com_vinculo_do_cliente(monkeypatch):
    """O client_id vem da ORIGEM da consulta — o termo é o nome do cliente."""
    from app.models.client import ClientTipo

    _ligar_radar(monkeypatch)
    _fake_ibge(monkeypatch)
    db = _ClientesFake([("cli-1", ClientTipo.PJ, None, "Metalúrgica Betim Ltda",
                        None, "Betim", "MG")])

    alvos = await monitor._alvos_de_clientes(db, {"erros": {}})

    assert len(alvos) == 1
    assert alvos[0].client_id == "cli-1"
    assert alvos[0].termo == "Metalúrgica Betim Ltda"
    assert alvos[0].codigo_ibge == "3106705"
    assert alvos[0].origem == "cliente"


async def test_pessoa_fisica_fica_de_fora_por_padrao(monkeypatch):
    """Sigilo profissional: nome de PF só entra com o segundo interruptor."""
    from app.models.client import ClientTipo

    _ligar_radar(monkeypatch, incluir_pf=False)
    _fake_ibge(monkeypatch)
    db = _ClientesFake([])

    await monitor._alvos_de_clientes(db, {"erros": {}})

    # A checagem é sobre a query montada, porque é ela que impede a PF de sair
    # do banco: o dado sensível não deve nem ser carregado.
    valores = [v for p in db.filtros_tipo for v in (p if isinstance(p, list) else [p])]
    assert ClientTipo.PJ in valores
    assert ClientTipo.PF not in valores


async def test_ibge_desligado_vira_erro_visivel_e_nao_lista_vazia(monkeypatch):
    """Sem IBGE não há como virar 'Betim/MG' em código: erro, não silêncio."""
    _ligar_radar(monkeypatch, ibge_ligado=False)
    resultado = {"erros": {}}

    alvos = await monitor._alvos_de_clientes(_ClientesFake([]), resultado)

    assert alvos == []
    assert resultado["erros"] == {"ibge_desabilitado": 1}


async def test_municipio_nao_canonicalizado_e_contado(monkeypatch):
    from app.models.client import ClientTipo

    _ligar_radar(monkeypatch)
    _fake_ibge(monkeypatch, codigo=None)   # IBGE não resolve o nome
    resultado = {"erros": {}}
    db = _ClientesFake([("cli-1", ClientTipo.PJ, None, "Alguma Empresa SA",
                        None, "Cidade Inexistente", "MG")])

    alvos = await monitor._alvos_de_clientes(db, resultado)

    assert alvos == []


async def test_termo_curto_demais_e_descartado(monkeypatch):
    """Termo de 3 letras casaria com meio diário — ruído, não sinal."""
    from app.models.client import ClientTipo

    _ligar_radar(monkeypatch)
    _fake_ibge(monkeypatch)
    # PJ com razão social curta: 3 caracteres casariam com meio diário.
    db = _ClientesFake([("cli-1", ClientTipo.PJ, None, "ABC", None, "Betim", "MG")])

    assert await monitor._alvos_de_clientes(db, {"erros": {}}) == []


def test_achado_de_cliente_fica_restrito_aquele_cliente():
    """Documento vinculado é material DAQUELE cliente, não acervo público."""
    doc = monitor._montar_documento(
        "3106705", "Metalúrgica Betim Ltda", _payload()["gazettes"][0],
        client_id="cli-1", origem="cliente",
    )
    assert doc["client_id"] == "cli-1"
    assert doc["extra"]["origem_alvo"] == "cliente"
    # Mesmo vinculado, segue pendente de curadoria humana.
    assert doc["extra"]["rag_status"] == "pendente"
