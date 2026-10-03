"""Contexto determinístico de provas; limites são política do consumidor."""
from app.models.case import Case
from app.models.prova import Prova


def contexto_provas(case: Case, provas: list[Prova], *, limite_fato: int = 400) -> str:
    """Contexto DETERMINÍSTICO do caso (só campos do próprio caso) — único insumo
    fático dado à IA (mesmo racional de provas._contexto_sugestao)."""
    area = case.area.value if hasattr(case.area, "value") else str(case.area or "—")
    tipo_acao = (getattr(case, "tipo_acao_prescricao", None)
                 or getattr(case, "extrajudicial_type", None)
                 or getattr(case, "case_type", None)
                 or "não informado")
    linhas = [
        f"Área do direito: {area}",
        f"Título do caso: {case.titulo or '—'}",
        f"Tipo de ação: {tipo_acao}",
        f"Tese principal: {(case.tese_principal or 'não informada').strip()[:2000]}",
        "",
        "Provas JÁ EXISTENTES no caso:",
    ]
    if provas:
        for p in provas:
            fato = (p.fato_probando or "não informado").strip()[:limite_fato]
            linhas.append(f"- [{p.tipo}] {p.titulo} — fato probando: {fato}")
    else:
        linhas.append("- (nenhuma prova cadastrada ainda)")
    return "\n".join(linhas)
