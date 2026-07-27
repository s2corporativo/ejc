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
* PERSISTÊNCIA por FLUSH periódico (job do APScheduler + shutdown do app) em
  ``route_usage_metrics``: UPSERT somando a contagem do bucket. Nunca há INSERT
  por request. Postgres foi escolhido em vez de Redis porque o Redis do stack é
  OPT-IN (``RATE_LIMIT_REDIS_ENABLED`` default False) e serve de cache com
  evicção — não sustenta a janela de 30-60 dias que a Onda 5 exige; e em vez de
  arquivo porque o container é recriado a cada deploy.
* Persistência no padrão de ``services/ai/provider_metrics_runtime._persistir``:
  sessão isolada, fail-open e circuit breaker — telemetria NUNCA derruba
  requisição nem transação de negócio.

Limite conhecido da medição
---------------------------
Quando uma ação passa a existir TAMBÉM na Central (ex.: exportação CSV, exclusão
de tarefa e ciência de prazo, migradas na Onda 5), o contador do endpoint deixa
de provar que a TELA legada está ociosa — ele passa a somar as duas origens.
Para separar origem seria preciso um cabeçalho de origem enviado pelo frontend
(ex.: ``X-EJC-Origem: central|legado``) ou analytics de navegação. Enquanto isso
não existir, o contador prova apenas que a AÇÃO é (ou não) usada.

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
    # ── AÇÕES EXCLUSIVAS DAS TELAS LEGADAS ───────────────────────────────────
    # As rotas /legado/* são de FRONTEND (moduleRegistry.tsx): o backend nunca
    # as recebe, então monitorá-las nunca contaria nada. O proxy correto para a
    # decisão de remoção é o ENDPOINT que só a tela legada aciona: zero chamadas
    # em 30-60 dias = ninguém usa aquela ação, em nenhuma tela.
    # Prazos (tela /legado/prazos → pages/Prazos.tsx)
    "/deadlines/{deadline_id}/ciencia": "legado:prazos:ciencia",
    "/deadlines/{deadline_id}/confirmar": "legado:prazos:confirmar",
    "/deadlines/calcular": "legado:prazos:calculo",
    "/deadlines/export.csv": "legado:prazos:export_csv",
    # Intimações (tela /legado/intimacoes → pages/Intimacoes.tsx)
    "/intimacoes/{com_id}/sugerir-prazo": "legado:intimacoes:sugerir",
    "/intimacoes/{com_id}/prazo-sugerido": "legado:intimacoes:sugestao",
    "/intimacoes/{com_id}/aceitar-prazo": "legado:intimacoes:aceitar",
    "/intimacoes/{com_id}/recusar-prazo": "legado:intimacoes:recusar",
    "/intimacoes/capturar-agora": "legado:intimacoes:captura_manual",
    # Tarefas (tela /legado/tarefas → pages/Tarefas.tsx)
    "/tasks/{task_id}": "legado:tarefas:editar_excluir",
    # Suspensões (tela /legado/suspensoes → pages/Suspensoes.tsx)
    "/suspensoes/": "legado:suspensoes:crud",
    "/suspensoes/{suspensao_id}": "legado:suspensoes:excluir",
    "/suspensoes/simular": "legado:suspensoes:simular",
    # ── Duplicatas depreciadas (Onda 3 §4.5) ─────────────────────────────────
    "/penal/ferramentas/prescricao-punitiva": "duplicata",
    "/admin-esp/ferramentas/recurso-multa-transito": "duplicata",
    "/trabalhista/ferramentas/horas-extras": "duplicata",
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
    """Agregado APENAS do que está em memória (janela corrente).
    Para a decisão da Onda 5 use `agregado_persistido`, que soma o histórico."""
    linhas = snapshot()
    if desde_iso:
        linhas = [x for x in linhas if x["hora"] >= desde_iso]
    return _montar_agregado(linhas, desde_iso)


