# ── tests/test_biblia_ejc_seed.py ────────────────────────────────────────────
# Parser + corpus + seed da "Bíblia de Conhecimento EJC" (scripts/parse_biblia_ejc,
# seeds/biblia_ejc/*.jsonl, scripts/seed_biblia_ejc).
#
# Três frentes:
#   1. parse_biblia() em unidade, com um documento sintético que reproduz a
#      estrutura real (áreas H1, SITs H2, volumes, Parte B com modelos);
#   2. integridade do corpus VERSIONADO no repo (chaves únicas, marcação de
#      material fictício, categorias compatíveis com a busca RAG);
#   3. executar_seed_biblia() com upsert monkeypatchado — garante governança
#      (confianca="media", fonte="biblia_ejc") sem precisar de Postgres.
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.parse_biblia_ejc import (
    AVISO_FICTICIO,
    CATEGORIA_MODELO,
    CATEGORIA_REFERENCIA,
    limpar_texto,
    parse_biblia,
    slugify,
)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "seeds" / "biblia_ejc"

# Reproduz em miniatura a estrutura real do DOCX (estilos → texto).
_PARAS_SINTETICOS = [
    ["Title", "B��blia (capa com mojibake — ignorada)"],
    ["Heading1", "BÍBLIA DE CONHECIMENTO EJC — EDIÇÃO INTEGRAL v2"],
    ["Heading1", "AVISO FUNDAMENTAL — LEIA ANTES DE USAR ESTE MATERIAL"],
    ["Compact", "Nenhuma situação aqui descrita pode ser usada em peça real."],
    ["Heading1", "INTRODUÇÃO METODOLÓGICA"],
    ["BodyText", "Cada situação segue um cartão padronizado com campos fixos."],
    ["Heading1", "1. DIREITO CIVIL — RESPONSABILIDADE CIVIL"],
    ["Heading2", "SIT-01 — Colisão traseira com danos materiais (Rotineira)"],
    ["FirstParagraph", "Fatos (fictícios): condutor A parado no semáforo sofre colisão traseira."],
    ["BodyText", "Tese jurídica principal: culpa presumida de quem colide na traseira."],
    ["Heading2", "SIT-02 — Erro médico com sequela permanente (Complexa)"],
    ["BodyText", "Fatos (fictícios): paciente fictício C alega lesão em cirurgia eletiva."],
    ["Heading1", "NOTAS FINAIS E INSTRUÇÕES DE USO"],
    ["BodyText", "Use as situações apenas como referência metodológica de treinamento."],
    ["Heading1", "BÍBLIA DE CONHECIMENTO EJC — VOLUME II"],
    ["Heading1", "AVISO FUNDAMENTAL — LEIA ANTES DE USAR ESTE MATERIAL"],
    ["BodyText", "O Volume II amplia as áreas do Volume I com novas situações fictícias."],
    ["Heading1", "1. DIREITO CIVIL — RESPONSABILIDADE CIVIL (ampliação)"],
    ["Heading2", "SIT-46 — Dano por abandono afetivo (Atípica — tese controvertida)"],
    ["BodyText", "Fatos (fictícios): filho fictício pleiteia indenização por abandono."],
    ["Heading1", "NOTAS FINAIS DO VOLUME II"],
    ["BodyText", "Reforço final: material fictício, revisão humana obrigatória sempre."],
    ["Heading1", "PARTE B — BIBLIOTECA JURÍDICA EJC (MODELOS, AUDITORIA E INTEGRAÇÃO)"],
    ["Heading2", "B.2 — MAPA DE CORRESPONDÊNCIA SITUAÇÃO (PARTE A) → MODELO (PARTE B)"],
    ["BodyText", "SIT-01 corresponde ao modelo 01 do Volume I desta biblioteca de peças."],
    ["Heading2", "B.1 — VOLUMES DE MODELOS (I a V)"],
    ["Heading2", "Volume I — Petições Iniciais e Defesas por Ramo"],
    ["Heading3", "1. AVISOS DE USO E CONTROLE DE QUALIDADE"],
    ["BodyText", "Modelos fictícios: substituir integralmente os dados antes de qualquer uso."],
    ["Heading3", "01 — DIREITO CIVIL: AÇÃO DE COBRANÇA POR INADIMPLEMENTO CONTRATUAL"],
    ["Heading4", "MODELO A — PEÇA INICIAL"],
    ["Heading5", "I — DOS FATOS"],
    ["BodyText", "O autor fictício celebrou contrato de prestação de serviços com o réu."],
    ["Heading3", "01 — DIREITO CIVIL: AÇÃO DE COBRANÇA POR INADIMPLEMENTO CONTRATUAL"],
    ["Heading4", "MODELO B — DEFESA CORRESPONDENTE"],
    ["BodyText", "O réu fictício apresenta contestação impugnando a planilha de débito."],
]


