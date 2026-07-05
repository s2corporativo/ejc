"""Pseudonimização reversível e consistente (LGPD art. 33/46) + modos por tarefa.

Dados FICTÍCIOS (CPF sintético 123.456.789-09, nomes inventados). Nenhum teste
toca rede. Contrato:
  - round-trip reidratar(pseudonimizar(t)) == t (CPF, CNPJ, processo, nomes);
  - consistência: mesma entidade → mesmo marcador; distintas → índices distintos;
  - relação preservada ("[CLIENTE_1] processa [PARTE_CONTRARIA_1]");
  - texto pseudonimizado sem PII estrutural residual;
  - modo_para_task: criminal→LOCAL_COMPLETO, analise_caso→EXTERNO_PSEUDONIMIZADO,
    resumo→MASCARAMENTO; override via AI_SANITIZATION_MODE_MAP respeitado.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.ai.pseudonymizer import (
    pseudonimizar,
    pseudonimizar_mensagens,
    reidratar,
    validar_sem_pii_pseudonimizado,
)
from app.services.ai.sanitization_policy import ModoSanitizacao, modo_para_task

CPF_FAKE = "123.456.789-09"
CPF2_FAKE = "987.654.321-00"
CNPJ_FAKE = "12.345.678/0001-99"
PROC_FAKE = "1234567-89.2020.8.13.0024"


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_round_trip_estrutural_e_nomes():
    texto = (
        f"O cliente João da Silva (CPF {CPF_FAKE}) contratou a ACME Ltda "
        f"(CNPJ {CNPJ_FAKE}) no processo {PROC_FAKE}."
    )
    entidades = {"cliente": ["João da Silva"], "empresa": ["ACME Ltda"]}
    ps, mapa = pseudonimizar(texto, entidades)
    # PII real não aparece no texto pseudonimizado.
    for pii in (CPF_FAKE, CNPJ_FAKE, PROC_FAKE, "João da Silva", "ACME Ltda"):
        assert pii not in ps
    assert reidratar(ps, mapa) == texto


def test_round_trip_advogado_e_parte_contraria():
    texto = "Dr. Fulano de Tal representa Maria Souza contra Empresa Ré XYZ."
    entidades = {
        "advogado": ["Fulano de Tal"],
        "cliente": ["Maria Souza"],
        "parte_contraria": ["Empresa Ré XYZ"],
    }
    ps, mapa = pseudonimizar(texto, entidades)
    assert "[ADVOGADO_1]" in ps and "[CLIENTE_1]" in ps and "[PARTE_CONTRARIA_1]" in ps
    assert reidratar(ps, mapa) == texto


# ── Consistência e preservação da relação ─────────────────────────────────────

def test_mesma_entidade_mesmo_marcador():
    texto = f"CPF {CPF_FAKE} do autor; novamente CPF {CPF_FAKE} no rodapé."
    ps, mapa = pseudonimizar(texto)
    assert ps.count("[CPF_1]") == 2          # mesma entidade → mesmo marcador
    assert "[CPF_2]" not in ps
    assert mapa == {"[CPF_1]": CPF_FAKE}


def test_entidades_distintas_indices_distintos():
    texto = f"Autor CPF {CPF_FAKE}; réu CPF {CPF2_FAKE}."
    ps, mapa = pseudonimizar(texto)
    assert "[CPF_1]" in ps and "[CPF_2]" in ps
    assert mapa["[CPF_1]"] == CPF_FAKE and mapa["[CPF_2]"] == CPF2_FAKE


def test_relacao_preservada():
    texto = "João da Silva processa a ACME Ltda por danos morais."
    entidades = {"cliente": ["João da Silva"], "parte_contraria": ["ACME Ltda"]}
    ps, _ = pseudonimizar(texto, entidades)
    assert "[CLIENTE_1] processa a [PARTE_CONTRARIA_1]" in ps


# ── Sem PII estrutural residual ───────────────────────────────────────────────

def test_pseudonimizado_sem_pii_residual():
    texto = (
        f"CPF {CPF_FAKE}, CNPJ {CNPJ_FAKE}, processo {PROC_FAKE}, "
        "e-mail teste@exemplo.com, tel (31) 99999-8888, CEP 30140-071"
    )
    ps, _ = pseudonimizar(texto)
    assert validar_sem_pii_pseudonimizado(ps) == []


# ── reidratar: idempotência e marcador ausente ────────────────────────────────

def test_reidratar_idempotente():
    texto = f"Processo {PROC_FAKE} do cliente."
    ps, mapa = pseudonimizar(texto)
    uma = reidratar(ps, mapa)
    assert reidratar(uma, mapa) == uma == texto  # 2ª passada não altera


def test_reidratar_ignora_marcador_ausente():
    assert reidratar("texto sem marcadores", {"[CPF_1]": CPF_FAKE}) == "texto sem marcadores"


# ── Mensagens (estado compartilhado entre system + user) ──────────────────────

def test_pseudonimizar_mensagens_estado_compartilhado():
    messages = [
        {"role": "system", "content": f"Contexto do cliente CPF {CPF_FAKE}."},
        {"role": "user", "content": f"Detalhe o caso do CPF {CPF_FAKE}."},
    ]
    limpos, mapa = pseudonimizar_mensagens(messages)
    # Mesma entidade em mensagens diferentes → mesmo marcador.
    assert "[CPF_1]" in limpos[0]["content"] and "[CPF_1]" in limpos[1]["content"]
    assert mapa == {"[CPF_1]": CPF_FAKE}
    for m in limpos:
        assert CPF_FAKE not in m["content"]


# ── modo_para_task ────────────────────────────────────────────────────────────

def test_modo_default_por_tarefa():
    assert modo_para_task("criminal") == ModoSanitizacao.LOCAL_COMPLETO
    assert modo_para_task("analise_caso") == ModoSanitizacao.EXTERNO_PSEUDONIMIZADO
    assert modo_para_task("resumo") == ModoSanitizacao.MASCARAMENTO
    assert modo_para_task("triagem") == ModoSanitizacao.MASCARAMENTO
    # Tarefa desconhecida → fallback seguro (mascaramento irreversível).
    assert modo_para_task("tarefa_inexistente") == ModoSanitizacao.MASCARAMENTO
    assert modo_para_task("CRIMINAL") == ModoSanitizacao.LOCAL_COMPLETO  # case-insensitive


def test_modo_override_por_config(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(
        st, "AI_SANITIZATION_MODE_MAP",
        '{"familia":"local_completo","analise_caso":"mascaramento"}',
    )
    assert modo_para_task("familia") == ModoSanitizacao.LOCAL_COMPLETO      # novo
    assert modo_para_task("analise_caso") == ModoSanitizacao.MASCARAMENTO   # sobrepõe default
    assert modo_para_task("criminal") == ModoSanitizacao.LOCAL_COMPLETO     # default preservado


def test_modo_override_invalido_cai_no_default(monkeypatch):
    st = get_settings()
    monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", "{json quebrado")
    assert modo_para_task("analise_caso") == ModoSanitizacao.EXTERNO_PSEUDONIMIZADO
    # Modo desconhecido em JSON válido é ignorado (cai no default).
    monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", '{"resumo":"modo_zumbi"}')
    assert modo_para_task("resumo") == ModoSanitizacao.MASCARAMENTO


# ── FIX 2 — piso não-rebaixável do LOCAL_COMPLETO ─────────────────────────────

def test_piso_local_completo_nao_rebaixavel(monkeypatch):
    """Override NÃO pode rebaixar tarefa de sigilo reforçado (default
    LOCAL_COMPLETO) para provider externo — ignora e mantém LOCAL_COMPLETO."""
    st = get_settings()
    monkeypatch.setattr(
        st, "AI_SANITIZATION_MODE_MAP",
        '{"criminal":"externo_pseudonimizado"}',
    )
    assert modo_para_task("criminal") == ModoSanitizacao.LOCAL_COMPLETO


def test_piso_reforco_para_local_completo_permitido(monkeypatch):
    """Reforçar QUALQUER tarefa para LOCAL_COMPLETO via override é permitido; e
    rebaixar criminal continua bloqueado no mesmo mapa."""
    st = get_settings()
    monkeypatch.setattr(
        st, "AI_SANITIZATION_MODE_MAP",
        '{"resumo":"local_completo","criminal":"mascaramento"}',
    )
    assert modo_para_task("resumo") == ModoSanitizacao.LOCAL_COMPLETO   # reforço aplicado
    assert modo_para_task("criminal") == ModoSanitizacao.LOCAL_COMPLETO  # rebaixamento ignorado


# ── FIX 4 — sincronismo placeholder do sanitizer × mapa de tipos ──────────────

def test_todo_placeholder_do_sanitizer_tem_tipo():
    """Todo placeholder em sanitizer._PATTERNS deve ter entrada em
    _TIPO_POR_PLACEHOLDER (evita marcador genérico 'PII' silencioso)."""
    from app.services.sanitizer import _PATTERNS
    from app.services.ai.pseudonymizer import _TIPO_POR_PLACEHOLDER
    for _pattern, placeholder in _PATTERNS:
        assert placeholder in _TIPO_POR_PLACEHOLDER, (
            f"placeholder {placeholder!r} do sanitizer sem tipo pseudonimizado"
        )
