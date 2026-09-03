"""Ficha viva do Banco de Teses (`app/services/ficha_viva_service.py`).

FASE "Legal Knowledge Skills" (§5 do Legal Drafting 2.0), implementada sobre a
estrutura canônica `teses` + `tese_caso_links` em vez de tabelas
`LegalSkill*` novas — decisão registrada no ledger de migrations do repositório
("a fonte de verdade é `teses` + `tese_caso_links`; não criar banco paralelo").

O que estes testes travam:
  • o histórico é imutável e não se enche de versões idênticas;
  • "fonte verificada" não é uma palavra digitada — exige vínculo real;
  • a recusa da ficha é registrada com justificativa e vira sinal de revisão;
  • a confiança é MEDIDA e não mente por omissão numa amostra de 1 caso.

Sem banco real: os objetos são os models SQLAlchemy não persistidos e a sessão
é um fake que só coleta `add()`. As funções que consultam (`_ultima_versao`,
`historico`) são exercitadas por injeção do último snapshot.
"""
from __future__ import annotations

import pytest

from app.models.tese import Tese, TeseOverride, TeseStatus, TeseTipo
from app.services import ficha_viva_service as fv

pytestmark = pytest.mark.anyio


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def _ficha(**kw) -> Tese:
    base = dict(
        id="tese-1",
        titulo="Cobrança indevida após quitação gera dano moral",
        descricao="Descrição fictícia para teste.",
        fundamentacao="art. 42, par. único, CDC",
        jurisprudencia="Julgado fictício de teste",
        contra_argumento="Ausência de prova da quitação",
        area_juridica="consumidor",
        tribunal="TJMG",
        magistrado=None,
        tags="consumidor,cobranca",
        observacoes=None,
        gatilhos=["cobrança após quitação", "negativação indevida"],
        tipo=TeseTipo.escritorio,
        status=TeseStatus.ativa,
        versao=1,
        vezes_usada=0,
        vezes_venceu=0,
        vezes_perdeu=0,
    )
    base.update(kw)
    return Tese(**base)


# ── 1. Snapshot e versionamento ──────────────────────────────────────────────

class TestSnapshot:
    def test_snapshot_serializa_enum_para_jsonb(self):
        snap = fv.montar_snapshot(_ficha())
        # Enum cru quebraria o JSONB na gravação.
        assert snap["tipo"] == "escritorio"
        assert snap["status"] == "ativa"
        assert snap["gatilhos"] == ["cobrança após quitação", "negativação indevida"]

    def test_snapshot_cobre_todos_os_campos_do_contrato(self):
        snap = fv.montar_snapshot(_ficha())
        assert set(snap) == set(fv.CAMPOS_SNAPSHOT)

    def test_sem_snapshot_anterior_ha_mudanca(self):
        assert fv.houve_mudanca(_ficha(), None) is True

    def test_snapshot_identico_nao_e_mudanca(self):
        f = _ficha()
        assert fv.houve_mudanca(f, fv.montar_snapshot(f)) is False

    def test_campo_alterado_e_mudanca(self):
        f = _ficha()
        anterior = fv.montar_snapshot(f)
        f.fundamentacao = "art. 42, par. único, CDC + Súmula 385/STJ"
        assert fv.houve_mudanca(f, anterior) is True