def _montar_agregado(linhas: list[dict], desde_iso: str | None) -> dict:
    """Agrega linhas (de memória e/ou banco) por rota e papel."""
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


def _drenar() -> list[tuple[tuple[str, str, str, str], int]]:
    """Retira os contadores da memória para persistir (operação atômica)."""
    with _lock:
        itens = list(_contadores.items())
        _contadores.clear()
    return itens


async def flush() -> dict:
    """Persiste o agregado em memória em ``route_usage_metrics`` (UPSERT somando).

    Fail-open: qualquer erro de banco devolve os contadores para a memória e
    apenas loga — telemetria nunca derruba o app nem perde a janela por um
    hiccup do banco.
    """
    itens = _drenar()
    if not itens:
        return {"buckets": 0, "eventos": 0}
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.core.database import AsyncSessionLocal
        from app.models.route_usage_metric import RouteUsageMetric

        async with AsyncSessionLocal() as db:
            for (rota, metodo, papel, hora_iso), contagem in itens:
                stmt = pg_insert(RouteUsageMetric).values(
                    rota=rota, metodo=metodo, papel=papel,
                    hora=datetime.fromisoformat(hora_iso), contagem=contagem,
                ).on_conflict_do_update(
                    constraint="uq_route_usage_bucket",
                    set_={"contagem": RouteUsageMetric.__table__.c.contagem + contagem},
                )
                await db.execute(stmt)
            await db.commit()
        eventos = sum(n for _, n in itens)
        logger.info("Telemetria de rotas: %d bucket(s), %d evento(s) persistidos",
                    len(itens), eventos)
        return {"buckets": len(itens), "eventos": eventos}
    except Exception as exc:   # pragma: no cover — fail-open
        with _lock:            # devolve para a memória: nada se perde
            for chave, contagem in itens:
                _contadores[chave] = _contadores.get(chave, 0) + contagem
        logger.warning("Flush da telemetria de rotas falhou (%s): contadores mantidos "
                       "em memória para a próxima tentativa", type(exc).__name__)
        return {"buckets": 0, "eventos": 0, "erro": type(exc).__name__}


async def _persistidos(desde_iso: str | None) -> list[dict]:
    """Lê o histórico já persistido (vazio se a tabela ainda não existir)."""
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.route_usage_metric import RouteUsageMetric

        async with AsyncSessionLocal() as db:
            q = select(RouteUsageMetric.rota, RouteUsageMetric.metodo,
                       RouteUsageMetric.papel, RouteUsageMetric.hora,
                       RouteUsageMetric.contagem)
            if desde_iso:
                q = q.where(RouteUsageMetric.hora >= datetime.fromisoformat(desde_iso))
            linhas = (await db.execute(q)).all()
        return [{"rota": r, "metodo": m, "papel": p, "hora": h.isoformat(),
                 "contagem": n, "motivo": ROTAS_MONITORADAS.get(r, "")}
                for r, m, p, h, n in linhas]
    except Exception as exc:   # pragma: no cover — leitura best-effort
        logger.warning("Histórico persistido indisponível (%s): usando só a memória",
                       type(exc).__name__)
        return []


async def agregado_persistido(desde_iso: str | None = None) -> dict:
    """Agregado COMPLETO: histórico persistido + o que ainda está em memória.

    É o que o endpoint administrativo devolve — a janela sobrevive a restarts.
    """
    linhas = await _persistidos(desde_iso) + [
        x for x in snapshot() if not desde_iso or x["hora"] >= desde_iso
    ]
    out = _montar_agregado(linhas, desde_iso)
    out["fonte"] = "banco (histórico) + memória (janela corrente ainda não persistida)"
    out["observacao"] = ("Contagens persistidas em route_usage_metrics por flush periódico; "
                         "o bloco ainda em memória é somado aqui. A janela sobrevive a "
                         "restarts — se o flush falhar, os contadores voltam para a memória.")
    return out


def resetar() -> None:
    """Zera os contadores (uso administrativo/teste)."""
    with _lock:
        _contadores.clear()
