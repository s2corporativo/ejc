"""Superfície de API da ficha viva do Banco de Teses (§5 do Legal Drafting 2.0).

Sem estes endpoints, `ficha_viva_service` seria código morto: o histórico
nunca se popularia e ninguém no sistema conseguiria registrar uma fonte ou uma
recusa. Os testes travam as quatro coisas que fazem a superfície valer:

  • o versionamento está LIGADO ao create e ao update (o risco real aqui é a
    feature existir e nunca ser acionada);
  • RBAC do Banco de Teses vale igual nos sub-recursos (staff lê, advogado+
    escreve) — rota nova nasce protegida;
  • registrar recusa exige ownership do CASO (senão é IDOR);
  • erro de domínio do service vira 422, não 500 — a regra é uma só, no
    service, não uma cópia no router.

Padrão do repo para rota sem Postgres (test_ai_idor_case_id_gates.py): handler
REAL chamado direto, fake de sessão, ownership monkeypatched. Sem rede, sem
banco. Dados fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.tese import Tese, TeseStatus, TeseTipo
from app.models.user import User, UserRole
from app.routers import teses as rot
from app.services import ficha_viva_service as fv

pytestmark = pytest.mark.anyio


def _user(role: UserRole = UserRole.advogado) -> User:
    return User(id="u-adv-1", role=role)


def _ficha(**kw) -> Tese:
    base = dict(
        id="tese-1", titulo="Título fictício da ficha para teste",
        descricao="Descrição fictícia.", fundamentacao="art. 42 CDC",
        jurisprudencia=None, contra_argumento=None, area_juridica="consumidor",
        tribunal="TJMG", magistrado=None, tags=None, observacoes=None,
        gatilhos=["cobrança após quitação"], tipo=TeseTipo.escritorio,
        status=TeseStatus.ativa, versao=1,
        vezes_usada=0, vezes_venceu=0, vezes_perdeu=0, taxa_sucesso=None,
        created_at=None, updated_at=None,
    )
    base.update(kw)
    return Tese(**base)


class _FakeDB:
    """Sessão fake: `execute()` devolve sempre a ficha configurada."""

    def __init__(self, ficha: Tese | None = None):
        self._ficha = ficha
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_kw):
        # `scalars()` precisa devolver algo REALMENTE iterável: dunder é
        # resolvido no tipo, então `SimpleNamespace(__iter__=...)` não serve.
        # `first()` responde à conferência de lastro do selo "verificada"
        # (`_exigir_lastro_conferivel`): o fake base representa "o documento
        # EXISTE"; `TestSeloVerificada._DBLastro` cobre o caso contrário.
        return SimpleNamespace(scalar_one_or_none=lambda: self._ficha,
                               scalars=lambda: iter(()),
                               first=lambda: ("doc-1",))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _liberar_caso(monkeypatch):
    async def fake(db, cu, case_id):
        return SimpleNamespace(id=case_id)
    # `verificar_acesso_caso` é importado no TOPO de routers/teses.py, então o
    # nome já está vinculado lá — patch no módulo de origem não teria efeito.
    monkeypatch.setattr(rot, "verificar_acesso_caso", fake)


def _bloquear_caso(monkeypatch):
    async def fake(db, cu, case_id):
        raise HTTPException(403, "Sem permissão para este caso")
    monkeypatch.setattr(rot, "verificar_acesso_caso", fake)


# ── 1. O versionamento está LIGADO ao ciclo de vida da ficha ─────────────────

class TestVersionamentoLigado:
    async def test_criar_ficha_grava_a_versao_1(self, monkeypatch):
        """A versão 1 é o estado ORIGINAL. Sem gravá-la na criação, o histórico
        começaria na primeira edição e o texto com que a ficha nasceu — o que
        fundamentou as primeiras peças — se perderia."""
        async def sem_versao(db, tese_id):
            return None
        monkeypatch.setattr(fv, "_ultima_versao", sem_versao)

        db = _FakeDB()
        out = await rot.criar_tese(
            rot.TeseIn(titulo="Ficha fictícia de teste",
                       descricao="Descrição fictícia suficientemente longa.",
                       gatilhos="cobrança após quitação, negativação indevida"),
            db=db, cu=_user())

        versoes = [o for o in db.added if type(o).__name__ == "TeseVersao"]
        assert len(versoes) == 1 and versoes[0].versao == 1
        assert versoes[0].resumo_mudanca == "Criação da ficha."
        # E o CSV de gatilhos foi normalizado na entrada.
        assert out["gatilhos"] == ["cobrança após quitação", "negativação indevida"]
        assert db.commits == 1

    async def test_editar_ficha_grava_versao_nova(self, monkeypatch):
        f = _ficha(versao=2)
        snap = fv.montar_snapshot(f)

        async def ultima(db, tese_id):
            return SimpleNamespace(versao=2, conteudo=snap)
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        db = _FakeDB(f)
        out = await rot.atualizar_tese(
            "tese-1",
            rot.TesePatch(jurisprudencia="Julgado fictício novo",
                          resumo_mudanca="Acrescentado julgado de suporte."),
            db=db, cu=_user())
        assert out["versao_registrada"] == 3
        assert f.versao == 3

    async def test_salvar_sem_alterar_nada_nao_polui_o_historico(self, monkeypatch):
        f = _ficha(versao=2)
        snap = fv.montar_snapshot(f)

        async def ultima(db, tese_id):
            return SimpleNamespace(versao=2, conteudo=snap)
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        db = _FakeDB(f)
        out = await rot.atualizar_tese(
            "tese-1", rot.TesePatch(tribunal="TJMG"), db=db, cu=_user())
        assert out["versao_registrada"] is None
        assert [o for o in db.added if type(o).__name__ == "TeseVersao"] == []
        assert f.versao == 2

    async def test_resumo_mudanca_nao_vira_campo_da_ficha(self, monkeypatch):
        """`resumo_mudanca` descreve a EDIÇÃO; gravá-lo como atributo da tese
        criaria uma coluna fantasma no snapshot."""
        f = _ficha()

        async def ultima(db, tese_id):
            return None
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        await rot.atualizar_tese(
            "tese-1", rot.TesePatch(tribunal="STJ", resumo_mudanca="mudou o tribunal"),
            db=_FakeDB(f), cu=_user())
        assert not hasattr(f, "resumo_mudanca") or \
            getattr(f, "resumo_mudanca", None) is None


# ── 2. RBAC — rota nova nasce protegida ──────────────────────────────────────

class TestRBAC:
    @pytest.mark.parametrize("papel", [UserRole.financeiro, UserRole.secretaria])
    async def test_fora_da_equipe_juridica_nao_le(self, papel):
        """Issue #694: allowlist EXATA — financeiro não acessa o Banco de Teses
        mesmo com ROLE_LEVEL acima de estagiário. Vale nos sub-recursos."""
        for handler in (rot.historico_da_ficha, rot.fontes_da_ficha,
                        rot.confianca_da_ficha, rot.listar_recusas_da_ficha):
            with pytest.raises(HTTPException) as e:
                await handler("tese-1", db=_FakeDB(_ficha()), cu=_user(papel))
            assert e.value.status_code == 403

    async def test_estagiario_le_mas_nao_escreve(self, monkeypatch):
        _liberar_caso(monkeypatch)
        estagiario = _user(UserRole.estagiario)
        # Lê.
        await rot.confianca_da_ficha("tese-1", db=_FakeDB(_ficha()), cu=estagiario)
        # Não escreve.
        with pytest.raises(HTTPException) as e:
            await rot.registrar_recusa_da_ficha(
                "tese-1",
                rot.OverrideIn(case_id="c1", motivo="estrategia",
                               justificativa="justificativa fictícia longa"),
                db=_FakeDB(_ficha()), cu=estagiario)
        assert e.value.status_code == 403

    async def test_ficha_inexistente_e_404(self):
        with pytest.raises(HTTPException) as e:
            await rot.confianca_da_ficha("nao-existe", db=_FakeDB(None), cu=_user())
        assert e.value.status_code == 404


# ── 3. Ownership do caso na recusa (IDOR) ────────────────────────────────────

class TestOwnershipDaRecusa:
    async def test_caso_alheio_e_barrado(self, monkeypatch):
        """O registro vincula a ficha a um caso concreto: escrever em caso de
        carteira alheia seria IDOR."""
        _bloquear_caso(monkeypatch)
        db = _FakeDB(_ficha())
        with pytest.raises(HTTPException) as e:
            await rot.registrar_recusa_da_ficha(
                "tese-1",
                rot.OverrideIn(case_id="caso-de-outro", motivo="fato_distinto",
                               justificativa="justificativa fictícia longa"),
                db=db, cu=_user())
        assert e.value.status_code == 403
        # Prova NEGATIVA: nada foi gravado nem commitado.
        assert db.added == [] and db.commits == 0

    async def test_caso_proprio_registra_com_a_versao_afastada(self, monkeypatch):
        _liberar_caso(monkeypatch)
        db = _FakeDB(_ficha(versao=5))
        out = await rot.registrar_recusa_da_ficha(
            "tese-1",
            rot.OverrideIn(case_id="caso-proprio", motivo="jurisprudencia_virou",
                           justificativa="O STJ mudou a orientação em 2026."),
            db=db, cu=_user())
        assert out["versao_tese"] == 5
        assert db.commits == 1


# ── 4. Erro de domínio vira 422, não 500 ─────────────────────────────────────

class TestErroDeDominio:
    async def test_fonte_verificada_sem_vinculo_e_422(self):
        """A invariante mora no service; o router só traduz. Sem isto, ela
        seria uma cópia — e as duas divergiriam."""
        with pytest.raises(HTTPException) as e:
            await rot.adicionar_fonte_da_ficha(
                "tese-1",
                rot.FonteIn(elemento="jurisprudencia", referencia="REsp fictício",
                            trecho="trecho fictício suficientemente longo",
                            status_verificacao="verificada"),
                db=_FakeDB(_ficha()), cu=_user())
        assert e.value.status_code == 422
        assert "verificada" in e.value.detail

    async def test_elemento_invalido_e_422(self):
        with pytest.raises(HTTPException) as e:
            await rot.adicionar_fonte_da_ficha(
                "tese-1",
                rot.FonteIn(elemento="chute", referencia="art. 42 CDC",
                            trecho="trecho fictício suficientemente longo"),
                db=_FakeDB(_ficha()), cu=_user())
        assert e.value.status_code == 422

    async def test_fonte_valida_e_gravada(self):
        db = _FakeDB(_ficha())
        out = await rot.adicionar_fonte_da_ficha(
            "tese-1",
            rot.FonteIn(elemento="fundamentacao", referencia="art. 42 CDC",
                        trecho="O consumidor cobrado em quantia indevida tem "
                               "direito à repetição do indébito.",
                        knowledge_doc_id="doc-1", status_verificacao="verificada"),
            db=db, cu=_user())
        assert out["status_verificacao"] == "verificada"
        assert db.commits == 1

    async def test_justificativa_curta_e_barrada_no_schema(self):
        """O piso da justificativa é o mesmo do service — importado, não
        recopiado, para as duas fronteiras não divergirem."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            rot.OverrideIn(case_id="c", motivo="estrategia", justificativa="não")