class TestRegistrarVersao:
    async def test_primeira_versao_nasce_com_numero_1(self, monkeypatch):
        async def sem_versao(db, tese_id):
            return None
        monkeypatch.setattr(fv, "_ultima_versao", sem_versao)

        db, f = _FakeDB(), _ficha()
        v = await fv.registrar_versao(db, f, user_id="u1", resumo_mudanca="criação")
        assert v is not None and v.versao == 1
        assert f.versao == 1
        assert db.added == [v]

    async def test_versao_seguinte_incrementa_e_avanca_a_ficha(self, monkeypatch):
        f = _ficha(versao=3)
        anterior = fv.montar_snapshot(f)
        f.jurisprudencia = "Outro julgado fictício"

        async def ultima(db, tese_id):
            return type("V", (), {"versao": 3, "conteudo": anterior})()
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        db = _FakeDB()
        v = await fv.registrar_versao(db, f, resumo_mudanca="troca de julgado")
        assert v.versao == 4 and f.versao == 4

    async def test_salvar_sem_alterar_nada_nao_gera_versao(self, monkeypatch):
        """Histórico cheio de versões idênticas é tão inútil quanto não ter
        histórico — ninguém acha a mudança que importa no meio do ruído."""
        f = _ficha(versao=2)
        snap = fv.montar_snapshot(f)

        async def ultima(db, tese_id):
            return type("V", (), {"versao": 2, "conteudo": snap})()
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        db = _FakeDB()
        assert await fv.registrar_versao(db, f) is None
        assert db.added == []
        assert f.versao == 2  # não avançou

    async def test_forcar_grava_mesmo_sem_mudanca(self, monkeypatch):
        f = _ficha(versao=2)
        snap = fv.montar_snapshot(f)

        async def ultima(db, tese_id):
            return type("V", (), {"versao": 2, "conteudo": snap})()
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        v = await fv.registrar_versao(_FakeDB(), f, forcar=True)
        assert v is not None and v.versao == 3


class TestDiferenca:
    def test_lista_so_o_que_mudou_com_de_e_para(self):
        f = _ficha()
        antes = fv.montar_snapshot(f)
        f.tribunal = "STJ"
        depois = fv.montar_snapshot(f)
        dif = fv.diferenca_entre_versoes(antes, depois)
        assert list(dif) == ["tribunal"]
        assert dif["tribunal"] == {"de": "TJMG", "para": "STJ"}

    def test_sem_mudanca_devolve_vazio(self):
        snap = fv.montar_snapshot(_ficha())
        assert fv.diferenca_entre_versoes(snap, snap) == {}


# ── 2. Lastro (fontes) ───────────────────────────────────────────────────────

class TestFontes:
    async def test_fonte_valida_e_aceita(self):
        db = _FakeDB()
        f = await fv.adicionar_fonte(
            db, tese_id="tese-1", elemento="fundamentacao",
            referencia="art. 42, par. único, CDC",
            trecho="O consumidor cobrado em quantia indevida tem direito à "
                   "repetição do indébito, por valor igual ao dobro do que "
                   "pagou em excesso.",
            knowledge_doc_id="doc-1", status_verificacao="verificada",
        )
        assert f.status_verificacao == "verificada"
        assert f.verificado_em is not None
        assert db.added == [f]

    async def test_trecho_obrigatorio(self):
        """Referência sem o texto que ela diz é exatamente o formato de uma
        citação alucinada."""
        with pytest.raises(fv.FichaVivaErro, match="trecho"):
            await fv.adicionar_fonte(
                db=_FakeDB(), tese_id="t", elemento="fundamentacao",
                referencia="Súmula 297/TST", trecho="   ")

    async def test_referencia_obrigatoria(self):
        with pytest.raises(fv.FichaVivaErro, match="[Rr]eferência"):
            await fv.adicionar_fonte(
                db=_FakeDB(), tese_id="t", elemento="fundamentacao",
                referencia="", trecho="texto fictício suficientemente longo")

    async def test_verificada_sem_vinculo_e_recusada(self):
        """Sem base curada, precedente ou URL oficial, 'verificada' seria só
        uma palavra digitada."""
        with pytest.raises(fv.FichaVivaErro, match="verificada"):
            await fv.adicionar_fonte(
                db=_FakeDB(), tese_id="t", elemento="jurisprudencia",
                referencia="REsp fictício", trecho="trecho fictício de teste",
                status_verificacao="verificada")

    async def test_elemento_fora_do_dominio_e_recusado(self):
        with pytest.raises(fv.FichaVivaErro, match="elemento"):
            await fv.adicionar_fonte(
                db=_FakeDB(), tese_id="t", elemento="chute",
                referencia="x", trecho="trecho fictício de teste")

    async def test_status_fora_do_dominio_e_recusado(self):
        with pytest.raises(fv.FichaVivaErro, match="status_verificacao"):
            await fv.adicionar_fonte(
                db=_FakeDB(), tese_id="t", elemento="fundamentacao",
                referencia="x", trecho="trecho fictício de teste",
                status_verificacao="mais_ou_menos")

    def test_cobertura_separa_verificado_de_declarado(self):
        """Uma ficha com 12 fontes não verificadas e outra com 2 verificadas
        não podem parecer igualmente sólidas."""
        class _F:
            def __init__(self, elemento, status):
                self.elemento, self.status_verificacao = elemento, status

        cob = fv.cobertura_de_fontes([
            _F("fundamentacao", "verificada"),
            _F("jurisprudencia", "nao_verificada"),
            _F("jurisprudencia", "nao_encontrada"),
        ])
        assert cob == {
            "total": 3, "verificadas": 1, "nao_verificadas": 2,
            "elementos_cobertos": ["fundamentacao", "jurisprudencia"],
            "elementos_sem_fonte": ["contra_argumento", "gatilho"],
        }


