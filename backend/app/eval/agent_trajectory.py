#!/usr/bin/env python3
# ── app/eval/agent_trajectory.py ──────────────────────────────────────────────
# Harness de avaliação de TRAJETÓRIA do agente (loop de tool-use — loop.py).
# Irmão do run_eval.py (que mede o RAG): mesma filosofia eval-driven — sem régua,
# toda mudança no loop/nas tools/no prompt do agente é aposta. Aqui a régua é a
# TRAJETÓRIA: a sequência de decisões do agente (quais tools chamou, se fundamentou
# a resposta, se respeitou o HITL/modo leitura e o orçamento).
#
# OFFLINE / DETERMINÍSTICO: o LLM é MOCKADO. Cada CENÁRIO do gold set traz um
# roteiro de turnos (respostas de tool-use roteirizadas) que substituem o provider
# real — nada de rede, LLM, banco ou Redis. Espelha o `loop_env` de
# tests/test_agente_ia.py: `chat_agentico` e as bordas do loop (ownership,
# entidades, AILog, gate de citações, store HITL, REGISTRY.executar) são
# substituídos por fakes em memória; o LOOP REAL (rodar_agente) é exercitado.
#
# MÉTRICAS (por cenário e agregadas):
#   1. ESCOLHA DE FERRAMENTA — o agente decidiu chamar a tool esperada para a
#      intenção (ex.: pergunta sobre precedentes → `buscar_precedentes`).
#   2. FUNDAMENTAÇÃO/FONTE — quando a resposta final afirma tese jurídica, cita
#      fonte (detector local de fonte; o gate real de citações roda dentro do loop,
#      aqui é mockado como passthrough para preservar o offline/determinismo).
#   3. HITL / MODO LEITURA — em `apenas_leitura`, nenhuma write-tool executa (é
#      bloqueada e o loop segue); em modo normal, a write-tool PAUSA em confirmação
#      (não executa sem aprovação) e só roda com o hash aprovado.
#   4. ORÇAMENTO — a trajetória respeita max_steps/tokens/custo: não estoura o teto
#      de passos e, ao atingir o teto, encerra com AVISO (nunca loop infinito).
#
# USO (dentro do backend; NÃO precisa de DATABASE_URL — tudo mockado):
#   python -m app.eval.agent_trajectory
#   python -m app.eval.agent_trajectory --gold app/eval/agent_scenarios.jsonl
#   python -m app.eval.agent_trajectory --out traj.json   # baseline p/ diff / CI
#
# O gold set (agent_scenarios.jsonl) é curado, FICTÍCIO (sem PII real) e pequeno —
# cresça-o cobrindo as intenções reais do escritório, como no gold set do RAG.
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import ExitStack
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

# Trecho da mensagem de parada por orçamento emitida por rodar_agente quando o
# laço encerra por teto (passos/tokens/custo) sem conclusão natural.
_MSG_FALLBACK_ORCAMENTO = "dentro do orçamento do agente"

# Detector LOCAL de FONTE jurídica (fundamentação): súmula, artigo de lei, código,
# tribunal ou classe recursal. Deliberadamente específico para não dar falso
# positivo em texto genérico. É a métrica offline de "presença de fonte" (o gate
# real citation_check/response_validator roda no loop de produção).
_PADRAO_FONTE = re.compile(
    r"(s[úu]mula\s+\d|"                       # Súmula 244
    r"art(?:\.|igo)\s*\d|"                     # art. 927 / artigo 5
    r"lei\s+n?[ºo\.]*\s*\d|"                   # Lei nº 8.078
    r"\bADCT\b|\bCLT\b|\bCDC\b|\bCPC\b|\bCC\b|\bCF\b|\bCP\b|"
    r"c[óo]digo\s+(civil|penal|de\s+processo|de\s+defesa)|"
    r"\bSTF\b|\bSTJ\b|\bTST\b|\bTJ[A-Z]{2}\b|"
    r"\bREsp\b|\bRE\b\s*\d|\bAgRg\b|jurisprud[êe]ncia\s+d[oa])",
    re.IGNORECASE,
)


def _tem_fonte(texto: str) -> bool:
    """True se `texto` cita ao menos uma fonte jurídica reconhecível."""
    return bool(_PADRAO_FONTE.search(texto or ""))


def caminho_gold_padrao() -> str:
    """Caminho absoluto do gold set embarcado (independe do cwd — usado no teste)."""
    return os.path.join(os.path.dirname(__file__), "agent_scenarios.jsonl")