@pytest.fixture(scope="module")
def resultado_sintetico():
    return parse_biblia([list(p) for p in _PARAS_SINTETICOS])


def _por_chave(docs):
    return {d["chave_origem"]: d for d in docs}


# ══════════════════════════════════════════════════════════════════════════
# 1. Parser em unidade
# ══════════════════════════════════════════════════════════════════════════

def test_parser_extrai_sits_com_area_complexidade_volume(resultado_sintetico):
    docs, stats = resultado_sintetico
    por_chave = _por_chave(docs)
    assert stats["situacoes"] == 3

    sit1 = por_chave["biblia_ejc:sit-01"]
    assert sit1["categoria"] == CATEGORIA_REFERENCIA
    assert sit1["extra"]["sit"] == "SIT-01"
    assert sit1["extra"]["area"] == "DIREITO CIVIL — RESPONSABILIDADE CIVIL"
    assert sit1["extra"]["complexidade"] == "Rotineira"
    assert sit1["extra"]["volume"] == "I"
    assert "colisão traseira" in sit1["conteudo"].lower()
    # texto integral: o parágrafo de tese também entrou
    assert "culpa presumida" in sit1["conteudo"]
    # e NÃO vazou para o SIT seguinte
    assert "culpa presumida" not in por_chave["biblia_ejc:sit-02"]["conteudo"]

    # qualificador no parêntese não quebra a complexidade; volume II detectado
    sit46 = por_chave["biblia_ejc:sit-46"]
    assert sit46["extra"]["complexidade"] == "Atípica"
    assert sit46["extra"]["volume"] == "II"
    assert sit46["extra"]["area"] == "DIREITO CIVIL — RESPONSABILIDADE CIVIL"


def test_parser_extrai_instrucoes_de_uso_dos_dois_volumes(resultado_sintetico):
    docs, stats = resultado_sintetico
    chaves = set(_por_chave(docs))
    assert stats["instrucoes"] == 5
    assert {"biblia_ejc:aviso-fundamental", "biblia_ejc:introducao-metodologica",
            "biblia_ejc:notas-finais", "biblia_ejc:aviso-fundamental-volii",
            "biblia_ejc:notas-finais-volii"} <= chaves


def test_parser_parte_b_governanca_e_modelos(resultado_sintetico):
    docs, _ = resultado_sintetico
    por_chave = _por_chave(docs)

    mapa = por_chave["biblia_ejc:b0-b-2-mapa-de-correspondencia-situacao-parte-a-modelo-parte-b"]
    assert mapa["categoria"] == CATEGORIA_REFERENCIA
    assert mapa["extra"]["tipo"] == "governanca"

    avisos_vol = por_chave["biblia_ejc:b1-voli-1-avisos-de-uso-e-controle-de-qualidade"]
    assert avisos_vol["categoria"] == CATEGORIA_REFERENCIA   # H3 "1. ..." não é modelo

    modelos = [d for d in docs if d["extra"]["tipo"] == "modelo"]
    assert len(modelos) == 2
    assert all(d["categoria"] == CATEGORIA_MODELO for d in modelos)
    # mesmo tema H3 duas vezes → chaves distintas e títulos desambiguados pelo H4
    assert len({d["chave_origem"] for d in modelos}) == 2
    assert "(MODELO A — PEÇA INICIAL)" in modelos[0]["titulo"]
    assert "(MODELO B — DEFESA CORRESPONDENTE)" in modelos[1]["titulo"]
    # subtítulos internos preservados como linhas no texto limpo
    assert "I — DOS FATOS" in modelos[0]["conteudo"]


def test_parser_marca_todo_doc_como_ficticio_com_aviso(resultado_sintetico):
    docs, _ = resultado_sintetico
    assert docs, "parser não produziu documentos"
    for d in docs:
        assert d["extra"]["ficticio"] is True
        assert d["extra"]["origem"].startswith("Bíblia de Conhecimento EJC")
        assert d["conteudo"].startswith(AVISO_FICTICIO)
        assert d["chave_origem"].startswith("biblia_ejc:")


