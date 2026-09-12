# ── app/services/visual_law_core.py ──────────────────────────────────────────
# Núcleo determinístico do módulo Visual Law (sem IA — não inventa nada):
#   · linha do tempo visual (fases + eventos + próximos passos + estagnação)
#   · matriz de risco probabilidade × impacto (tratamento contábil CPC 25)
#   · badges de alerta (conversão dos fatores do case_health)
#   · calculadora de breakeven/VPL de acordo (reusa CalculoAcordo)
#
# Obs.: app/services/visual_law.py é OUTRO serviço (diagramas Mermaid via IA);
# este módulo é 100% determinístico, por isso vive em arquivo próprio.
#
# Estrutura: funções PURAS testáveis sem banco (tests/test_visual_law.py),
# mais helpers async finos de acesso a dados usados por routers/visual_law.py.
# O contrato JSON espelha frontend/src/types/visualLaw.ts.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento
from app.services.calculo_acordo import CalculoAcordo

# ══════════════════════════════════════════════════════════════════════════════
# Linha do tempo visual — fases, próximos passos e estagnação
# ══════════════════════════════════════════════════════════════════════════════

# Jornada judicial padrão (ordem canônica). O rito administrativo é trilha à
# parte (fase única): não percorre as fases judiciais.
FASES_JUDICIAIS = ["pre_processual", "conhecimento", "recursal", "execucao"]

FASE_LABELS = {
    "pre_processual": "Pré-processual",
    "conhecimento": "Conhecimento",
    "recursal": "Recursal",
    "execucao": "Execução",
    "administrativo": "Administrativo",
}

# Passos típicos esperados a partir da fase ATUAL — mapa estático (sem IA).
# Editável: ajuste os textos conforme a prática do escritório.
PROXIMOS_PASSOS_POR_FASE = {
    "pre_processual": ["Distribuição da ação", "Citação da parte contrária"],
    "conhecimento": ["Sentença", "Prazo recursal (15 dias úteis)"],
    "recursal": ["Julgamento do recurso", "Trânsito em julgado"],
    "execucao": ["Penhora/constrição", "Expedição de alvará"],
    "administrativo": ["Decisão administrativa", "Recurso administrativo (se cabível)"],
}

# Limiares de estagnação (dias sem movimentação) — mesmos marcos do case_health.
ESTAGNACAO_ATENCAO_DIAS = 30
ESTAGNACAO_CRITICO_DIAS = 60


def montar_fases(fase_atual: Optional[str]) -> list[dict]:
    """Fases da jornada processual com status concluída/atual/futura.

    Caso administrativo: trilha própria de fase única (status "atual").
    Fase desconhecida/nula: assume início da jornada (pre_processual)."""
    fase = fase_atual or "pre_processual"
    if fase == "administrativo":
        return [{"fase": "administrativo", "label": FASE_LABELS["administrativo"],
                 "status": "atual"}]
    idx = FASES_JUDICIAIS.index(fase) if fase in FASES_JUDICIAIS else 0
    return [
        {"fase": f, "label": FASE_LABELS[f],
         "status": "concluida" if i < idx else ("atual" if i == idx else "futura")}
        for i, f in enumerate(FASES_JUDICIAIS)
    ]


def montar_proximos_passos(fase_atual: Optional[str],
                           prazos_pendentes: list[dict]) -> list[dict]:
    """Próximos passos determinísticos, na ordem: (i) prazos pendentes futuros
    REAIS do caso (origem "prazo"); (ii) passos típicos da jornada a partir da
    fase atual (origem "estimativa", mapa estático). Sem IA.

    `prazos_pendentes`: [{"titulo": str, "data": str|None}] (data ISO)."""
    passos = [
        {"titulo": p["titulo"], "origem": "prazo", "data_estimada": p.get("data"),
         "detalhe": "Prazo pendente cadastrado no caso"}
        for p in prazos_pendentes
    ]
    fase = fase_atual or "pre_processual"
    label = FASE_LABELS.get(fase, fase)
    for titulo in PROXIMOS_PASSOS_POR_FASE.get(fase, []):
        passos.append({
            "titulo": titulo, "origem": "estimativa", "data_estimada": None,
            "detalhe": f"Passo típico após a fase {label} — estimativa, não é dado do processo",
        })
    return passos


