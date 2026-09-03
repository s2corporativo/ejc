"""Contrato de UX da simplificação arquitetural do módulo Clientes.

A lista é porta de entrada (localizar/cadastrar) e a Ficha Mestra concentra a
continuidade operacional. Estes testes evitam a volta de ações duplicadas na
listagem e preservam a comunicação explícita de falha na checagem de conflito.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLIENTES = ROOT / "frontend/src/pages/Clientes.tsx"
DOSSIE = ROOT / "frontend/src/pages/DossieCliente.tsx"


def _fonte(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_clientes_e_porta_de_entrada_enxuta():
    fonte = _fonte(CLIENTES)

    assert "ClientesStats" not in fonte
    assert "Dossiê Digital" not in fonte
    assert "/criar-acesso" not in fonte
    assert ">Cliente</th>" in fonte
    assert ">Contato</th>" in fonte
    assert ">Status</th>" in fonte
    assert ">Privacidade</th>" in fonte
    assert "Nome / Razão" not in fonte
    assert ">Desde</th>" not in fonte


def test_cadastro_continua_na_ficha_mestra():
    fonte = _fonte(CLIENTES)

    assert "useNavigate" in fonte
    assert 'const { data: criado } = await api.post<Client>("/clients/", form)' in fonte
    assert "navigate(`/clientes/${criado.id}`)" in fonte
    assert '"Salvar e abrir ficha"' in fonte


def test_cadastro_progressivo_nao_expoe_campos_complementares_de_inicio():
    fonte = _fonte(CLIENTES)

    assert "mostrarAvancado" in fonte
    assert "Adicionar endereço e dados para conflito" in fonte
    assert "{mostrarAvancado && (" in fonte
    assert "Parte contrária (se já conhecida — verificação de conflito)" in fonte


def test_falha_de_conflito_nao_parece_resultado_negativo():
    fonte = _fonte(CLIENTES)

    assert 'type ResultadoConflito = ConflitoCheck | "indisponivel" | null' in fonte
    assert "setConflitoIndisponivel(true)" in fonte
    assert 'return "indisponivel"' in fonte
    assert 'title="Conflito não pôde ser verificado"' in fonte
    assert "a análise de conflito deve ser realizada" in fonte


def test_dossie_permanece_ficha_mestra_canonica():
    fonte = _fonte(DOSSIE)

    assert 'eyebrow="Ficha Mestra do Cliente"' in fonte
    assert '{ id: "resumo", label: "Resumo"' in fonte
    assert '{ id: "atendimentos", label: "Atendimentos"' in fonte
    assert '{ id: "casos", label: "Casos"' in fonte
    assert '{ id: "prazos", label: "Prazos"' in fonte
    assert '{ id: "financeiro", label: "Financeiro"' in fonte
    assert '{ id: "documentos", label: "Documentos"' in fonte
    assert "Acesso ao portal" in fonte
    assert "PendingItemsPanel" in fonte