# ── 5. Corrida de versão (achado do pente fino de 03/09) ─────────────────────
# `registrar_versao` lê a ÚLTIMA versão e grava a seguinte. Dois PATCH
# concorrentes na MESMA ficha leriam a mesma "última" e tentariam gravar o
# mesmo número — o UNIQUE(tese_id, versao) rejeitaria o segundo com 500 e a
# edição se perderia. A premissa de worker único do repo NÃO protege: o
# servidor é async e interleava nos `await`.

class TestCorridaDeVersao:
    def test_o_select_da_edicao_trava_a_linha(self):
        """O lock é o que serializa as edições da MESMA ficha. Sem ele, o 409
        abaixo seria o comportamento normal em vez da última barreira."""
        import inspect
        fonte = inspect.getsource(rot.atualizar_tese)
        assert ".with_for_update()" in fonte

    async def test_colisao_residual_vira_409_e_nao_500(self, monkeypatch):
        """Chamador futuro que não trave a linha recebe um 409 acionável —
        'recarregue e reaplique' — em vez de um 500 com erro cru de banco."""
        from sqlalchemy.exc import IntegrityError

        class _DBQueColide(_FakeDB):
            def __init__(self, ficha):
                super().__init__(ficha)
                self.rollbacks = 0

            async def commit(self):
                raise IntegrityError("INSERT tese_versoes", {}, Exception("uq"))

            async def rollback(self):
                self.rollbacks += 1

        async def ultima(db, tese_id):
            return None
        monkeypatch.setattr(fv, "_ultima_versao", ultima)

        db = _DBQueColide(_ficha())
        with pytest.raises(HTTPException) as e:
            await rot.atualizar_tese(
                "tese-1", rot.TesePatch(tribunal="STJ"), db=db, cu=_user())
        assert e.value.status_code == 409
        assert "Recarregue" in e.value.detail
        # Rollback feito: a sessão não fica suja para o próximo uso.
        assert db.rollbacks == 1