@dataclass
class CenarioMetrica:
    id: str
    intencao: str
    # 1. escolha de ferramenta
    tool_esperada: str | None = None
    tool_correta: bool | None = None
    ferramentas_escolhidas: list[str] = field(default_factory=list)
    # 2. fundamentação/fonte
    espera_fonte: bool = False
    tem_fonte: bool | None = None
    # 3. HITL / modo leitura
    hitl_tipo: str = "nenhum"
    hitl_respeitado: bool = True
    writes_executadas: list[str] = field(default_factory=list)
    bloqueou_escrita: bool = False
    status: str | None = None
    # 4. orçamento
    orcamento_tipo: str = "ok"
    orcamento_respeitado: bool = True
    passos: int = 0
    max_steps: int = 0
    erro: str | None = None


@dataclass
class AgregadoTraj:
    n: int = 0
    acerto_ferramenta: float | None = None
    n_ferramenta: int = 0
    pct_com_fonte: float | None = None
    n_fonte: int = 0
    violacoes_hitl: int = 0
    pct_dentro_orcamento: float = 0.0
    por_cenario: list[dict] = field(default_factory=list)


def _carregar_cenarios(caminho: str) -> list[dict]:
    """Carrega o gold set JSONL (uma linha = um cenário). Ignora vazias/comentário."""
    cenarios: list[dict] = []
    with open(caminho, "r", encoding="utf-8") as fh:
        for i, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                cenarios.append(json.loads(linha))
            except json.JSONDecodeError as e:
                print(f"[gold] linha {i} inválida, ignorada: {e}", file=sys.stderr)
    return cenarios


def _montar_turno(turno: dict, passo: int) -> dict:
    """Converte um turno do roteiro (gold set) na resposta que `chat_agentico`
    devolveria: text/text_para_log, tool_calls (id sintético), stop_reason, usage."""
    tools = turno.get("tools") or []
    tool_calls = [{
        "id": f"tc-{passo}-{i}",
        "name": t.get("name", ""),
        "input": t.get("input") or {},
    } for i, t in enumerate(tools)]
    usage = turno.get("usage") or {
        "model": "claude-mock", "input_tokens": 20, "output_tokens": 20}
    text = turno.get("text", "")
    return {
        "text": text,
        "text_para_log": turno.get("text_para_log", text),
        "tool_calls": tool_calls,
        "stop_reason": turno.get("stop_reason", "tool_use" if tool_calls else "end_turn"),
        "usage": usage,
        "provider": "anthropic",
        "model": usage.get("model", "claude-mock"),
    }


