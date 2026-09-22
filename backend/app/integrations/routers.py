# ── app/integrations/routers.py ──────────────────────────────────────────────
# Routers das integrações externas públicas (/api/integracoes/*).
#
# Segurança:
#   • TODOS os endpoints exigem JWT (get_current_user), além do AuthMiddleware.
#   • Rate limit por fonte evita transformar o EJC em proxy aberto.
#   • Consultas que tocam dado de terceiro (DJEN/CNPJ) geram audit_log.
#   • 502 usa detail genérico; resposta/stack do upstream não vaza ao cliente.
#   • Hosts dos novos conectores são fixos/allowlisted nos respectivos clients.
#
# O Conecta gov.br permanece fora até credenciamento institucional real.
# SEM `from __future__ import annotations`: slowapi/FastAPI resolve anotações
# deste módulo em runtime.
import logging
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services import datajud_service

from app.integrations.brasilapi_client import BrasilApiClient, BrasilApiError
from app.integrations.ckan_public_client import (
    CkanPublicClient,
    CkanPublicError,
)
from app.integrations.cnj_sgt_client import CnjSgtClient, CnjSgtError
from app.integrations.datajud_client import TRIBUNAL_ALIASES, DataJudError
from app.integrations.djen_comunica_client import (
    DjenComunicaClient,
    DjenComunicaError,
)
from app.integrations.ibge_localidades_client import (
    IbgeLocalidadesClient,
    IbgeLocalidadesError,
)
from app.integrations.ide_sisema_client import IdeSisemaClient, IdeSisemaError
from app.integrations.pgfn_open_data_client import PgfnOpenDataClient, PgfnOpenDataError
from app.integrations.querido_diario_client import QueridoDiarioClient, QueridoDiarioError
from app.integrations.tcu_client import TcuPublicClient, TcuPublicError

logger = logging.getLogger("ejc.integracoes")

datajud_router = APIRouter(prefix="/integracoes/datajud", tags=["integracoes"])
djen_router = APIRouter(prefix="/integracoes/djen", tags=["integracoes"])
# Nome mantido por compatibilidade com main.py. O prefixo foi elevado para
# /integracoes e as rotas BrasilAPI ganharam /brasilapi explicitamente, mantendo
# os paths finais históricos e permitindo centralizar as novas fontes sem editar
# main.py enquanto ele está sob lock de outro PR.
brasilapi_router = APIRouter(prefix="/integracoes", tags=["integracoes"])

class _DataJudCanonicalAdapter:
    """Compatibilidade do contrato antigo sobre o serviço canônico."""

    async def consultar_processo(self, numero: str, _alias: str | None = None):
        return await datajud_service.consultar_processo(numero)


_datajud = _DataJudCanonicalAdapter()
_djen = DjenComunicaClient()
_brasilapi = BrasilApiClient()
_cnj_sgt = CnjSgtClient()
_tcu = TcuPublicClient()
_ibge = IbgeLocalidadesClient()
_querido = QueridoDiarioClient()
_sisema = IdeSisemaClient()
_pgfn = PgfnOpenDataClient()
_ckan = {
    "ibama": CkanPublicClient("ibama"),
    "mj": CkanPublicClient("mj"),
    "cvm": CkanPublicClient("cvm"),
    "tse": CkanPublicClient("tse"),
}
_CKAN_DEFAULT_QUERY = {
    "ibama": "auto de infração embargo",
    "mj": "Consumidor.gov.br",
    "cvm": "companhias abertas",
    "tse": "candidatos 2026",
}

_ALIAS_POR_SIGLA = {
    alias.removeprefix("api_publica_").upper(): alias
    for alias in datajud_service._SEG_TR_ALIAS.values()
}
_ALIAS_POR_SIGLA.update(TRIBUNAL_ALIASES)

