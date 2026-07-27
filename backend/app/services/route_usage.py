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

Privacidade (LGPD) — sem identificadores DIRETOS
------------------------------------------------
Grava apenas: TEMPLATE da rota (``/api/casos/{case_id}``, nunca o path com id),
método, PAPEL do usuário (``advogado``, ``admin``…) e a hora truncada.
NUNCA: user_id, IP, querystring, corpo, número de caso.

O que NÃO se pode afirmar (auditoria P2-3): isto não é anonimização. Em papel
com titular único — tipicamente ``superadmin`` —, a tupla (papel, rota, hora) é
registro de comportamento de pessoa identificável POR ASSOCIAÇÃO (LGPD art. 5º
I). Mitigações aplicadas: k-anonimato no recorte por papel (ver
``_K_ANONIMATO``) e expurgo automático acima de ``RETENCAO_DIAS``.
Decisão registrada em docs/LGPD_TELEMETRIA_ROTAS.md.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

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
# k-anonimato do recorte por papel: papéis com menos de _K_ANONIMATO eventos na
# janela são colapsados em "outros". Preserva o dado que a Onda 5 precisa (o
# TOTAL por rota, intacto) e derruba o recorte que permitiria singularizar um
# titular único (ex.: o superadmin).
_K_ANONIMATO = 5
RETENCAO_DIAS = 90            # janela declarada é de 30-60 dias; expurgo acima disso
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
    # k-anonimato (P2-3): o total por rota é preservado; só o RECORTE por papel
    # é generalizado, colapsando papéis raros em "outros".
    for alvo in por_rota.values():
        raros = {papel: n for papel, n in alvo["por_papel"].items() if n < _K_ANONIMATO}
        if raros:
            for papel in raros:
                del alvo["por_papel"][papel]
            alvo["por_papel"]["outros"] = alvo["por_papel"].get("outros", 0) + sum(raros.values())
            alvo["papeis_generalizados"] = True
    dados = sorted(por_rota.values(), key=lambda d: (-d["total"], d["rota"]))
    return {
        "desde": desde_iso,
        "rotas": dados,
        "sem_uso_no_periodo": [d["rota"] for d in dados if d["total"] == 0],
        "observacao": ("Contadores em MEMÓRIA do processo (premissa de worker único do EJC): "
                       "reiniciar o backend zera a janela. Para a decisão da Onda 5, considere "
                       "apenas períodos sem restart — o campo `desde` delimita a janela."),
        "privacidade": (f"Sem identificadores diretos: apenas template da rota, método, papel "
                        f"e hora — nunca user_id, IP, querystring ou dados do caso. O recorte "
                        f"por papel aplica k-anonimato (k={_K_ANONIMATO}: papéis com menos "
                        f"eventos entram em 'outros'); registros acima de {RETENCAO_DIAS} dias "
                        f"são expurgados. Não é anonimização — ver docs/LGPD_TELEMETRIA_ROTAS.md."),
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

    LIMITE CONHECIDO (auditoria P2-4): se a conexão cair DEPOIS de o COMMIT ter
    sido efetivado no servidor, o restore devolve buckets já persistidos e a
    rodada seguinte soma de novo (o UPSERT é incremental, não idempotente).
    Isso INFLA a contagem — nunca a reduz —, então não gera falso "sem uso", que
    é o risco que importa aqui. Aceitável para telemetria; corrigir exigiria
    idempotência por token de rodada.
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
    except BaseException as exc:
        # BaseException (P2-4): com scheduler.shutdown(wait=False), um flush em
        # voo recebe CancelledError — que NÃO é Exception no 3.11. Capturando só
        # Exception, a janela drenada evaporava em silêncio. Restauramos primeiro
        # e só então repropagamos o cancelamento.
        descartados = 0
        with _lock:            # devolve para a memória: nada se perde
            for chave, contagem in itens:
                if len(_contadores) >= _MAX_ENTRADAS and chave not in _contadores:
                    descartados += contagem   # P2-2: teto vale também no restore
                    continue
                _contadores[chave] = _contadores.get(chave, 0) + contagem
        if descartados:
            logger.warning("Telemetria: teto de %d buckets atingido no restore — %d "
                           "evento(s) descartado(s)", _MAX_ENTRADAS, descartados)
        logger.warning("Flush da telemetria de rotas falhou (%s): contadores mantidos "
                       "em memória para a próxima tentativa", type(exc).__name__)
        if isinstance(exc, asyncio.CancelledError):
            raise
        return {"buckets": 0, "eventos": 0, "erro": type(exc).__name__,
                "eventos_descartados_por_teto": descartados}


class HistoricoIndisponivel(RuntimeError):
    """O histórico persistido não pôde ser lido (banco fora, erro de consulta).

    Distinta de "tabela ainda não criada": ali o vazio é a verdade (nunca houve
    flush); aqui o vazio seria uma MENTIRA perigosa — leria-se `total: 0` como
    "rota sem uso" e a Onda 5 removeria endpoint em uso diário (P1-1).
    """


def _tabela_ausente(exc: BaseException) -> bool:
    """True quando o erro é 'relação não existe' — migration 122 ainda não aplicada."""
    texto = f"{type(exc).__name__}: {exc}".lower()
    return ("undefinedtable" in texto or "does not exist" in texto
            or "no such table" in texto or "relation" in texto and "not exist" in texto)


async def _persistidos(desde: datetime | None) -> list[dict]:
    """Lê o histórico persistido.

    Devolve [] APENAS quando a tabela ainda não existe (fail-open legítimo).
    Qualquer outra falha levanta ``HistoricoIndisponivel`` — o chamador marca o
    payload como incompleto em vez de exibir zeros.
    """
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.route_usage_metric import RouteUsageMetric

        async with AsyncSessionLocal() as db:
            q = select(RouteUsageMetric.rota, RouteUsageMetric.metodo,
                       RouteUsageMetric.papel, RouteUsageMetric.hora,
                       RouteUsageMetric.contagem)
            if desde is not None:
                q = q.where(RouteUsageMetric.hora >= desde)
            linhas = (await db.execute(q)).all()
        return [{"rota": r, "metodo": m, "papel": p, "hora": h.isoformat(),
                 "contagem": n, "motivo": ROTAS_MONITORADAS.get(r, "")}
                for r, m, p, h, n in linhas]
    except Exception as exc:
        if _tabela_ausente(exc):
            logger.info("route_usage_metrics ainda não existe (migration 122 pendente): "
                        "histórico vazio é o estado real")
            return []
        logger.error("Histórico de telemetria INDISPONÍVEL (%s) — resposta será marcada "
                     "como incompleta", type(exc).__name__)
        raise HistoricoIndisponivel(type(exc).__name__) from exc


async def agregado_persistido(desde: datetime | None = None) -> dict:
    """Agregado COMPLETO: histórico persistido + o que ainda está em memória.

    É o que o endpoint administrativo devolve — a janela sobrevive a restarts.
    `desde` já chega validado como datetime (o contrato do endpoint rejeita
    string inválida com 422); nunca se faz parsing tolerante aqui.
    """
    desde_iso = desde.isoformat() if desde is not None else None
    historico_indisponivel = False
    try:
        historico = await _persistidos(desde)
    except HistoricoIndisponivel:
        historico, historico_indisponivel = [], True

    linhas = historico + [
        x for x in snapshot() if not desde_iso or x["hora"] >= desde_iso
    ]
    out = _montar_agregado(linhas, desde_iso)
    if historico_indisponivel:
        # NUNCA deixar total: 0 ser lido como "sem uso" (P1-1): o consumidor
        # precisa saber que o histórico não entrou na conta.
        out["historico_indisponivel"] = True
        out.pop("sem_uso_no_periodo", None)
        out["fonte"] = "APENAS memória — histórico persistido indisponível"
        out["alerta"] = ("Histórico persistido NÃO pôde ser lido: os totais abaixo refletem "
                         "somente a memória do processo. NÃO use este resultado para decidir "
                         "remoção de rota.")
        return out
    out["fonte"] = "banco (histórico) + memória (janela corrente ainda não persistida)"
    out["observacao"] = ("Contagens persistidas em route_usage_metrics por flush periódico; "
                         "o bloco ainda em memória é somado aqui. A janela sobrevive a "
                         "restarts — se o flush falhar, os contadores voltam para a memória.")
    return out


def resetar() -> None:
    """Zera os contadores (uso administrativo/teste)."""
    with _lock:
        _contadores.clear()


async def expurgar_antigos(dias: int = RETENCAO_DIAS) -> dict:
    """Remove buckets acima da janela de retenção (LGPD art. 15-16: dado deixa de
    ser necessário à finalidade). Chamado pelo job do APScheduler."""
    try:
        from sqlalchemy import delete

        from app.core.database import AsyncSessionLocal
        from app.models.route_usage_metric import RouteUsageMetric

        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                delete(RouteUsageMetric).where(RouteUsageMetric.hora < corte))
            await db.commit()
        removidos = getattr(res, "rowcount", 0) or 0
        if removidos:
            logger.info("Telemetria de rotas: %d bucket(s) acima de %d dias expurgados",
                        removidos, dias)
        return {"removidos": removidos, "corte": corte.isoformat()}
    except Exception as exc:
        if _tabela_ausente(exc):
            return {"removidos": 0, "corte": None}
        logger.warning("Expurgo da telemetria falhou (%s)", type(exc).__name__)
        return {"removidos": 0, "erro": type(exc).__name__}
