"""Regressão jurídica do lote piloto simulado da Biblioteca Jurídica.

Estes 23 arquivos foram produzidos como modelos/simulações em 08/2026 e não
podem se apresentar ao RAG como fonte oficial, jurisprudência verificada ou
conteúdo humano. A lista é deliberadamente FECHADA: documentos futuros nessas
áreas não herdam esta classificação por localização de pasta.

O arquivo consumidor_bancario/14_* não pertence ao conjunto: foi saneado
separadamente na frente de hardening #1143 e hoje representa uma fonte jurídica
reconstruída/verificável, não um modelo simulado.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANNER = "MODELO SIMULADO — NÃO CITAR COMO JURISPRUDÊNCIA"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)

ARQUIVOS_MODELO = (
    "docs/biblioteca_juridica/administrativo/08_san-es-administrativas-proporcionalidade-e-grada-o.md",
    "docs/biblioteca_juridica/administrativo/09_prescri-o-quinquenal-da-pretens-o-punitiva-administrativa.md",
    "docs/biblioteca_juridica/ambiental/06_multa-ambiental-aplicada-a-pessoa-jur-dica.md",
    "docs/biblioteca_juridica/ambiental/07_responsabilidade-civil-ambiental-objetiva-art-14-1-da-lei-6.md",
    "docs/biblioteca_juridica/consumidor_bancario/15_fraude-pix-e-mecanismo-especial-de-devolu-o-med.md",
    "docs/biblioteca_juridica/consumidor_bancario/16_negativa-o-indevida-dano-moral-in-re-ipsa.md",
    "docs/biblioteca_juridica/consumidor_bancario/17_revisional-de-contrato-banc-rio-limita-o-de-encargos.md",
    "docs/biblioteca_juridica/empresarial/12_desconsideracao-personalidade-juridica-art50-cc-tema-1210-stj.md",
    "docs/biblioteca_juridica/empresarial/13_recupera-o-judicial-e-cr-ditos-tribut-rios.md",
    "docs/biblioteca_juridica/licitacoes/10_habilita-o-jur-dica-e-qualifica-o-t-cnica-na-lei-14-133-21.md",
    "docs/biblioteca_juridica/licitacoes/11_dispensa-de-licita-o-e-fraude-fracionamento.md",
    "docs/biblioteca_juridica/licitacoes/12_preg-o-eletr-nico-lei-14-133-21.md",
    "docs/biblioteca_juridica/processual_civil/20_tutela-de-urg-ncia-e-evid-ncia-art-300-e-311-cpc.md",
    "docs/biblioteca_juridica/processual_civil/21_intima-es-eletr-nicas-e-djen-dje-prazos.md",
    "docs/biblioteca_juridica/processual_civil/22_honor-rios-advocat-cios-sucumb-ncia-e-cumprimento-de-senten.md",
    "docs/biblioteca_juridica/trabalhista_empresarial/18_responsabilidade-subsidi-ria-terceiriza-o-l-cita.md",
    "docs/biblioteca_juridica/trabalhista_empresarial/19_prescri-o-trabalhista-tema-290-stf-e-lei-14-457-2022.md",
    "docs/biblioteca_juridica/tributario/01_monofasia-pis-cofins-restitui-o.md",
    "docs/biblioteca_juridica/tributario/02_prescri-o-quinquenal-tribut-ria-re-566-621-sc-e-tema-616-stf.md",
    "docs/biblioteca_juridica/tributario/03_exclus-o-do-icms-da-base-de-c-lculo-do-pis-cofins-tema-69-st.md",
    "docs/biblioteca_juridica/tributario/04_ipi-conceito-de-insumo-tema-779-stj.md",
    "docs/biblioteca_juridica/tributario/05_execu-o-fiscal-penhora-online-via-sisbajud.md",
    "docs/biblioteca_juridica/tributario/23_compensa-o-tribut-ria-art-170-a-ctn.md",
)


def _ler(rel: str) -> tuple[dict[str, str], str]:
    path = ROOT / rel
    assert path.is_file(), f"modelo piloto ausente: {rel}"
    texto = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(texto)
    assert match, f"{rel}: front-matter ausente ou fora do padrão"

    campos: dict[str, str] = {}
    for linha in match.group(1).splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            campos[chave.strip()] = valor.strip()
    return campos, match.group(2)


def test_escopo_do_lote_simulado_e_fechado_em_23_arquivos() -> None:
    assert len(ARQUIVOS_MODELO) == 23
    assert len(set(ARQUIVOS_MODELO)) == 23
    assert not any("consumidor_bancario/14_" in rel for rel in ARQUIVOS_MODELO)


def test_modelos_nao_se_declaram_fonte_oficial() -> None:
    for rel in ARQUIVOS_MODELO:
        campos, _ = _ler(rel)
        assert campos.get("origem_conteudo") == "modelo_simulado", rel
        assert campos.get("gerado_por_IA") == "true", rel
        assert campos.get("tipo_camada") == "modelo_peca", rel
        assert campos.get("nivel_confiaca") == "BAIXA", rel


def test_modelos_exibem_alerta_antes_do_conteudo_juridico() -> None:
    for rel in ARQUIVOS_MODELO:
        _, corpo = _ler(rel)
        assert BANNER in corpo[:600], (
            f"{rel}: banner de modelo simulado ausente dos primeiros 600 caracteres"
        )
