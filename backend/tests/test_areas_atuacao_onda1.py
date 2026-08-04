"""Onda 1 — bloqueio de risco do módulo Áreas de Atuação (auditoria 2026-07).

Cobre, no padrão dos vizinhos (chamada direta às funções, sem harness de banco):
  (a) PATCH com schema extra="forbid" — mass assignment rejeitado com 422;
  (b) ferramentas BLOQUEADAS respondem 503 (indisponibilidade controlada);
  (c) ferramentas da matriz P0 carregam selo homologada=False + aviso;
  (d) parâmetro de classificação jurídica inválido → 422 (sem fallback silencioso);
  (e) EIRELI rejeitada em registros novos (POST e PATCH empresarial);
  (f) /pecas/demonstrativo rejeita ferramenta não homologada com 422;
  (g) Onda 3 (Issue #702) — `ferramenta` obrigatória e validada contra rotas
      reais + proveniência mínima (`versao_regra` conferido contra a versão
      vigente) rejeitam bypass por omissão e demonstrativo forjado.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import ramos
from app.routers.ramos import FERRAMENTAS_BLOQUEADAS, FERRAMENTAS_NAO_HOMOLOGADAS
from app.schemas.areas_atuacao import (
    AdminUpdate, BancarioUpdate, CivelUpdate,
    EmpresarialUpdate, PenalUpdate, TrabalhistaUpdate,
)


# ══════════════════════════════════════════════════════════════════════════
# (a) Mass assignment nos PATCH — campos de controle e desconhecidos → 422
# FastAPI converte ValidationError de body em resposta 422; validar o schema
# diretamente prova o comportamento sem precisar de app/banco de pé.
# ══════════════════════════════════════════════════════════════════════════
_SCHEMAS_UPDATE = [EmpresarialUpdate, CivelUpdate, PenalUpdate,
                   TrabalhistaUpdate, AdminUpdate, BancarioUpdate]


@pytest.mark.parametrize("schema", _SCHEMAS_UPDATE)
@pytest.mark.parametrize("campo_controle", [
    {"deleted_at": None},                       # reativação de registro excluído
    {"deleted_at": "2026-01-01T00:00:00Z"},     # soft-delete via PATCH
    {"case_id": "outro-caso"},                  # troca de vínculo (IDOR lateral)
    {"created_at": "2020-01-01T00:00:00Z"},
    {"updated_at": "2020-01-01T00:00:00Z"},
    {"id": "novo-id"},
    {"campo_que_nao_existe": 1},
])
def test_patch_rejeita_campo_de_controle_e_desconhecido(schema, campo_controle):
    with pytest.raises(ValidationError):
        schema(**campo_controle)


def test_patch_aceita_campos_da_whitelist_e_e_parcial():
    body = EmpresarialUpdate(observacoes="ok", capital_social=10_000.0)
    dump = body.model_dump(exclude_unset=True)
    assert dump == {"observacoes": "ok", "capital_social": 10_000.0}


def test_handlers_patch_usam_schema_tipado():
    """Regressão: nenhum PATCH de área volta a receber dict cru."""
    from typing import get_type_hints
    esperados = {
        ramos.emp_atualizar: EmpresarialUpdate,
        ramos.civ_atualizar: CivelUpdate,
        ramos.pen_atualizar: PenalUpdate,
        ramos.trab_atualizar: TrabalhistaUpdate,
        ramos.adm_atualizar: AdminUpdate,
        ramos.ban_atualizar: BancarioUpdate,
    }
    for handler, schema in esperados.items():
        # ramos.py usa `from __future__ import annotations` — resolver os hints.
        anot = get_type_hints(handler)["body"]
        assert anot is schema, f"{handler.__name__} deveria receber {schema.__name__}"


# ══════════════════════════════════════════════════════════════════════════
# (b) Mecanismo de bloqueio (503) — Onda 2 Fase A desbloqueou as 4 ferramentas
# originalmente bloqueadas (corrigidas em test_areas_atuacao_onda2.py); aqui
# permanece a garantia de que o MECANISMO segue funcional para bloqueios futuros.
# ══════════════════════════════════════════════════════════════════════════
def _assert_503(exc: HTTPException):
    assert exc.status_code == 503
    assert exc.detail["codigo"] == "ferramenta_nao_homologada"
    assert exc.detail["motivo"]
    assert "indisponível" in exc.detail["mensagem"]


def test_mecanismo_de_bloqueio_503_segue_funcional(monkeypatch):
    from app.services import homologacao_ferramentas as hf
    monkeypatch.setitem(hf.FERRAMENTAS_NAO_HOMOLOGADAS,
                        "/teste/ferramentas/bloqueada", "motivo de teste")
    with pytest.raises(HTTPException) as e:
        hf.bloquear_nao_homologada("/teste/ferramentas/bloqueada")
    _assert_503(e.value)


def test_bloqueadas_sao_subconjunto_da_matriz():
    assert FERRAMENTAS_BLOQUEADAS <= set(FERRAMENTAS_NAO_HOMOLOGADAS)
    # Onda 2 — Fase A: as 4 bloqueadas da Onda 1 foram corrigidas e desbloqueadas.
    assert len(FERRAMENTAS_BLOQUEADAS) == 0


def test_ferramentas_corrigidas_na_onda2_sairam_da_matriz():
    corrigidas = {
        # Fase A
        "/empresarial/ferramentas/prazos-rj",
        "/empresarial/ferramentas/juros-mora",
        "/penal/ferramentas/prazos-processuais",
        "/penal/ferramentas/verificar-anpp",
        "/civel/ferramentas/prazos-contestacao",
        "/penal/ferramentas/prescricao-punitiva",
        "/penal/ferramentas/prescricao-penal",
        # Fase B
        "/trabalhista-esp/ferramentas/prazos",
        "/trabalhista-esp/ferramentas/prescricao-trabalhista",
        "/transito/ferramentas/prazos-recurso",
        "/transito/ferramentas/pontuacao-cnh",
        "/admin-esp/ferramentas/recurso-multa-transito",
        # Fase C
        "/consumidor/ferramentas/devolucao-dobro",
        "/consumidor/ferramentas/prazos-cdc",
        "/previdenciario/ferramentas/prazos",
        "/empresarial/ferramentas/verificar-cade",
    }
    assert corrigidas.isdisjoint(FERRAMENTAS_NAO_HOMOLOGADAS)
    # Estado final pós-Fase C: APENAS a dosimetria segue selada.
    assert set(FERRAMENTAS_NAO_HOMOLOGADAS) == {"/penal/ferramentas/dosimetria"}


# ══════════════════════════════════════════════════════════════════════════
# (c) Selo de homologação nas ferramentas que seguem calculando
# ══════════════════════════════════════════════════════════════════════════
def _assert_selo(r: dict):
    assert r["homologada"] is False
    assert "não homologado para uso profissional" in r["aviso_homologacao"]
    assert "não gere demonstrativo" in r["aviso_homologacao"]


async def test_verificar_cade_sem_prazo_ficticio_e_sem_selo():
    """Onda 2 Fase C: o CADE saiu da matriz (resposta corrigida na Onda 1 —
    controle prévio, sem prazo fictício) e ganhou metadados de regra."""
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=100_000_000.0,
        valor_faturamento_outro_grupo=90_000_000.0, cu=None,
    )
    assert "homologada" not in r and "aviso_homologacao" not in r
    assert "prazo_notificacao" not in r
    assert "pode ser consumada antes da decisão" in r["controle_previo"]
    assert r["versao_regra"] == "2026-07" and r["fontes"]
    # Ramo pendente (sem 2º grupo) também sem o prazo fictício.
    p = await ramos.emp_cade(valor_faturamento_br=800_000_000.0,
                             valor_operacao=100_000_000.0, cu=None)
    assert "prazo_notificacao" not in p and "homologada" not in p


async def test_selo_demais_ferramentas_da_matriz():
    # Após a Fase C, só a dosimetria permanece com selo (simulador assistido).
    r = await ramos.penal_dosimetria(pena_minima_meses=24, pena_maxima_meses=96, cu=None)
    _assert_selo(r)


async def test_ferramenta_fora_da_matriz_nao_ganha_selo():
    r = await ramos.trab_deposito(valor_condenacao=8_000.0, cu=None)
    assert "homologada" not in r
    assert "aviso_homologacao" not in r


# ══════════════════════════════════════════════════════════════════════════
# (d) Classificação jurídica inválida → 422, sem cair em default
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("chamada", [
    lambda: ramos.consumidor_prazos_cdc(pretensao="inexistente",
                                        data_marco=date(2026, 1, 1), cu=None),
    lambda: ramos.previdenciario_prazos(natureza="inexistente", cu=None),
    lambda: ramos.previdenciario_carencia(
        beneficio="inexistente", categoria="empregada", meses_contribuicao=100,
        decorre_acidente_ou_doenca_isenta="nao", cu=None),
    lambda: ramos.lgpd_prazos(data_evento=date(2026, 1, 1), tipo="inexistente", cu=None),
    lambda: ramos.transito_valor_multa(gravidade="inexistente", cu=None),
    lambda: ramos.civ_dano_moral(tipo_caso="inexistente", salarios_minimos_pedido=10.0, cu=None),
    lambda: ramos.imobiliario_prazos_despejo(data_citacao=date(2026, 1, 1),
                                             forma_comunicacao="citacao_pessoal",
                                             fundamento="inexistente", cu=None),
    lambda: ramos.transito_prazos_recurso(
        fase="inexistente", data_notificacao_autuacao=date(2026, 1, 1), cu=None),
    lambda: ramos.transito_pontuacao_cnh(pontos_total=10, qtd_gravissimas=0,
                                         exerce_atividade_remunerada="talvez", cu=None),
    lambda: ramos.consumidor_devolucao_dobro(
        valor_cobrado_indevidamente=100.0, houve_pagamento="sim",
        cobranca_contraria_boa_fe_objetiva="sim", engano_justificavel="talvez", cu=None),
    lambda: ramos.imobiliario_distrato(valor_pago=1_000.0,
                                       regime_patrimonio_afetacao="talvez", cu=None),
    lambda: ramos.consumidor_negativacao(existe_inscricao_anterior="talvez", cu=None),
    lambda: ramos.previdenciario_tempo_contribuicao(idade=60, tempo_contribuicao_anos=35.0,
                                                    sexo="X", cu=None),
])
async def test_classificacao_invalida_retorna_422(chamada):
    with pytest.raises(HTTPException) as e:
        await chamada()
    assert e.value.status_code == 422


async def test_classificacao_valida_continua_funcionando():
    r = await ramos.previdenciario_carencia(
        beneficio="aposentadoria_idade_tc", categoria="empregada",
        meses_contribuicao=200, decorre_acidente_ou_doenca_isenta="nao", cu=None)
    assert r["carencia_cumprida"] is True
    r2 = await ramos.lgpd_prazos(data_evento=date(2026, 3, 2), tipo="resposta_titular", cu=None)
    assert r2["prazo_final"]


# ══════════════════════════════════════════════════════════════════════════
# (e) EIRELI rejeitada em registros novos (tipo extinto — Lei 14.195/2021)
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("valor", ["EIRELI", "eireli", " Eireli "])
def test_post_empresarial_rejeita_eireli(valor):
    with pytest.raises(ValidationError) as e:
        ramos.EmpresarialIn(case_id="c1", tipo_societario=valor)
    assert "EIRELI foi extinta" in str(e.value)


@pytest.mark.parametrize("valor", ["EIRELI", "eireli"])
def test_patch_empresarial_rejeita_eireli(valor):
    with pytest.raises(ValidationError) as e:
        EmpresarialUpdate(tipo_societario=valor)
    assert "EIRELI foi extinta" in str(e.value)


def test_tipos_societarios_vigentes_continuam_aceitos():
    assert ramos.EmpresarialIn(case_id="c1", tipo_societario="SLU").tipo_societario == "SLU"
    assert EmpresarialUpdate(tipo_societario="LTDA").tipo_societario == "LTDA"
    assert EmpresarialUpdate(tipo_societario=None).tipo_societario is None


# ══════════════════════════════════════════════════════════════════════════
# (f) Gate de homologação em /pecas/demonstrativo
# ══════════════════════════════════════════════════════════════════════════
def _cu_advogado():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"),
                           full_name="Advogado Teste", oab_number=None)


def _prova_provenencia(**overrides) -> dict:
    """Metadados de proveniência (Onda 3, Issue #702) válidos por padrão —
    `versao_regra` bate com a versão vigente (`ramos.VERSAO_REGRA_ATUAL`).
    Testes que querem exercitar o gate de proveniência sobrescrevem via
    `overrides`."""
    base = {"fontes": ["fonte de teste"], "vigencia_regra": "vigente",
            "versao_regra": ramos.VERSAO_REGRA_ATUAL}
    base.update(overrides)
    return base


@pytest.mark.parametrize("ferramenta", [
    "/penal/ferramentas/dosimetria",                     # selo (simulador assistido)
    "/api/penal/ferramentas/dosimetria",                 # com prefixo /api
    "/penal/ferramentas/dosimetria?pena_minima_meses=24",  # com querystring
    "/Penal/Ferramentas/Dosimetria",                     # casing
    "//penal//ferramentas//dosimetria",                  # barras duplicadas
    "/penal/ferramentas/dosimetri%61",                   # percent-encoding
    "/api//Penal/ferramentas/dosimetria/",               # combinação
])
async def test_demonstrativo_rejeita_ferramenta_nao_homologada(ferramenta):
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste", ferramenta=ferramenta,
                               **_prova_provenencia())
    with pytest.raises(HTTPException) as e:
        # O gate dispara antes de qualquer uso do banco → db=None é seguro aqui.
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "ferramenta_nao_homologada"
    assert e.value.detail["motivo"]


@pytest.fixture
def _demonstrativo_liberado(monkeypatch):
    """Libera a TRAVA GERAL de exportação de demonstrativo (AI-107/AI-113, PR
    #496) para exercitar isoladamente o gate POR FERRAMENTA (Onda 1, PR #493).

    Os dois gates nasceram em frentes paralelas e coexistem: a matriz por
    ferramenta é uma DENYLIST (o que não está nela passa), e a trava geral —
    `PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED`, default OFF — impede que uma
    calculadora que ninguém revisou vire documento por omissão. Estes dois
    testes verificam o gate por ferramenta, então precisam da trava aberta;
    sem a fixture, o 403 da trava responderia antes e o teste não estaria
    medindo o que o nome diz.

    Se o escritório decidir reabrir a exportação em produção, a mudança é no
    default de `PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED` — decisão do titular,
    registrada em config, não efeito colateral de merge."""
    from app.core.config import get_settings
    monkeypatch.setattr(
        get_settings(), "PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED", True)


def test_demonstrativo_sem_campo_ferramenta_reprova_gate():
    """INVERSO do teste original (Onda 3, Issue #702): `ferramenta` passou a
    ser OBRIGATÓRIA — a ausência do campo não passa mais silenciosamente pelo
    gate de homologação. Antes desta Issue, `test_demonstrativo_sem_campo_
    ferramenta_passa_do_gate` afirmava e cobria o bypass; este teste prova a
    negação: a omissão é rejeitada na própria validação do schema (Pydantic
    `ValidationError` — equivalente ao 422 que o FastAPI devolve na borda
    HTTP para erro de corpo da requisição), antes de qualquer gate de
    negócio ou uso do banco."""
    from app.routers.peca_geracao import DemonstrativoRequest
    with pytest.raises(ValidationError) as e:
        DemonstrativoRequest(titulo="Cálculo de teste", **_prova_provenencia())
    assert "ferramenta" in str(e.value)


async def test_demonstrativo_ferramenta_caminho_inexistente_422():
    """AC #702: caminho que não corresponde a NENHUMA rota real de ferramenta
    é rejeitado — não pode passar pela lógica de 'não está na matriz de não
    homologadas, logo está liberado' (a matriz é denylist, não allowlist)."""
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste",
                               ferramenta="/inventado/ferramentas/nao-existe",
                               **_prova_provenencia())
    with pytest.raises(HTTPException) as e:
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "ferramenta_desconhecida"


async def test_demonstrativo_versao_regra_divergente_reprova_forjado():
    """Mecanismo de proveniência (piso, opção (c) da Issue #702): `versao_regra`
    é o mesmo valor que a PRÓPRIA ferramenta carimba em toda resposta
    (ramos.VERSAO_REGRA_ATUAL). Um demonstrativo que alega uma versão que
    nunca foi a vigente não pode ter saído de uma execução real da
    ferramenta — é rejeitado mesmo com ferramenta homologada e caminho
    válido (o gate roda ANTES da trava geral, então nem depende dela estar
    liberada)."""
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(
        titulo="Cálculo de teste",
        ferramenta="/trabalhista-esp/ferramentas/deposito-recursal",
        fontes=["fonte forjada"], vigencia_regra="forjada",
        versao_regra="1999-01",   # nunca foi a versão vigente
    )
    with pytest.raises(HTTPException) as e:
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "versao_regra_divergente"


async def test_demonstrativo_ferramenta_homologada_passa_do_gate(_demonstrativo_liberado):
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste",
                               ferramenta="/trabalhista-esp/ferramentas/deposito-recursal",
                               **_prova_provenencia())
    with pytest.raises(AttributeError):   # passou do gate; parou só no db=None
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())


async def test_trava_geral_bloqueia_mesmo_ferramenta_homologada():
    """Não-regressão (AC #702): com a flag geral desligada (default), o
    comportamento segue sendo 403 mesmo com ferramenta homologada, caminho
    válido e proveniência correta. Sem este teste, um merge futuro poderia
    reabrir a exportação sem ninguém perceber."""
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste",
                               ferramenta="/trabalhista-esp/ferramentas/deposito-recursal",
                               **_prova_provenencia())
    with pytest.raises(HTTPException) as e:
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 403


async def test_ferramenta_nao_homologada_responde_422_mesmo_com_trava_fechada():
    """Ordem dos gates: o motivo ESPECÍFICO da não homologação precisa chegar ao
    advogado. Com a trava geral na frente, tudo virava um 403 genérico e o 422
    da matriz nunca aparecia."""
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste",
                               ferramenta="/penal/ferramentas/dosimetria",
                               **_prova_provenencia())
    with pytest.raises(HTTPException) as e:
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "ferramenta_nao_homologada"
