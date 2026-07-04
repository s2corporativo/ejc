# tests/test_peca_service.py — presets de peças processuais (peca_service).
# Cobre: tipos novos aceitos, aliases pt-BR resolvidos e perfil injetado no prompt.
from types import SimpleNamespace

import pytest

from app.models.legal_doc import PecaTipo
from app.services import peca_service as ps
from app.services.peca_service import (
    PERFIS_PECA,
    TIPO_PECA_LEGAL_DOC,
    TIPOS_PECA,
    TIPOS_PECA_ALIASES,
    _tipo_identificado,
    gerar_peca_pipeline,
)


# ── 1. Tipos novos aceitos ───────────────────────────────────────────────────

def test_tipos_novos_registrados():
    for tipo in ("contrarrazoes", "apelacao", "replica", "agravo_de_instrumento"):
        assert tipo in TIPOS_PECA
        assert tipo in TIPO_PECA_LEGAL_DOC
        assert tipo in PERFIS_PECA
    # "agravo" legado permanece válido (frontend envia esse literal)
    assert "agravo" in TIPOS_PECA
    assert PERFIS_PECA["agravo"] == PERFIS_PECA["agravo_de_instrumento"]


def test_mapeamento_legal_doc():
    assert TIPO_PECA_LEGAL_DOC["contrarrazoes"] == PecaTipo.contrarrazoes
    assert TIPO_PECA_LEGAL_DOC["apelacao"] == PecaTipo.recurso
    assert TIPO_PECA_LEGAL_DOC["agravo_de_instrumento"] == PecaTipo.recurso
    assert TIPO_PECA_LEGAL_DOC["replica"] == PecaTipo.outro


def test_perfis_conteudo_minimo():
    assert "art. 319" in PERFIS_PECA["peticao_inicial"]
    assert "337" in PERFIS_PECA["contestacao"]
    assert "PONTO A PONTO" in PERFIS_PECA["replica"].upper()
    assert "1.015" in PERFIS_PECA["agravo_de_instrumento"]
    assert "PREQUESTIONAMENTO" in PERFIS_PECA["apelacao"].upper()
    assert "admissibilidade" in PERFIS_PECA["contrarrazoes"]
    # todo perfil declara prazo e campos a preencher
    for chave, texto in PERFIS_PECA.items():
        assert "PRAZO" in texto.upper(), chave
        assert "CAMPOS A PREENCHER" in texto.upper(), chave


# ── 2. Aliases pt-BR resolvidos ──────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("recurso de apelação", "apelacao"),
    ("Apelação", "apelacao"),
    ("contrarrazões de apelação", "contrarrazoes"),
    ("Contrarrazões", "contrarrazoes"),
    ("réplica à contestação", "replica"),
    ("impugnação à contestação", "replica"),
    ("agravo de instrumento", "agravo_de_instrumento"),
    ("agravo", "agravo_de_instrumento"),
    ('{"tipo_confirmado": "agravo_de_instrumento"}', "agravo_de_instrumento"),
    ("petição inicial", "peticao_inicial"),
    ("contestação", "contestacao"),
])
def test_alias_resolvido(texto, esperado):
    assert _tipo_identificado(texto) == esperado


def test_aliases_apontam_para_tipos_validos():
    for alias, chave in TIPOS_PECA_ALIASES.items():
        assert chave in TIPOS_PECA, f"alias '{alias}' aponta para tipo inexistente"


# ── 3. Perfil injetado no prompt da etapa de redação ─────────────────────────

class _FakeDB:
    def add(self, obj):  # noqa: D401
        pass

    async def commit(self):
        pass

    async def execute(self, *a, **kw):
        raise RuntimeError("sem banco no teste")


async def test_perfil_injetado_no_prompt(monkeypatch):
    prompts_capturados: list[list[dict]] = []

    async def fake_chat(messages, **kw):
        prompts_capturados.append(messages)
        return SimpleNamespace(
            texto="ok", modelo="fake", provedor="fake",
            input_tokens=1, output_tokens=1,
        )

    async def fake_rag(db, query, limite=6, scope_client_id=None):
        return []

    monkeypatch.setattr(ps, "gw_chat", fake_chat)
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_rag)

    eventos = [
        e async for e in gerar_peca_pipeline(
            db=_FakeDB(),
            user_id="u1",
            tipo_peca="agravo_de_instrumento",
            area_direito="civil",
            descricao_fatos="Decisão interlocutória indeferiu tutela de urgência.",
            pedidos="Reforma da decisão.",
            nomes_proteger=[],
            case_id=None,
            instrucoes_adicionais=None,
        )
    ]

    assert any("event: concluido" in e for e in eventos)
    # o último prompt (etapa 7 — redação) deve conter o perfil do rito
    prompt_redacao = prompts_capturados[-1][1]["content"]
    assert "PERFIL DA PEÇA — AGRAVO DE INSTRUMENTO" in prompt_redacao
    assert "1.015" in prompt_redacao
    assert "1.016-1.018" in prompt_redacao
    assert "EFEITO SUSPENSIVO" in prompt_redacao.upper()


async def test_perfil_nao_injetado_para_tipo_sem_preset(monkeypatch):
    prompts_capturados: list[list[dict]] = []

    async def fake_chat(messages, **kw):
        prompts_capturados.append(messages)
        return SimpleNamespace(
            texto="ok", modelo="fake", provedor="fake",
            input_tokens=1, output_tokens=1,
        )

    async def fake_rag(db, query, limite=6, scope_client_id=None):
        return []

    monkeypatch.setattr(ps, "gw_chat", fake_chat)
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_rag)

    eventos = [
        e async for e in gerar_peca_pipeline(
            db=_FakeDB(),
            user_id="u1",
            tipo_peca="parecer",
            area_direito="civil",
            descricao_fatos="Consulta sobre viabilidade de ação.",
            pedidos="Parecer fundamentado.",
            nomes_proteger=[],
            case_id=None,
            instrucoes_adicionais=None,
        )
    ]

    assert any("event: concluido" in e for e in eventos)
    assert "PERFIL DA PEÇA" not in prompts_capturados[-1][1]["content"]
