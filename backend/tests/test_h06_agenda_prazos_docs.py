from pathlib import Path


def test_roteiro_h06_agenda_prazos_preserva_gates_criticos():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "qa" / "homologacao" / "H06_AGENDA_PRAZOS_EXECUCAO.md").read_text(
        encoding="utf-8"
    )
    for marcador in (
        "regime_calculo",
        "quatro olhos",
        "DJEN revisado",
        "DataJud não materializa Deadline automaticamente",
        "sobreposição real de intervalos",
        "aceite humano explícito",
    ):
        assert marcador in texto