# ── 3. Recusa (overrides) ────────────────────────────────────────────────────

class TestOverrides:
    async def test_recusa_registra_a_versao_afastada(self):
        """Se a ficha mudar depois, o registro tem de continuar dizendo o que
        foi recusado de fato."""
        db, f = _FakeDB(), _ficha(versao=7)
        o = await fv.registrar_override(
            db, tese=f, case_id="caso-1", motivo="fato_distinto",
            justificativa="Neste caso não houve quitação prévia comprovada.")
        assert o.versao_tese == 7
        assert db.added == [o]

    async def test_justificativa_curta_e_recusada(self):
        """É a justificativa que transforma a recusa em sinal para revisar."""
        with pytest.raises(fv.FichaVivaErro, match="justificativa"):
            await fv.registrar_override(
                _FakeDB(), tese=_ficha(), case_id="c", motivo="estrategia",
                justificativa="não")

    async def test_motivo_fora_do_dominio_e_recusado(self):
        with pytest.raises(fv.FichaVivaErro, match="motivo"):
            await fv.registrar_override(
                _FakeDB(), tese=_ficha(), case_id="c", motivo="sei_la",
                justificativa="justificativa fictícia longa o bastante")

    def test_erro_na_ficha_repetido_pede_revisao(self):
        overrides = [
            TeseOverride(id=str(i), tese_id="t", case_id=f"c{i}",
                         motivo="erro_na_ficha", justificativa="j")
            for i in range(2)
        ]
        sinal = fv.sinal_de_revisao(overrides)
        assert sinal["precisa_revisao"] is True
        assert sinal["gatilho_largo"] is False
        assert any("erro na ficha" in r for r in sinal["recomendacoes"])

    def test_fato_distinto_repetido_aponta_gatilho_largo(self):
        """Diagnóstico DIFERENTE de 'ficha errada': a ficha pode estar certa e
        estar sendo oferecida onde não cabe."""
        overrides = [
            TeseOverride(id=str(i), tese_id="t", case_id=f"c{i}",
                         motivo="fato_distinto", justificativa="j")
            for i in range(3)
        ]
        sinal = fv.sinal_de_revisao(overrides)
        assert sinal["gatilho_largo"] is True
        assert sinal["precisa_revisao"] is False
        assert any("largo demais" in r for r in sinal["recomendacoes"])

    def test_uma_recusa_isolada_nao_dispara_nada(self):
        sinal = fv.sinal_de_revisao([
            TeseOverride(id="1", tese_id="t", case_id="c",
                         motivo="erro_na_ficha", justificativa="j")])
        assert sinal["precisa_revisao"] is False
        assert sinal["recomendacoes"] == []


