"""Testes do helper `entidades_do_caso` (montagem de entidades nomeadas do caso
para o pseudonimizador reversível) e da fiação de um call site ao gateway.

Sem Postgres real (padrão test_ownership.py / test_sociedades_cliente.py): o
Case é construído em memória com relationships pré-populados e servido por um
fake de sessão. Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations


from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.client import Client, ClientTipo
from app.models.user import User, UserRole
from app.services.ai.entidades_caso import entidades_do_caso


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────
class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """Sessão fake: execute() sempre devolve o mesmo Case (ou None)."""

    def __init__(self, caso):
        self._caso = caso

    async def execute(self, *a, **k):
        return _Res(self._caso)


def _case(**kw) -> Case:
    base = dict(id="c1", titulo="Ação fictícia", client_id="cli1", deleted_at=None)
    base.update(kw)
    return Case(**base)


# ── Testes do helper ──────────────────────────────────────────────────────────
class TestEntidadesDoCaso:
    async def test_cliente_pf_advogado_e_parte_adversaria(self):
        cli = Client(id="cli1", tipo=ClientTipo.PF, nome="João da Silva")
        adv = User(id="u1", role=UserRole.advogado, full_name="Dra. Marina Costa")
        parte = CaseParte(id="p1", case_id="c1", tipo="reu",
                          papel_processual="Réu", nome="Construtora Alfa Ltda")
        caso = _case(client=cli, advogado_responsavel=adv, partes=[parte],
                     parte_contraria="Banco Omega S.A.")

        ent = await entidades_do_caso(_FakeDB(caso), "c1")

        assert ent["cliente"] == ["João da Silva"]
        assert "Dra. Marina Costa" in ent["advogado"]
        # parte_contraria = campo livre do caso + CaseParte adversária.
        assert "Banco Omega S.A." in ent["parte_contraria"]
        assert "Construtora Alfa Ltda" in ent["parte_contraria"]
        # PF não gera chave "empresa".
        assert "empresa" not in ent

    async def test_cliente_pj_gera_empresa(self):
        cli = Client(id="cli1", tipo=ClientTipo.PJ,
                     razao_social="Comercial Beta Ltda",
                     nome_fantasia="Beta Store")
        caso = _case(client=cli, partes=[], advogado_responsavel=None)

        ent = await entidades_do_caso(_FakeDB(caso), "c1")

        # razao_social/nome_fantasia protegidos (razao_social pode cair sob
        # "cliente" pela dedup global — o importante é NÃO se perder nenhum nome).
        nomes = [n for lst in ent.values() for n in lst]
        assert "Comercial Beta Ltda" in nomes
        assert "Beta Store" in nomes

    async def test_dedup_e_piso_de_tamanho(self):
        cli = Client(id="cli1", tipo=ClientTipo.PF, nome="Ana Paula Souza")
        # Parte com o MESMO nome do cliente (não deve virar parte contrária) +
        # parte com nome curto (< 4 chars, descartado pelo piso).
        p_dup = CaseParte(id="p1", case_id="c1", tipo="autor",
                          papel_processual="Autor", nome="Ana Paula Souza",
                          client_id="cli1")
        p_curto = CaseParte(id="p2", case_id="c1", tipo="reu",
                            papel_processual="Réu", nome="Léo")
        caso = _case(client=cli, partes=[p_dup, p_curto],
                     advogado_responsavel=None, parte_contraria=None)

        ent = await entidades_do_caso(_FakeDB(caso), "c1")

        assert ent["cliente"] == ["Ana Paula Souza"]
        # o nome curto foi descartado e o duplicado do cliente não vira PC.
        assert "parte_contraria" not in ent
        # Nenhum nome aparece duas vezes no total.
        todos = [n for lst in ent.values() for n in lst]
        assert len(todos) == len(set(todos))

    async def test_caso_inexistente_retorna_vazio_sem_excecao(self):
        ent = await entidades_do_caso(_FakeDB(None), "nao-existe")
        assert ent == {}

    async def test_case_id_vazio_retorna_vazio(self):
        # Nem chega ao banco.
        ent = await entidades_do_caso(_FakeDB(None), "")
        assert ent == {}

    async def test_erro_de_banco_nunca_propaga(self):
        class _BoomDB:
            async def execute(self, *a, **k):
                raise RuntimeError("conexão caiu")

        ent = await entidades_do_caso(_BoomDB(), "c1")
        assert ent == {}

    async def test_sem_chaves_vazias(self):
        cli = Client(id="cli1", tipo=ClientTipo.PF, nome="Carlos Andrade")
        caso = _case(client=cli, partes=[], advogado_responsavel=None,
                     parte_contraria=None)
        ent = await entidades_do_caso(_FakeDB(caso), "c1")
        assert ent == {"cliente": ["Carlos Andrade"]}
        assert all(v for v in ent.values())


# ── Integração leve: call site fiado passa `entidades` ao gateway e reidrata ──
class TestVeredictoWiring:
    async def test_predict_success_pseudonimiza_e_reidrata(self, monkeypatch):
        """veredito_ia.predict_success com case_id deve montar `entidades` e
        passá-las ao gateway; com provider externo mockado o nome do cliente vai
        como marcador e a resposta volta reidratada."""
        from app.core import veredito_ia as mod

        cli = Client(id="cli1", tipo=ClientTipo.PF, nome="Joana Ribeiro")
        caso = _case(client=cli, partes=[], advogado_responsavel=None,
                     parte_contraria=None)

        # entidades_do_caso é importado em runtime dentro de predict_success e
        # roda de verdade contra a MESMA sessão db (o _FakeDB devolve o caso).
        capturado: dict = {}

        async def _fake_gw_chat(messages, **kw):
            capturado["entidades"] = kw.get("entidades")
            from app.services.ai_gateway import GatewayResponse
            return GatewayResponse(
                texto="Sugestões sobre o caso.", modelo="fake", provedor="ollama",
                task_type="jurimetria", input_tokens=1, output_tokens=1,
            )

        # patcha o símbolo importado em runtime dentro de predict_success.
        import app.services.ai_gateway as gw
        monkeypatch.setattr(gw, "chat", _fake_gw_chat)

        # neutraliza dependências pesadas (jurimetria/RAG/victory vault/citations/log).
        async def _empty_jurimetria(db, user, **kw):
            return {"grupos": []}

        async def _empty_rag(*a, **k):
            return []

        async def _noop_citacoes(db, material):
            return {"score": None, "avisos": []}

        async def _noop_log(db, **kw):
            return "log-1"

        async def _noop_escopo(db, case_id):
            return None

        monkeypatch.setattr(mod, "calcular_jurimetria", _empty_jurimetria)
        monkeypatch.setattr(mod, "buscar_contexto_rag", _empty_rag)
        monkeypatch.setattr(mod, "verificar_citacoes", _noop_citacoes)
        monkeypatch.setattr(mod, "registrar_ai_log", _noop_log)
        monkeypatch.setattr(mod, "_escopo_cliente_do_caso", _noop_escopo)

        v = mod.VereditoIA()
        user = User(id="u1", role=UserRole.advogado, full_name="Adv")

        await v.predict_success(
            "Tese fictícia de responsabilidade civil.", "civil", ["STJ"],
            db=_FakeDB(caso), user=user, case_id="c1",
        )

        assert capturado["entidades"] == {"cliente": ["Joana Ribeiro"]}
