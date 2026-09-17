"""Paridade FLAGS de integração ⊆ .env.example.

`tests/test_env_example_paridade.py` garante que todo campo de `Settings` esteja
documentado no `.env.example`. As flags das integrações públicas (Issue #836)
NÃO passam por `Settings`: `app/integrations/feature_flags.py` as lê direto com
`os.getenv`, então escapam daquele teste.

Foi exatamente esse ponto cego que deixou as dez integrações invisíveis: o
código estava pronto e exposto por rota, mas nenhuma das variáveis que as ligam
aparecia no `.env.example` — não havia como um operador descobrir que elas
existiam, nem o nome da variável para habilitá-las.

Este teste fecha o buraco pela outra ponta: integração nova sem documentação da
sua flag reprova aqui.
"""
from __future__ import annotations

from pathlib import Path

from app.integrations.feature_flags import FLAGS

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def _nomes_documentados() -> set[str]:
    """Nomes de variável presentes no .env.example, comentados ou não.

    Aceita `NOME=` e `# NOME=` — o mesmo critério do teste de paridade de
    Settings, para que documentar uma flag desligada não exija defini-la.
    """
    documentados: set[str] = set()
    for linha in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        crua = linha.strip().lstrip("#").strip()
        if "=" in crua:
            nome = crua.split("=", 1)[0].strip()
            if nome:
                documentados.add(nome)
    return documentados


def test_toda_flag_de_integracao_esta_no_env_example():
    documentados = _nomes_documentados()
    ausentes = sorted(env for env in FLAGS.values() if env not in documentados)
    assert not ausentes, (
        "Flags de integração sem entrada no .env.example (documente com "
        f"`NOME=false` e um comentário do que a fonte faz): {ausentes}"
    )


def test_env_example_nao_documenta_flag_de_integracao_inexistente():
    """Flag documentada que sumiu de FLAGS vira lixo que confunde o operador."""
    documentados = _nomes_documentados()
    conhecidas = set(FLAGS.values())
    suspeitas = sorted(
        nome
        for nome in documentados
        if nome.endswith(("_OPEN_DATA_ENABLED",))
        and nome not in conhecidas
    )
    assert not suspeitas, (
        "`.env.example` documenta flag de integração que não existe em "
        f"feature_flags.FLAGS: {suspeitas}"
    )
