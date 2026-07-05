# ── app/routers/lgpd_registros.py ─────────────────────────────────────────────
# LGPD como vertical de PRODUTO — Registro de Operações de Tratamento (ROPA,
# art. 37) por CLIENTE + gerador de RIPD (Relatório de Impacto, art. 38) em
# Visual Law. Registro client-scoped persistido.
#
# ⚠ O ROPA guarda METADADO das operações (categorias de dados/titulares), NUNCA
# dados pessoais de titular real — ver models/lgpd_tratamento.py.
#
# Segurança (ESPELHA routers/sociedades_cliente.py):
#   • escrita: mesmos papéis do CRM de clientes (_ESCRITA);
#   • leitura: equipe interna (cliente_externo bloqueado);
#   • visibilidade: gestão (socio+) vê tudo; advogado comum só vê registros de
#     clientes que "enxerga" (responsável pelo cliente OU atua em caso dele) —
#     REUSA os helpers _cond_cliente_visivel/_cliente_visivel de sociedades
#     (não duplica a matriz). Registro fora do escopo responde 404;
#   • audit log em toda escrita (criar_audit_log); soft delete no registro.
#
# RIPD em PDF: padrão de hardening COPIADO de routers/ambiental_estrategia.py /
# tributario_fiscal.py — vlt.esc() em toda string, {download_url}, GET /download
# com UUID validado (sem traversal), _limpar_pdfs_antigos (TTL/LGPD),
# rate_limit em TODAS as rotas.
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.lgpd_tratamento import BaseLegal, RegistroTratamento
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.lgpd_tratamento import RegistroCreate, RegistroUpdate
from app.services.lgpd_service import avaliar_risco, montar_resumo
# Reuso da matriz de visibilidade do cliente (não duplicar o mecanismo).
from app.routers.sociedades_cliente import _cliente_visivel, _cond_cliente_visivel

settings = get_settings()
router = APIRouter(prefix="/lgpd/registros", tags=["LGPD / ROPA & RIPD"])

# Mesmos papéis de escrita do CRM de clientes (clients.py _CLIENTES).
_ESCRITA = {"superadmin", "admin", "socio", "advogado", "secretaria"}

# Retenção do PDF do RIPD (consolida o ROPA do cliente): varredura best-effort
# remove os mais antigos que o TTL a cada geração (LGPD).
PDF_TTL_SEGUNDOS = 3600  # 1h

# Rótulos legíveis das hipóteses legais (RIPD e tela).
_BASE_LEGAL_LABEL = {
    BaseLegal.consentimento.value:      "Consentimento (art. 7º, I)",
    BaseLegal.contrato.value:           "Execução de contrato (art. 7º, V)",
    BaseLegal.obrigacao_legal.value:    "Obrigação legal/regulatória (art. 7º, II)",
    BaseLegal.legitimo_interesse.value: "Legítimo interesse (art. 7º, IX / art. 10)",
    BaseLegal.exercicio_direitos.value: "Exercício de direitos em processo (art. 7º, VI)",
    BaseLegal.protecao_vida.value:      "Proteção da vida/incolumidade (art. 7º, VII)",
    BaseLegal.tutela_saude.value:       "Tutela da saúde (art. 7º, VIII / art. 11, II, f)",
    BaseLegal.politica_publica.value:   "Execução de política pública (art. 7º, III)",
    BaseLegal.pesquisa.value:           "Estudos por órgão de pesquisa (art. 7º, IV)",
    BaseLegal.credito.value:            "Proteção ao crédito (art. 7º, X)",
}