def test_parser_ignora_capa_e_mojibake(resultado_sintetico):
    docs, _ = resultado_sintetico
    assert all("�" not in d["conteudo"] for d in docs)
    assert all("EDIÇÃO INTEGRAL v2" not in d["titulo"] for d in docs)


def test_limpar_texto_e_slugify():
    assert limpar_texto("a b​  c\t d") == "a b c d"
    assert slugify("01 — DIREITO CIVIL: AÇÃO DE COBRANÇA!") == "01-direito-civil-acao-de-cobranca"


# ══════════════════════════════════════════════════════════════════════════
# 2. Integridade do corpus versionado (seeds/biblia_ejc/*.jsonl)
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def corpus():
    arquivos = sorted(CORPUS_DIR.glob("*.jsonl"))
    assert arquivos, f"corpus ausente em {CORPUS_DIR}"
    return [json.loads(l) for a in arquivos for l in a.open(encoding="utf-8") if l.strip()]


def test_corpus_completo_e_sem_duplicatas(corpus):
    chaves = [d["chave_origem"] for d in corpus]
    assert len(chaves) == len(set(chaves)), "chave_origem duplicada no corpus"
    sits = sorted(d["extra"]["sit"] for d in corpus if d["extra"]["tipo"] == "situacao")
    assert len(sits) == 84
    assert sits == [f"SIT-{n:02d}" for n in range(1, 85)]   # SIT-01..84 sem lacunas
    assert sum(1 for d in corpus if d["extra"]["tipo"] == "instrucao_uso") == 5
    assert sum(1 for d in corpus if d["extra"]["tipo"] == "modelo") >= 200


def test_corpus_governanca_de_ia(corpus):
    categorias_ok = {CATEGORIA_REFERENCIA, CATEGORIA_MODELO}
    for d in corpus:
        assert d["categoria"] in categorias_ok, d["chave_origem"]
        assert d["extra"]["ficticio"] is True, d["chave_origem"]
        assert d["conteudo"].startswith(AVISO_FICTICIO), d["chave_origem"]
        assert 50 <= len(d["conteudo"]), d["chave_origem"]
        assert len(d["titulo"]) <= 500 and len(d["chave_origem"]) <= 255
        # nunca em categoria de jurisprudência/precedente — não pode ser citado como caso real
        assert not re.search(r"jurisprudencia|precedente|sumula", d["categoria"])


def test_corpus_complexidades_validas(corpus):
    for d in corpus:
        if d["extra"]["tipo"] == "situacao":
            assert d["extra"]["complexidade"] in {"Rotineira", "Complexa", "Atípica"}
            assert d["extra"]["volume"] in {"I", "II"}
            assert d["extra"]["area"]


# ══════════════════════════════════════════════════════════════════════════
# 3. Seed (upsert monkeypatchado — sem Postgres)
# ══════════════════════════════════════════════════════════════════════════

async def test_seed_usa_confianca_media_e_fonte_biblia(monkeypatch):
    import app.services.ingestion_service as ing
    from scripts.seed_biblia_ejc import FONTE_SLUG, executar_seed_biblia

    chamadas: list[dict] = []

    async def fake_upsert(db, **kw):
        chamadas.append(kw)
        return "novo"

    async def fake_fonte(db, slug, descricao, categoria_rag=None):
        assert slug == FONTE_SLUG

    execucoes: list[dict] = []

    async def fake_exec(db, slug, **kw):
        execucoes.append({"slug": slug, **kw})

    monkeypatch.setattr(ing, "upsert_documento", fake_upsert)
    monkeypatch.setattr(ing, "registrar_fonte", fake_fonte)
    monkeypatch.setattr(ing, "marcar_execucao", fake_exec)

    class _FakeDB:
        async def commit(self):
            pass

    resumo = await executar_seed_biblia(_FakeDB(), embutir_vetores=False)
    assert resumo["total"] == len(chamadas) > 300
    assert resumo["novos"] == resumo["total"]
    assert all(c["confianca"] == "media" for c in chamadas)
    assert all(c["fonte"] == FONTE_SLUG for c in chamadas)
    assert all(c["extra"]["ficticio"] is True for c in chamadas)
    assert all(c["embutir_vetores"] is False for c in chamadas)
    assert execucoes and execucoes[0]["slug"] == FONTE_SLUG and execucoes[0]["total"] == resumo["total"]
