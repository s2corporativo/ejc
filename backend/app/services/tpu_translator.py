# ── app/services/tpu_translator.py ───────────────────────────────────────────
# Tradução de códigos da Tabela Processual Unificada do CNJ (classes,
# assuntos, movimentos) para rótulo legível.
#
# Fase A NÃO carrega a base completa da TPU (são milhares de códigos,
# atualizados periodicamente pelo CNJ) — só um seed pequeno de exemplo para
# os casos mais comuns, com fallback explícito "código não mapeado". Carregar
# a tabela completa fica para uma fase futura (ver relatório da tarefa).
from __future__ import annotations

# Seed reduzido — amostra ilustrativa, não exaustiva. Ampliar aqui conforme
# necessidade real observada em produção, ou substituir por carga completa
# da TPU num Bloco futuro.
_CLASSES: dict[str, str] = {
    "7": "Procedimento Comum Cível",
    "1116": "Cumprimento de Sentença",
    "1699": "Procedimento do Juizado Especial Cível",
    "436": "Reclamação Trabalhista",
}

_ASSUNTOS: dict[str, str] = {
    "10375": "Indenização por Dano Moral",
    "9985": "Rescisão do Contrato de Trabalho",
    "1127": "Inadimplemento",
}

_MOVIMENTOS: dict[str, str] = {
    "26": "Distribuição",
    "51": "Audiência",
    "132": "Recebido para Despacho/Decisão",
    "246": "Publicação",
    "848": "Concluso ao Juiz",
}


def _traduzir(tabela: dict[str, str], codigo: str | int | None) -> str:
    if codigo is None:
        return "código não mapeado (ausente)"
    chave = str(codigo)
    return tabela.get(chave, f"código não mapeado ({chave})")


def traduzir_classe(codigo: str | int | None) -> str:
    return _traduzir(_CLASSES, codigo)


def traduzir_assunto(codigo: str | int | None) -> str:
    return _traduzir(_ASSUNTOS, codigo)


def traduzir_movimento(codigo: str | int | None) -> str:
    return _traduzir(_MOVIMENTOS, codigo)