# ── 6. Vazamento entre casos na LISTA de recusas (P1 do pente fino 03/09) ────
# `justificativa` é texto livre escrito por um advogado SOBRE UM CASO CONCRETO
# ("não aplicamos porque a vítima é menor e o padrasto confessou"). A rota
# devolvia isso e o `case_id` a qualquer membro de EQUIPE_JURIDICA —
# `estagiario` incluído —, de qualquer caso do escritório, inclusive de caso
# com `sigilo_reforcado`. É a mesma classe fechada pela Fase 3A, e a rota
# vizinha `casos-candidatos` já trazia o comentário "sem isso a varredura seria
# um vazamento".

class TestVisibilidadeDasRecusas:
    class _DBOverrides(_FakeDB):
        """Distingue a consulta FILTRADA (tem JOIN em cases) da irrestrita."""

        def __init__(self, ficha, todas, visiveis):
            super().__init__(ficha)
            self._todas, self._visiveis = todas, visiveis
            self.sqls: list[str] = []

        async def execute(self, stmt, *_a, **_kw):
            sql = str(stmt)
            if "tese_overrides" in sql:
                self.sqls.append(sql)
                linhas = self._visiveis if " JOIN cases" in sql else self._todas
                return SimpleNamespace(scalars=lambda: iter(linhas))
            return await super().execute(stmt, *_a, **_kw)

    @staticmethod
    def _override(case_id: str):
        from app.models.tese import TeseOverride
        return TeseOverride(
            id=f"o-{case_id}", tese_id="tese-1", case_id=case_id, versao_tese=1,
            motivo="fato_distinto",
            justificativa="A vítima é menor e os fatos não casam com a ficha.")

    async def test_equipe_so_ve_recusas_de_casos_que_pode_abrir(self):
        proprio, alheio = self._override("caso-meu"), self._override("caso-alheio")
        db = self._DBOverrides(_ficha(), [proprio, alheio], [proprio])
        out = await rot.listar_recusas_da_ficha(
            "tese-1", db=db, cu=_user(UserRole.advogado))

        assert [o["case_id"] for o in out["overrides"]] == ["caso-meu"]
        # E o corte é DECLARADO — o advogado sabe que há mais, sem ver o quê.
        assert out["total_no_escritorio"] == 2
        assert out["ocultos_por_visibilidade"] == 1
        # A consulta filtrada realmente juntou `cases`.
        assert any(" JOIN cases" in s for s in db.sqls)

    async def test_o_sinal_de_revisao_continua_sobre_TODAS(self):
        """Contagem por motivo não expõe caso nenhum, e é o dado que diz se a
        ficha institucional precisa ser revista. Filtrá-lo faria dois advogados
        verem diagnósticos diferentes da MESMA ficha."""
        db = self._DBOverrides(
            _ficha(),
            [self._override("c1"), self._override("c2")],
            [self._override("c1")])
        out = await rot.listar_recusas_da_ficha(
            "tese-1", db=db, cu=_user(UserRole.advogado))
        assert out["sinal"]["total_overrides"] == 2
        assert out["sinal"]["gatilho_largo"] is True   # 2 × fato_distinto
        assert len(out["overrides"]) == 1

    async def test_gestao_ve_tudo_sem_join(self):
        db = self._DBOverrides(
            _ficha(), [self._override("c1"), self._override("c2")], [])
        out = await rot.listar_recusas_da_ficha(
            "tese-1", db=db, cu=_user(UserRole.socio))
        assert len(out["overrides"]) == 2
        assert out["ocultos_por_visibilidade"] == 0
        assert not any(" JOIN cases" in s for s in db.sqls)


