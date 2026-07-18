"""FASE 6 (Orquestrador Jurídico) — tools do agente que embrulham os motores
determinísticos (padrão de test_agente_ia.py: tudo mockado, sem rede/banco;
dados FICTÍCIOS).

Cobre:
  1. Registro: 9 tools novas no REGISTRY; leitura sem HITL, escrita com HITL
     restrita a papéis sênior (L9); contrato de schema Anthropic.
  2. calcular_prazo: projeção determinística com base legal VERBATIM do
     catálogo; SEMPRE termo_inicial_confirmado=False; NUNCA cria Deadline;
     evento incerto não projeta; peça desconhecida → erro estruturado.
  3. detectar_providencias / identificar_rito_e_fase: rito determinístico com
     requer_confirmacao_humana e peças com base legal do CATALOGO_PECAS.
  4. classificar_area: taxonomia determinística (sem LLM); sem correspondência
     segura → None + decisão humana.
  5. ler_checklist_peca / consultar_tabela_oab / montar_cronologia: embrulho
     verbatim dos serviços existentes.
  6. criar_prazo_confirmado: só o handler (pós-aprovação HITL) chama o service
     com termo_inicial_confirmado=True; GateBloqueado vira dado estruturado
     (nada persistido); ownership re-verificado.
  7. confirmar_e_criar_prazo (service extraído): gates de checklist/termo
     preservados — nada persiste quando um gate falha.
  8. gerar_kit_documental: embrulha gerar_kit_inicial (rascunhos HITL), sem
     ecoar o conteúdo integral dos documentos.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.ai.agent.tools import motores
from app.services.ai.agent.tools.context import AgentContext
from app.services import motor_peca_service as mps

TEXTO_CASO = (
    "Petição inicial distribuída pelo procedimento comum em face do cliente. "
    "O autor alega inadimplemento contratual e pede indenização por danos."
)


class _FakeDB:
    """DB mínimo: rastreia add/commit para provar (não-)persistência."""

    def __init__(self):
        self.added: list = []
        self.committed = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def get(self, model, pk):
        return None


def _case(**kw):
    base = dict(
        id="case-1", client_id="cli-1", tribunal=None, fase=None,
        area=SimpleNamespace(value="civil"),
        descricao_fatos=TEXTO_CASO,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ctx(db=None, role="advogado"):
    return AgentContext(
        db=db if db is not None else _FakeDB(),
        user=SimpleNamespace(id="u1", role=SimpleNamespace(value=role),
                             full_name="Advogado Teste"),
        case_id="case-1", client_id="cli-1", role=role, area="civil",
    )


@pytest.fixture
def acesso_ok(monkeypatch):
    case = _case()

    async def _ok(db, user, case_id):
        return case

    monkeypatch.setattr(motores, "verificar_acesso_caso", _ok)
    return case


@pytest.fixture
def texto_fake(monkeypatch):
    async def _texto(db, case, texto=None):
        return texto or TEXTO_CASO

    monkeypatch.setattr(mps, "texto_base_do_caso", _texto)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Registro / HITL / papéis
# ══════════════════════════════════════════════════════════════════════════════

_LEITURA = {
    "montar_cronologia", "identificar_rito_e_fase", "detectar_providencias",
    "calcular_prazo", "consultar_tabela_oab", "ler_checklist_peca",
    "classificar_area",
}
_ESCRITA = {"criar_prazo_confirmado", "gerar_kit_documental"}


class TestRegistroMotores:
    def test_tools_registradas_com_hitl_correto(self):
        from app.services.ai.agent.tools.registry import REGISTRY
        for nome in _LEITURA:
            spec = REGISTRY.get(nome)
            assert spec is not None, f"tool {nome} não registrada"
            assert spec.requer_confirmacao is False, nome
            assert spec.roles is None, nome  # leitura visível a qualquer papel
        for nome in _ESCRITA:
            spec = REGISTRY.get(nome)
            assert spec is not None, f"tool {nome} não registrada"
            assert spec.requer_confirmacao is True, nome  # HITL obrigatório
            assert "advogado" in spec.roles and "auxiliar" not in spec.roles

    def test_contrato_schema_anthropic(self):
        from app.services.ai.agent.tools.registry import REGISTRY
        for nome in _LEITURA | _ESCRITA:
            sch = REGISTRY.get(nome).schema_anthropic()
            assert set(sch) == {"name", "description", "input_schema"}
            assert sch["input_schema"]["type"] == "object"

    def test_tools_originais_intocadas(self):
        """Aditivo: contrato das 4 tools originais preservado."""
        from app.services.ai.agent.tools.registry import REGISTRY
        assert REGISTRY.get("buscar_precedentes").requer_confirmacao is False
        assert REGISTRY.get("ler_dossie").requer_confirmacao is False
        assert REGISTRY.get("gerar_minuta_peca").requer_confirmacao is True
        assert REGISTRY.get("registrar_nota_caso").requer_confirmacao is True


# ══════════════════════════════════════════════════════════════════════════════
# 2. calcular_prazo — projeção NUNCA confirmada, NUNCA cria Deadline
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcularPrazo:
    async def test_projecao_com_evento_base_legal_verbatim_sem_deadline(
            self, acesso_ok, texto_fake):
        db = _FakeDB()
        out = await motores.calcular_prazo(
            {"peca_codigo": "contestacao", "evento": "publicacao_dje",
             "data_evento": "2026-03-10"},
            _ctx(db),
        )
        # Termo derivado do evento (dies a quo = publicação) e projeção feita.
        assert out["termo_inicial"] == "2026-03-10"
        assert out["termo_inicial_origem"] == "derivado_de_evento"
        assert out["data_projetada"] is not None
        # Base legal VERBATIM do CATALOGO_PECAS (nunca reformulada).
        assert out["base_legal"] == mps.CATALOGO_PECAS["contestacao"]["base_legal"]
        assert (out["evento_processual"]["base_legal"]
                == "CPC, art. 224, §§2º e 3º")
        # INVARIANTES: nunca confirmado; nenhum Deadline criado.
        assert out["termo_inicial_confirmado"] is False
        assert out["pendente_confirmacao_humana"] is True
        assert "confirmação humana" in out["aviso_confirmacao"].lower()
        assert db.added == [] and db.committed == 0

    async def test_evento_incerto_nao_projeta_nada(self, acesso_ok, texto_fake):
        """Evento 'audiencia' sem confirmação de ciência → 'verificar': nada é
        presumido, sem data projetada, sem termo."""
        out = await motores.calcular_prazo(
            {"peca_codigo": "apelacao", "evento": "audiencia",
             "data_evento": "2026-03-10"},
            _ctx(),
        )
        assert out["termo_inicial"] is None
        assert out["data_projetada"] is None
        assert out["termo_inicial_confirmado"] is False
        assert out["evento_processual"]["contagem_confirmavel"] is False

    async def test_termo_explicito_tem_precedencia(self, acesso_ok, texto_fake):
        out = await motores.calcular_prazo(
            {"peca_codigo": "contestacao", "termo_inicial": "2026-03-12",
             "evento": "publicacao_dje", "data_evento": "2026-03-10"},
            _ctx(),
        )
        assert out["termo_inicial"] == "2026-03-12"
        assert out["termo_inicial_origem"] == "informado_pelo_advogado"
        assert out["termo_inicial_confirmado"] is False

    async def test_peca_desconhecida_erro_estruturado(self, acesso_ok):
        out = await motores.calcular_prazo({"peca_codigo": "inexistente"}, _ctx())
        assert out["erro"] == "peca_desconhecida"
        assert "contestacao" in out["pecas_validas"]

    async def test_data_invalida_erro(self, acesso_ok):
        out = await motores.calcular_prazo(
            {"peca_codigo": "contestacao", "termo_inicial": "10/03/2026"}, _ctx())
        assert "termo_inicial" in out["erro"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. Rito / providências — determinísticos, verbatim, confirmação humana
# ══════════════════════════════════════════════════════════════════════════════

class TestRitoEProvidencias:
    async def test_identificar_rito_e_fase(self, acesso_ok, texto_fake):
        out = await motores.identificar_rito_e_fase({}, _ctx())
        assert out["requer_confirmacao_humana"] is True
        assert out["rito"]["codigo"]  # rito determinístico do rito_engine
        assert out["fase_atual"] == out["rito"]["etapa_atual"]
        assert out["rito"]["requer_confirmacao_humana"] is True

    async def test_detectar_providencias_base_legal_do_catalogo(
            self, acesso_ok, texto_fake):
        out = await motores.detectar_providencias({}, _ctx())
        assert out["requer_confirmacao_humana"] is True
        for p in out["pecas_cabiveis"]:
            info = mps.prazo_da_peca(p["codigo"], out["rito"]["codigo"])
            # base legal e prazo VERBATIM do mapa determinístico.
            assert p["base_legal"] == info["base_legal"]
            assert p["prazo_dias"] == info["prazo_dias"]
        # Texto de inicial/procedimento comum → contestação entre as cabíveis.
        codigos = {p["codigo"] for p in out["pecas_cabiveis"]}
        assert "contestacao" in codigos

    async def test_rito_sem_mapeamento_avisa_selecao_manual(
            self, acesso_ok, monkeypatch):
        async def _texto(db, case, texto=None):
            return "audiência de instrução no juizado especial criminal jecrim"

        monkeypatch.setattr(mps, "texto_base_do_caso", _texto)
        out = await motores.detectar_providencias({}, _ctx())
        if not out["pecas_cabiveis"]:
            assert "manualmente" in out["pecas_aviso"]


# ══════════════════════════════════════════════════════════════════════════════
# 4. classificar_area — taxonomia determinística
# ══════════════════════════════════════════════════════════════════════════════

class TestClassificarArea:
    async def test_normaliza_sinonimos_juridicos(self, acesso_ok):
        out = await motores.classificar_area({"texto": "Direito do Trabalho"}, _ctx())
        assert out == {"area": "trabalhista", "reconhecida": True,
                       "metodo": "taxonomia_deterministica"}
        out2 = await motores.classificar_area({"texto": "Cível"}, _ctx())
        assert out2["area"] == "civil"

    async def test_sem_correspondencia_segura_decide_o_humano(self, acesso_ok):
        out = await motores.classificar_area({"texto": "xyz inexistente"}, _ctx())
        assert out["area"] is None and out["reconhecida"] is False
        assert "advogado" in out["aviso"]
        assert "trabalhista" in out["areas_validas"]

    async def test_texto_vazio_erro(self, acesso_ok):
        out = await motores.classificar_area({"texto": "  "}, _ctx())
        assert out["erro"] == "texto vazio"


# ══════════════════════════════════════════════════════════════════════════════
# 5. Checklist / tabela OAB / cronologia — embrulho verbatim
# ══════════════════════════════════════════════════════════════════════════════

class TestChecklistOABCronologia:
    async def test_ler_checklist_peca(self, acesso_ok, texto_fake, monkeypatch):
        itens_fake = [{"key": "procuracao_vigente", "titulo": "Procuração",
                       "ok": False, "detalhe": "Nenhuma procuração vigente."}]

        async def _chk(db, case, codigo, texto):
            assert codigo == "contestacao"
            return itens_fake, False

        monkeypatch.setattr(mps, "montar_checklist", _chk)
        out = await motores.ler_checklist_peca({"peca_codigo": "contestacao"}, _ctx())
        assert out["pronto"] is False and out["itens"] == itens_fake
        assert out["peca_nome"] == "Contestação"
        assert out["pressupostos"]  # pressupostos verbatim do catálogo

    async def test_ler_checklist_peca_desconhecida(self, acesso_ok):
        out = await motores.ler_checklist_peca({"peca_codigo": "nada"}, _ctx())
        assert out["erro"] == "peca_desconhecida"

    async def test_consultar_tabela_oab_verbatim_com_fonte(
            self, acesso_ok, monkeypatch):
        from app.services import geracao_documental as gd

        item = SimpleNamespace(
            item_codigo="3.1", descricao="Ação cível em geral",
            valor_minimo=2500.0, percentual=None, unidade="por processo",
            vigencia_inicio=date(2026, 1, 1), vigencia_fim=None,
            fonte="Tabela OAB/MG 2026 — Resolução X",
        )

        async def _itens(db, area, hoje, limite=5):
            assert area == "civil"
            return [item]

        monkeypatch.setattr(gd, "_itens_oab_vigentes", _itens)
        out = await motores.consultar_tabela_oab({"area": "Cível"}, _ctx())
        assert out["total"] == 1
        # VERBATIM com fonte obrigatória.
        assert out["itens"][0]["fonte"] == "Tabela OAB/MG 2026 — Resolução X"
        assert out["itens"][0]["valor_minimo"] == 2500.0
        assert "nao vinculante" in out["aviso"]

    async def test_consultar_tabela_oab_sem_item_nunca_inventa(
            self, acesso_ok, monkeypatch):
        from app.services import geracao_documental as gd

        async def _vazio(db, area, hoje, limite=5):
            return []

        monkeypatch.setattr(gd, "_itens_oab_vigentes", _vazio)
        out = await motores.consultar_tabela_oab({}, _ctx())  # área do caso (civil)
        assert out["total"] == 0 and out["itens"] == []
        assert "Nunca inventamos valores" in out["aviso"]

    async def test_montar_cronologia_ordena_ascendente(self, acesso_ok, monkeypatch):
        from app.services import visual_law_core as vl

        async def _eventos(db, case_id):
            return [  # contrato do montar_eventos_caso: mais recente primeiro
                {"data": date(2026, 3, 5), "categoria": "prazo",
                 "tipo": "processual", "descricao": "Prazo — Contestação"},
                {"data": date(2026, 2, 1), "categoria": "documento",
                 "tipo": "peticao", "descricao": "Petição inicial"},
            ]

        monkeypatch.setattr(vl, "montar_eventos_caso", _eventos)
        out = await motores.montar_cronologia({}, _ctx())
        assert out["total"] == 2
        assert out["ordenacao"] == "cronologica_ascendente"
        assert [e["data"] for e in out["eventos"]] == ["2026-02-01", "2026-03-05"]


# ══════════════════════════════════════════════════════════════════════════════
# 6. criar_prazo_confirmado — handler pós-aprovação HITL
# ══════════════════════════════════════════════════════════════════════════════

class TestCriarPrazoConfirmado:
    async def test_handler_confirma_termo_apos_aprovacao_hitl(
            self, acesso_ok, monkeypatch):
        """A aprovação humana na pausa HITL É a confirmação: o handler chama o
        service (fonte única do /motor-peca/gerar) com
        termo_inicial_confirmado=True e exigir_base_fatica=False."""
        capturado: dict = {}
        deadline = SimpleNamespace(
            id="dl-1", titulo="Prazo — Contestação",
            base_legal=mps.CATALOGO_PECAS["contestacao"]["base_legal"],
            tipo=SimpleNamespace(value="processual"),
        )

        async def _fake_service(db, cu, case, **kw):
            capturado.update(kw)
            return {"deadline": deadline, "data_prazo": date(2026, 4, 1),
                    "evento_info": None, "termo_inicial": date(2026, 3, 10),
                    "prazo_info": mps.prazo_da_peca("contestacao"),
                    "rito_codigo": "processo_civil_comum",
                    "texto_limpo": "x", "fatos": "x"}

        monkeypatch.setattr(mps, "confirmar_e_criar_prazo", _fake_service)
        out = await motores.criar_prazo_confirmado(
            {"peca_codigo": "contestacao", "termo_inicial": "2026-03-10"}, _ctx())
        assert capturado["termo_inicial_confirmado"] is True
        assert capturado["exigir_base_fatica"] is False
        assert capturado["origem"] == "agente_juridico"
        assert out["criado"] is True
        assert out["deadline"]["id"] == "dl-1"
        assert out["deadline"]["data_prazo"] == "2026-04-01"
        assert (out["deadline"]["base_legal"]
                == mps.CATALOGO_PECAS["contestacao"]["base_legal"])

    async def test_gate_bloqueado_vira_dado_estruturado(self, acesso_ok, monkeypatch):
        async def _bloqueia(db, cu, case, **kw):
            raise mps.GateBloqueado({
                "mensagem": "Geração bloqueada — checklist da peça com itens pendentes",
                "pendentes": [{"key": "procuracao_vigente", "ok": False}],
            })

        monkeypatch.setattr(mps, "confirmar_e_criar_prazo", _bloqueia)
        out = await motores.criar_prazo_confirmado(
            {"peca_codigo": "contestacao", "termo_inicial": "2026-03-10"}, _ctx())
        assert out["criado"] is False and out["erro"] == "gate_bloqueado"
        assert "checklist" in out["detalhe"]["mensagem"]

    async def test_ownership_reverificado_fail_closed(self, monkeypatch):
        async def _nega(db, user, case_id):
            raise PermissionError("sem acesso")

        monkeypatch.setattr(motores, "verificar_acesso_caso", _nega)
        with pytest.raises(PermissionError):
            await motores.criar_prazo_confirmado(
                {"peca_codigo": "contestacao"}, _ctx())


# ══════════════════════════════════════════════════════════════════════════════
# 7. Service extraído — gates preservados (nada persiste em falha de gate)
# ══════════════════════════════════════════════════════════════════════════════

class TestConfirmarECriarPrazoService:
    @pytest.fixture
    def checklist_pronto(self, monkeypatch):
        async def _chk(db, case, codigo, texto):
            return ([{"key": "ok", "titulo": "ok", "ok": True, "detalhe": "ok"}],
                    True)

        monkeypatch.setattr(mps, "montar_checklist", _chk)

    @pytest.fixture
    def audit_fake(self, monkeypatch):
        async def _audit(db, *a, **k):
            return None

        monkeypatch.setattr(mps, "criar_audit_log", _audit)

    async def test_sem_confirmacao_humana_gate_bloqueia_sem_persistir(
            self, texto_fake, checklist_pronto):
        db = _FakeDB()
        with pytest.raises(mps.GateBloqueado) as exc:
            await mps.confirmar_e_criar_prazo(
                db, _ctx().user, _case(),
                peca_codigo="contestacao", termo_inicial=date(2026, 3, 10),
                termo_inicial_confirmado=False,  # gate 2
            )
        assert exc.value.detail["termo_inicial_confirmado"] is False
        assert db.added == [] and db.committed == 0  # NADA persistido

    async def test_checklist_pendente_bloqueia_sem_persistir(
            self, texto_fake, monkeypatch):
        async def _chk(db, case, codigo, texto):
            return ([{"key": "procuracao_vigente", "titulo": "Procuração",
                      "ok": False, "detalhe": "pendente"}], False)

        monkeypatch.setattr(mps, "montar_checklist", _chk)
        db = _FakeDB()
        with pytest.raises(mps.GateBloqueado) as exc:
            await mps.confirmar_e_criar_prazo(
                db, _ctx().user, _case(),
                peca_codigo="contestacao", termo_inicial=date(2026, 3, 10),
                termo_inicial_confirmado=True,
            )
        assert "checklist" in exc.value.detail["mensagem"]
        assert db.added == [] and db.committed == 0

    async def test_confirmado_cria_deadline_auditado(
            self, texto_fake, checklist_pronto, audit_fake):
        from app.services.deadline_calculator import prazo_dias_uteis

        db = _FakeDB()
        termo = date(2026, 3, 10)
        r = await mps.confirmar_e_criar_prazo(
            db, _ctx().user, _case(),
            peca_codigo="contestacao", termo_inicial=termo,
            termo_inicial_confirmado=True, origem="agente_juridico",
        )
        assert db.committed == 1 and len(db.added) == 1
        d = db.added[0]
        assert d is r["deadline"]
        assert d.confirmado is True and d.origem == "agente_juridico"
        assert d.base_legal == mps.CATALOGO_PECAS["contestacao"]["base_legal"]
        # Data fatal determinística (15 dias úteis, recesso aplicado).
        assert r["data_prazo"] == prazo_dias_uteis(termo, 15, tribunal=None,
                                                   aplicar_recesso=True)


# ══════════════════════════════════════════════════════════════════════════════
# 8. gerar_kit_documental — rascunhos HITL, sem ecoar conteúdo integral
# ══════════════════════════════════════════════════════════════════════════════

class TestGerarKitDocumental:
    async def test_embrulha_gerar_kit_inicial_resumido(self, acesso_ok, monkeypatch):
        from app.services import geracao_documental as gd

        cliente = SimpleNamespace(id="cli-1", deleted_at=None)

        class _DB(_FakeDB):
            async def get(self, model, pk):
                return cliente

        capturado: dict = {}

        async def _fake_kit(db, case, cli, cu, **kw):
            capturado.update(kw)
            return {
                "case_id": case.id, "status": "rascunho", "aviso": gd.AVISO_RASCUNHO,
                "procuracao": {"legal_doc_id": "ld-1", "titulo": "Procuração",
                               "tipo_poderes": kw["tipo_poderes"],
                               "conteudo": "TEXTO GIGANTE DA PROCURAÇÃO"},
                "contrato": {"legal_doc_id": "ld-2", "titulo": "Contrato",
                             "valor_sugerido": {"origem": None, "sugerido": None},
                             "conteudo": "TEXTO GIGANTE DO CONTRATO"},
                "checklist": {"legal_doc_id": "ld-3", "titulo": "Checklist",
                              "conteudo": "TEXTO GIGANTE DO CHECKLIST"},
            }

        monkeypatch.setattr(gd, "gerar_kit_inicial", _fake_kit)
        out = await motores.gerar_kit_documental(
            {"tipo_poderes": "ad_judicia"}, _ctx(_DB()))
        assert out["criado"] is True and out["status"] == "rascunho"
        assert capturado["tipo_poderes"] == "ad_judicia"
        assert out["procuracao"]["legal_doc_id"] == "ld-1"
        # Conteúdo integral NÃO é ecoado ao loop (fica no LegalDoc rascunho).
        assert "conteudo" not in out["procuracao"]
        assert "conteudo" not in out["contrato"]
        assert "conteudo" not in out["checklist"]

    async def test_tipo_poderes_invalido(self, acesso_ok):
        out = await motores.gerar_kit_documental({"tipo_poderes": "plenos"}, _ctx())
        assert out["erro"] == "tipo_poderes_invalido"
        assert out["validos"] == ["ad_judicia", "ad_judicia_et_extra", "especiais"]

    async def test_cliente_inexistente(self, acesso_ok):
        out = await motores.gerar_kit_documental({}, _ctx(_FakeDB()))
        assert out["erro"] == "cliente_do_caso_nao_encontrado"