async def avaliar_cenario(cenario: dict) -> CenarioMetrica:
    """Roda UM cenário com o LLM mockado (roteiro de turnos) e mede a trajetória.
    Todas as bordas do loop são substituídas por fakes em memória; o loop REAL
    (rodar_agente) é exercitado ponta a ponta."""
    import app.services.ai.agent.loop as loop
    import app.services.ai_gateway as gw
    import app.services.ai_guard as guard
    import app.services.ai.entidades_caso as ent
    import app.services.ai.core.response_validator as rv
    import app.services.ai.agent.hitl_state as hitl
    from app.services.ai.agent.tools.registry import REGISTRY
    from app.services.ai.agent.hitl_state import hash_tool_call
    from app.core.config import get_settings

    cid = str(cenario.get("id") or "?")
    m = CenarioMetrica(id=cid, intencao=str(cenario.get("intencao") or ""))
    try:
        turnos = list(cenario.get("turnos") or [])
        area = cenario.get("area") or "civel"
        role = cenario.get("role") or "advogado"
        tool_result_canon = cenario.get("tool_result") or {"total": 0, "trechos": []}
        orc_override = cenario.get("orcamento_override") or {}

        estado = {"i": 0}
        executadas: list[tuple[str, dict]] = []
        eventos: list[tuple[str, dict]] = []
        hitl_store: dict[str, dict] = {}

        async def fake_chat(messages, tools, *a, **k):
            i = estado["i"]
            estado["i"] += 1
            if i < len(turnos):
                return _montar_turno(turnos[i], i + 1)
            # Roteiro esgotado (segurança): conclui naturalmente, sem tool.
            return _montar_turno({"text": "Conclusão.", "stop_reason": "end_turn"}, i + 1)

        async def fake_acesso(db, user, case_id):
            return SimpleNamespace(client_id="c1", area=SimpleNamespace(value=area))

        async def fake_entidades(db, case_id):
            return {}

        async def fake_ailog(db, **kw):
            return "log-id"

        async def fake_validar(db, conteudo, **kw):
            # Passthrough: o gate real (citações) roda no loop de produção; aqui a
            # métrica de fonte é medida diretamente sobre a resposta final.
            return {"conteudo": conteudo, "alertas": [], "revisao_obrigatoria": False}

        async def fake_salvar(estado_, ttl=None):
            tok = f"tok-{len(hitl_store) + 1}"
            hitl_store[tok] = estado_
            return tok

        async def fake_carregar(token):
            return hitl_store.pop(token, None)

        async def spy_exec(name, args, ctx):
            executadas.append((name, args))
            if REGISTRY.requer_confirmacao(name):
                return {"conteudo": "minuta (rascunho)", "is_rascunho": True}
            return tool_result_canon

        def on_event(tipo, dados):
            eventos.append((tipo, dados))

        # Pré-aprovação por hash (cenário "escrita_aprovada"): aprova os ARGS
        # EXATOS das write-tools do roteiro — a write executa sem pausar (H1).
        aprovacoes: set[str] = set()
        if cenario.get("aprovar_escrita"):
            for t in turnos:
                for tl in (t.get("tools") or []):
                    nome = tl.get("name", "")
                    if REGISTRY.requer_confirmacao(nome):
                        aprovacoes.add(hash_tool_call(nome, tl.get("input") or {}))

        st = get_settings()
        with ExitStack() as stack:
            stack.enter_context(patch.object(gw, "chat_agentico", fake_chat))
            stack.enter_context(patch.object(loop, "verificar_acesso_caso", fake_acesso))
            stack.enter_context(patch.object(ent, "entidades_do_caso", fake_entidades))
            stack.enter_context(patch.object(guard, "registrar_ai_log", fake_ailog))
            stack.enter_context(patch.object(rv, "validar", fake_validar))
            stack.enter_context(patch.object(hitl, "salvar", fake_salvar))
            stack.enter_context(patch.object(hitl, "carregar", fake_carregar))
            stack.enter_context(patch.object(REGISTRY, "executar", spy_exec))
            # Área não-sigilosa (sem mapa) → o loop não faz fail-closed por sigilo.
            stack.enter_context(patch.object(st, "AI_SANITIZATION_MODE_MAP", ""))
            if "max_steps" in orc_override:
                stack.enter_context(
                    patch.object(st, "AI_AGENT_MAX_STEPS", int(orc_override["max_steps"])))
            if "max_custo_brl" in orc_override:
                stack.enter_context(
                    patch.object(st, "AI_AGENT_MAX_CUSTO_BRL", float(orc_override["max_custo_brl"])))

            max_steps = int(getattr(st, "AI_AGENT_MAX_STEPS", 8))
            r = await loop.rodar_agente(
                db=None,
                user=SimpleNamespace(id="u1", role=SimpleNamespace(value=role)),
                case_id="c1",
                mensagem=cenario.get("mensagem") or "",
                apenas_leitura=bool(cenario.get("apenas_leitura")),
                aprovacoes_hash=aprovacoes or None,
                on_event=on_event,
            )

        # ── Extração da trajetória ────────────────────────────────────────────
        passos = r.get("passos") or []
        status = r.get("status")
        resposta = r.get("resposta") or ""
        alertas = r.get("alertas") or []
        m.status = status
        m.passos = len(passos)
        m.max_steps = max_steps

        # Ferramentas ESCOLHIDAS pelo modelo (decisão), inclusive a write pendente.
        escolhidas: set[str] = set()
        for p in passos:
            for f in (p.get("ferramentas") or []):
                if f:
                    escolhidas.add(f)
        if status == "pendente_confirmacao" and r.get("ferramenta"):
            escolhidas.add(r["ferramenta"])
        m.ferramentas_escolhidas = sorted(escolhidas)

        # 1. escolha de ferramenta
        esperada = cenario.get("ferramenta_esperada")
        if esperada:
            m.tool_esperada = esperada
            m.tool_correta = esperada in escolhidas

        # 2. fundamentação/fonte
        m.espera_fonte = bool(cenario.get("espera_fonte"))
        if m.espera_fonte:
            m.tem_fonte = _tem_fonte(resposta)

        # 3. HITL / modo leitura
        writes = [n for (n, _) in executadas if REGISTRY.requer_confirmacao(n)]
        m.writes_executadas = writes
        m.bloqueou_escrita = any(t == "ferramenta_bloqueada" for t, _ in eventos)
        m.hitl_tipo = cenario.get("hitl") or "nenhum"
        if m.hitl_tipo == "pausa":
            m.hitl_respeitado = (status == "pendente_confirmacao" and not writes)
        elif m.hitl_tipo == "bloqueia_leitura":
            m.hitl_respeitado = (not writes and m.bloqueou_escrita and status == "ok")
        elif m.hitl_tipo == "escrita_aprovada":
            executadas_nomes = [n for (n, _) in executadas]
            m.hitl_respeitado = (status == "ok" and esperada in executadas_nomes)
        else:  # "nenhum": trajetória de leitura pura — nenhuma escrita pode rodar.
            m.hitl_respeitado = not writes

        # 4. orçamento
        m.orcamento_tipo = cenario.get("orcamento") or "ok"
        dentro = len(passos) <= max_steps
        if m.orcamento_tipo == "estoura":
            tem_aviso = any(("teto de" in a.lower() or "orçamento" in a.lower())
                            for a in alertas)
            dentro = dentro and tem_aviso and (_MSG_FALLBACK_ORCAMENTO in resposta)
        else:  # "ok": não pode ter caído no fallback de orçamento.
            dentro = dentro and (_MSG_FALLBACK_ORCAMENTO not in resposta)
        m.orcamento_respeitado = dentro
    except Exception as e:
        m.erro = str(e)[:300]
    return m