# ── 4. Confiança MEDIDA ──────────────────────────────────────────────────────

class TestConfianca:
    def test_uma_vitoria_em_um_caso_nao_vira_confianca_alta(self):
        """O ponto do módulo: `taxa_sucesso` sozinha diria 100%. Número
        verdadeiro, conclusão falsa — e um advogado decide a tese da peça
        por ele."""
        c = fv.confianca(_ficha(vezes_venceu=1, vezes_perdeu=0))
        assert c["rotulo"] == "amostra_insuficiente"
        assert c["taxa_sucesso"] == 1.0          # a taxa vai junto, rotulada
        assert "não sustenta conclusão" in c["explicacao"]

    def test_amostra_suficiente_e_boa_taxa_vira_alta(self):
        c = fv.confianca(_ficha(vezes_venceu=8, vezes_perdeu=2))
        assert c["rotulo"] == "alta" and c["casos_decididos"] == 10

    def test_amostra_suficiente_e_taxa_ruim_vira_baixa(self):
        c = fv.confianca(_ficha(vezes_venceu=2, vezes_perdeu=8))
        assert c["rotulo"] == "baixa"

    def test_faixa_intermediaria_vira_media(self):
        c = fv.confianca(_ficha(vezes_venceu=3, vezes_perdeu=3))
        assert c["rotulo"] == "media"

    def test_sem_caso_decidido_nao_inventa_taxa(self):
        c = fv.confianca(_ficha())
        assert c["taxa_sucesso"] is None
        assert c["explicacao"] == "Nenhum caso decidido ainda."

    def test_overrides_entram_no_mesmo_retrato(self):
        c = fv.confianca(_ficha(vezes_venceu=8, vezes_perdeu=2), overrides=[
            TeseOverride(id=str(i), tese_id="t", case_id=f"c{i}",
                         motivo="jurisprudencia_virou", justificativa="j")
            for i in range(2)
        ])
        # Ficha com boa taxa histórica PODE precisar de revisão — a orientação
        # mudou depois dos casos que a mediram.
        assert c["rotulo"] == "alta"
        assert c["revisao"]["precisa_revisao"] is True


# ── 5. Gatilhos ──────────────────────────────────────────────────────────────

class TestGatilhos:
    def test_aceita_lista_json_e_csv(self):
        esperado = ["cobrança após quitação", "negativação indevida"]
        assert fv.normalizar_gatilhos(esperado) == esperado
        assert fv.normalizar_gatilhos(
            '["cobrança após quitação", "negativação indevida"]') == esperado
        assert fv.normalizar_gatilhos(
            "cobrança após quitação, negativação indevida") == esperado

    def test_remove_repeticao_ignorando_caixa_e_espaco(self):
        assert fv.normalizar_gatilhos(
            ["Cobrança Indevida", "cobrança  indevida", "  "]) == ["Cobrança Indevida"]

    def test_json_invalido_cai_para_csv_em_vez_de_perder_o_conteudo(self):
        """Recusar por formato faria o campo simplesmente não ser preenchido —
        o pior resultado possível para ele. E salvar como `["a"` seria salvar
        lixo: o fallback limpa os restos de sintaxe do JSON quebrado."""
        assert fv.normalizar_gatilhos('["a", "b"') == ["a", "b"]
        assert fv.normalizar_gatilhos('["cobrança indevida", "negativação"') == [
            "cobrança indevida", "negativação"]

    def test_valor_sem_sentido_devolve_vazio_sem_levantar(self):
        assert fv.normalizar_gatilhos(None) == []
        assert fv.normalizar_gatilhos(42) == []

    def test_teto_de_itens(self):
        assert len(fv.normalizar_gatilhos([f"gatilho {i}" for i in range(80)])) == 30
