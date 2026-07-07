# ── tests/test_financeiro_consolidado_enum.py ────────────────────────────────
# Regressão: o SQL de /financeiro/consolidado NÃO pode comparar a coluna enum
# `tipo` (feetipo) com o literal 'sucumbencia' — esse label NÃO existe no enum
# (fixo/exito/misto/por_hora/custas_despesas), e o Postgres estoura
# InvalidTextRepresentationError (500) já no parse da query. Sucumbência é
# detectada por `descricao ILIKE '%sucumb%'`.
import pathlib


def test_sql_nao_compara_enum_tipo_com_sucumbencia():
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "app" / "routers" / "financeiro_consolidado.py"
    )
    texto = src.read_text(encoding="utf-8")
    for proibido in ("tipo='sucumbencia'", "tipo = 'sucumbencia'", "tipo != 'sucumbencia'"):
        assert proibido not in texto, (
            f"Comparar o enum feetipo com {proibido!r} (label inexistente) causa 500 — "
            "detecte sucumbência por `descricao ILIKE '%sucumb%'`."
        )
