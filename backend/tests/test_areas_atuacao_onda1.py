"""Onda 1 — bloqueio de risco do módulo Áreas de Atuação (auditoria 2026-07).

Cobre, no padrão dos vizinhos (chamada direta às funções, sem harness de banco):
  (a) PATCH com schema extra="forbid" — mass assignment rejeitado com 422;
  (b) ferramentas BLOQUEADAS respondem 503 (indisponibilidade controlada);
  (c) ferramentas da matriz P0 carregam selo homologada=False + aviso;
  (d) parâmetro de classificação jurídica inválido → 422 (sem fallback silencioso);
  (e) EIRELI rejeitada em registros novos (POST e PATCH empresarial);
  (f) /pecas/demonstrativo rejeita ferramenta não homologada com 422.
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
        "/empresarial/ferramentas/prazos-rj",
        "/empresarial/ferramentas/juros-mora",
        "/penal/ferramentas/prazos-processuais",
        "/penal/ferramentas/verificar-anpp",
        "/civel/ferramentas/prazos-contestacao",
        "/penal/ferramentas/prescricao-punitiva",
        "/penal/ferramentas/prescricao-penal",
    }
    assert corrigidas.isdisjoint(FERRAMENTAS_NAO_HOMOLOGADAS)


# ══════════════════════════════════════════════════════════════════════════
# (c) Selo de homologação nas ferramentas que seguem calculando
# ══════════════════════════════════════════════════════════════════════════
def _assert_selo(r: dict):
    assert r["homologada"] is False
    assert "não homologado para uso profissional" in r["aviso_homologacao"]
    assert "não gere demonstrativo" in r["aviso_homologacao"]


async def test_selo_verificar_cade_sem_prazo_ficticio():
    r = await ramos.emp_cade(
        valor_faturamento_br=800_000_000.0, valor_operacao=100_000_000.0,
        valor_faturamento_outro_grupo=90_000_000.0, cu=None,
    )
    _assert_selo(r)
    assert "prazo_notificacao" not in r
    assert "pode ser consumada antes da decisão" in r["controle_previo"]
    # Ramo pendente (sem 2º grupo) também sem o prazo fictício e com selo.
    p = await ramos.emp_cade(valor_faturamento_br=800_000_000.0,
                             valor_operacao=100_000_000.0, cu=None)
    _assert_selo(p)
    assert "prazo_notificacao" not in p


async def test_selo_demais_ferramentas_da_matriz():
    resultados = [
        # Dosimetria: corrigida na Onda 2, mas PERMANECE com selo (simulador assistido).
        await ramos.penal_dosimetria(pena_minima_meses=24, pena_maxima_meses=96, cu=None),
        await ramos.trab_prazos(data_sentenca=date(2026, 3, 2), cu=None),
        await ramos.trab_prescricao(data_demissao=date(2025, 1, 10), cu=None),
        await ramos.transito_prazos_recurso(data_notificacao=date(2026, 3, 2),
                                            valor_multa=293.47, fase="autuacao", cu=None),
        await ramos.adm_multa_transito(data_notificacao=date(2026, 3, 2),
                                       valor_multa=293.47, cu=None),
        await ramos.transito_pontuacao_cnh(pontos_total=25, categoria_profissional="sim", cu=None),
        await ramos.consumidor_devolucao_dobro(valor_cobrado=100.0, houve_ma_fe="sim", cu=None),
        await ramos.consumidor_prazos_cdc(data_fato=date(2026, 6, 1), tipo="fato", cu=None),
        await ramos.previdenciario_prazos(data_indeferimento=date(2026, 6, 1),
                                          tipo="recurso_administrativo", cu=None),
    ]
    for r in resultados:
        _assert_selo(r)


async def test_ferramenta_fora_da_matriz_nao_ganha_selo():
    r = await ramos.trab_deposito(valor_condenacao=8_000.0, cu=None)
    assert "homologada" not in r
    assert "aviso_homologacao" not in r


# ══════════════════════════════════════════════════════════════════════════
# (d) Classificação jurídica inválida → 422, sem cair em default
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("chamada", [
    lambda: ramos.consumidor_prazos_cdc(data_fato=date(2026, 1, 1), tipo="inexistente", cu=None),
    lambda: ramos.previdenciario_prazos(data_indeferimento=date(2026, 1, 1),
                                        tipo="inexistente", cu=None),
    lambda: ramos.previdenciario_carencia(meses_contribuicao=100, beneficio="inexistente", cu=None),
    lambda: ramos.lgpd_prazos(data_evento=date(2026, 1, 1), tipo="inexistente", cu=None),
    lambda: ramos.transito_valor_multa(gravidade="inexistente", cu=None),
    lambda: ramos.civ_dano_moral(tipo_caso="inexistente", salarios_minimos_pedido=10.0, cu=None),
    lambda: ramos.imobiliario_prazos_despejo(data_citacao=date(2026, 1, 1),
                                             fundamento="inexistente", cu=None),
    lambda: ramos.transito_prazos_recurso(data_notificacao=date(2026, 1, 1),
                                          valor_multa=100.0, fase="inexistente", cu=None),
    lambda: ramos.transito_pontuacao_cnh(pontos_total=10, categoria_profissional="talvez", cu=None),
    lambda: ramos.consumidor_devolucao_dobro(valor_cobrado=100.0, houve_ma_fe="talvez", cu=None),
    lambda: ramos.imobiliario_distrato(valor_pago=1_000.0,
                                       tem_patrimonio_afetacao="talvez", cu=None),
    lambda: ramos.consumidor_negativacao(existe_inscricao_anterior_legitima="talvez", cu=None),
    lambda: ramos.previdenciario_tempo_contribuicao(idade=60, tempo_contribuicao_anos=35.0,
                                                    sexo="X", cu=None),
])
async def test_classificacao_invalida_retorna_422(chamada):
    with pytest.raises(HTTPException) as e:
        await chamada()
    assert e.value.status_code == 422


async def test_classificacao_valida_continua_funcionando():
    r = await ramos.previdenciario_carencia(meses_contribuicao=200,
                                            beneficio="aposentadoria", cu=None)
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


@pytest.mark.parametrize("ferramenta", [
    "/penal/ferramentas/dosimetria",                     # selo (simulador assistido)
    "/consumidor/ferramentas/devolucao-dobro",           # selo
    "/api/consumidor/ferramentas/devolucao-dobro",       # com prefixo /api
    "/consumidor/ferramentas/prazos-cdc?tipo=fato",      # com querystring
    "/Consumidor/Ferramentas/Devolucao-Dobro",           # casing
    "//consumidor//ferramentas//devolucao-dobro",        # barras duplicadas
    "/consumidor/ferramentas/devolucao%2Ddobro",         # percent-encoding
    "/api//Penal/ferramentas/dosimetria/",               # combinação
])
async def test_demonstrativo_rejeita_ferramenta_nao_homologada(ferramenta):
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste", ferramenta=ferramenta)
    with pytest.raises(HTTPException) as e:
        # O gate dispara antes de qualquer uso do banco → db=None é seguro aqui.
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
    assert e.value.status_code == 422
    assert e.value.detail["codigo"] == "ferramenta_nao_homologada"
    assert e.value.detail["motivo"]


async def test_demonstrativo_sem_campo_ferramenta_passa_do_gate():
    """Retrocompatibilidade: sem `ferramenta`, o gate não interfere (a chamada
    segue até o banco — db=None estoura AttributeError, prova de que NÃO houve
    rejeição 422 nem quebra de contrato para clientes antigos)."""
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste")
    with pytest.raises(AttributeError):
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())


async def test_demonstrativo_ferramenta_homologada_passa_do_gate():
    from app.routers.peca_geracao import DemonstrativoRequest, gerar_demonstrativo
    req = DemonstrativoRequest(titulo="Cálculo de teste",
                               ferramenta="/trabalhista-esp/ferramentas/deposito-recursal")
    with pytest.raises(AttributeError):   # passou do gate; parou só no db=None
        await gerar_demonstrativo(req, db=None, cu=_cu_advogado())