_ERROS_UPSTREAM = (
    DataJudError,
    DjenComunicaError,
    BrasilApiError,
    CkanPublicError,
    CnjSgtError,
    TcuPublicError,
    IbgeLocalidadesError,
    QueridoDiarioError,
    IdeSisemaError,
    PgfnOpenDataError,
    ValueError,
    httpx.HTTPError,
)


def _falha_upstream(origem: str, exc: Exception) -> HTTPException:
    logger.warning(
        "Integração %s falhou: %s: %s",
        origem,
        type(exc).__name__,
        str(exc)[:500],
    )
    return HTTPException(502, f"Falha na consulta à API externa ({origem}).")


def _somente_digitos(valor: str, tamanho: int, campo: str) -> str:
    limpo = "".join(ch for ch in valor if ch.isdigit())
    if len(limpo) != tamanho:
        raise HTTPException(
            400,
            f"{campo} inválido: esperado {tamanho} dígitos (com ou sem máscara).",
        )
    return limpo


async def _auditar_consulta(
    db: AsyncSession, cu: User, entidade: str, registro_id: str,
) -> None:
    await criar_audit_log(
        db,
        cu.id,
        getattr(cu.role, "value", str(cu.role)),
        "CONSULTA_EXTERNA",
        entidade,
        registro_id,
    )
    await db.commit()


# ── DataJud / DJEN / BrasilAPI existentes ────────────────────────────────────

