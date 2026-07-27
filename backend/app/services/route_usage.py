"""Telemetria de USO de rotas candidatas à remoção (Onda 3 §4.5 · pré-requisito da Onda 5).

Por que existe
--------------
A retirada das rotas legadas/duplicadas foi condicionada a 30-60 dias de uso
ZERO — dado que não existia. Este módulo registra esse uso.

Decisões de reuso (inventário da Onda 3)
----------------------------------------
* Captura no ``AuthMiddleware`` (app/core/auth_middleware.py): é o único ponto
  que já intercepta 100% das rotas ``/api`` e já tem o PAPEL do usuário
  decodificado do JWT — nada de trabalho extra no caminho quente.
* NÃO usa ``audit_logs``/``criar_audit_log``: aquela tabela é trilha probatória
  LGPD (imutável, com ``ip`` e diffs de entidade) e custaria 1 INSERT por
  request em tabela com 5 índices. Telemetria de navegação a poluiria.
* Agregação em MEMÓRIA no padrão do rate-limit em memória
  (app/core/rate_limit.py): dict sob lock, com teto de entradas. Custo por
  request = um incremento de contador; zero I/O no caminho quente.
* Persistência no padrão de ``services/ai/provider_metrics_runtime._persistir``:
  sessão isolada, fail-open e circuit breaker — telemetria NUNCA derruba
  requisição nem transação de negócio.

Privacidade (LGPD)
------------------
Grava apenas: TEMPLATE da rota (``/api/casos/{case_id}``, nunca o path com id),
método, papel do usuário (``advogado``, ``admin``…) e a hora truncada.
NUNCA: user_id, IP, querystring, corpo, número de caso ou qualquer dado pessoal.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("ejc.route_usage")

# Rotas monitoradas — só elas entram no contador (custo ~zero nas demais).
# Chave: template do path SEM o prefixo /api. Valor: motivo do monitoramento.
ROTAS_MONITORADAS: dict[str, str] = {
    # Legados (candidatos a remoção na Onda 5)
    "/legado/prazos": "legado",
    "/legado/tarefas": "legado",
    "/legado/intimacoes": "legado",
    "/legado/suspensoes": "legado",
    # Duplicatas depreciadas (Onda 3 §4.5) — canônica em ramos._DUPLICATAS_DEPRECIADAS
    "/penal/ferramentas/prescricao-punitiva": "duplicata",
    "/admin-esp/ferramentas/recurso-multa-transito": "duplicata",
    "/trabalhista/ferramentas/horas-extras": "duplicata",
    # Alias de vitrine dos ramos
    "/ramos/{slug}": "alias",
}

_MAX_ENTRADAS = 4096          # teto de segurança do dict (espelha rate_limit)
_lock = threading.Lock()
# {(rota, metodo, papel, hora_iso): contagem}
_contadores: dict[tuple[str, str, str, str], int] = {}


def _normalizar(path: str) -> str:
    """Remove o prefixo /api e a barra final para casar com ROTAS_MONITORADAS."""
    p = (path or "").split("?")[0]
    if p.startswith("/api/"):
        p = p[len("/api"):]
    return p.rstrip("/") or "/"


def registrar(path_template: str, metodo: str, papel: str | None) -> None:
    """Incrementa o contador em memória. Chamado no caminho quente — não faz I/O
    e nunca levanta exceção."""
    try:
        rota = _normalizar(path_template)
        if rota not in ROTAS_MONITORADAS:
            return
        hora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        chave = (rota, (metodo or "GET").upper(), papel or "desconhecido", hora.isoformat())
        with _lock:
            if len(_contadores) >= _MAX_ENTRADAS and chave not in _contadores:
                return          # teto atingido: descarta em vez de crescer sem limite
            _contadores[chave] = _contadores.get(chave, 0) + 1
    except Exception:           # pragma: no cover — telemetria é best-effort
        pass


def snapshot() -> list[dict]:
    """Fotografia dos contadores acumulados (sem zerar)."""
    with _lock:
        itens = sorted(_contadores.items())
    return [
        {"rota": r, "metodo": m, "papel": p, "hora": h, "contagem": n,
         "motivo": ROTAS_MONITORADAS.get(r, "")}
        for (r, m, p, h), n in itens
    ]


def agregado(desde_iso: str | None = None) -> dict:
    """Agregado por rota (e por papel), opcionalmente a partir de uma hora ISO.
    É o insumo da decisão da Onda 5: rota com total 0 no período pode sair."""
    linhas = snapshot()
    if desde_iso:
        linhas = [x for x in linhas if x["hora"] >= desde_iso]
    por_rota: dict[str, dict] = {}
    for rota, motivo in ROTAS_MONITORADAS.items():
        por_rota[rota] = {"rota": rota, "motivo": motivo, "total": 0,
                          "por_papel": {}, "primeira_chamada": None, "ultima_chamada": None}
    for x in linhas:
        alvo = por_rota.setdefault(
            x["rota"], {"rota": x["rota"], "motivo": x["motivo"], "total": 0,
                        "por_papel": {}, "primeira_chamada": None, "ultima_chamada": None})
        alvo["total"] += x["contagem"]
        alvo["por_papel"][x["papel"]] = alvo["por_papel"].get(x["papel"], 0) + x["contagem"]
        if alvo["primeira_chamada"] is None or x["hora"] < alvo["primeira_chamada"]:
            alvo["primeira_chamada"] = x["hora"]
        if alvo["ultima_chamada"] is None or x["hora"] > alvo["ultima_chamada"]:
            alvo["ultima_chamada"] = x["hora"]
    dados = sorted(por_rota.values(), key=lambda d: (-d["total"], d["rota"]))
    return {
        "desde": desde_iso,
        "rotas": dados,
        "sem_uso_no_periodo": [d["rota"] for d in dados if d["total"] == 0],
        "observacao": ("Contadores em MEMÓRIA do processo (premissa de worker único do EJC): "
                       "reiniciar o backend zera a janela. Para a decisão da Onda 5, considere "
                       "apenas períodos sem restart — o campo `desde` delimita a janela."),
        "privacidade": ("Sem PII: apenas template da rota, método, papel do usuário e hora. "
                        "Nunca user_id, IP, querystring ou dados do caso."),
    }


def resetar() -> None:
    """Zera os contadores (uso administrativo/teste)."""
    with _lock:
        _contadores.clear()