def _req_escrita(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _ESCRITA:
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar registros LGPD")
    return cu


def _req_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura restrita à equipe interna — padrão sociedades._req_leitura."""
    if cu.role.value == "cliente_externo":
        raise HTTPException(status_code=403, detail="Sem permissão para consultar registros LGPD")
    return cu


async def _carregar_registro(db: AsyncSession, cu: User, registro_id: str) -> RegistroTratamento:
    """404 se não existe, soft-deleted OU fora do escopo do usuário (não vaza a
    existência de registro de cliente alheio — mesmo racional de sociedades)."""
    reg = (await db.execute(
        select(RegistroTratamento).where(
            RegistroTratamento.id == registro_id,
            RegistroTratamento.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    cli = (await db.execute(
        select(Client).where(Client.id == reg.client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return reg


def _out_registro(reg: RegistroTratamento) -> dict:
    """Serialização com risco + fatores recalculados a partir dos campos atuais."""
    _, fatores = avaliar_risco(reg)
    return {
        "id": reg.id,
        "client_id": reg.client_id,
        "nome_operacao": reg.nome_operacao,
        "finalidade": reg.finalidade,
        "base_legal": reg.base_legal,
        "base_legal_label": _BASE_LEGAL_LABEL.get(reg.base_legal, reg.base_legal),
        "categorias_dados": reg.categorias_dados,
        "categorias_titulares": reg.categorias_titulares,
        "dados_sensiveis": bool(reg.dados_sensiveis),
        "compartilhamento": reg.compartilhamento,
        "transferencia_internacional": bool(reg.transferencia_internacional),
        "paises_transferencia": reg.paises_transferencia,
        "prazo_retencao": reg.prazo_retencao,
        "medidas_seguranca": reg.medidas_seguranca,
        "risco": reg.risco,
        "fatores_risco": fatores,
        "created_at": reg.created_at.isoformat() if reg.created_at else None,
        "updated_at": reg.updated_at.isoformat() if reg.updated_at else None,
    }


# ── ROPA (CRUD) ───────────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(rate_limit("lgpd-listar", 60))])
async def listar(
    client_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_leitura),
):
    """Lista os registros de tratamento (ROPA). Cada item traz risco e fatores.
    Visibilidade por matriz de casos: advogado fora do caso do cliente não vê;
    gestão vê tudo."""
    q = (
        select(RegistroTratamento)
        .join(Client, Client.id == RegistroTratamento.client_id)
        .where(RegistroTratamento.deleted_at.is_(None), Client.deleted_at.is_(None))
    )
    if not is_gestao(cu):
        q = q.where(_cond_cliente_visivel(cu))
    if client_id:
        q = q.where(RegistroTratamento.client_id == client_id)
    q = q.order_by(RegistroTratamento.created_at.desc())

    rows = (await db.execute(q)).scalars().all()
    return {"data": [_out_registro(r) for r in rows], "total": len(rows)}


@router.post("", status_code=201, dependencies=[Depends(rate_limit("lgpd-criar", 30))])
async def criar(
    payload: RegistroCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    cli = (await db.execute(
        select(Client).where(Client.id == payload.client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    risco, _ = avaliar_risco(payload)  # risco DETERMINÍSTICO calculado no service
    reg = RegistroTratamento(
        id=str(uuid4()),
        client_id=payload.client_id,
        nome_operacao=payload.nome_operacao.strip(),
        finalidade=payload.finalidade.strip(),
        base_legal=payload.base_legal.value,
        categorias_dados=payload.categorias_dados.strip(),
        categorias_titulares=payload.categorias_titulares.strip(),
        dados_sensiveis=payload.dados_sensiveis,
        compartilhamento=payload.compartilhamento,
        transferencia_internacional=payload.transferencia_internacional,
        paises_transferencia=payload.paises_transferencia,
        prazo_retencao=payload.prazo_retencao.strip(),
        medidas_seguranca=payload.medidas_seguranca.strip(),
        risco=risco,
    )
    db.add(reg)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "lgpd_registros_tratamento",
                          reg.id, detalhes=f"cliente {payload.client_id}: {reg.nome_operacao} "
                                           f"(risco {risco})")
    await db.commit()
    return _out_registro(reg)


@router.patch("/{registro_id}", dependencies=[Depends(rate_limit("lgpd-editar", 30))])
async def atualizar(
    registro_id: str,
    payload: RegistroUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    reg = await _carregar_registro(db, cu, registro_id)
    mudancas = payload.model_dump(exclude_unset=True)
    if "base_legal" in mudancas and mudancas["base_legal"] is not None:
        mudancas["base_legal"] = mudancas["base_legal"].value
    for k, v in mudancas.items():
        setattr(reg, k, v)
    # Recalcula o risco: dados sensíveis / transferência / base legal mudam o nível.
    reg.risco, _ = avaliar_risco(reg)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "lgpd_registros_tratamento",
                          registro_id, detalhes=f"campos: {sorted(mudancas)} (risco {reg.risco})")
    await db.commit()
    return _out_registro(reg)


@router.delete("/{registro_id}", response_model=MsgResponse,
               dependencies=[Depends(rate_limit("lgpd-remover", 30))])
async def remover(
    registro_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    """Soft delete — mesmo gate de exclusão do CRM de clientes (admin/socio+)."""
    reg = await _carregar_registro(db, cu, registro_id)
    reg.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "lgpd_registros_tratamento",
                          registro_id)
    await db.commit()
    return MsgResponse(detail="Registro removido")


# ── Resumo (estatísticas do ROPA — header da tela) ────────────────────────────

async def _registros_do_cliente(db: AsyncSession, cu: User, client_id: str) -> list:
    """Registros ativos do cliente, já validado o acesso (404 fora do escopo)."""
    cli = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return (await db.execute(
        select(RegistroTratamento)
        .where(RegistroTratamento.client_id == client_id,
               RegistroTratamento.deleted_at.is_(None))
        .order_by(RegistroTratamento.created_at.desc())
    )).scalars().all()


@router.get("/{client_id}/resumo", dependencies=[Depends(rate_limit("lgpd-resumo", 60))])
async def resumo(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_leitura),
):
    registros = await _registros_do_cliente(db, cu, client_id)
    return montar_resumo(registros)


# ── RIPD (PDF Visual Law) ─────────────────────────────────────────────────────

def _ripd_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "lgpd_ripd")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    """Retenção LGPD: o RIPD consolida o ROPA do cliente. Varredura best-effort
    remove os mais antigos que o TTL a cada geração — tolerante a falhas."""
    try:
        agora = time.time()
        for nome in os.listdir(out_dir):
            if not nome.endswith(".pdf"):
                continue
            caminho = os.path.join(out_dir, nome)
            try:
                if agora - os.path.getmtime(caminho) > PDF_TTL_SEGUNDOS:
                    os.remove(caminho)
            except OSError:
                continue
    except OSError:
        pass


def _html_ripd(nome_cliente: str, registros: list, resumo_stats: dict) -> str:
    """Monta o HTML do RIPD. TODA string variável passa por vlt.esc() — os
    campos do ROPA vêm de entrada do usuário."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    dist = resumo_stats["distribuicao_risco"]

    partes: list[str] = [vlt.render_banner(
        "RELATÓRIO DE IMPACTO À PROTEÇÃO DE DADOS (RIPD)",
        f"{esc(nome_cliente)} · art. 38 da LGPD (Lei 13.709/2018)",
    )]

    partes.append(
        "<h1>1. Objeto</h1>"
        "<p>Este Relatório de Impacto à Proteção de Dados Pessoais (RIPD/DPIA) "
        f"consolida o Registro das Operações de Tratamento (ROPA, art. 37 da LGPD) "
        f"de <strong>{esc(nome_cliente)}</strong> e a respectiva análise "
        "preliminar de risco, nos termos do art. 38 da Lei 13.709/2018.</p>"
    )

    # Panorama (estatísticas do ROPA).
    partes.append(
        "<h1>2. Panorama do tratamento</h1>"
        "<table><tr><th>Indicador</th><th>Valor</th></tr>"
        f"<tr><td>Operações de tratamento mapeadas</td><td>{resumo_stats['total_operacoes']}</td></tr>"
        f"<tr><td>Operações com dados sensíveis (art. 11)</td>"
        f"<td>{resumo_stats['com_dados_sensiveis']}</td></tr>"
        f"<tr><td>Operações com transferência internacional (arts. 33-36)</td>"
        f"<td>{resumo_stats['com_transferencia_internacional']}</td></tr>"
        f"<tr><td>Distribuição de risco</td>"
        f"<td>alto: {dist['alto']} · médio: {dist['medio']} · baixo: {dist['baixo']}</td></tr>"
        "</table>"
    )

    if not registros:
        partes.append(
            "<h1>3. Operações</h1>"
            "<p>Nenhuma operação de tratamento cadastrada para este cliente. "
            "Cadastre o ROPA antes de emitir o RIPD.</p>"
        )
    else:
        partes.append("<h1>3. Operações de tratamento e análise de risco</h1>")
        for i, reg in enumerate(registros, start=1):
            _, fatores = avaliar_risco(reg)
            base_label = _BASE_LEGAL_LABEL.get(reg.base_legal, reg.base_legal)
            partes.append(
                f"<h2>3.{i} {esc(reg.nome_operacao)} "
                f"<span style='font-size:9pt;color:{vlt.TEXTO_SUAVE};'>"
                f"(risco {esc(reg.risco)})</span></h2>"
                "<table>"
                f"<tr><th>Finalidade</th><td>{esc(reg.finalidade)}</td></tr>"
                f"<tr><th>Base legal</th><td>{esc(base_label)}</td></tr>"
                f"<tr><th>Categorias de dados</th><td>{esc(reg.categorias_dados)}</td></tr>"
                f"<tr><th>Categorias de titulares</th><td>{esc(reg.categorias_titulares)}</td></tr>"
                f"<tr><th>Dados sensíveis</th><td>{'Sim' if reg.dados_sensiveis else 'Não'}</td></tr>"
                f"<tr><th>Compartilhamento</th><td>{esc(reg.compartilhamento) or '—'}</td></tr>"
                f"<tr><th>Transferência internacional</th>"
                f"<td>{'Sim — ' + esc(reg.paises_transferencia or '(países não informados)') if reg.transferencia_internacional else 'Não'}</td></tr>"
                f"<tr><th>Prazo de retenção</th><td>{esc(reg.prazo_retencao)}</td></tr>"
                f"<tr><th>Medidas de segurança</th><td>{esc(reg.medidas_seguranca)}</td></tr>"
                "</table>"
            )
            if fatores:
                partes.append(
                    "<p style='margin-bottom:2px;'><strong>Fatores de risco "
                    "identificados</strong></p><ul>"
                    + "".join(f"<li style='font-size:9.5pt;'>{esc(f)}</li>" for f in fatores)
                    + "</ul>"
                )
            else:
                partes.append(
                    "<p style='font-size:9.5pt;'>Sem fatores agravantes automáticos "
                    "— risco de base (baixo). A análise não dispensa a avaliação do "
                    "encarregado (DPO).</p>"
                )

    partes.append(
        "<div style='background:#fffbe6;border:1px solid #f0ad4e;border-left:"
        f"4px solid {vlt.OURO_CLARO};padding:12px;margin:16px 0;font-size:9.5pt;'>"
        "<strong>NOTA METODOLÓGICA — REVISÃO HUMANA OBRIGATÓRIA</strong><br>"
        "A classificação de risco é uma triagem DETERMINÍSTICA (sem IA), baseada em "
        "fatores legais objetivos (dados sensíveis, transferência internacional e "
        "base legal). Não substitui a análise do encarregado (DPO) nem a decisão "
        "fundamentada exigida pelo art. 38 da LGPD.</div>"
    )

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        "Documento preliminar (HITL) · Base: ROPA (art. 37) do cliente</div>"
    )

    rodape = ("De Paula Teixeira Advogados · Relatório de Impacto à Proteção de "
              "Dados (RIPD) — documento preliminar (HITL)")
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


