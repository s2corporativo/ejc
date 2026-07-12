"""Fase D — controle de versão/numeração de peças (rodapé EJC-<RAMO>-<NNN>).

Cobre, sem depender de Postgres:
  - formatação/sigla do código por ramo e a linha de controle do rodapé;
  - atomicidade da numeração exercitada com um fake do UPSERT ... RETURNING;
  - propriedade RENDER-ONLY: a linha de controle é injetada só no HTML/DOCX,
    nunca no corpo/prompt da IA;
  - migration 090 offline (revisão/head, DDL idempotente) e colunas no model.

Com RUN_DB_TESTS=1 e Postgres migrado, valida o incremento atômico real por
ramo (civil: 001, 002; ramo novo reinicia em 001).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.peca_numeracao import (
    ABREV_AREA,
    linha_controle,
    proximo_codigo_peca,
    sigla_area,
    status_label,
)


# ── 1. Sigla por ramo + fallback ─────────────────────────────────────────────

def test_sigla_cobre_ramos_conhecidos():
    assert sigla_area("civil") == "CIV"
    assert sigla_area("trabalhista") == "TRAB"
    assert sigla_area("tributario") == "TRIB"
    assert sigla_area("consumidor") == "CDC"
    assert sigla_area("digital_lgpd") == "LGPD"


def test_sigla_normaliza_caixa_e_espacos():
    assert sigla_area("  CIVIL  ") == "CIV"


def test_sigla_fallback_ramo_desconhecido():
    # 3 primeiras letras em maiúsculas quando o ramo não está no mapa.
    assert sigla_area("marítimo") == "MAR"
    assert sigla_area("") == "GEN"


def test_abrev_cobre_as_17_areas_direito():
    from app.services.peca_service import AREAS_DIREITO

    assert len(AREAS_DIREITO) == 17
    faltando = [a for a in AREAS_DIREITO if a not in ABREV_AREA]
    assert not faltando, f"ramos sem sigla dedicada: {faltando}"


# ── 2. Numeração atômica (fake do UPSERT ... RETURNING) ──────────────────────

class _FakeResult:
    def __init__(self, valor: int):
        self._valor = valor

    def scalar_one(self) -> int:
        return self._valor


class _FakeDB:
    """Emula o INSERT ... ON CONFLICT ... RETURNING: devolve valores em sequência."""

    def __init__(self, sequencia):
        self._seq = iter(sequencia)
        self.chamadas = 0

    async def execute(self, *_a, **_k):
        self.chamadas += 1
        return _FakeResult(next(self._seq))


async def test_proximo_codigo_formata_zero_padding_e_sigla():
    db = _FakeDB([1, 2, 3])
    assert await proximo_codigo_peca(db, "civil") == "EJC-CIV-001"
    assert await proximo_codigo_peca(db, "civil") == "EJC-CIV-002"
    assert await proximo_codigo_peca(db, "civil") == "EJC-CIV-003"
    assert db.chamadas == 3


async def test_proximo_codigo_ramo_desconhecido_usa_fallback():
    db = _FakeDB([1])
    assert await proximo_codigo_peca(db, "espacial") == "EJC-ESP-001"


async def test_proximo_codigo_passa_de_999_sem_truncar():
    db = _FakeDB([1234])
    assert await proximo_codigo_peca(db, "civil") == "EJC-CIV-1234"


# ── 3. Linha de controle do rodapé ───────────────────────────────────────────

def test_linha_controle_formato_completo():
    from datetime import date

    linha = linha_controle(
        codigo_peca="EJC-CIV-007",
        titulo="Petição Inicial",
        versao=1,
        status="aprovada",
        revisado_em=date(2026, 7, 12),
    )
    assert linha == "EJC-CIV-007 | Petição Inicial | v1.0 | revisada em 12/07/2026 | Aprovada"


def test_linha_controle_degrada_sem_codigo_nem_revisao():
    linha = linha_controle(
        codigo_peca=None, titulo=None, versao=None, status=None, revisado_em=None,
    )
    # Não quebra e sinaliza pendência de revisão.
    assert "revisão pendente" in linha
    assert linha.startswith("EJC-")


def test_status_label_aceita_enum_string_e_none():
    from app.models.legal_doc import PecaStatus

    assert status_label(PecaStatus.em_revisao) == "Em revisão"
    assert status_label("protocolada") == "Protocolada"
    assert status_label(None) == "—"


# ── 4. Render: injeção só no HTML, nunca no corpo da IA ──────────────────────

def test_html_injeta_rodape_controle_quando_ha_codigo():
    from app.services.pdf_service import _art_peca_html

    corpo_ia = "<p>Texto da peça gerado pela IA, sem qualquer código.</p>"
    html = _art_peca_html(
        "Petição Inicial", corpo_ia,
        pronto_protocolo=True,
        codigo_peca="EJC-TRAB-042", versao=2, status="aprovada",
    )
    # Código aparece no meta-grid e na linha de controle (footer-doc).
    assert "EJC-TRAB-042" in html
    assert 'class="footer-doc"' in html
    assert "v2.0" in html
    # O corpo da IA NÃO continha o código — foi injetado só no render.
    assert "EJC-TRAB-042" not in corpo_ia


def test_html_degrada_sem_codigo_sem_footer_controle():
    from app.services.pdf_service import _art_peca_html

    html = _art_peca_html(
        "Minuta", "<p>corpo</p>", pronto_protocolo=False, codigo_peca=None,
    )
    # Sem código não há linha de controle EJC-... no rodapé, mas renderiza.
    assert "EJC-" not in html
    assert "Minuta revisavel" in html


def test_pipeline_nao_injeta_codigo_no_prompt_ou_corpo():
    """Regra 9 do padrão-ouro: o rodapé/código é do SISTEMA (render), nunca do
    texto gerado. O módulo do pipeline não deve montar a linha de controle."""
    src = Path("app/services/peca_service.py").read_text(encoding="utf-8")
    # peca_service apenas RESERVA o código; não formata o rodapé (linha_controle).
    assert "proximo_codigo_peca" in src
    assert "linha_controle" not in src


# ── 5. Migration 090 (offline) + colunas no model ────────────────────────────

def test_model_tem_colunas_area_e_codigo_peca():
    from app.models.legal_doc import LegalDoc

    cols = LegalDoc.__table__.columns
    assert "area" in cols
    assert "codigo_peca" in cols
    assert cols["codigo_peca"].index is True


def test_migration_090_revisao_e_head():
    import importlib.util

    caminho = Path("alembic/versions/090_peca_versionamento.py")
    spec = importlib.util.spec_from_file_location("mig090", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "090_peca_versionamento"
    assert mod.down_revision == "089_fichas_triagem"


def test_migration_090_ddl_idempotente():
    texto = Path("alembic/versions/090_peca_versionamento.py").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS area" in texto
    assert "ADD COLUMN IF NOT EXISTS codigo_peca" in texto
    assert "CREATE TABLE IF NOT EXISTS peca_codigo_contador" in texto
    assert "ON CONFLICT" not in texto  # o UPSERT vive no service, não na migration
    # downgrade coerente (DROP IF EXISTS).
    assert "DROP TABLE IF EXISTS peca_codigo_contador" in texto
    assert "DROP COLUMN IF EXISTS codigo_peca" in texto


# ── 6. DB vivo (opcional): incremento atômico real por ramo ──────────────────

@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)
async def test_proximo_codigo_incrementa_por_ramo_no_banco():
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    ramo_a = "civil"
    ramo_b = "zzz_teste_novo"
    async with AsyncSessionLocal() as db:
        # Estado limpo para os ramos deste teste.
        await db.execute(
            text("DELETE FROM peca_codigo_contador WHERE area IN (:a, :b)"),
            {"a": ramo_a, "b": ramo_b},
        )
        await db.commit()

        c1 = await proximo_codigo_peca(db, ramo_a)
        c2 = await proximo_codigo_peca(db, ramo_a)
        await db.commit()
        assert c1 == "EJC-CIV-001"
        assert c2 == "EJC-CIV-002"

        # Ramo novo reinicia em 001, independente do contador de civil.
        cb = await proximo_codigo_peca(db, ramo_b)
        await db.commit()
        assert cb.endswith("-001")

        await db.execute(
            text("DELETE FROM peca_codigo_contador WHERE area IN (:a, :b)"),
            {"a": ramo_a, "b": ramo_b},
        )
        await db.commit()
