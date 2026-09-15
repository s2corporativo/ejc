"""Guarda estrutural: superfícies de IA caras exigem rate_limit.

Auditoria FASE 0 (2026-09-15): os routers canônicos de IA usam a dependency
`rate_limit(nome, max)` nos endpoints POST caros, mas `cerebro.py` e
`ai_skills.py` estavam sem nenhum limite — `POST /api/cerebro/analise-estrategica`
e `POST /api/ai/skills/execute` eram caminhos de custo alto sem o mesmo
controle dos irmãos. Este teste impede regressão e mantém os irmãos sob guarda.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fonte(relativo: str) -> str:
    return (REPO_ROOT / relativo).read_text(encoding="utf-8")


def test_cerebro_endpoints_caros_tem_rate_limit():
    src = _fonte("backend/app/routers/cerebro.py")
    assert 'rate_limit("cerebro-analise-estrategica", 10)' in src, (
        "POST /cerebro/analise-estrategica é caminho de IA caro e precisa de rate limit"
    )
    assert 'rate_limit("cerebro-juris-pesquisa", 15)' in src, (
        "POST /cerebro/jurisprudencia/pesquisa precisa de rate limit"
    )


def test_ai_skills_endpoints_caros_tem_rate_limit():
    src = _fonte("backend/app/routers/ai_skills.py")
    assert 'rate_limit("ai-skills-execute", 15)' in src, (
        "POST /ai/skills/execute é o caminho de skills mais usado e precisa de rate limit"
    )
    assert 'rate_limit("ai-skills-execute-doc", 10)' in src, (
        "POST /ai/skills/execute-doc processa documentos caros e precisa de rate limit"
    )
    assert 'rate_limit("ai-skills-transcribe", 10)' in src, (
        "POST /ai/skills/transcribe-media transcreve mídias e precisa de rate limit"
    )


def test_irmaos_canonicos_mantem_rate_limit():
    src = _fonte("backend/app/routers/ai.py")
    assert 'rate_limit("ia-analisar-caso", 15)' in src, (
        "routers canônicos de IA não podem perder o rate limit existente"
    )
