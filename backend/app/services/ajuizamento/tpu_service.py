# ── app/services/ajuizamento/tpu_service.py ──────────────────────────────────
# TpuService — Tabelas Processuais Unificadas (classes, assuntos, movimentos,
# documentos) sobre cache local persistido (`judicial_tpu_itens`).
#
# Fonte oficial de sincronização: SGT/CNJ público (app/integrations/
# cnj_sgt_client.CnjSgtClient — pesquisarItemPublicoWS/ultimaVersao). A
# sincronização é CONDITIONAL à flag CNJ_SGT_ENABLED; a API TPU do gateway
# PDPJ (https://gateway.stg.cloud.pje.jus.br/tpu/) exige SSO e não é usada
# até habilitação. Sem sync, o serviço opera sobre o cache (vazio → a
# validação avisa "código não verificado", nunca bloqueia).
#
# Nada é hardcoded: nenhuma lista de classes/assuntos vive no código.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.feature_flags import enabled as flag_habilitada
from app.models.ajuizamento import JudicialTpuItem
from app.services.ajuizamento.capacidades import EstadoCapacidade

TIPOS = ("classe", "assunto", "movimento", "documento")
_TIPO_SGT = {"classe": "C", "assunto": "A", "movimento": "M"}   # documento: sem tabela no SGT público


class TpuTipoInvalido(ValueError):
    pass


def _validar_tipo(tipo: str) -> str:
    t = (tipo or "").strip().lower()
    if t not in TIPOS:
        raise TpuTipoInvalido(f"tipo TPU inválido: {tipo!r} (use {', '.join(TIPOS)})")
    return t


def _normalizar_item_sgt(bruto: Any) -> dict[str, Any] | None:
    """Reduz um item do SGT (dict solto do parser SOAP) ao contrato do cache.
    Chaves conhecidas do WS público: cod_item, nome, situacao, cod_item_pai,
    dt_publicacao (variações de caixa toleradas)."""
    if not isinstance(bruto, dict):
        return None
    lower = {str(k).lower(): v for k, v in bruto.items()}
    codigo = lower.get("cod_item") or lower.get("codigo") or lower.get("seq_item")
    nome = lower.get("nome") or lower.get("descricao")
    if not codigo or not nome:
        return None
    situacao = str(lower.get("situacao") or "A").upper()
    return {
        "codigo": str(codigo).strip(),
        "descricao": str(nome).strip()[:400],
        "situacao": "ativo" if situacao.startswith("A") else "inativo",
        "pai_codigo": (str(lower.get("cod_item_pai")).strip() if lower.get("cod_item_pai") else None),
        "versao": (str(lower.get("dt_publicacao")).strip()[:40] if lower.get("dt_publicacao") else None),
    }


