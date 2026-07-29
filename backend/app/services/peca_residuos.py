# ── app/services/peca_residuos.py ────────────────────────────────────────────
# DETECTOR DE RESÍDUOS do caso de origem (Modo Molde — Fase 2 do plano de
# simplificação).
#
# O Modo Molde reaproveita a ESTRUTURA de uma peça anterior. O risco jurídico
# concreto é o dado do cliente anterior sobreviver na peça nova: nome, CPF/CNPJ,
# número de processo ou parte contrária de OUTRO caso protocolados no caso
# atual — quebra de sigilo (EOAB art. 34, LGPD) e nulidade processual.
#
# Até aqui isso era apenas uma FRASE no prompt ("a peça deve passar por detector
# de resíduos"): nenhuma verificação real acontecia. Este módulo faz a
# verificação determinística — sem IA, sem custo, auditável.
#
# Contrato:
#   • `coletar_identificadores` lê o caso (nome do cliente, documento, processo,
#     parte contrária). É a ÚNICA parte que toca o banco;
#   • `detectar_residuos` é PURA: recebe texto + identificadores e devolve os
#     achados. Identificador que também pertence ao caso de DESTINO nunca é
#     achado (é legítimo — mesmo cliente, mesmo processo);
#   • nada aqui bloqueia sozinho: o achado sobe como aviso HITL para o advogado
#     decidir, no mesmo espírito do citation gate.
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Piso de tamanho para nome virar termo de busca: abaixo disso o ruído
# ("Ltda", "S/A", iniciais) geraria falso positivo em toda peça.
_MIN_NOME = 5

# Rótulos legíveis por categoria (usados na mensagem ao advogado).
_ROTULOS = {
    "cliente": "nome do cliente do caso de origem",
    "parte_contraria": "parte contrária do caso de origem",
    "documento": "CPF/CNPJ do caso de origem",
    "processo": "número de processo do caso de origem",
}


@dataclass
class IdentificadoresCaso:
    """Identificadores rastreáveis de um caso, por categoria."""

    cliente: list[str] = field(default_factory=list)
    parte_contraria: list[str] = field(default_factory=list)
    documento: list[str] = field(default_factory=list)   # só dígitos
    processo: list[str] = field(default_factory=list)    # só dígitos

    def digitos(self) -> set[str]:
        return {d for d in (*self.documento, *self.processo) if d}

    def nomes_norm(self) -> set[str]:
        return {
            n for n in (
                *(_normalizar(x) for x in self.cliente),
                *(_normalizar(x) for x in self.parte_contraria),
            ) if len(n) >= _MIN_NOME
        }


def _normalizar(texto: Any) -> str:
    """Minúsculas, sem acento, espaços colapsados — comparação tolerante a
    variação de digitação entre a peça de origem e a nova."""
    bruto = str(texto or "").strip()
    if not bruto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", bruto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.casefold().split())


def _digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


async def coletar_identificadores(
    db: AsyncSession, case_id: str | None
) -> IdentificadoresCaso:
    """Identificadores do caso (fail-soft: caso inexistente devolve vazio).

    Único ponto que toca o banco. Lê o CPF/CNPJ em claro porque a comparação
    precisa do documento COMPLETO — o valor nunca é logado nem persistido."""
    ids = IdentificadoresCaso()
    if not case_id:
        return ids

    from app.models.case import Case
    from app.models.client import Client

    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if caso is None:
        return ids

    if caso.numero_processo:
        ids.processo.append(_digitos(caso.numero_processo))
    if caso.parte_contraria:
        ids.parte_contraria.append(str(caso.parte_contraria))

    if caso.client_id:
        cliente = (await db.execute(
            select(Client).where(Client.id == caso.client_id)
        )).scalar_one_or_none()
        if cliente is not None:
            for nome in (cliente.nome, cliente.razao_social):
                if nome:
                    ids.cliente.append(str(nome))
            doc = cliente.documento_plain
            if doc:
                ids.documento.append(_digitos(doc))

    ids.documento = [d for d in ids.documento if d]
    ids.processo = [p for p in ids.processo if p]
    return ids


