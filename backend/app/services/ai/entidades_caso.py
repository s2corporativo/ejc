# ── app/services/ai/entidades_caso.py ────────────────────────────────────────
# Helper: monta o dict de ENTIDADES NOMEADAS de um CASO para o pseudonimizador
# reversível (`pseudonimizar_mensagens`/`ai_gateway.chat(..., entidades=...)`).
#
# Enquanto o gateway pseudonimiza a PII ESTRUTURAL (CPF/CNPJ/processo/e-mail/
# telefone/CEP) automaticamente, os NOMES PRÓPRIOS (cliente, empresa, advogado,
# parte contrária) só viram marcadores consistentes ([CLIENTE_1], [EMPRESA_1],
# [ADVOGADO_1], [PARTE_CONTRARIA_1]) se o chamador informar `entidades`. Este
# helper carrega o Case (com client, partes e advogado) e monta esse dict a
# partir do vocabulário de nomes do próprio caso.
#
# CONTRATO DE ROBUSTEZ: NUNCA levanta exceção (uma falha aqui não pode derrubar
# uma análise de IA). Caso inexistente / sem partes / erro de banco → retorna {}
# com log de aviso. O dict retornado NÃO tem chaves vazias.
#
# ⚠️  Os nomes montados aqui são PII: alimentam APENAS o pseudonimizador (que os
#     troca por marcadores antes de qualquer provider externo) — nunca são
#     logados nem persistidos por este módulo.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.case import Case

logger = logging.getLogger("ejc.ai.entidades_caso")

# Mesmo piso do pseudonimizador (nomes < 4 chars são descartados para evitar
# falso-positivo de substituição, ex.: iniciais, "SA").
_PISO_NOME = 4

# Papéis processuais ADVERSARIAIS (parte contrária) — comparados sobre o
# papel_processual + tipo da CaseParte, normalizados (minúsculo, sem acento
# resolvido por substring). "na dúvida, inclui todos os que não são o cliente".
_PAPEIS_ADVERSARIAIS = (
    "reu", "réu", "requerido", "executado", "parte contraria", "parte contrária",
    "adverso", "impugnado", "suscitado", "denunciado", "embargado",
)


def _push(destino: list[str], vistos: set[str], *nomes: str | None) -> None:
    """Adiciona `nomes` válidos a `destino`, deduplicando GLOBALMENTE (case-insensitive)
    e aplicando o piso de tamanho. Um mesmo nome entra em UMA única chave (a
    primeira na ordem de processamento), espelhando a consistência de marcador
    do pseudonimizador."""
    for nome in nomes:
        nome = (nome or "").strip()
        if len(nome) < _PISO_NOME:
            continue
        chave = nome.casefold()
        if chave in vistos:
            continue
        vistos.add(chave)
        destino.append(nome)


async def entidades_do_caso(db: AsyncSession, case_id: str) -> dict[str, list[str]]:
    """Retorna {"cliente": [...], "empresa": [...], "advogado": [...],
    "parte_contraria": [...]} para o `case_id`, pronto para `entidades=` do
    gateway. Chaves vazias são omitidas. NUNCA levanta — em qualquer falha
    retorna {} (fail-safe: a IA segue com pseudonimização estrutural apenas)."""
    if not case_id:
        return {}
    try:
        caso = (
            await db.execute(
                select(Case)
                .where(Case.id == str(case_id), Case.deleted_at.is_(None))
                .options(
                    selectinload(Case.client),
                    selectinload(Case.partes),
                    selectinload(Case.advogado_responsavel),
                )
            )
        ).scalar_one_or_none()
        if caso is None:
            logger.warning("entidades_do_caso: caso %s inexistente/removido — {}", case_id)
            return {}

        vistos: set[str] = set()
        cliente: list[str] = []
        empresa: list[str] = []
        advogado: list[str] = []
        parte_contraria: list[str] = []

        # ── Cliente / Empresa ────────────────────────────────────────────────
        cli = caso.client
        if cli is not None:
            tipo = str(getattr(cli.tipo, "value", cli.tipo) or "")
            # nome de exibição SEM o placeholder "Cliente sem nome" da property.
            nome_exib = (cli.nome or cli.razao_social or "").strip()
            _push(cliente, vistos, nome_exib)
            if tipo == "PJ":
                _push(empresa, vistos, cli.razao_social, cli.nome_fantasia)

        # ── Advogado responsável (User.full_name; `nome` como fallback) ──────
        adv = caso.advogado_responsavel
        if adv is not None:
            _push(advogado, vistos, getattr(adv, "full_name", None) or getattr(adv, "nome", None))

        # ── Parte contrária: campo livre do caso + partes adversariais ───────
        # nomes já capturados como cliente/empresa não voltam (dedup global).
        cand_pc: list[str] = []
        if caso.parte_contraria:
            cand_pc.append(caso.parte_contraria)
        for p in (caso.partes or []):
            nome_p = (p.nome or "").strip()
            if not nome_p:
                continue
            # Não trate como adversária a parte VINCULADA ao nosso cliente.
            if p.client_id and caso.client_id and p.client_id == caso.client_id:
                continue
            papel = f"{p.papel_processual or ''} {p.tipo or ''}".casefold()
            adversarial = any(tok in papel for tok in _PAPEIS_ADVERSARIAIS)
            # adversarial explícito OU (na dúvida) qualquer parte que não seja o cliente.
            if adversarial or nome_p.casefold() not in vistos:
                cand_pc.append(nome_p)
        _push(parte_contraria, vistos, *cand_pc)

        entidades: dict[str, list[str]] = {}
        if cliente:
            entidades["cliente"] = cliente
        if empresa:
            entidades["empresa"] = empresa
        if advogado:
            entidades["advogado"] = advogado
        if parte_contraria:
            entidades["parte_contraria"] = parte_contraria
        return entidades
    except Exception as e:  # noqa: BLE001 — helper best-effort: nunca quebra a IA
        logger.warning("entidades_do_caso(%s) falhou: %s", case_id, str(e)[:200])
        return {}
