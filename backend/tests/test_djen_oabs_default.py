# ── tests/test_djen_oabs_default.py ───────────────────────────────────────────
# Regressão do resgate de 2026-08-27 (PR #1311, Issue #1310).
#
# A OAB do 2º sócio (Guilherme Alves de Paula, OAB/MG 252.599, inscrição
# definitiva em 24/08/2026) foi acrescentada ao monitoramento do DJEN por
# edição MANUAL no checkout de produção (/opt/ejc), nunca commitada. O pré-voo
# do deploy manual a encontrou por acaso; um `git checkout --force` para
# destravar aquele deploy a teria apagado em silêncio, e ninguém notaria até
# um prazo vencer.
#
# Os demais testes de DJEN substituem `DJEN_OABS_MONITORADAS` por valores
# sintéticos (é o certo para o que eles testam), então TODOS continuariam
# verdes se este default regredisse para uma OAB só. Este arquivo existe
# exatamente para tapar esse buraco: ele afirma o valor real de produção.
#
# Ao admitir um novo advogado, atualize o default E esta lista juntos — a
# falha aqui é o lembrete de que o cadastro tem duas pontas.
from app.core.config import Settings
from app.services.ingestors.djen import parse_oabs

# Sócios com inscrição na OAB/MG cujas intimações o escritório monitora.
_OABS_ESPERADAS = {("252599", "MG"), ("251174", "MG")}


def test_default_de_producao_monitora_ambos_os_socios():
    """O default do código traz as duas OABs — não pode voltar a uma só."""
    default = Settings.model_fields["DJEN_OABS_MONITORADAS"].default
    assert set(parse_oabs(default)) == _OABS_ESPERADAS


def test_default_sobrevive_ao_parser():
    """Nenhuma das entradas do default é descartada por formato inválido.

    `parse_oabs` ignora entrada malformada com um aviso em log — silenciosa
    para quem só olha a variável. Um separador errado no default reduziria o
    monitoramento sem nenhum erro visível.
    """
    default = Settings.model_fields["DJEN_OABS_MONITORADAS"].default
    entradas_declaradas = [p for p in default.split(",") if p.strip()]
    assert len(parse_oabs(default)) == len(entradas_declaradas)


def test_env_example_declara_o_mesmo_valor_do_codigo():
    """`.env.example` é o que se copia para montar o `.env` de um ambiente novo.

    Se ele divergir do default do código, um ambiente recém-provisionado
    monitora um conjunto de OABs diferente do que o repositório afirma.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    linhas = (raiz / ".env.example").read_text(encoding="utf-8").splitlines()
    declarado = next(
        linha.split("=", 1)[1].strip()
        for linha in linhas
        if linha.startswith("DJEN_OABS_MONITORADAS=")
    )
    assert set(parse_oabs(declarado)) == _OABS_ESPERADAS