def classificar_estagnacao(dias_parado: int) -> str:
    """> 60 dias = crítico · > 30 dias = atenção · senão ok."""
    if dias_parado > ESTAGNACAO_CRITICO_DIAS:
        return "critico"
    if dias_parado > ESTAGNACAO_ATENCAO_DIAS:
        return "atencao"
    return "ok"


def montar_estagnacao(dias_parado: int, fechado: bool = False) -> dict:
    """Caso encerrado/arquivado não estagna: parado é o estado esperado,
    então o nível é sempre "ok" (sem banner de alerta no frontend)."""
    if fechado:
        return {"dias_parado": dias_parado, "nivel": "ok"}
    return {"dias_parado": dias_parado, "nivel": classificar_estagnacao(dias_parado)}


def dias_parado_desde(referencia: Optional[datetime],
                      agora: Optional[datetime] = None) -> int:
    """Dias corridos desde `referencia` (último movimento ou created_at).
    Pura (datas injetáveis); datetime naive → assume UTC, como no case_health."""
    if referencia is None:
        return 0
    agora = agora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    return max(0, (agora - referencia).days)


async def dias_sem_movimentacao(db: AsyncSession, case: Case) -> int:
    """Dias desde o último CaseMovimento (ou created_at) — critério do case_health."""
    ult_mov = (await db.execute(
        select(func.max(CaseMovimento.data_evento))
        .where(CaseMovimento.case_id == case.id)
    )).scalar()
    return dias_parado_desde(ult_mov or case.created_at)


async def montar_eventos_caso(db: AsyncSession, case_id: str) -> list[dict]:
    """Cronologia unificada do caso: movimentos + prazos + documentos +
    honorários, ordenada por data (mais recente primeiro). Agrega dados reais —
    não inventa. Extraída de routers/cases.py::linha_do_tempo para reuso no
    Visual Law; o contrato de cada evento é o MESMO do endpoint original."""
    from app.models.deadline import Deadline
    from app.models.document import Document
    from app.models.fee import Fee

    def _val(x):
        return x.value if hasattr(x, "value") else x

    eventos: list[dict] = []
    for m in (await db.execute(
        select(CaseMovimento).where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.data_evento.desc()).limit(300)
    )).scalars().all():
        eventos.append({"data": m.data_evento, "categoria": "movimento",
                        "tipo": m.tipo, "descricao": (m.descricao or "")[:240]})
    for p in (await db.execute(
        select(Deadline).where(Deadline.case_id == case_id, Deadline.deleted_at.is_(None))
        .limit(300)
    )).scalars().all():
        eventos.append({"data": p.data_prazo, "categoria": "prazo", "tipo": _val(p.tipo),
                        "descricao": f"{p.titulo} [{_val(p.status)}]"})
    for d in (await db.execute(
        select(Document).where(Document.case_id == case_id, Document.deleted_at.is_(None))
        .limit(300)
    )).scalars().all():
        eventos.append({"data": d.created_at, "categoria": "documento",
                        "tipo": d.tipo or "doc", "descricao": d.titulo})
    for f in (await db.execute(
        select(Fee).where(Fee.case_id == case_id, Fee.deleted_at.is_(None))
        .limit(300)
    )).scalars().all():
        dt = f.data_pagamento or f.data_vencimento
        if dt:
            eventos.append({"data": dt, "categoria": "honorario", "tipo": _val(f.tipo),
                            "descricao": f"{f.descricao} [{_val(f.status)}]"})

    eventos.sort(key=lambda e: (e["data"].isoformat() if hasattr(e["data"], "isoformat")
                                else str(e["data"])), reverse=True)
    return eventos


# ══════════════════════════════════════════════════════════════════════════════
# Matriz de risco — probabilidade × impacto (CPC 25)
# ══════════════════════════════════════════════════════════════════════════════

PROBABILIDADES = ["remoto", "possivel", "provavel"]   # eixo x (0..2)
IMPACTOS = ["baixo", "medio", "alto"]                 # eixo y (0..2)

# Probabilidade a partir do risco cadastrado no caso (terminologia CPC 25)
_RISCO_PARA_PROB = {"baixo": "remoto", "medio": "possivel", "alto": "provavel"}