@router.post("/{client_id}/ripd", dependencies=[Depends(rate_limit("lgpd-ripd", 10))])
async def gerar_ripd(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_leitura),
):
    """Gera o PDF Visual Law do RIPD consolidando o ROPA do cliente + análise de
    risco. Retorna a URL de download."""
    cli = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    registros = (await db.execute(
        select(RegistroTratamento)
        .where(RegistroTratamento.client_id == client_id,
               RegistroTratamento.deleted_at.is_(None))
        .order_by(RegistroTratamento.created_at.desc())
    )).scalars().all()

    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    nome_cliente = getattr(cli, "nome_exibicao", None) or getattr(cli, "nome", None) or "Cliente"
    html_full = _html_ripd(nome_cliente, registros, montar_resumo(registros))
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _ripd_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"ripd_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "lgpd_registros_tratamento",
                          client_id, detalhes=f"RIPD gerado ({len(registros)} operações)")
    await db.commit()
    return {"download_url": f"/lgpd/registros/ripd/{arquivo_id}/download"}


@router.get("/ripd/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("lgpd-ripd-download", 30))])
async def download_ripd(arquivo_id: str, cu: User = Depends(_req_leitura)):
    """Download do RIPD gerado. `arquivo_id` validado como UUID (nunca
    interpolado livre no path — sem traversal)."""
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                        arquivo_id):
        raise HTTPException(422, "Identificador de RIPD inválido.")
    path = os.path.join(_ripd_dir(), f"ripd_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "RIPD não encontrado — gere via POST "
                                 "/lgpd/registros/{client_id}/ripd.")
    return FileResponse(path, media_type="application/pdf",
                        filename="ripd_relatorio_impacto.pdf")
