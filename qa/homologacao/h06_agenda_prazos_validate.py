"""Validação estática do gate H06 Agenda/Prazos.

Não faz rede, não lê credenciais e não toca banco. O objetivo é impedir que o
roteiro operacional perca os gates jurídicos/técnicos mínimos enquanto a
execução autenticada continua sendo responsabilidade do runner geral + aceite
humano.
"""
from pathlib import Path


ROTEIRO = Path(__file__).with_name("H06_AGENDA_PRAZOS_EXECUCAO.md")


def test_h06_roteiro_contem_gates_minimos():
    texto = ROTEIRO.read_text(encoding="utf-8")
    obrigatorios = [
        "regime_calculo",
        "case_id IS NULL",
        "quatro olhos",
        "calculado_por",
        "confirmado=false",
        "DataJud não materializa Deadline automaticamente",
        "DJEN revisado",
        "fonte oficial",
        "sobreposição real de intervalos",
        "reset 7d/3d/1d",
        "aceite humano explícito",
        "SHA testado",
    ]
    ausentes = [item for item in obrigatorios if item not in texto]
    assert not ausentes, f"Roteiro H06 perdeu gates obrigatórios: {ausentes}"


def test_h06_proibe_dados_reais_e_credenciais_versionadas():
    texto = ROTEIRO.read_text(encoding="utf-8")
    assert "HOMOLOG-FICTICIO" in texto
    assert "nunca CPF, cliente, processo, intimação ou documento real" in texto
    assert "variáveis de ambiente" in texto
    assert "nunca registradas no Git" in texto