# Faixas de impacto financeiro (R$) — configuráveis no código
IMPACTO_TETO_BAIXO = 50_000.0    # até aqui: impacto baixo
IMPACTO_TETO_MEDIO = 500_000.0   # até aqui: impacto médio; acima: alto

# Tratamento contábil da contingência conforme CPC 25 (provisões e contingências)
TRATAMENTO_CPC25 = {
    "provavel": "provisionar",
    "possivel": "divulgar_em_nota",
    "remoto": "nao_divulgar",
}

# Nível do quadrante pela soma dos eixos (combinação simples e monotônica):
#   0–1 → baixo · 2 → moderado · 3 → elevado · 4 → crítico
_NIVEL_POR_SOMA = {0: "baixo", 1: "baixo", 2: "moderado", 3: "elevado", 4: "critico"}
NIVEL_LABELS = {"baixo": "Baixo", "moderado": "Moderado",
                "elevado": "Elevado", "critico": "Crítico"}


# Faixas PRÓPRIAS (3, não as 4 de case_health._classificar) — respondem a
# pergunta "qual a probabilidade de resultado desfavorável", não "qual a saúde
# do caso". Mesmo score de entrada (calcular_score_caso), pergunta diferente:
# não unificar com os limiares de case_health.py (ver nota lá).
_LIMIAR_REMOTO = 80
_LIMIAR_POSSIVEL = 50


def derivar_probabilidade(risco: Optional[str],
                          score: Optional[int] = None) -> tuple[str, str]:
    """(probabilidade, fonte). Prioriza o risco cadastrado no caso; sem risco,
    deriva do score do case_health (>=80 remoto · >=50 possível · senão
    provável). Sem score informado, assume pior caso (conservador)."""
    r = (risco or "").strip().lower()
    if r in _RISCO_PARA_PROB:
        return _RISCO_PARA_PROB[r], "risco_cadastrado"
    s = score if score is not None else 0
    if s >= _LIMIAR_REMOTO:
        return "remoto", "score_saude"
    if s >= _LIMIAR_POSSIVEL:
        return "possivel", "score_saude"
    return "provavel", "score_saude"


def classificar_impacto(valor_causa: Optional[float]) -> str:
    """Impacto financeiro pelas faixas configuráveis; sem valor → indefinido."""
    if valor_causa is None:
        return "indefinido"
    v = float(valor_causa)
    if v <= IMPACTO_TETO_BAIXO:
        return "baixo"
    if v <= IMPACTO_TETO_MEDIO:
        return "medio"
    return "alto"


def montar_quadrante(probabilidade: str, impacto: str) -> dict:
    """Posição na matriz 3×3, nível combinado e tratamento contábil (CPC 25).
    Impacto indefinido (sem valor da causa): assume eixo y neutro (médio) —
    o frontend não marca a célula nesse caso, mas o nível segue informativo."""
    x = PROBABILIDADES.index(probabilidade)
    y = 1 if impacto == "indefinido" else IMPACTOS.index(impacto)
    return {
        "x": x,
        "y": y,
        "nivel": _NIVEL_POR_SOMA[x + y],
        "tratamento_contabil": TRATAMENTO_CPC25[probabilidade],
    }


