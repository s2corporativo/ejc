"""Persistência minimizada dos snapshots de jurimetria externa.

Esta camada recebe SOMENTE a resposta já agregada do serviço de jurimetria
externa. Ela nunca recebe documentos brutos do DataJud e rejeita, de forma
fail-closed, qualquer chave que pareça identificador processual/PII.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models.jurimetria_snapshot import JurimetriaSnapshot

_FORBIDDEN_KEYS = {
    "numeroprocesso", "numero_processo", "nr_cnj", "canonical_process",
    "identifier", "partes", "parte", "cpf", "cnpj", "relator",
    "raw_datajud", "ementa", "acordao",
}

_AGGREGATE_KEYS = {
    "total", "por_municipio", "por_assunto", "por_municipio_assunto",
    "reforma_2grau", "fontes_complementares",
}
_FILTER_KEYS = {"tribunal", "municipios", "classe", "assunto", "desde", "ate"}


def _assert_minimizado(valor: Any, caminho: str = "snapshot") -> None:
    if isinstance(valor, dict):
        for chave, item in valor.items():
            normal = str(chave).replace("-", "_").lower()
            if normal in _FORBIDDEN_KEYS:
                raise ValueError(
                    f"snapshot jurimétrico rejeitado: chave sensível em {caminho}.{chave}"
                )
            _assert_minimizado(item, f"{caminho}.{chave}")
    elif isinstance(valor, list):
        for idx, item in enumerate(valor):
            _assert_minimizado(item, f"{caminho}[{idx}]")


def _parse_coletado_em(valor: str | None) -> datetime:
    if not valor:
        return datetime.now(timezone.utc)
    texto = str(valor).strip()
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    data = datetime.fromisoformat(texto)
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(timezone.utc)


def preparar_snapshot(resposta: dict[str, Any]) -> dict[str, Any]:
    """Extrai somente filtros e agregados necessários à série histórica."""
    escopo = resposta.get("escopo") if isinstance(resposta.get("escopo"), dict) else {}
    coleta = resposta.get("coleta") if isinstance(resposta.get("coleta"), dict) else {}
    tpu = resposta.get("tpu") if isinstance(resposta.get("tpu"), dict) else {}

    filtros = {k: escopo.get(k) for k in _FILTER_KEYS if k in escopo}
    agregado = {k: resposta.get(k) for k in _AGGREGATE_KEYS if k in resposta}
    pacote = {"filtros": filtros, "agregado": agregado}
    _assert_minimizado(pacote)

    fonte = str(resposta.get("fonte") or "DataJud/CNJ")[:160]
    tribunal = str(escopo.get("tribunal") or "desconhecido")[:20]
    coletado_em = _parse_coletado_em(coleta.get("coletado_em"))
    tpu_versao = str(tpu.get("versao") or "")[:40] or None
    material_chave = json.dumps(
        {
            "fonte": fonte,
            "tribunal": tribunal,
            "filtros": filtros,
            "coletado_em": coletado_em.isoformat(),
            "tpu_versao": tpu_versao,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    snapshot_key = hashlib.sha256(material_chave).hexdigest()

    return {
        "snapshot_key": snapshot_key,
        "fonte": fonte,
        "tribunal": tribunal,
        "filtros": filtros,
        "agregado": agregado,
        "tpu_versao": tpu_versao,
        "n_documentos": int(coleta.get("n_documentos") or 0),
        "amostra_truncada": bool(resposta.get("amostra_truncada") or coleta.get("truncado")),
        "coletado_em": coletado_em,
    }


async def salvar_snapshot(db, resposta: dict[str, Any]) -> tuple[JurimetriaSnapshot, bool]:
    """Cria snapshot idempotente. Não commita; o chamador controla a transação."""
    dados = preparar_snapshot(resposta)
    existente = (
        await db.execute(
            select(JurimetriaSnapshot).where(
                JurimetriaSnapshot.snapshot_key == dados["snapshot_key"]
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        return existente, False
    snapshot = JurimetriaSnapshot(**dados)
    db.add(snapshot)
    await db.flush()
    return snapshot, True


async def listar_snapshots(db, *, tribunal: str | None = None, limit: int = 24) -> list[dict]:
    """Histórico agregado para a equipe jurídica; nunca devolve dado processual."""
    q = select(JurimetriaSnapshot)
    if tribunal:
        q = q.where(JurimetriaSnapshot.tribunal == tribunal)
    q = q.order_by(JurimetriaSnapshot.coletado_em.desc()).limit(max(1, min(limit, 100)))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": row.id,
            "fonte": row.fonte,
            "tribunal": row.tribunal,
            "filtros": row.filtros or {},
            "agregado": row.agregado or {},
            "tpu_versao": row.tpu_versao,
            "n_documentos": int(row.n_documentos or 0),
            "amostra_truncada": bool(row.amostra_truncada),
            "coletado_em": row.coletado_em.isoformat() if row.coletado_em else None,
        }
        for row in rows
    ]