@datajud_router.get("/processos/{tribunal}/{numero_processo}")
@limiter.limit("30/minute")
async def consultar_processo_datajud(
    request: Request,
    tribunal: str,
    numero_processo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alias = _ALIAS_POR_SIGLA.get(tribunal.upper())
    if not alias:
        raise HTTPException(
            400,
            f"Tribunal '{tribunal}' não mapeado — use a sigla oficial "
            "(ex.: TJMG, TJSP, TRT3, TRF1, STJ, TST).",
        )
    numero = _somente_digitos(numero_processo, 20, "Número de processo (CNJ)")
    try:
        # Família DataJud possui uma única implementação de transporte,
        # retry, cache e governança. O parâmetro tribunal permanece no
        # contrato HTTP, mas o alias oficial é derivado do número CNJ pela
        # fachada canônica para impedir divergência entre routers.
        resultado = await _datajud.consultar_processo(numero, alias)
    except datajud_service.DataJudDesabilitadoError as exc:
        raise HTTPException(503, str(exc))
    except (datajud_service.TribunalNaoMapeadoError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    except (DataJudError, httpx.HTTPError) as exc:
        raise _falha_upstream("DataJud", exc)
    await _auditar_consulta(db, current_user, "integracoes_datajud", numero)
    return resultado


@djen_router.get("/oab/{uf}/{numero_oab}")
@limiter.limit("30/minute")
async def consultar_djen_por_oab(
    request: Request,
    uf: str = Path(pattern=r"^[A-Za-z]{2}$"),
    numero_oab: str = Path(pattern=r"^\d{1,10}$"),
    data_inicio: Optional[date] = Query(None, description="dataDisponibilizacaoInicio"),
    data_fim: Optional[date] = Query(None, description="dataDisponibilizacaoFim"),
    pagina: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        resultado = await _djen.consultar_por_oab(
            numero_oab,
            uf.upper(),
            data_inicio=data_inicio,
            data_fim=data_fim,
            pagina=pagina,
        )
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("DJEN/Comunica", exc)
    await _auditar_consulta(
        db, current_user, "integracoes_djen", f"OAB {numero_oab}/{uf.upper()}"
    )
    return resultado


@djen_router.get("/processos/{numero_processo}")
@limiter.limit("30/minute")
async def consultar_djen_por_processo(
    request: Request,
    numero_processo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    numero = _somente_digitos(numero_processo, 20, "Número de processo (CNJ)")
    try:
        resultado = await _djen.consultar_por_processo(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("DJEN/Comunica", exc)
    await _auditar_consulta(db, current_user, "integracoes_djen", numero)
    return resultado


@brasilapi_router.get("/brasilapi/cnpj/{cnpj}")
@limiter.limit("30/minute")
async def consultar_cnpj(
    request: Request,
    cnpj: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    numero = _somente_digitos(cnpj, 14, "CNPJ")
    try:
        resultado = await _brasilapi.consultar_cnpj(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("BrasilAPI/CNPJ", exc)
    await _auditar_consulta(db, current_user, "integracoes_cnpj", numero)
    return resultado


@brasilapi_router.get("/brasilapi/cep/{cep}")
@limiter.limit("30/minute")
async def consultar_cep(
    request: Request,
    cep: str,
    current_user: User = Depends(get_current_user),
):
    numero = _somente_digitos(cep, 8, "CEP")
    try:
        return await _brasilapi.consultar_cep(numero)
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("BrasilAPI/CEP", exc)


# ── CNJ TPU/SGT ──────────────────────────────────────────────────────────────

@brasilapi_router.get("/cnj/tpu/versao")
@limiter.limit("20/minute")
async def versao_tpu(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    try:
        return {"ultima_versao": await _cnj_sgt.ultima_versao(), "fonte": "CNJ/SGT"}
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("CNJ/SGT", exc)


@brasilapi_router.get("/cnj/tpu/pesquisar")
@limiter.limit("30/minute")
async def pesquisar_tpu(
    request: Request,
    tipo_tabela: str = Query(..., pattern=r"^[AMC]$"),
    valor: str = Query(..., min_length=1, max_length=200),
    tipo_pesquisa: str = Query("N", pattern=r"^[GNC]$"),
    current_user: User = Depends(get_current_user),
):
    try:
        resultado = await _cnj_sgt.pesquisar(
            tipo_tabela, valor, tipo_pesquisa=tipo_pesquisa
        )
        return {"fonte": "CNJ/SGT — Tabelas Processuais Unificadas", "resultado": resultado}
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("CNJ/SGT", exc)


# ── TCU ──────────────────────────────────────────────────────────────────────

@brasilapi_router.get("/tcu/acordaos")
@limiter.limit("20/minute")
async def listar_acordaos_tcu(
    request: Request,
    inicio: int = Query(0, ge=0),
    quantidade: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    try:
        itens = await _tcu.listar_acordaos(inicio=inicio, quantidade=quantidade)
        return {"fonte": "TCU — Dados Abertos", "total_retornado": len(itens), "items": itens}
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("TCU", exc)


# ── IBGE Localidades ─────────────────────────────────────────────────────────

@brasilapi_router.get("/ibge/municipios/{uf}")
@limiter.limit("30/minute")
async def municipios_ibge(
    request: Request,
    uf: str = Path(pattern=r"^[A-Za-z]{2}$"),
    current_user: User = Depends(get_current_user),
):
    try:
        itens = await _ibge.municipios_por_uf(uf.upper())
        return {"uf": uf.upper(), "total": len(itens), "items": itens}
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("IBGE Localidades", exc)


@brasilapi_router.get("/ibge/canonicalizar")
@limiter.limit("30/minute")
async def canonicalizar_municipio_ibge(
    request: Request,
    nome: str = Query(..., min_length=1, max_length=120),
    uf: str = Query(..., pattern=r"^[A-Za-z]{2}$"),
    current_user: User = Depends(get_current_user),
):
    try:
        item = await _ibge.canonicalizar(nome, uf.upper())
        if item is None:
            raise HTTPException(404, "Município não localizado de forma unívoca no IBGE.")
        return item
    except HTTPException:
        raise
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("IBGE Localidades", exc)


# ── CKAN oficiais: IBAMA, MJ/Consumidor.gov.br, CVM e TSE ────────────────────

@brasilapi_router.get("/dados-publicos/{fonte}/recursos")
@limiter.limit("20/minute")
async def recursos_ckan_oficiais(
    request: Request,
    fonte: str = Path(pattern=r"^(ibama|mj|cvm|tse)$"),
    q: Optional[str] = Query(None, max_length=200),
    formatos: Optional[str] = Query(None, max_length=80, description="CSV,JSON,XML,ZIP"),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    consulta = (q or _CKAN_DEFAULT_QUERY[fonte]).strip()
    fmts = [x.strip() for x in formatos.split(",") if x.strip()] if formatos else None
    try:
        recursos = await _ckan[fonte].recursos_por_busca(
            consulta, formatos=fmts, rows=5, limit=limit
        )
        return {
            "fonte": fonte,
            "consulta": consulta,
            "total": len(recursos),
            "items": [r.to_dict() for r in recursos],
            "observacao": (
                "Retorno contém metadados/links de recursos oficiais; arquivos volumosos "
                "não são baixados automaticamente pelo EJC."
            ),
        }
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream(f"CKAN/{fonte}", exc)


# ── PGFN — Dívida Ativa (bulk oficial) ───────────────────────────────────────

@brasilapi_router.get("/pgfn/divida-ativa/recursos")
@limiter.limit("10/minute")
async def recursos_pgfn(
    request: Request,
    ano: Optional[int] = Query(None, ge=2019, le=2100),
    current_user: User = Depends(get_current_user),
):
    try:
        itens = await _pgfn.listar_recursos(ano=ano)
        return {
            "fonte": "PGFN — Dados Abertos da Dívida Ativa",
            "total": len(itens),
            "items": itens,
            "observacao": "Catálogo de arquivos bulk; não realiza consulta individual de CPF/CNPJ.",
        }
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("PGFN", exc)


# ── Querido Diário (agregador secundário municipal) ──────────────────────────

@brasilapi_router.get("/querido-diario/{codigo_ibge}")
@limiter.limit("20/minute")
async def buscar_querido_diario(
    request: Request,
    codigo_ibge: str = Path(pattern=r"^\d{7}$"),
    termo: str = Query(..., min_length=2, max_length=300),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    tamanho: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    try:
        return await _querido.buscar(
            codigo_ibge=codigo_ibge,
            termo=termo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            tamanho=tamanho,
        )
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("Querido Diário", exc)


# ── IDE-Sisema/MG (WFS público) ──────────────────────────────────────────────

@brasilapi_router.get("/ide-sisema/camadas")
@limiter.limit("10/minute")
async def listar_camadas_sisema(
    request: Request,
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    try:
        camadas = await _sisema.listar_camadas()
        if q:
            termo = q.casefold()
            camadas = [
                c for c in camadas
                if termo in f"{c.get('name','')} {c.get('title','')} {c.get('abstract','')}".casefold()
            ]
        return {"fonte": "IDE-Sisema — Sisema/MG", "total": len(camadas), "items": camadas[:limit]}
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("IDE-Sisema", exc)


@brasilapi_router.get("/ide-sisema/feicoes")
@limiter.limit("20/minute")
async def consultar_sisema(
    request: Request,
    type_name: str = Query(..., min_length=1, max_length=180),
    bbox: Optional[str] = Query(None, max_length=120, description="minx,miny,maxx,maxy"),
    count: int = Query(50, ge=1, le=200),
    srs_name: str = Query("EPSG:4326", pattern=r"^EPSG:(4326|4674)$"),
    current_user: User = Depends(get_current_user),
):
    coords = None
    if bbox:
        try:
            coords = [float(x.strip()) for x in bbox.split(",")]
        except ValueError:
            raise HTTPException(400, "bbox inválido: use minx,miny,maxx,maxy")
    try:
        return await _sisema.consultar_camadas(
            type_name, bbox=coords, count=count, srs_name=srs_name
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except _ERROS_UPSTREAM as exc:
        raise _falha_upstream("IDE-Sisema", exc)