def montar_matriz() -> list[list[dict]]:
    """Os 9 quadrantes (3 linhas de impacto × 3 colunas de probabilidade),
    com labels, para o frontend renderizar: matriz[y][x] = {nivel, label}."""
    return [
        [{"nivel": _NIVEL_POR_SOMA[x + y], "label": NIVEL_LABELS[_NIVEL_POR_SOMA[x + y]]}
         for x in range(len(PROBABILIDADES))]
        for y in range(len(IMPACTOS))
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Badges de alerta — conversão dos fatores do case_health
# ══════════════════════════════════════════════════════════════════════════════

# fator do case_health → (severidade, label). Pulsante = severidade crítica.
_BADGE_FATOR = {
    "prazo_vencido": ("critica", "Prazo vencido"),
    "prazo_critico_sem_ciencia": ("atencao", "Prazo crítico sem ciência"),
    "sem_procuracao": ("atencao", "Sem procuração ativa"),
    "honorario_atrasado": ("atencao", "Honorário em atraso"),
    "sem_posmortem": ("info", "Sem pós-mortem registrado"),
}
# Orientação de ação por fator — exibe no detalhe/badge como o advogado
# resolve o alerta (auditoria 12/08/2026: o gate "Sem procuração ativa"
# não orientava onde registrar a procuração para ativar o gate).
_BADGE_ORIENTACAO: dict[str, str] = {
    "sem_procuracao": (
        "Registre a procuração formalmente na aba Procurações do caso "
        "(Clientes → caso → subtab Procurações) para que o gate de "
        "procuração vigente seja ativado. Documentos anexados em outro "
        "módulo não habilitam este gate."
    ),
}


def badge_estagnacao(dias_parado: int) -> Optional[dict]:
    """Regra do requisito: parado há MAIS de 60 dias → badge crítico pulsante
    ("Atenção Crítica"); entre 31 e 60 dias → atenção, não pulsante."""
    if dias_parado > ESTAGNACAO_CRITICO_DIAS:
        return {"codigo": "parado_60d", "severidade": "critica",
                "label": "Atenção Crítica",
                "detalhe": f"Processo sem movimentação há {dias_parado} dias",
                "pulsante": True}
    if dias_parado > ESTAGNACAO_ATENCAO_DIAS:
        return {"codigo": "parado_30d", "severidade": "atencao",
                "label": "Atenção",
                "detalhe": f"Processo sem movimentação há {dias_parado} dias",
                "pulsante": False}
    return None


def montar_badges(fatores: list[dict], dias_parado: int,
                  fechado: bool = False) -> list[dict]:
    """Converte os fatores do case_health em badges visuais. O fator
    "sem_movimentacao" é substituído pelo badge de estagnação (regra 30/60
    dias, calculada aqui em dias exatos) para não duplicar o alerta.

    Caso encerrado/arquivado (`fechado`): nenhum badge de estagnação é emitido
    — parado é o estado esperado; os demais fatores continuam virando badges."""
    badges: list[dict] = []
    b = None if fechado else badge_estagnacao(dias_parado)
    if b:
        badges.append(b)
    for f in fatores:
        codigo = f.get("fator") or "desconhecido"
        if codigo == "sem_movimentacao":
            continue  # já coberto pelo badge de estagnação acima
        sev, label = _BADGE_FATOR.get(codigo, ("info", codigo))
        detalhe = (f.get("detalhe") or "") or _BADGE_ORIENTACAO.get(codigo, "")
        badges.append({"codigo": codigo, "severidade": sev, "label": label,
                       "detalhe": detalhe, "pulsante": sev == "critica"})
    return badges


# ══════════════════════════════════════════════════════════════════════════════
# Calculadora de breakeven / VPL de acordo
# ══════════════════════════════════════════════════════════════════════════════

# Tempo médio de tramitação por tribunal (anos) — aproximações baseadas no
# relatório Justiça em Números/CNJ (tempo até a baixa, valores arredondados).
# Mapa estático e editável: ajuste quando nova edição do relatório for publicada.
TEMPO_MEDIO_TRAMITACAO_ANOS = {
    "TJMG": 4.5,
    "TJSP": 4.2,
    "TRF6": 5.0,
    "TST": 2.5,
    "TRT3": 2.5,
}
# Tribunais superiores: tempo ADICIONAL sobre a estimativa base (o recurso sobe).
ADICIONAL_TRIBUNAL_SUPERIOR_ANOS = {"STJ": 2.0}
TEMPO_TRAMITACAO_DEFAULT_ANOS = 4.0


def tempo_tramitacao_estimado(tribunal: Optional[str]) -> tuple[float, str]:
    """(anos, fonte). fonte "tribunal_cnj" quando o tribunal está no mapa;
    "default" caso contrário (inclui tribunal nulo/desconhecido/"outro")."""
    t = (tribunal or "").strip().upper()
    if t in TEMPO_MEDIO_TRAMITACAO_ANOS:
        return TEMPO_MEDIO_TRAMITACAO_ANOS[t], "tribunal_cnj"
    if t in ADICIONAL_TRIBUNAL_SUPERIOR_ANOS:
        return (TEMPO_TRAMITACAO_DEFAULT_ANOS
                + ADICIONAL_TRIBUNAL_SUPERIOR_ANOS[t]), "tribunal_cnj"
    return TEMPO_TRAMITACAO_DEFAULT_ANOS, "default"


def normalizar_pct(pct: float) -> float:
    """Converte percentual em escala 0–100 para fração (10 → 0.10; 0.5 → 0.005).

    O contrato da API (BreakevenIn) é SEMPRE escala percentual 0–100 — é o que
    o formulário CalculadoraAcordo do frontend envia. Sem heurística: 1 significa
    1% (0.01), nunca 100%."""
    return pct / 100.0


def calcular_breakeven(
    valor_causa: float,
    prob_exito: float,
    tempo_anos: float,
    selic_anual: float,
    custas_pct: float = 0.10,
    honorarios_sucumbencia_pct: float = 0.10,
    tribunal: Optional[str] = None,
    tempo_fonte: str = "informado",
    selic_fonte: str = "informada",
) -> dict:
    """Ponto de equilíbrio do acordo (determinístico, sem IA).

    VPL do litígio = (valor esperado − custos) / (1 + selic)^tempo.
    O breakeven é o valor de acordo HOJE que equivale financeiramente ao
    litígio (o próprio VPL do litígio — piso racional do acordo).
    Reusa o motor de CalculoAcordo com os parâmetros injetados."""
    base = CalculoAcordo(selic_atual=selic_anual).calcular_ponto_equilibrio(
        valor_causa, prob_exito, tempo_anos,
        custas_pct=custas_pct,
        honorarios_sucumbencia_pct=honorarios_sucumbencia_pct,
    )
    valor_esperado = round(valor_causa * prob_exito, 2)
    custos = base["custos_estimados"]                # total (número)
    detalhe = base["custos_detalhe"]                 # {custas, honorarios_...}
    vpl = base["valor_presente_liquido"]
    liquido = round(valor_esperado - custos, 2)
    custo_do_tempo = round(liquido - vpl, 2)

    memoria = [
        f"Valor esperado = R$ {valor_causa:.2f} × {prob_exito:.2f} = R$ {valor_esperado:.2f}",
        (f"Custas estimadas = R$ {valor_causa:.2f} × {custas_pct * 100:.1f}% "
         f"= R$ {detalhe['custas']:.2f}"),
        (f"Honorários de sucumbência esperados = R$ {valor_causa:.2f} × "
         f"{honorarios_sucumbencia_pct * 100:.1f}% × (1 − {prob_exito:.2f}) = "
         f"R$ {detalhe['honorarios_sucumbencia_esperados']:.2f} (devidos apenas em caso de derrota)"),
        (f"Resultado líquido esperado = R$ {valor_esperado:.2f} − R$ {custos:.2f} "
         f"= R$ {liquido:.2f}"),
        (f"VPL do litígio = R$ {liquido:.2f} / (1 + {selic_anual:.4f})^{tempo_anos:.2f} "
         f"= R$ {vpl:.2f} (Selic anual, fonte: {selic_fonte})"),
        (f"Breakeven: um acordo imediato de R$ {vpl:.2f} equivale financeiramente "
         f"a litigar por {tempo_anos:.2f} ano(s) (fonte do tempo: {tempo_fonte})"),
        f"Custo do tempo = R$ {liquido:.2f} − R$ {vpl:.2f} = R$ {custo_do_tempo:.2f}",
    ]

    return {
        "valor_esperado": valor_esperado,
        "custos_estimados": custos,
        "custos_detalhe": detalhe,
        "vpl_litigio": vpl,
        "sugestao_acordo": vpl,      # piso racional do acordo (VPL do litígio)
        "breakeven": vpl,            # acordo hoje ≡ litígio
        "comparativo": {
            "litigio_vpl": vpl,
            "acordo_imediato_equivalente": vpl,
            "custo_do_tempo": custo_do_tempo,
        },
        "memoria_calculo": memoria,
        "parametros": {
            "valor_causa": round(float(valor_causa), 2),
            "prob_exito": prob_exito,
            "tempo_anos": tempo_anos,
            "tempo_fonte": tempo_fonte,
            "tribunal": tribunal,
            "custas_pct": custas_pct,
            "honorarios_sucumbencia_pct": honorarios_sucumbencia_pct,
            "selic_anual": selic_anual,
            "selic_fonte": selic_fonte,
        },
    }
