# ── app/services/querido_diario_monitor.py ───────────────────────────────────
# Monitoramento periódico de diários oficiais MUNICIPAIS (Querido Diário) →
# base de conhecimento, com curadoria humana obrigatória.
#
# POR QUE ESTE MÓDULO EXISTE
#
# O cliente do Querido Diário (`integrations/querido_diario_client.py`) já
# existia, mas só era alcançável sob demanda por endpoint — ninguém abre uma
# tela todo dia para perguntar se saiu algo no diário do município. O valor
# operacional da fonte é justamente o contrário: descobrir sozinho que saiu.
#
# O QUE ELE FAZ, E O QUE DELIBERADAMENTE NÃO FAZ
#
# Faz: varre os municípios e termos declarados em configuração, na janela de
# dias configurada, e grava cada achado como documento de conhecimento com
# `rag_status='pendente'` — igual ao caminho DJEN→RAG (`djen_service`).
#
# NÃO faz: vincular o achado a um caso ou cliente. Vincular exigiria casar
# texto de diário com processo por heurística, e um vínculo errado é pior que
# vínculo nenhum num sistema jurídico. O achado entra como conhecimento
# PÚBLICO (`client_id=None`) e a curadoria humana decide.
#
# NATUREZA DA FONTE (registrado porque tem consequência jurídica)
#
# O Querido Diário é agregador cívico, não a fonte que torna o ato
# juridicamente autêntico — o próprio cliente documenta isso. Por isso todo
# documento gravado aqui carrega a URL do diário de origem e o marcador de
# conferência obrigatória: o excerto NUNCA é prova autossuficiente.
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Pausa entre chamadas: a documentação da API recomenda uso razoável, na ordem
# de 60 req/min. 1,1 s mantém folga mesmo com municípios × termos grandes.
_PAUSA_ENTRE_CHAMADAS_S = 1.1

_CATEGORIA = "diario_oficial_municipal"


def _csv(valor: str | None) -> list[str]:
    return [p.strip() for p in (valor or "").split(",") if p.strip()]


def _chave_origem(codigo_ibge: str, url: str) -> str:
    """Chave de dedup: a URL do diário identifica a edição de forma estável.

    Inclui o código IBGE porque a mesma edição pode ser devolvida em consultas
    de termos diferentes — o dedup de `upsert_documento` colapsa as repetições.
    """
    return f"querido_diario:{codigo_ibge}:{url}"


def _montar_documento(codigo_ibge: str, termo: str, item: dict[str, Any]) -> dict | None:
    """Projeta um resultado da API no contrato de `upsert_documento`.

    Devolve None quando o item não traz o mínimo para ser auditável (URL de
    origem e algum texto) — documento sem origem conferível não entra na base.
    """
    url = (item.get("url") or item.get("file_url") or "").strip()
    excertos = [e.strip() for e in (item.get("excerpts") or []) if e and e.strip()]
    if not url or not excertos:
        return None

    data_pub = (item.get("date") or "").strip()
    territorio = (item.get("territory_name") or "").strip()
    uf = (item.get("state_code") or "").strip()
    rotulo_local = " / ".join(p for p in (territorio, uf) if p) or codigo_ibge

    conteudo = "\n\n".join(excertos)
    titulo = f"Diário Oficial de {rotulo_local}"
    if data_pub:
        titulo = f"{titulo} — {data_pub}"

    return {
        "titulo": titulo[:500],
        "categoria": _CATEGORIA,
        "conteudo": conteudo,
        "chave_origem": _chave_origem(codigo_ibge, url),
        "fonte": url,
        "extra": {
            "rag_status": "pendente",
            "tipo_fonte": "diario_oficial_municipal",
            "origem_captura": "querido_diario_monitor",
            "codigo_ibge": codigo_ibge,
            "termo_monitorado": termo,
            "data_publicacao": data_pub,
            "municipio": territorio,
            "uf": uf,
            # O agregador não autentica o ato: a conferência no diário oficial
            # de origem é obrigatória antes de qualquer uso jurídico.
            "natureza": "agregador_secundario",
            "conferencia_original_obrigatoria": True,
        },
    }


async def executar_monitoramento(db: AsyncSession) -> dict[str, Any]:
    """Varre municípios × termos configurados e ingere os achados.

    Devolve um dicionário de RESULTADO (não um "ok" mudo): quantos municípios e
    termos foram consultados, quantos achados vieram, quantos documentos novos
    entraram e quais consultas falharam. É esse dicionário que vai para o
    heartbeat — monitorar resultado, não execução (achado V2-3.1).
    """
    from app.core.config import get_settings
    from app.integrations import feature_flags
    from app.integrations.querido_diario_client import (
        QueridoDiarioClient,
        QueridoDiarioError,
    )
    from app.services import ingestion_service

    s = get_settings()
    municipios = _csv(getattr(s, "QUERIDO_DIARIO_MONITOR_MUNICIPIOS", ""))
    termos = _csv(getattr(s, "QUERIDO_DIARIO_MONITOR_TERMOS", ""))
    janela = max(1, int(getattr(s, "QUERIDO_DIARIO_MONITOR_JANELA_DIAS", 2)))

    resultado: dict[str, Any] = {
        "municipios": len(municipios),
        "termos": len(termos),
        "consultas": 0,
        "achados": 0,
        "novos": 0,
        "atualizados": 0,
        "erros": {},
    }

    # A flag da integração vale também para o job: ligar o monitor sem ligar a
    # fonte seria contornar o gate por um caminho lateral.
    if not feature_flags.enabled("querido_diario"):
        resultado["erros"]["integracao_desabilitada"] = 1
        return resultado
    if not municipios or not termos:
        # Configuração incompleta é ERRO visível, não sucesso vazio: sem isto o
        # painel mostraria "ok" para um monitor que nunca consultou nada.
        resultado["erros"]["configuracao_incompleta"] = 1
        return resultado

    hoje = date.today()
    inicio = hoje - timedelta(days=janela)
    cliente = QueridoDiarioClient()

    primeira = True
    for codigo_ibge in municipios:
        for termo in termos:
            if not primeira:
                await asyncio.sleep(_PAUSA_ENTRE_CHAMADAS_S)
            primeira = False
            resultado["consultas"] += 1
            try:
                payload = await cliente.buscar(
                    codigo_ibge=codigo_ibge,
                    termo=termo,
                    data_inicio=inicio,
                    data_fim=hoje,
                )
            except (QueridoDiarioError, ValueError) as exc:
                chave = type(exc).__name__
                resultado["erros"][chave] = resultado["erros"].get(chave, 0) + 1
                logger.warning(
                    "[QueridoDiário] consulta %s/%s falhou: %s",
                    codigo_ibge, termo, chave,
                )
                continue

            itens = payload.get("gazettes") or []
            resultado["achados"] += len(itens)
            for item in itens:
                doc = _montar_documento(codigo_ibge, termo, item)
                if not doc:
                    continue
                try:
                    # Savepoint: um documento problemático não derruba a varredura.
                    async with db.begin_nested():
                        estado = await ingestion_service.upsert_documento(
                            db, embutir_vetores=False, **doc
                        )
                    if estado == "novo":
                        resultado["novos"] += 1
                    elif estado == "atualizado":
                        resultado["atualizados"] += 1
                except Exception as exc:  # noqa: BLE001 — um item não para o job
                    chave = f"ingestao_{type(exc).__name__}"
                    resultado["erros"][chave] = resultado["erros"].get(chave, 0) + 1

    await db.commit()
    return resultado
