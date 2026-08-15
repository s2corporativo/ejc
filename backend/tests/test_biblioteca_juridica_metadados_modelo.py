"""Regressão: o lote piloto da biblioteca jurídica é MODELO SIMULADO.

O lote de 24 documentos (docs/biblioteca_juridica/, 08/2026) foi gerado por IA
(Manus) com julgados/URLs não verificados — 15 arquivos contêm blocos
`NAO_CONFIRMADO` e um contém URLs "(Simulado)". Por decisão do titular
(15/08/2026, Issue #1147), o lote é mantido como acervo de MODELOS
estruturais, nunca como fonte de jurisprudência: o front-matter deve declarar
`origem_conteudo: modelo_simulado`, `gerado_por_IA: true`,
`tipo_camada: modelo_peca` e `nivel_confiaca: BAIXA`, e o corpo deve abrir
com o banner de alerta. Este teste impede que os arquivos voltem a se
apresentar como `fonte_oficial`/confiança ALTA — o que os faria entrar no
circuito de citação do RAG como jurisprudência real.

Exceção: consumidor_bancario/14_* pertence ao PR #1143 (quarentena/correção
do JUR-CONS-000016) e é validado lá; quando o #1143 integrar, remover a
exceção.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs" / "biblioteca_juridica"
AREAS = (
    "tributario",
    "ambiental",
    "administrativo",
    "licitacoes",
    "empresarial",
    "consumidor_bancario",
    "trabalhista_empresarial",
    "processual_civil",
)
EXCECAO_PR_1143 = "14_responsabilidade-objetiva-por-fraude-banc-ria.md"
BANNER = "MODELO SIMULADO — NÃO CITAR COMO JURISPRUDÊNCIA"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _arquivos_do_lote():
    arquivos = []
    for area in AREAS:
        adir = BASE / area
        if adir.is_dir():
            arquivos.extend(
                p for p in sorted(adir.glob("*.md")) if p.name != EXCECAO_PR_1143
            )
    return arquivos


def _campos(texto: str) -> dict:
    m = FRONTMATTER.match(texto)
    assert m, "front-matter ausente ou fora do padrão ---\\n...\\n---"
    campos = {}
    for linha in m.group(1).splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            campos[chave.strip()] = valor.strip()
    return campos, m.group(2)


def test_lote_existe():
    assert len(_arquivos_do_lote()) >= 23, "lote piloto não encontrado"


def test_lote_declara_modelo_simulado_gerado_por_ia():
    for path in _arquivos_do_lote():
        campos, _ = _campos(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT)
        assert campos.get("origem_conteudo") == "modelo_simulado", (
            f"{rel}: origem_conteudo={campos.get('origem_conteudo')!r} — "
            "modelo gerado por IA não pode se declarar fonte_oficial"
        )
        assert campos.get("gerado_por_IA") == "true", (
            f"{rel}: gerado_por_IA={campos.get('gerado_por_IA')!r} — "
            "conteúdo é produção de IA (Manus, lote 08/2026)"
        )
        assert campos.get("tipo_camada") == "modelo_peca", (
            f"{rel}: tipo_camada={campos.get('tipo_camada')!r} — modelos não "
            "entram no circuito de jurisprudência do RAG"
        )
        assert campos.get("nivel_confiaca") == "BAIXA", (
            f"{rel}: nivel_confiaca={campos.get('nivel_confiaca')!r} — "
            "julgados não verificados não podem declarar confiança ALTA"
        )


def test_lote_tem_banner_de_alerta_no_corpo():
    for path in _arquivos_do_lote():
        _, corpo = _campos(path.read_text(encoding="utf-8"))
        assert BANNER in corpo.split("\n\n", 2)[0] or BANNER in corpo[:600], (
            f"{path.relative_to(ROOT)}: banner de modelo simulado ausente do "
            "início do documento"
        )