# ── 7. Selo "verificada" não é auto-atribuível (P2-3 do pente fino) ──────────
# A regra anterior aceitava QUALQUER `fonte_url`, então `fonte_url="x"` bastava.
# E o selo não é cosmético: `context_builder._lastro_das_fichas` seleciona
# exatamente `verificada` e injeta a fonte no dossiê do redator como `[FONTE
# VERIFICADA]`, enquanto a `fundamentacao` do catálogo vai como `[NÃO
# VERIFICADA]` — a hierarquia de confiança invertida.

class TestSeloVerificada:
    class _DBLastro(_FakeDB):
        def __init__(self, ficha, existe: bool):
            super().__init__(ficha)
            self._existe = existe

        async def execute(self, stmt, *_a, **_kw):
            sql = str(stmt)
            if "knowledge_docs" in sql or "authority_records" in sql:
                return SimpleNamespace(
                    first=lambda: ("doc-1",) if self._existe else None)
            return await super().execute(stmt, *_a, **_kw)

    async def test_url_qualquer_nao_confere_o_selo(self):
        with pytest.raises(HTTPException) as e:
            await rot.adicionar_fonte_da_ficha(
                "tese-1",
                rot.FonteIn(elemento="fundamentacao", referencia="Súmula fictícia",
                            trecho="trecho fictício suficientemente longo",
                            fonte_url="https://blog.exemplo.fictic.io/post",
                            status_verificacao="verificada"),
                db=self._DBLastro(_ficha(), existe=False), cu=_user())
        assert e.value.status_code == 422
        assert "lastro conferível" in e.value.detail

    async def test_url_nao_http_e_recusada(self):
        with pytest.raises(HTTPException) as e:
            await rot.adicionar_fonte_da_ficha(
                "tese-1",
                rot.FonteIn(elemento="fundamentacao", referencia="x y",
                            trecho="trecho fictício suficientemente longo",
                            fonte_url="javascript:alert(1)"),
                db=self._DBLastro(_ficha(), existe=True), cu=_user())
        assert e.value.status_code == 422
        assert "http(s)" in e.value.detail

    async def test_dominio_oficial_confere_o_selo(self):
        """Reusa a allowlist canônica de `knowledge_governance.fonte_oficial`."""
        out = await rot.adicionar_fonte_da_ficha(
            "tese-1",
            rot.FonteIn(elemento="fundamentacao", referencia="art. 373 CPC",
                        trecho="O ônus da prova incumbe ao autor.",
                        fonte_url="https://www.planalto.gov.br/ccivil_03/lei.htm",
                        status_verificacao="verificada"),
            db=self._DBLastro(_ficha(), existe=False), cu=_user())
        assert out["status_verificacao"] == "verificada"

    async def test_documento_inexistente_na_base_nao_confere_o_selo(self):
        with pytest.raises(HTTPException) as e:
            await rot.adicionar_fonte_da_ficha(
                "tese-1",
                rot.FonteIn(elemento="fundamentacao", referencia="art. 373 CPC",
                            trecho="trecho fictício suficientemente longo",
                            knowledge_doc_id="doc-que-nao-existe",
                            status_verificacao="verificada"),
                db=self._DBLastro(_ficha(), existe=False), cu=_user())
        assert e.value.status_code == 422

    async def test_documento_existente_confere_o_selo(self):
        out = await rot.adicionar_fonte_da_ficha(
            "tese-1",
            rot.FonteIn(elemento="fundamentacao", referencia="art. 373 CPC",
                        trecho="trecho fictício suficientemente longo",
                        knowledge_doc_id="doc-1", status_verificacao="verificada"),
            db=self._DBLastro(_ficha(), existe=True), cu=_user())
        assert out["status_verificacao"] == "verificada"

    async def test_nao_verificada_nao_exige_lastro_algum(self):
        """Referência ainda não ingerida continua registrável — com o status
        honesto e a URL guardada."""
        out = await rot.adicionar_fonte_da_ficha(
            "tese-1",
            rot.FonteIn(elemento="jurisprudencia", referencia="REsp fictício",
                        trecho="trecho fictício suficientemente longo",
                        fonte_url="https://exemplo.fictic.io/acordao"),
            db=self._DBLastro(_ficha(), existe=False), cu=_user())
        assert out["status_verificacao"] == "nao_verificada"
