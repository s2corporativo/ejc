"""Contrato de UX do módulo Clientes após a consolidação do PR #1449.

Resolução de merge sobre a main estabilizada: a listagem evoluiu com ações
operacionais (Dossiê Digital, acesso ao portal, documentos de admissão) e
mantém a Ficha Mestra como destino canônico do cadastro. Os pontos éticos do
PR original permanecem obrigatórios: cadastro termina na Ficha Mestra e a
falha da checagem de conflito é explícita, nunca silenciada como "sem
conflito" (CED/OAB, arts. 19 a 22).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLIENTES = ROOT / "frontend/src/pages/Clientes.tsx"
DOSSIE = ROOT / "frontend/src/pages/DossieCliente.tsx"
ADR = ROOT / "docs/decisoes/ADR_CLIENTES_FICHA_MESTRA_CANONICA_2026-09-02.md"


def _fonte(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_listagem_aponta_para_ficha_mestra():
    fonte = _fonte(CLIENTES)

    assert 'window.location.href = `/clientes/${c.id}`' in fonte
    assert "Dossiê Digital" in fonte
    assert ">Contato</th>" in fonte
    assert ">Status</th>" in fonte


def test_cadastro_continua_na_ficha_mestra():
    fonte = _fonte(CLIENTES)

    assert "useNavigate" in fonte
    assert 'const { data: criado } = await api.post<Client>("/clients/", form)' in fonte
    assert "navigate(`/clientes/${criado.id}`)" in fonte
    assert '"Salvar cliente"' in fonte


def test_verificacao_de_conflito_presente_no_cadastro():
    fonte = _fonte(CLIENTES)

    assert "checarConflito" in fonte
    assert "/clients/checar-conflito" in fonte
    assert "Parte contrária" in fonte


def test_falha_de_conflito_nao_parece_resultado_negativo():
    fonte = _fonte(CLIENTES)

    assert 'type ResultadoConflito = ConflitoCheck | "indisponivel" | null' in fonte
    assert "setConflitoIndisponivel(true)" in fonte
    assert 'return "indisponivel"' in fonte
    assert 'title="Conflito não pôde ser verificado"' in fonte
    assert "a análise de conflito deve ser realizada" in fonte


def test_base_etica_do_conflito_e_oficial_e_rastreavel():
    fonte = _fonte(ADR)

    assert "Código de Ética e Disciplina da OAB" in fonte
    assert "arts. **19 a 22**" in fonte
    assert "Resolução CFOAB nº 02/2015" in fonte
    assert "https://www.oab.org.br/leisnormas/legislacao/resolucoes/02-2015" in fonte
    assert "13/09/2026" in fonte


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
