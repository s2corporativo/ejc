"""Acentuação nas minutas geradas (Onda 1 da refatoração).

A auditoria de julho/2026 registrou peças saindo sem acentuação. A causa não
estava no pipeline PDF/DOCX — `document_format.sem_caracteres_problematicos`
já preserva acento desde a remoção da dobra ASCII — e sim nas STRINGS DE ORIGEM
do gerador determinístico (`documental.py`) e nos avisos de rascunho: o texto da
procuração, do contrato de honorários e do relatório inicial estava escrito em
ASCII no próprio código.

Estes testes travam o teor acentuado no ponto de origem: se alguém reescrever
uma cláusula sem acento, a suíte reprova antes de o documento chegar ao cliente.
"""
from __future__ import annotations

from app.models.case import Case
from app.models.client import Client
from app.services.document_format import (
    aviso_minuta_automatica,
    aviso_rascunho_ia,
    padronizar_documento_juridico,
)
from app.services.documental import (
    _clausula_poderes,
    _contrato_honorarios,
    _procuracao,
    _relatorio_inicial,
)


# Grafias ASCII de termos jurídicos que NÃO podem voltar ao texto das minutas.
# Cada entrada é a forma errada; a correta traz acento.
_ASCII_PROIBIDO = (
    "PROCURACAO", "CLAUSULA", "HONORARIOS", "PRESTACAO", "SERVICOS",
    "ADVOCATICIOS", "RELATORIO", "JURIDICO", "REVISAO", "PADRAO",
    "RESCISAO", "PROTECAO", "COMUNICACAO", "ELETRONICA", "RENUNCIA",
    "acao", "acoes", "citacao", "citacoes", "quitacao", "procedencia",
    "juridica", "urgencia", "instancia", "jurisdicao", "audiencias",
    "conciliacao", "mediacao", "instrucao", "peticoes", "certidoes",
    "orgaos", "beneficios", "Justica", "depositos", "alvara", "clausula",
    "honorarios", "servicos", "exito", "economico", "paragrafo", "analise",
    "estrategia", "procuracao", "sintese", "revisao", "escritorio",
    "controversias", "correcao", "monetaria", "suspensao", "obrigacoes",
    "regulatorias", "execucao", "condicoes", "disposicao", "notificacoes",
)


def _sem_ascii_juridico(texto: str) -> list[str]:
    """Termos ASCII proibidos encontrados no texto (lista vazia = aprovado)."""
    return [termo for termo in _ASCII_PROIBIDO if termo in texto]


def _case() -> Case:
    return Case(titulo="Cobrança Indevida", numero_processo=None)


def _cli() -> Client:
    return Client(nome="Fulano de Tal")


def test_avisos_de_rascunho_sao_acentuados():
    for aviso in (aviso_rascunho_ia(), aviso_minuta_automatica()):
        assert "REVISÃO" in aviso
        assert "PADRÃO JURÍDICO-PROFISSIONAL" in aviso
        assert "responsável" in aviso
        assert not _sem_ascii_juridico(aviso)


def test_procuracao_ad_judicia_sai_acentuada():
    texto = _procuracao(_case(), _cli(), "Dra. Fulana")
    assert "PROCURAÇÃO AD JUDICIA" in texto
    assert "cláusula ad judicia" in texto
    assert "Juízo, Instância ou Tribunal" in texto
    assert not _sem_ascii_juridico(texto)


def test_procuracao_poderes_gerais_sai_acentuada_em_todas_as_alineas():
    texto = _procuracao(
        _case(), _cli(), "Dra. Fulana",
        tipo_poderes="ad_judicia_et_extra", permite_substabelecimento=True,
    )
    assert "tutelas de urgência" in texto
    assert "renunciar ao direito sobre que se funda a ação" in texto
    assert "Justiça Gratuita" in texto
    assert "audiências de conciliação, mediação" in texto
    assert not _sem_ascii_juridico(texto)


def test_titulos_das_clausulas_de_poderes_sao_acentuados():
    for tipo, esperado in (
        ("ad_judicia", "PROCURAÇÃO AD JUDICIA"),
        ("ad_judicia_et_extra", "PROCURAÇÃO AD JUDICIA ET EXTRA"),
        ("especiais", "PROCURAÇÃO COM PODERES ESPECIAIS"),
    ):
        titulo, corpo = _clausula_poderes(tipo, True, "poder X")
        assert titulo == esperado
        assert not _sem_ascii_juridico(corpo)


def test_contrato_de_honorarios_sai_acentuado_com_e_sem_proposta():
    for proposta in (
        None,
        {"valor": 5000, "forma_pagamento": "3x", "exito_percentual": 20, "versao": 2},
    ):
        texto = _contrato_honorarios(_case(), _cli(), "Dra. Fulana", "civel", proposta=proposta)
        assert "CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS E HONORÁRIOS" in texto
        assert "CLÁUSULA 1 - OBJETO" in texto
        assert "HONORÁRIOS DE ÊXITO" in texto
        assert not _sem_ascii_juridico(texto)


def test_relatorio_inicial_sai_acentuado():
    texto = _relatorio_inicial(_case(), _cli(), "civel")
    assert "RELATÓRIO JURÍDICO INICIAL" in texto
    assert "PRÓXIMAS PROVIDÊNCIAS" in texto
    assert "sujeita a revisão jurídica" in texto
    assert not _sem_ascii_juridico(texto)


def test_padronizacao_nao_desfaz_a_acentuacao_das_minutas():
    """Guarda o elo seguinte: o normalizador aplicado a toda minuta preserva
    acento (a dobra ASCII agressiva foi removida e não pode voltar)."""
    original = "Petição de execução — cláusula 3ª, § 2º, ação revisional."
    assert padronizar_documento_juridico(original) == (
        "Petição de execução - cláusula 3ª, § 2º, ação revisional."
    )
