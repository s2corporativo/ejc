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
        return SimpleNamespace(scalar_one_or_none=lambda: self._ficha,
                               scalars=lambda: iter(()))

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
