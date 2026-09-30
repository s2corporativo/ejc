from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import criar_audit_log
from app.models.document import DocConfidencialidade
from app.models.user import User
from app.modules.dpt360.report_service import build_executive_report
from app.modules.dpt360.schemas import DptPrepareShareRequest, DptPrepareShareResponse
from app.services.document_ingestion_orchestrator import ingerir_documento_local
from app.services.document_persistence_service import DadosPersistenciaDocumento


def _role(user: User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")))


def render_report_markdown(report: dict[str, Any]) -> str:
    """Renderiza somente o produto final estruturado; nunca raciocínio interno."""
    import json

    empresa = str(report.get("empresa") or "Empresa")
    linhas = [
        f"# Relatório Executivo DPT — {empresa}",
        "",
        f"Período: {int(report.get('periodo_dias') or 0)} dias",
        f"Gerado em: {report.get('generated_at') or ''}",
        "",
        "> Conteúdo aprovado para preparação documental. A publicação no Portal",
        "> continua sendo um ato separado e explícito do escritório.",
        "",
    ]
    secoes = (
        ("Situação jurídica", report.get("situacao_juridica") or []),
        ("Principais riscos", report.get("principais_riscos") or []),
        ("Providências futuras", report.get("providencias_futuras") or []),
        ("Pendências", report.get("pendencias") or {}),
        ("Mudanças jurídicas relevantes", report.get("mudancas_juridicas_relevantes") or []),
        ("Recomendações", report.get("recomendacoes") or []),
        ("Próximos passos", report.get("proximos_passos") or []),
    )
    for titulo, valor in secoes:
        linhas.extend(
            [
                f"## {titulo}",
                "",
                "~~~json",
                json.dumps(valor, ensure_ascii=False, indent=2, default=str),
                "~~~",
                "",
            ]
        )
    nota = str(report.get("nota") or "").strip()
    if nota:
        linhas.extend(["## Nota", "", nota, ""])
    return "\n".join(linhas).strip() + "\n"


async def prepare_approved_report_for_portal(
    db: AsyncSession,
    user: User,
    client_id: str,
    payload: DptPrepareShareRequest,
) -> DptPrepareShareResponse:
    if not payload.aprovado:
        raise HTTPException(
            status_code=422,
            detail="A preparação exige aprovação humana explícita do relatório.",
        )

    report = await build_executive_report(db, user, client_id, days=payload.days)
    if report is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    settings = get_settings()
    content = render_report_markdown(report).encode("utf-8")
    upload = UploadFile(
        filename=f"relatorio-executivo-dpt-{client_id[:8]}.md",
        file=BytesIO(content),
    )
    dados = DadosPersistenciaDocumento(
        titulo=f"Relatório Executivo DPT — {report.get('empresa') or 'Empresa'}",
        tipo="relatorio",
        confidencialidade=DocConfidencialidade.normal,
        client_id=client_id,
        uploaded_by=user.id,
        user_role=_role(user),
    )
    resultado = await ingerir_documento_local(
        db,
        upload,
        filename=upload.filename,
        upload_root=Path(settings.UPLOAD_DIR),
        max_bytes=int(settings.MAX_UPLOAD_MB * 1024 * 1024),
        dados=dados,
    )
    doc = resultado.documento

    await criar_audit_log(
        db,
        user_id=user.id,
        user_role=_role(user),
        acao="APPROVE_DPT_REPORT_FOR_PORTAL",
        entidade="documents",
        registro_id=doc.id,
        detalhes="Relatório DPT aprovado e preparado como documento canônico; não publicado.",
        dados_depois={
            "client_id": client_id,
            "document_id": doc.id,
            "publicado_portal": False,
        },
    )
    await db.commit()

    return DptPrepareShareResponse(
        document_id=doc.id,
        client_id=client_id,
        publicado_portal=False,
        next_step="Revise o documento canônico e use a publicação explícita do Portal/Data Room.",
    )