class TpuService:
    def __init__(self, db: AsyncSession, cliente_sgt: Any | None = None) -> None:
        self.db = db
        self._sgt = cliente_sgt

    # ── Estado ────────────────────────────────────────────────────────────
    @staticmethod
    def estado_sync() -> tuple[EstadoCapacidade, str]:
        if flag_habilitada("cnj_sgt"):
            return EstadoCapacidade.SUPPORTED, "SGT/CNJ público habilitado (CNJ_SGT_ENABLED)"
        return EstadoCapacidade.CONDITIONAL, "sincronização exige CNJ_SGT_ENABLED=true; operando sobre o cache local"

    async def resumo(self) -> dict[str, Any]:
        linhas = (await self.db.execute(
            select(JudicialTpuItem.tipo, func.count(), func.max(JudicialTpuItem.sincronizado_em))
            .group_by(JudicialTpuItem.tipo)
        )).all()
        por_tipo = {t: {"itens": 0, "sincronizado_em": None} for t in TIPOS}
        for tipo, n, ultimo in linhas:
            por_tipo[tipo] = {"itens": int(n), "sincronizado_em": ultimo.isoformat() if ultimo else None}
        estado, motivo = self.estado_sync()
        return {"sync": {"estado": estado.value, "motivo": motivo}, "por_tipo": por_tipo}

    # ── Leitura (cache) ───────────────────────────────────────────────────
    async def listar(self, tipo: str, busca: str | None = None, limite: int = 50,
                     somente_ativos: bool = True) -> list[dict[str, Any]]:
        t = _validar_tipo(tipo)
        stmt = select(JudicialTpuItem).where(JudicialTpuItem.tipo == t)
        if somente_ativos:
            stmt = stmt.where(JudicialTpuItem.situacao == "ativo")
        if busca:
            b = busca.strip()
            stmt = stmt.where(or_(
                JudicialTpuItem.codigo == b,
                func.lower(JudicialTpuItem.descricao).like(f"%{b.lower()}%"),
            ))
        stmt = stmt.order_by(JudicialTpuItem.descricao).limit(max(1, min(limite, 200)))
        return [self._dict(i) for i in (await self.db.execute(stmt)).scalars().all()]

    async def obter(self, tipo: str, codigo: str) -> dict[str, Any] | None:
        t = _validar_tipo(tipo)
        item = (await self.db.execute(
            select(JudicialTpuItem).where(JudicialTpuItem.tipo == t, JudicialTpuItem.codigo == str(codigo))
        )).scalar_one_or_none()
        return self._dict(item) if item else None

    async def lookup_fn(self):
        """Devolve um lookup síncrono (tipo, codigo) → descrição para o
        preflight, pré-carregando o cache dos tipos consultáveis. Retorna None
        quando o cache está vazio (o preflight trata como 'não verificado')."""
        linhas = (await self.db.execute(
            select(JudicialTpuItem.tipo, JudicialTpuItem.codigo, JudicialTpuItem.descricao)
            .where(JudicialTpuItem.tipo.in_(("classe", "assunto")))
        )).all()
        if not linhas:
            return None
        cache = {(t, c): d for t, c, d in linhas}
        return lambda tipo, codigo: cache.get((tipo, str(codigo)))

    # ── Escrita ───────────────────────────────────────────────────────────
    async def importar_itens(self, tipo: str, itens: list[dict[str, Any]], origem: str) -> int:
        """Upsert de itens já normalizados (sync SGT ou carga administrativa a
        partir de arquivo oficial). Commit é do chamador."""
        t = _validar_tipo(tipo)
        if not itens:
            return 0
        codigos = [str(i["codigo"]) for i in itens if i.get("codigo")]
        existentes = {
            e.codigo: e for e in (await self.db.execute(
                select(JudicialTpuItem).where(JudicialTpuItem.tipo == t, JudicialTpuItem.codigo.in_(codigos))
            )).scalars().all()
        }
        agora = datetime.now(timezone.utc)
        n = 0
        for i in itens:
            codigo = str(i.get("codigo") or "").strip()
            descricao = str(i.get("descricao") or "").strip()
            if not codigo or not descricao:
                continue
            alvo = existentes.get(codigo)
            if alvo is None:
                alvo = JudicialTpuItem(id=str(uuid4()), tipo=t, codigo=codigo, descricao=descricao[:400])
                self.db.add(alvo)
                existentes[codigo] = alvo
            alvo.descricao = descricao[:400]
            alvo.situacao = i.get("situacao") or "ativo"
            alvo.pai_codigo = i.get("pai_codigo")
            alvo.versao = i.get("versao")
            alvo.origem = origem[:40]
            alvo.sincronizado_em = agora
            n += 1
        return n

    async def sincronizar_por_termo(self, tipo: str, termo: str, tipo_pesquisa: str = "N") -> dict[str, Any]:
        """Sincroniza do SGT/CNJ os itens que casam com `termo` (nome ou
        código). O WS público não expõe dump completo — a carga se faz por
        termos/códigos, acumulando no cache."""
        t = _validar_tipo(tipo)
        estado, motivo = self.estado_sync()
        if estado != EstadoCapacidade.SUPPORTED:
            return {"estado": estado.value, "motivo": motivo, "importados": 0}
        if t not in _TIPO_SGT:
            return {"estado": EstadoCapacidade.UNSUPPORTED.value,
                    "motivo": "SGT público não expõe a tabela de documentos", "importados": 0}
        cliente = self._sgt
        if cliente is None:
            from app.integrations.cnj_sgt_client import CnjSgtClient
            cliente = CnjSgtClient()
        bruto = await cliente.pesquisar(_TIPO_SGT[t], termo, tipo_pesquisa=tipo_pesquisa)
        versao = None
        try:
            versao = await cliente.ultima_versao()
        except Exception:   # noqa: BLE001 — versão é metadado; não derruba o sync
            versao = None
        itens_brutos = bruto if isinstance(bruto, list) else [bruto]
        normalizados = [n for n in (_normalizar_item_sgt(b) for b in itens_brutos) if n]
        if versao:
            for n in normalizados:
                n["versao"] = n.get("versao") or str(versao)[:40]
        importados = await self.importar_itens(t, normalizados, origem="cnj_sgt")
        return {"estado": estado.value, "motivo": motivo, "importados": importados, "versao": versao}

    @staticmethod
    def _dict(i: JudicialTpuItem) -> dict[str, Any]:
        return {
            "tipo": i.tipo, "codigo": i.codigo, "descricao": i.descricao,
            "situacao": i.situacao, "pai_codigo": i.pai_codigo, "versao": i.versao,
            "origem": i.origem,
            "sincronizado_em": i.sincronizado_em.isoformat() if i.sincronizado_em else None,
        }
