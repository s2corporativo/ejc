# ── app/routers/ramos.py ──────────────────────────────────────────────────────
# AGREGADOR dos sub-routers de Áreas de Atuação (fatiamento P5, 20/08/2026).
# NENHUM path de rota mudou: os sub-routers usam caminhos absolutos e este
# módulo monta todos SEM prefixo adicional — paridade do snapshot de rotas
# preservada por construção. HITL: todas as saídas de cálculo são minutas.

from fastapi import APIRouter
import logging
from functools import wraps

from app.services.homologacao_ferramentas import motivo_nao_homologada, selo_homologacao

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Áreas de Atuação"])

# Tags default DESTE agregador. APIRouter.add_api_route sempre SOMA self.tags
# às tags da rota (current_tags = router.tags + route.tags), então repassar
# _r.tags integralmente na cópia duplicava a tag em TODAS as rotas — a origem
# já carrega as tags default do sub-router de origem (Task 23 / Onda 27c:
# 82/82 rotas copiadas ficavam com ['Áreas de Atuação', 'Áreas de Atuação']
# no OpenAPI). A cópia repassa só o DELTA de tags da origem (hoje vazio:
# nenhum endpoint dos ramos declara tags próprias além do default do router).
_TAGS_PADRAO_AGR = frozenset(router.tags)


def _tags_para_copia(rota_origem) -> list[str]:
    """Delta de tags da rota de origem (sem as tags default do agregador)."""
    return [_t for _t in (rota_origem.tags or []) if _t not in _TAGS_PADRAO_AGR]


def _copiar_rotas(origem: APIRouter) -> None:
    for _r in origem.routes:
        if getattr(_r, "path", None):
            router.add_api_route(_r.path, _r.endpoint, methods=_r.methods,
                                 dependencies=_r.dependencies,
                                 response_model=_r.response_model,
                                 status_code=_r.status_code,
                                 tags=_tags_para_copia(_r), summary=_r.summary,
                                 description=_r.description,
                                 responses=_r.responses,
                                 operation_id=_r.operation_id,
                                 response_class=_r.response_class,
                                 include_in_schema=_r.include_in_schema,
                                 openapi_extra=_r.openapi_extra,
                                 name=_r.name,
                                 deprecated=getattr(_r, "deprecated", False))


from app.routers import ramos_empresarial as _ramos_empresarial
_copiar_rotas(_ramos_empresarial.router)

from app.routers import ramos_civel as _ramos_civel
_copiar_rotas(_ramos_civel.router)

from app.routers import ramos_penal as _ramos_penal
_copiar_rotas(_ramos_penal.router)

from app.routers import ramos_trabalhista_esp as _ramos_trabalhista_esp
_copiar_rotas(_ramos_trabalhista_esp.router)

from app.routers import ramos_admin_esp as _ramos_admin_esp
_copiar_rotas(_ramos_admin_esp.router)

from app.routers import ramos_bancario as _ramos_bancario
_copiar_rotas(_ramos_bancario.router)

from app.routers import ramos_vitrine as _ramos_vitrine
_copiar_rotas(_ramos_vitrine.router)

# PAF federal versionado: monta antes das ferramentas complementares e substitui
# somente o path histórico correspondente. O handler legado permanece disponível
# no módulo original para rollback, mas não é montado pelo agregador canônico.
from app.routers import ramos_tributario_paf as _ramos_tributario_paf
_copiar_rotas(_ramos_tributario_paf.router)

def _selar_endpoint_nao_homologado(endpoint, caminho: str):
    """Aplica o selo da matriz à resposta real da API sem alterar a assinatura.

    O gate de `/pecas/demonstrativo` já impede promoção profissional usando a
    mesma matriz. Este wrapper fecha a outra metade do contrato: a própria rota
    consultada passa a devolver `homologada=false`, permitindo que a UI avise o
    usuário e desabilite o demonstrativo antes de qualquer tentativa de exportar.
    """
    @wraps(endpoint)
    async def endpoint_selado(*args, **kwargs):
        out = await endpoint(*args, **kwargs)
        if isinstance(out, dict):
            return selo_homologacao(caminho, out)
        return out

    return endpoint_selado