def _ocorre_nome(texto_norm: str, nome_norm: str) -> bool:
    """Nome presente com fronteira de palavra (evita casar 'Ana' em 'Susana')."""
    return re.search(rf"(?<!\w){re.escape(nome_norm)}(?!\w)", texto_norm) is not None


def detectar_residuos(
    texto: str,
    origem: IdentificadoresCaso,
    destino: IdentificadoresCaso | None = None,
) -> list[dict[str, Any]]:
    """Achados de identificadores do caso de ORIGEM sobreviventes no texto.

    Função PURA. Identificador que também pertence ao caso de destino é
    legítimo e nunca vira achado. Devolve lista de
    {categoria, rotulo, termo, mensagem} — vazia quando a peça está limpa."""
    if not (texto or "").strip():
        return []

    destino = destino or IdentificadoresCaso()
    texto_norm = _normalizar(texto)
    # Dígitos do texto sem separadores: casa "123.456.789-00" e "12345678900".
    texto_digitos = re.sub(r"\D", "", texto)

    legitimos_nomes = destino.nomes_norm()
    legitimos_digitos = destino.digitos()

    achados: list[dict[str, Any]] = []
    vistos: set[tuple[str, str]] = set()

    def _registrar(categoria: str, termo: str) -> None:
        chave = (categoria, _normalizar(termo))
        if chave in vistos:
            return
        vistos.add(chave)
        achados.append({
            "categoria": categoria,
            "rotulo": _ROTULOS[categoria],
            "termo": termo,
            "mensagem": (
                f"Encontrado no texto o {_ROTULOS[categoria]}: “{termo}”. "
                "Remova ou substitua antes de aprovar a peça."
            ),
        })

    for categoria, valores in (
        ("cliente", origem.cliente),
        ("parte_contraria", origem.parte_contraria),
    ):
        for bruto in valores:
            nome_norm = _normalizar(bruto)
            if len(nome_norm) < _MIN_NOME or nome_norm in legitimos_nomes:
                continue
            if _ocorre_nome(texto_norm, nome_norm):
                _registrar(categoria, str(bruto).strip())

    for categoria, valores in (
        ("documento", origem.documento),
        ("processo", origem.processo),
    ):
        for bruto in valores:
            digitos = _digitos(bruto)
            # Piso de 11 dígitos: CPF (11), CNPJ (14) e CNJ (20). Abaixo disso
            # a sequência é curta demais para identificar alguém.
            if len(digitos) < 11 or digitos in legitimos_digitos:
                continue
            if digitos in texto_digitos:
                _registrar(categoria, digitos)

    return achados


async def detectar_residuos_do_molde(
    db: AsyncSession,
    texto: str,
    *,
    documento_molde_id: str | None,
    case_id_destino: str | None,
) -> list[dict[str, Any]]:
    """Conveniência do fluxo de geração: resolve o caso de ORIGEM a partir da
    peça usada como molde e roda a detecção contra o caso de destino.

    Fail-soft por contrato: qualquer falha devolve [] — o detector é uma rede
    de segurança adicional e jamais pode derrubar a entrega da peça (o HITL do
    advogado continua sendo a barreira final)."""
    if not documento_molde_id or not (texto or "").strip():
        return []
    try:
        from app.models.legal_doc import LegalDoc

        molde = (await db.execute(
            select(LegalDoc).where(LegalDoc.id == documento_molde_id)
        )).scalar_one_or_none()
        if molde is None or not molde.case_id:
            return []
        # Molde do PRÓPRIO caso não gera resíduo: os dados são os mesmos.
        if molde.case_id == case_id_destino:
            return []
        origem = await coletar_identificadores(db, molde.case_id)
        destino = await coletar_identificadores(db, case_id_destino)
        return detectar_residuos(texto, origem, destino)
    except Exception:  # fail-soft deliberado
        return []
