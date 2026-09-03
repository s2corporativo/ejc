"""Validação de PERTINÊNCIA da citação (`app/services/ai/pertinencia.py`).

Lacuna nomeada pela auditoria do módulo de minutas: o EJC valida se a citação
EXISTE (DV do número CNJ, súmula na base curada, artigo no diploma certo e
vigente) e nunca se ela SUSTENTA a afirmação que acompanha. É o erro que
sobrevive a todos os gates e chega ao juiz — busca por entailment/NLI no
repositório retornava zero antes deste módulo.

O caso que motiva a feature, e que os testes usam: citar o **art. 373, I do
CPC** (existe, vigente, diploma certo — passa em todos os gates atuais) para
sustentar **inversão do ônus da prova**, que é o art. 6º, VIII do CDC. O texto
do 373, I diz o oposto: o ônus é do autor quanto ao fato constitutivo.

Nada toca rede ou banco: o gateway é mockado e a base é um fake que responde à
consulta do texto da autoridade. Textos legais transcritos abaixo são o teor
real dos dispositivos, usados como dado de teste.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.ai import pertinencia

pytestmark = pytest.mark.anyio

# Teor real do art. 373 do CPC/2015 (Lei 13.105/2015).
ART_373 = (
    "Art. 373. O ônus da prova incumbe: I - ao autor, quanto ao fato "
    "constitutivo de seu direito; II - ao réu, quanto à existência de fato "
    "impeditivo, modificativo ou extintivo do direito do autor."
)

PECA_ERRADA = (
    "Trata-se de ação de indenização por vício do produto. Requer-se a "
    "inversão do ônus da prova em favor do consumidor, nos termos do art. "
    "373, I do CPC. Requer-se ainda a condenação da ré ao pagamento das "
    "custas processuais."
)

PECA_CERTA = (
    "Compete ao autor demonstrar o fato constitutivo de seu direito, na "
    "forma do art. 373, I do CPC. Passa-se à narrativa dos fatos."
)


@pytest.fixture
def ligada(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "PERTINENCIA_ENABLED", True)
    monkeypatch.setattr(st, "AI_ENABLED", True)
    return st


def _resposta(veredito: str, trecho: str = "", motivo: str = "motivo fictício"):
    return SimpleNamespace(
        texto=f"VEREDITO: {veredito}\nTRECHO: {trecho}\nMOTIVO: {motivo}",
        modelo="m-fake", provedor="ollama", input_tokens=1, output_tokens=1,
    )


def _mock_gateway(monkeypatch, resposta, capturado: dict | None = None):
    async def fake_chat(messages, **kw):
        if capturado is not None:
            capturado["messages"] = messages
            capturado.update(kw)
        return resposta
    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)


# ── 1. Extração da afirmação ─────────────────────────────────────────────────

class TestExtrairAfirmacao:
    def test_recorta_a_frase_que_carrega_a_citacao(self):
        ini = PECA_ERRADA.index("art. 373")
        afirmacao = pertinencia.extrair_afirmacao(
            PECA_ERRADA, (ini, ini + len("art. 373, I do CPC")))
        assert "inversão do ônus da prova" in afirmacao
        # Não arrasta a frase seguinte (custas), que nada tem a ver.
        assert "custas processuais" not in afirmacao

    def test_span_invalido_devolve_vazio_sem_levantar(self):
        assert pertinencia.extrair_afirmacao(PECA_ERRADA, None) == ""
        assert pertinencia.extrair_afirmacao(PECA_ERRADA, (50, 10)) == ""
        assert pertinencia.extrair_afirmacao(PECA_ERRADA, (0, 99999)) == ""
        assert pertinencia.extrair_afirmacao("", (0, 1)) == ""

    def test_abreviacao_nao_e_fronteira_de_frase(self):
        """`art.` e `n.` não podem cortar a afirmação ao meio — o corte só vale
        antes de maiúscula, e o vocabulário jurídico é cheio de abreviação."""
        texto = "O autor invoca a norma. Aplica-se o art. 373, I do CPC ao caso."
        ini = texto.index("art. 373")
        afirmacao = pertinencia.extrair_afirmacao(texto, (ini, ini + 8))
        assert afirmacao.startswith("Aplica-se")


# ── 2. A barreira antialucinação: o trecho tem de existir na autoridade ──────

class TestTrechoConfere:
    def test_trecho_literal_confere(self):
        assert pertinencia.trecho_confere(
            "ao autor, quanto ao fato constitutivo de seu direito", ART_373)

    def test_tolera_acento_caixa_e_espaco_mas_nao_o_conteudo(self):
        assert pertinencia.trecho_confere(
            "AO AUTOR,  quanto ao  fato constitutivo de seu direito", ART_373)
        assert not pertinencia.trecho_confere(
            "ao autor cabe requerer a inversão do ônus da prova", ART_373)

    def test_trecho_curto_demais_e_rejeitado(self):
        """Trecho curto casaria por acaso e não provaria leitura da autoridade."""
        assert not pertinencia.trecho_confere("o ônus", ART_373)
        assert not pertinencia.trecho_confere("", ART_373)
        assert not pertinencia.trecho_confere(None, ART_373)


# ── 3. Veredito ──────────────────────────────────────────────────────────────

class TestAvaliarCitacao:
    async def test_citacao_impertinente_e_reprovada(self, ligada, monkeypatch):
        """O caso real: art. 373, I do CPC invocado para inversão do ônus."""
        _mock_gateway(monkeypatch, _resposta(
            "NAO_SUSTENTADA", motivo="O dispositivo atribui o ônus ao autor; "
            "não trata de inversão em favor do consumidor."))
        p = await pertinencia.avaliar_citacao(
            "Requer-se a inversão do ônus da prova, nos termos do art. 373, I do CPC.",
            ART_373, fonte="CPC/2015",
        )
        assert p.veredito == pertinencia.NAO_SUSTENTADA
        assert p.bloqueante is True

    async def test_citacao_pertinente_com_trecho_que_confere(self, ligada, monkeypatch):
        _mock_gateway(monkeypatch, _resposta(
            "SUSTENTADA", trecho="ao autor, quanto ao fato constitutivo de seu direito"))
        p = await pertinencia.avaliar_citacao(
            "Compete ao autor demonstrar o fato constitutivo, art. 373, I do CPC.",
            ART_373,
        )
        assert p.veredito == pertinencia.SUSTENTADA
        assert p.bloqueante is False

    async def test_sustentada_com_trecho_inventado_vira_indeterminada(
            self, ligada, monkeypatch):
        """O coração do módulo: sem esta conferência, a pertinência seria só uma
        segunda opinião da IA sobre a primeira. A IA 'concorda' e cita um
        fundamento que NÃO está no dispositivo — o veredito é descartado."""
        _mock_gateway(monkeypatch, _resposta(
            "SUSTENTADA",
            trecho="o juiz poderá inverter o ônus da prova em favor do consumidor"))
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.INDETERMINADA
        assert p.trecho_rejeitado is True
        assert p.bloqueante is False  # não saber ≠ saber que está errado

    async def test_falha_do_provedor_vira_indeterminada_sem_levantar(
            self, ligada, monkeypatch):
        async def explode(messages, **kw):
            raise RuntimeError("provedor fora do ar (simulado)")
        monkeypatch.setattr("app.services.ai_gateway.chat", explode)
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.INDETERMINADA
        assert p.bloqueante is False

    async def test_resposta_fora_do_formato_vira_indeterminada(
            self, ligada, monkeypatch):
        _mock_gateway(monkeypatch, SimpleNamespace(
            texto="Acho que sim, parece pertinente.", modelo="m", provedor="ollama",
            input_tokens=1, output_tokens=1))
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.INDETERMINADA

    async def test_afirmacao_e_autoridade_vao_delimitadas(self, ligada, monkeypatch):
        """Anti-injeção: o texto da autoridade vem da base e a afirmação vem de
        uma peça que pode ter sido montada a partir de OCR de terceiro."""
        cap: dict = {}
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"), cap)
        await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        user = next(m for m in cap["messages"] if m["role"] == "user")
        assert "[AFIRMACAO DA PECA::" in user["content"]
        assert "[TEXTO DA AUTORIDADE::" in user["content"]

    async def test_piso_de_sigilo_e_propagado(self, ligada, monkeypatch):
        """A afirmação carrega os FATOS do caso — num caso sigiloso, esta
        verificação não pode ser a porta dos fundos que o resto fechou."""
        from app.services.ai.sanitization_policy import ModoSanitizacao
        cap: dict = {}
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"), cap)
        await pertinencia.avaliar_citacao(
            "Afirmação fictícia.", ART_373,
            modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO,
        )
        assert cap["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO


# ── 4. Varredura do texto inteiro ────────────────────────────────────────────

class _DBAutoridade:
    """Sessão fake das DUAS consultas do caminho de artigo, distinguidas pelo
    SQL: a de LOCALIZAÇÃO (`_fonte_artigo`, 6 colunas, reusada do verificador de
    existência) e a de CONTEÚDO (`string_agg` dos chunks, 2 colunas)."""

    def __init__(self, texto: str | None = ART_373, titulo: str = "CPC/2015"):
        self._texto, self._titulo = texto, titulo

    async def execute(self, stmt, *_a, **_kw):
        sql = str(stmt)
        if "string_agg" in sql:                      # consulta de CONTEÚDO
            linha = (self._titulo, self._texto) if self._texto else None
        elif self._texto:                            # consulta de LOCALIZAÇÃO
            linha = ("doc-1", self._titulo, "planalto:cpc", 1, True, None)
        else:
            linha = None
        return SimpleNamespace(first=lambda: linha)


def _citacao(status="verificada", tipo="artigo", span=(0, 10)):
    return {
        "citacao": "art. 373 CPC", "tipo": tipo, "status": status,
        "numero": "373", "diploma": "CPC", "span": list(span),
        "fonte_verificacao": "CPC/2015",
    }


class TestAvaliarTexto:
    async def test_desligada_devolve_relatorio_vazio(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "PERTINENCIA_ENABLED", False)
        rel = await pertinencia.avaliar_texto(None, PECA_ERRADA, [_citacao()])
        assert rel.habilitada is False and rel.total == 0

    async def test_so_confronta_citacao_cuja_existencia_foi_confirmada(
            self, ligada, monkeypatch):
        """Para citação não verificada, o problema é a EXISTÊNCIA — o gate atual
        já cuida. Perguntar 'sustenta?' de algo que talvez nem exista confundiria
        o revisor e gastaria chamada de IA."""
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"))
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(), PECA_ERRADA, [_citacao(status="identificada")])
        assert rel.total == 0

    async def test_julgado_fica_indeterminado_e_nao_bloqueia(self, ligada):
        """A base não guarda ementa de julgado: dizer 'pertinente' seria
        inventar, e dizer 'impertinente' seria injusto. Escopo declarado."""
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(), PECA_ERRADA, [_citacao(tipo="processo_cnj")])
        assert rel.total == 1 and rel.indeterminadas == 1
        assert rel.nao_sustentadas == 0
        assert "base curada não guarda" in rel.itens[0]["motivo"]

    async def test_sem_texto_na_base_fica_indeterminado(self, ligada):
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(texto=None), PECA_ERRADA, [_citacao()])
        assert rel.indeterminadas == 1 and rel.nao_sustentadas == 0

    async def test_teto_por_chamada_e_declarado_nao_silencioso(
            self, ligada, monkeypatch):
        _mock_gateway(monkeypatch, _resposta(
            "SUSTENTADA", trecho="ao autor, quanto ao fato constitutivo de seu direito"))
        n = pertinencia.MAX_POR_CHAMADA + 3
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(), PECA_CERTA, [_citacao() for _ in range(n)])
        assert rel.total == n
        assert rel.sustentadas == pertinencia.MAX_POR_CHAMADA
        assert rel.indeterminadas == 3
        assert any("teto por chamada" in i["motivo"] for i in rel.itens)

    async def test_relatorio_agrega_e_explica(self, ligada, monkeypatch):
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"))
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(), PECA_ERRADA, [_citacao()])
        assert rel.nao_sustentadas == 1
        assert any("NÃO ampara" in m for m in rel.motivos)


# ── 5. Integração com o gate de citações ─────────────────────────────────────

class TestIntegracaoComOGate:
    async def test_nao_sustentada_vira_bloqueante(self):
        from app.services import citation_gate
        bloq = await citation_gate.avaliar_bloqueantes_pertinencia({
            "habilitada": True,
            "itens": [{"citacao": "art. 373 CPC", "tipo": "artigo",
                       "veredito": "nao_sustentada", "motivo": "não trata de inversão."}],
        })
        assert len(bloq) == 1
        assert "NÃO ampara" in bloq[0]["motivo"]

    async def test_indeterminada_nunca_bloqueia(self):
        """Não saber não é o mesmo que saber que está errado. Bloquear por
        indeterminação tornaria a dimensão inutilizável na primeira lacuna
        da base."""
        from app.services import citation_gate
        bloq = await citation_gate.avaliar_bloqueantes_pertinencia({
            "habilitada": True,
            "itens": [{"citacao": "x", "tipo": "artigo",
                       "veredito": "indeterminada", "motivo": "sem texto"},
                      {"citacao": "y", "tipo": "artigo",
                       "veredito": "sustentada", "motivo": "ok"}],
        })
        assert bloq == []

    async def test_dimensao_desligada_nao_bloqueia(self):
        from app.services import citation_gate
        assert await citation_gate.avaliar_bloqueantes_pertinencia(None) == []
        assert await citation_gate.avaliar_bloqueantes_pertinencia(
            {"habilitada": False, "itens": []}) == []

    async def test_falha_da_pertinencia_nao_derruba_o_gate_de_existencia(
            self, ligada, monkeypatch):
        """Uma verificação adicional que derrubasse a principal seria pior que
        não existir."""
        from app.services import citation_gate

        async def explode(*a, **kw):
            raise RuntimeError("falha inesperada na pertinência (simulada)")
        monkeypatch.setattr(pertinencia, "avaliar_texto", explode)

        async def fake_verificar(db, texto, **kw):
            return {"total": 0, "confirmadas": 0, "nao_encontradas": 0,
                    "citacoes": [], "score": 100}
        monkeypatch.setattr(
            "app.services.verificador_jurisprudencia.verificar_jurisprudencia",
            fake_verificar)

        rel = await citation_gate.validar_citacoes(None, "Texto fictício.")
        # Gate de EXISTÊNCIA intacto — o ponto do fail-safe.
        assert rel.bloqueia_aprovacao is False
        # E o estado é DISTINGUÍVEL de "dimensão desligada" (achado P2-5 do
        # pente fino 03/09): `None` significa desligada no schema, e devolver
        # `None` numa FALHA faria o revisor ler uma checagem que não rodou como
        # uma checagem que ele desligou. Mesma honestidade do `indeterminada`
        # por citação.
        assert rel.pertinencia is not None
        assert rel.pertinencia["erro"] is True
        assert rel.pertinencia["habilitada"] is True
        assert any("PERTINÊNCIA indisponível" in m for m in rel.motivos)

    async def test_desligada_de_fato_devolve_none(self, monkeypatch):
        """Contraprova: com a flag OFF, `None` continua significando
        'dimensão desligada' — os dois estados não se confundem."""
        from app.core.config import get_settings
        from app.services import citation_gate
        monkeypatch.setattr(get_settings(), "PERTINENCIA_ENABLED", False)

        async def fake_verificar(db, texto, **kw):
            return {"total": 0, "confirmadas": 0, "nao_encontradas": 0,
                    "citacoes": [], "score": 100}
        monkeypatch.setattr(
            "app.services.verificador_jurisprudencia.verificar_jurisprudencia",
            fake_verificar)

        rel = await citation_gate.validar_citacoes(None, "Texto fictício.")
        assert rel.pertinencia is None


# ── 6. Roteamento e nível — o defeito que tornaria a feature inútil ──────────
# Achado do pente fino de 03/09: sem entrada própria no gateway,
# `verificacao_pertinencia` caía no default `analise_juridica` e recebia o piso
# de nível "alto", que injeta o método FIRAC ("(1) FATOS … (5) CONCLUSÃO") num
# prompt cujo contrato inteiro é `VEREDITO:/TRECHO:/MOTIVO:` conferido por
# regex. A resposta viria em prosa, o parse falharia e TODA citação viraria
# `indeterminada` — a verificação silenciosamente inútil, sem erro nenhum.

class TestRoteamentoENivel:
    def test_tarefa_e_de_saida_estruturada(self):
        """Piso de nível "padrao" e modo de prosa ignorado — é o que impede o
        FIRAC de entrar num prompt de formato exato."""
        from app.services import ai_gateway
        assert pertinencia.TASK_TYPE in ai_gateway._TAREFAS_SAIDA_ESTRUTURADA
        assert ai_gateway._nivel_piso(pertinencia.TASK_TYPE) == "padrao"

    def test_nivel_padrao_nao_injeta_firac(self):
        """Prova direta: com "padrao" a instrução extra não traz FIRAC."""
        from app.services import ai_gateway
        msgs = ai_gateway._aplicar_nivel(
            [{"role": "system", "content": pertinencia._SYSTEM}],
            None, task_label=pertinencia.TASK_TYPE)
        assert not any("FIRAC" in m["content"] for m in msgs)

    def test_nivel_alto_injetaria_firac_em_tarefa_de_prosa(self):
        """Contraprova — o risco era real, não hipotético: numa tarefa de prosa
        o mesmo caminho injeta FIRAC."""
        from app.services import ai_gateway
        msgs = ai_gateway._aplicar_nivel(
            [{"role": "system", "content": "x"}], "alto", task_label="analise_juridica")
        assert any("FIRAC" in m["content"] for m in msgs)

    def test_cadeia_e_economica_nao_a_de_analise_juridica(self):
        """Pergunta fechada de 400 tokens, uma POR CITAÇÃO: cair na cadeia mais
        cara multiplicava o custo pelo número de citações da peça."""
        from app.services import ai_gateway
        assert pertinencia.TASK_TYPE in ai_gateway.TASK_ROUTING
        cadeia = [p for p, _ in ai_gateway.TASK_ROUTING[pertinencia.TASK_TYPE]]
        # Local primeiro, pago por último — mesma forma de `resumo`.
        assert cadeia[0] == "ollama"
        assert cadeia[-1] == "anthropic"

    def test_modelo_anthropic_e_o_rapido_nao_o_complexo(self):
        from app.core.config import get_settings
        from app.services import ai_gateway
        assert ai_gateway._resolver_modelo(
            "anthropic", pertinencia.TASK_TYPE, None
        ) == get_settings().ANTHROPIC_MODEL_RAPIDO

    async def test_call_site_pede_nivel_padrao_explicitamente(
            self, ligada, monkeypatch):
        """Segunda camada, no ponto que conhece o contrato da resposta: mesmo
        que o piso do gateway mude, este call site não regride."""
        cap: dict = {}
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"), cap)
        await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert cap["nivel_inteligencia"] == "padrao"


# ── 7. Achados ALTA do pente fino de 03/09 ──────────────────────────────────

class TestTextoDaAutoridade:
    """`texto_da_autoridade` é o insumo de TUDO: se ele traz o texto errado, a
    IA responde certo sobre o texto errado e a peça é bloqueada por engano."""

    class _DBEspiao:
        """Captura o SQL e os parâmetros das consultas."""

        def __init__(self, linha_conteudo=("CPC/2015", ART_373)):
            self.sqls: list[str] = []
            self.params: list[dict] = []
            self._conteudo = linha_conteudo

        async def execute(self, stmt, params=None, *_a, **_kw):
            sql = str(stmt)
            self.sqls.append(sql)
            self.params.append(params or {})
            if "string_agg" in sql:
                return SimpleNamespace(first=lambda: self._conteudo)
            return SimpleNamespace(
                first=lambda: ("doc-1", "CPC/2015", "planalto:cpc", 1, True, None))

    async def test_artigo_busca_o_CHUNK_nao_o_diploma_inteiro(self):
        """`_fonte_artigo` devolve o `doc_id` do CÓDIGO — há um documento por
        diploma. Agregar seus chunks entregava, para "art. 373 do CPC", o
        preâmbulo e os primeiros artigos cortados em 4000 caracteres; o modelo
        respondia NAO_SUSTENTADA (corretamente, sobre o texto errado) e, com
        CITACOES_POLITICA=bloquear (o DEFAULT), travava a aprovação de quase
        toda peça que citasse artigo."""
        db = self._DBEspiao()
        texto, _ = await pertinencia.texto_da_autoridade(
            db, {"tipo": "artigo", "numero": "373", "diploma": "CPC"})
        assert texto == ART_373
        sql_conteudo = next(s for s in db.sqls if "string_agg" in s)
        assert "kc.conteudo ~* :artigo_re" in sql_conteudo
        # E o regex é o do artigo pedido, não o do diploma.
        p_conteudo = db.params[db.sqls.index(sql_conteudo)]
        assert "373" in p_conteudo["artigo_re"]

    async def test_sumula_sem_tribunal_e_ambigua_e_nao_devolve_texto(self):
        """"Súmula 7" existe no STF, no STJ e no TST com textos DIFERENTES. A
        consulta anterior varria os quatro com `LIMIT 1` sem `ORDER BY`: o
        Postgres escolhia, a pertinência confrontava contra a súmula de um
        tribunal sorteado, e o resultado podia mudar entre execuções."""
        db = self._DBEspiao()
        texto, fonte = await pertinencia.texto_da_autoridade(
            db, {"tipo": "sumula", "numero": "7", "tribunal": None})
        assert (texto, fonte) == (None, None)
        assert db.sqls == []          # nem consultou — ambiguidade não vira SQL

    async def test_sumula_com_tribunal_consulta_so_aquele_tribunal(self):
        db = self._DBEspiao()
        await pertinencia.texto_da_autoridade(
            db, {"tipo": "sumula", "numero": "7", "tribunal": "STJ"})
        assert db.params[0]["k"] == ["sumula:stj:7"]


class TestGrafiaDoVeredito:
    """O veredito BLOQUEANTE era o mais sujeito a se perder por grafia — e se
    perdia na direção PERMISSIVA (`indeterminada` nunca bloqueia)."""

    @pytest.mark.parametrize("grafia", [
        "NAO_SUSTENTADA", "NÃO_SUSTENTADA", "NÃO SUSTENTADA",
        "NAO-SUSTENTADA", "não sustentada",
    ])
    async def test_negacao_em_portugues_natural_ainda_bloqueia(
            self, ligada, monkeypatch, grafia):
        _mock_gateway(monkeypatch, SimpleNamespace(
            texto=f"VEREDITO: {grafia}\nTRECHO: \nMOTIVO: não ampara",
            modelo="m", provedor="ollama", input_tokens=1, output_tokens=1))
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.NAO_SUSTENTADA
        assert p.bloqueante is True

    async def test_sustentada_nao_e_confundida_com_a_negacao(
            self, ligada, monkeypatch):
        _mock_gateway(monkeypatch, _resposta(
            "SUSTENTADA", trecho="ao autor, quanto ao fato constitutivo de seu direito"))
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.SUSTENTADA

    async def test_resposta_em_uma_linha_nao_vira_falsa_alucinacao(
            self, ligada, monkeypatch):
        """O lookahead exigia `\\n` antes de MOTIVO: numa resposta de uma linha,
        o grupo engolia " MOTIVO: …", `trecho_confere` reprovava, e uma
        transcrição FIEL era arquivada como "indício de fundamento inventado"."""
        literal = "ao autor, quanto ao fato constitutivo de seu direito"
        _mock_gateway(monkeypatch, SimpleNamespace(
            texto=f"VEREDITO: SUSTENTADA TRECHO: {literal} MOTIVO: confere",
            modelo="m", provedor="ollama", input_tokens=1, output_tokens=1))
        p = await pertinencia.avaliar_citacao("Afirmação fictícia.", ART_373)
        assert p.veredito == pertinencia.SUSTENTADA
        assert p.trecho_rejeitado is False


class TestEntidadesDoCaso:
    async def test_entidades_chegam_ao_gateway(self, ligada, monkeypatch):
        """A AFIRMAÇÃO é uma frase inteira da peça e carrega nomes em claro.
        Sem a lista do caso, só o NER heurístico do gateway os protegeria."""
        cap: dict = {}
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"), cap)
        await pertinencia.avaliar_citacao(
            "Afirmação fictícia.", ART_373,
            entidades={"cliente": ["João da Silva"]})
        assert cap["entidades"] == {"cliente": ["João da Silva"]}

    async def test_avaliar_texto_monta_as_entidades_uma_vez(
            self, ligada, monkeypatch):
        chamadas = {"n": 0}

        async def fake_entidades(db, case_id):
            chamadas["n"] += 1
            return {"cliente": ["João da Silva"]}
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades)

        cap: dict = {}
        _mock_gateway(monkeypatch, _resposta("NAO_SUSTENTADA"), cap)
        rel = await pertinencia.avaliar_texto(
            _DBAutoridade(), PECA_ERRADA, [_citacao(), _citacao()],
            case_id="caso-1")
        assert rel.nao_sustentadas == 2
        assert chamadas["n"] == 1     # uma vez por relatório, não por citação
        assert cap["entidades"] == {"cliente": ["João da Silva"]}