from app.routers import ramos_ferramentas_complementares as _ramos_ferramentas_complementares
for _r in _ramos_ferramentas_complementares.router.routes:
    if (
        getattr(_r, "path", None)
        and _r.path != _ramos_tributario_paf.ROTA_AUTO_INFRACAO
    ):
        _endpoint = _r.endpoint
        if motivo_nao_homologada(_r.path):
            _endpoint = _selar_endpoint_nao_homologado(_endpoint, _r.path)
        router.add_api_route(_r.path, _endpoint, methods=_r.methods,
                             dependencies=_r.dependencies,
                             response_model=_r.response_model,
                             status_code=_r.status_code,
                             tags=_tags_para_copia(_r), summary=_r.summary,
                             description=_r.description,
                             responses=_r.responses,
                             operation_id=_r.operation_id,
                             response_class=_r.response_class,
                             include_in_schema=_r.include_in_schema,
                             openapi_extra=_r.openapi_extra,
                             name=_r.name,
                             deprecated=getattr(_r, "deprecated", False))


# ── Registro de caminhos válidos das ferramentas (Onda 3, Issue #702) ────────
# Fonte única para validar o campo `ferramenta` do demonstrativo de cálculo em
# routers/peca_geracao.py: deriva da própria APIRouter (precisa vir DEPOIS de
# todas as rotas acima estarem registradas), então nunca diverge das rotas de
# fato existentes — não é uma lista mantida à mão que pode ficar desatualizada.
# `normalizar_caminho_ferramenta` é a MESMA porta usada pelo selo e pelo
# bloqueio: caminho válido, selo, bloqueio e gate do demonstrativo compartilham
# uma única semântica de normalização.
# ── Compatibilidade: símbolos consumidos por peca_geracao.py e testes ──
from app.routers.ramos_empresarial import EmpresarialIn, emp_listar, emp_criar, emp_atualizar, emp_remover, emp_tipos, emp_prazos_rj, emp_cade  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_civel import CivelIn, civ_listar, civ_criar, civ_atualizar, civ_remover, civ_prazo_contestacao, civ_alimentos, civ_usucapiao  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_penal import PenalIn, pen_listar, pen_criar, pen_atualizar, pen_remover, pen_prazos, pen_anpp, pen_prescricao  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_trabalhista_esp import TrabalhistaIn, trab_listar, trab_criar, trab_atualizar, trab_remover, trab_prazos, trab_prescricao, trab_deposito  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_admin_esp import AdminIn, adm_listar, adm_criar, adm_atualizar, adm_remover, adm_multa_transito, transito_prazos_recurso, transito_pontuacao_cnh  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_bancario import BancarioIn, ban_listar, ban_criar, ban_atualizar, ban_remover, ban_juros, ban_superendiv, ban_ba  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_vitrine import consumidor_devolucao_dobro, consumidor_prazos_cdc, consumidor_negativacao, familia_debito_alimentos, familia_itcmd, imobiliario_reajuste_aluguel, imobiliario_prazos_despejo, imobiliario_distrato, previdenciario_prazos, previdenciario_tempo_contribuicao, previdenciario_carencia, lgpd_multa, lgpd_prazos, penal_prescricao, penal_dosimetria, trabalhista_horas_extras, trabalhista_horas_extras_alias, empresarial_juros_mora, bancario_juros_abusivos, tributario_multa_mora, transito_valor_multa, adm_ms  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_tributario_paf import trib_auto_infracao_prazos  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_ferramentas_complementares import civ_prescricao_consumidor, civ_dano_moral, civ_partilha_divorcio, civ_rescisao_locacao, trab_verbas_rescisorias, adm_reajuste_contrato, bancario_taxas_bacen, trib_prescricao_decadencia, trib_parcelamento, trib_simples_nacional, trib_regime_tributario, trib_reforma_tributaria, amb_auto_infracao, amb_crimes_ambientais, amb_tac, amb_licenciamento, amb_reserva_legal, _MODALIDADES_PARCELAMENTO, _REFORMA_CRONOGRAMA  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_comum import TETOS_DEPOSITO_RECURSAL, _teto_deposito_para, _add_meses_data, _ultimo_dia_do_mes, _SUNSET_DUPLICATAS, _sm_vigente  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_comum import VERSAO_REGRA_ATUAL, _serialize  # noqa: F401 (reexport p/ compat)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat; motivo/selo já importados acima)
    FERRAMENTAS_BLOQUEADAS, FERRAMENTAS_NAO_HOMOLOGADAS,
    normalizar_caminho_ferramenta,
)


CAMINHOS_FERRAMENTAS_VALIDOS: frozenset[str] = frozenset(
    normalizar_caminho_ferramenta(rota.path)
    for rota in router.routes
    if "/ferramentas/" in getattr(rota, "path", "")
)