async def avaliar_cenarios(cenarios: list[dict]) -> tuple[list[CenarioMetrica], AgregadoTraj]:
    """Roda todos os cenários (sequencial, determinístico) e agrega as métricas."""
    metricas = [await avaliar_cenario(c) for c in cenarios]
    return metricas, _agregar(metricas)


def _agregar(metricas: list[CenarioMetrica]) -> AgregadoTraj:
    validos = [m for m in metricas if m.erro is None]
    ag = AgregadoTraj(n=len(validos))
    com_esperada = [m for m in validos if m.tool_esperada]
    ag.n_ferramenta = len(com_esperada)
    if com_esperada:
        ag.acerto_ferramenta = round(
            sum(1 for m in com_esperada if m.tool_correta) / len(com_esperada), 4)
    com_fonte = [m for m in validos if m.espera_fonte]
    ag.n_fonte = len(com_fonte)
    if com_fonte:
        ag.pct_com_fonte = round(
            sum(1 for m in com_fonte if m.tem_fonte) / len(com_fonte), 4)
    ag.violacoes_hitl = sum(1 for m in validos if not m.hitl_respeitado)
    if validos:
        ag.pct_dentro_orcamento = round(
            sum(1 for m in validos if m.orcamento_respeitado) / len(validos), 4)
    ag.por_cenario = [vars(m) for m in metricas]
    return ag


def _sim_nao_na(v: bool | None) -> str:
    return "n/a" if v is None else ("sim" if v else "NÃO")


async def _main(args) -> int:
    cenarios = _carregar_cenarios(args.gold)
    if not cenarios:
        print(f"Nenhum cenário em {args.gold}", file=sys.stderr)
        return 2
    metricas, ag = await avaliar_cenarios(cenarios)
    for m in metricas:
        flag = "ERRO" if m.erro else "ok"
        tool = ("n/a" if m.tool_esperada is None
                else ("hit" if m.tool_correta else "MISS"))
        print(f"  [{flag:4}] {m.id:24} tool={tool:4} fonte={_sim_nao_na(m.tem_fonte):4} "
              f"hitl={'ok' if m.hitl_respeitado else 'VIOLA':5} "
              f"orc={'ok' if m.orcamento_respeitado else 'ESTOUROU':8} "
              f"passos={m.passos}/{m.max_steps}"
              + (f"  ({m.erro})" if m.erro else ""))
    print("\n== AGREGADO (trajetória do agente) ==")
    print(f"cenarios={ag.n}")
    print(f"acerto de ferramenta = {ag.acerto_ferramenta}  (n={ag.n_ferramenta})")
    print(f"% com fonte (quando exige tese) = {ag.pct_com_fonte}  (n={ag.n_fonte})")
    print(f"violações de HITL/leitura = {ag.violacoes_hitl}")
    print(f"% trajetórias dentro do orçamento = {ag.pct_dentro_orcamento}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(vars(ag), fh, ensure_ascii=False, indent=2)
        print(f"\nresultados → {args.out}")
    # Gates opcionais de regressão (para CI): falham abaixo do piso.
    rc = 0
    if args.min_tool is not None and (ag.acerto_ferramenta or 0.0) < args.min_tool:
        print(f"\nFALHA: acerto de ferramenta {ag.acerto_ferramenta} < piso {args.min_tool}",
              file=sys.stderr)
        rc = 1
    if args.max_violacoes_hitl is not None and ag.violacoes_hitl > args.max_violacoes_hitl:
        print(f"\nFALHA: violações de HITL {ag.violacoes_hitl} > teto {args.max_violacoes_hitl}",
              file=sys.stderr)
        rc = 1
    return rc


def main() -> None:
    p = argparse.ArgumentParser(
        description="Avaliação de TRAJETÓRIA do agente do EJC (offline, LLM mockado).")
    p.add_argument("--gold", default=caminho_gold_padrao(), help="gold set JSONL de cenários")
    p.add_argument("--out", default=None, help="grava métricas agregadas em JSON (baseline p/ diff)")
    p.add_argument("--min-tool", type=float, default=None,
                   help="piso de acerto de ferramenta p/ CI (falha abaixo)")
    p.add_argument("--max-violacoes-hitl", type=int, default=None,
                   help="teto de violações de HITL/leitura p/ CI (falha acima)")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
