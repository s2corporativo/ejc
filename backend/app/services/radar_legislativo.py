# ── app/services/radar_legislativo.py ────────────────────────────────────────
# Radar Legislativo — monitora proposições na Câmara dos Deputados, no Senado
# Federal e na ALMG (estadual MG) por termos derivados dos ramos ativos do
# escritório, e alimenta o Radar Regulatório existente: cada proposição NOVA
# vira um registro em `diario_oficial_alertas` (o mesmo modelo agregado pelo
# endpoint /v1/regulatorio/digest-semanal e pela página RadarRegulatorio.tsx).
#
# Decisões (docs/CATALOGO_APIS_EJC.md — sondagem ao vivo 2026-07):
#   • Câmara v2: OK mas lenta (~13s) → timeout 30s.
#   • Senado: OK via sufixo .json (API modernizada 05/2025 — client abstraído
#     em _parse_senado, tolerante a mais de um shape).
#   • ALMG: probe deu TIMEOUT 25s → timeout 45s, retries suaves e degradação
#     TOTAL: falha da ALMG nunca derruba o job (loga e segue com as demais).
#   • Dedup persistente: tabela `radar_legislativo_visto` criada via
#     CREATE TABLE IF NOT EXISTS (padrão indices_bcb_cache — SEM migration).
#   • Rate educado: sleep 1s entre termos; commit POR FONTE (falha de uma
#     fonte não perde o que as outras coletaram).
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Any, Awaitable, Callable

from app.core.config import get_settings

logger = logging.getLogger("ejc.radar_legislativo")

# ── Constantes de API ─────────────────────────────────────────────────────────
CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2"
SENADO_LISTA_URL = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista.json"
# Parâmetro `expressao` + `formato=json` conforme padrão da API v2 da ALMG
# (swagger dadosabertos.almg.gov.br inacessível no probe — parse TOLERANTE a
# múltiplos shapes; ver _parse_almg).
ALMG_PESQUISA_URL = "https://dadosabertos.almg.gov.br/api/v2/proposicoes/pesquisa/direcionada"

TIMEOUT_CAMARA = 30   # sondagem: ~13s de latência típica
TIMEOUT_SENADO = 20
TIMEOUT_ALMG = 45     # sondagem: timeout aos 25s → folga + retries suaves

FONTES = ("camara", "senado", "almg")
_SLEEP_ENTRE_TERMOS = 1.0        # rate educado com APIs públicas
_MAX_DETALHES_POR_TERMO = 5      # Câmara: detalhe só p/ itens novos, com teto

# ── Termos default por ramo (slug da tabela `areas` / AREAS_DIREITO) ─────────
# Curtos e de alto sinal — a busca das 3 casas é por expressão/keyword.
# Customização/override por ramo via RADAR_LEGISLATIVO_TERMOS (JSON no .env).
TERMOS_POR_RAMO: dict[str, list[str]] = {
    "trabalhista":     ["reforma trabalhista", "CLT"],
    "civil":           ["código civil"],
    "previdenciario":  ["previdência benefício"],
    "tributario":      ["reforma tributária", "ICMS", "ISS"],
    "criminal":        ["código penal"],
    "consumidor":      ["código de defesa do consumidor"],
    "administrativo":  ["licitação", "improbidade administrativa"],
    "familia":         ["pensão alimentícia"],
    "empresarial":     ["recuperação judicial"],
    "ambiental":       ["licenciamento ambiental"],
    "bancario":        ["superendividamento"],
    "imobiliario":     ["locação imóvel"],
    "sucessoes":       ["inventário partilha"],
    "constitucional":  ["emenda constitucional"],
    "juizados":        ["juizados especiais"],
    "digital_lgpd":    ["proteção de dados"],
    "transito":        ["código de trânsito"],
}


# ── HTTP (indireção única — mockável nos testes) ─────────────────────────────
async def _get_json(
    fonte: str,
    url: str,
    params: dict | None = None,
    *,
    timeout: float = 20,
    tentativas: int = 2,
) -> Any | None:
    """GET JSON com retries suaves (backoff 1.5s·n). Retorna None na falha
    final — nunca propaga exceção (degradação: quem chama trata None)."""
    import httpx

    for tentativa in range(1, tentativas + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, headers={"Accept": "application/json"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            if tentativa < tentativas:
                await asyncio.sleep(1.5 * tentativa)
                continue
            logger.warning(f"[{fonte}] GET {url} falhou após {tentativa} tentativa(s): {e}")
    return None


# ── Normalização — funções puras (testáveis sem rede) ────────────────────────
# Shape único: {fonte, id_externo, tipo, numero, ano, ementa, url,
#               data_apresentacao, ultima_tramitacao}

def _item(fonte: str, id_externo: Any, tipo: Any, numero: Any, ano: Any,
          ementa: Any, url: str, data_apresentacao: str | None = None,
          ultima_tramitacao: str | None = None) -> dict:
    return {
        "fonte": fonte,
        "id_externo": str(id_externo),
        "tipo": str(tipo or "").strip() or "PROP",
        "numero": int(numero or 0),
        "ano": int(ano or 0),
        "ementa": str(ementa or "").strip(),
        "url": url,
        "data_apresentacao": data_apresentacao,
        "ultima_tramitacao": ultima_tramitacao,
    }


def _parse_camara(payload: Any) -> list[dict]:
    """Lista de /proposicoes da Câmara → shape único (a lista não traz data de
    apresentação/tramitação — completadas depois via detalhar_camara)."""
    dados = payload.get("dados") if isinstance(payload, dict) else None
    saida = []
    for p in dados or []:
        pid = p.get("id")
        if not pid:
            continue
        saida.append(_item(
            "camara", pid, p.get("siglaTipo"), p.get("numero"), p.get("ano"),
            p.get("ementa"),
            f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}",
        ))
    return saida


def _parse_camara_detalhe(payload: Any) -> tuple[str | None, str | None]:
    """/proposicoes/{id} → (data_apresentacao, ultima_tramitacao)."""
    dados = payload.get("dados") if isinstance(payload, dict) else None
    if not isinstance(dados, dict):
        return None, None
    data_apr = (dados.get("dataApresentacao") or "")[:10] or None
    st = dados.get("statusProposicao") or {}
    partes = [st.get("descricaoSituacao"), st.get("descricaoTramitacao")]
    quando = (st.get("dataHora") or "")[:10]
    tram = " — ".join(x for x in partes if x)
    if tram and quando:
        tram = f"{tram} ({quando})"
    return data_apr, (tram or None)


def _parse_senado(payload: Any) -> list[dict]:
    """Senado (lista.json). API modernizada em 2025 — parser tolerante:
    aceita o shape clássico PesquisaBasicaMateria.Materias.Materia (dict
    quando há 1 resultado) e um shape achatado `materias: [...]`."""
    if not isinstance(payload, dict):
        return []
    materias = (
        ((payload.get("PesquisaBasicaMateria") or {}).get("Materias") or {}).get("Materia")
        or payload.get("materias")
        or []
    )
    if isinstance(materias, dict):   # 1 resultado → dict em vez de lista
        materias = [materias]
    saida = []
    for m in materias:
        if not isinstance(m, dict):
            continue
        ident = m.get("IdentificacaoMateria") or m
        codigo = ident.get("CodigoMateria") or ident.get("codigo") or ident.get("id")
        if not codigo:
            continue
        basicos = m.get("DadosBasicosMateria") or {}
        saida.append(_item(
            "senado", codigo,
            ident.get("SiglaSubtipoMateria") or ident.get("SiglaTipoMateria")
            or ident.get("sigla") or "MAT",
            ident.get("NumeroMateria") or ident.get("numero"),
            ident.get("AnoMateria") or ident.get("ano"),
            m.get("EmentaMateria") or basicos.get("EmentaMateria") or m.get("ementa"),
            f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}",
            data_apresentacao=(basicos.get("DataApresentacao")
                               or m.get("DataApresentacao") or None),
        ))
    return saida


def _parse_almg(payload: Any) -> list[dict]:
    """ALMG /api/v2/proposicoes/pesquisa/direcionada — parser DEFENSIVO:
    o swagger não foi alcançável na sondagem, então aceitamos os shapes
    plausíveis ({resultado:{listaItem:[...]}}, {list:[...]}, lista crua)."""
    if isinstance(payload, list):
        itens = payload
    elif isinstance(payload, dict):
        resultado = payload.get("resultado")
        itens = (
            (resultado or {}).get("listaItem") if isinstance(resultado, dict) else None
        ) or payload.get("list") or payload.get("proposicoes") or payload.get("dados") or []
    else:
        return []
    saida = []
    for p in itens:
        if not isinstance(p, dict):
            continue
        tipo = (p.get("siglaTipoProjeto") or p.get("siglaTipo") or p.get("tipo")
                or "PL")
        numero = p.get("numero") or p.get("num")
        ano = p.get("ano")
        pid = p.get("id") or (f"{tipo}-{numero}-{ano}" if numero and ano else None)
        if not pid:
            continue
        saida.append(_item(
            "almg", pid, tipo, numero, ano,
            p.get("ementa") or p.get("assunto") or p.get("resumo"),
            p.get("url") or p.get("link")
            or f"https://www.almg.gov.br/atividade-parlamentar/projetos-de-lei/texto/?tipo={tipo}&num={numero}&ano={ano}",
            data_apresentacao=(str(p.get("dataApresentacao")
                               or p.get("dataPublicacao") or "")[:10] or None),
            ultima_tramitacao=p.get("ultimaTramitacao") or p.get("situacao"),
        ))
    return saida


# ── Conectores (uma chamada por termo — falha ⇒ lista vazia) ─────────────────
async def buscar_camara(termo: str) -> list[dict]:
    payload = await _get_json(
        "camara", f"{CAMARA_API}/proposicoes",
        params={"keywords": termo, "ordem": "DESC", "ordenarPor": "id", "itens": 15},
        timeout=TIMEOUT_CAMARA,
    )
    return _parse_camara(payload) if payload else []


async def detalhar_camara(id_externo: str) -> tuple[str | None, str | None]:
    """Detalhe /proposicoes/{id} (data de apresentação + última tramitação).
    Best-effort — usado só para itens NOVOS, com teto por termo. Se o detalhe
    não trouxer tramitação, tenta /tramitacoes (última entrada)."""
    payload = await _get_json(
        "camara", f"{CAMARA_API}/proposicoes/{id_externo}", timeout=TIMEOUT_CAMARA,
    )
    data_apr, tram = _parse_camara_detalhe(payload) if payload else (None, None)
    if payload and not tram:
        pt = await _get_json(
            "camara", f"{CAMARA_API}/proposicoes/{id_externo}/tramitacoes",
            timeout=TIMEOUT_CAMARA,
        )
        dados = (pt or {}).get("dados") or []
        if dados:
            ult = dados[-1]
            tram = ult.get("despacho") or ult.get("descricaoTramitacao")
    return data_apr, tram


async def buscar_senado(termo: str) -> list[dict]:
    payload = await _get_json(
        "senado", SENADO_LISTA_URL,
        params={"palavraChave": termo, "ano": datetime.now().year},
        timeout=TIMEOUT_SENADO,
    )
    return _parse_senado(payload) if payload else []


async def buscar_almg(termo: str) -> list[dict]:
    payload = await _get_json(
        "almg", ALMG_PESQUISA_URL,
        params={"expressao": termo, "formato": "json"},
        timeout=TIMEOUT_ALMG,
    )
    return _parse_almg(payload) if payload else []


_BUSCADORES: dict[str, Callable[[str], Awaitable[list[dict]]]] = {
    "camara": buscar_camara,
    "senado": buscar_senado,
    "almg": buscar_almg,
}


# ── Termos monitorados (ramos ativos + customização via .env) ────────────────
def _termos_customizados() -> dict[str, list[str]]:
    """RADAR_LEGISLATIVO_TERMOS (JSON): {"ramo": ["termo", ...]} — SOBREPÕE a
    lista default do ramo; ramos fora da taxonomia são aceitos (aditivos).
    JSON inválido → ignora com warning (nunca derruba o job)."""
    bruto = (get_settings().RADAR_LEGISLATIVO_TERMOS or "").strip()
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
        if not isinstance(dados, dict):
            raise ValueError("esperado objeto JSON {ramo: [termos]}")
        saida: dict[str, list[str]] = {}
        for ramo, termos in dados.items():
            if isinstance(termos, str):
                termos = [termos]
            lista = [str(t).strip() for t in termos or [] if str(t).strip()]
            if lista:
                saida[str(ramo)] = lista
        return saida
    except Exception as e:
        logger.warning(f"RADAR_LEGISLATIVO_TERMOS inválido (ignorado): {e}")
        return {}


async def termos_monitorados(db) -> dict[str, list[str]]:
    """Ramo → termos: parte dos ramos ATIVOS do escritório (tabela `areas`;
    fallback: AREAS_DIREITO), aplica os defaults TERMOS_POR_RAMO e depois o
    override/adição de RADAR_LEGISLATIVO_TERMOS."""
    slugs: list[str] = []
    try:
        from sqlalchemy import text
        rows = (await db.execute(text(
            "SELECT slug FROM areas WHERE ativo = true"
        ))).scalars().all()
        slugs = [str(s) for s in rows]
    except Exception as e:
        logger.warning(f"Tabela `areas` indisponível ({e}) — fallback AREAS_DIREITO")
    if not slugs:
        from app.services.peca_service import AREAS_DIREITO
        slugs = list(AREAS_DIREITO)

    termos = {s: list(TERMOS_POR_RAMO[s]) for s in slugs if TERMOS_POR_RAMO.get(s)}
    termos.update(_termos_customizados())      # override por ramo + ramos extras
    return termos


# ── Dedup persistente (CREATE TABLE IF NOT EXISTS — sem migration) ───────────
async def _ensure_tabela(db) -> None:
    from sqlalchemy import text
    # DDL portátil (Postgres e SQLite nos testes) — chave natural fonte+id.
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS radar_legislativo_visto (
            fonte VARCHAR(20) NOT NULL,
            id_externo VARCHAR(80) NOT NULL,
            tipo VARCHAR(30),
            numero INTEGER,
            ano INTEGER,
            ementa TEXT,
            url TEXT,
            data_apresentacao VARCHAR(30),
            ultima_tramitacao TEXT,
            termo VARCHAR(200),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (fonte, id_externo)
        )
    """))


async def _ja_visto(db, fonte: str, id_externo: str) -> bool:
    from sqlalchemy import text
    row = (await db.execute(text(
        "SELECT 1 FROM radar_legislativo_visto WHERE fonte = :f AND id_externo = :i"
    ), {"f": fonte, "i": id_externo})).first()
    return row is not None


async def _marcar_visto(db, item: dict, termo: str) -> None:
    from sqlalchemy import text
    await db.execute(text("""
        INSERT INTO radar_legislativo_visto
            (fonte, id_externo, tipo, numero, ano, ementa, url,
             data_apresentacao, ultima_tramitacao, termo)
        VALUES (:fonte, :id_externo, :tipo, :numero, :ano, :ementa, :url,
                :data_apresentacao, :ultima_tramitacao, :termo)
        ON CONFLICT (fonte, id_externo) DO NOTHING
    """), {**item, "ementa": item["ementa"][:4000], "termo": termo[:200]})


# ── Acoplamento ao Radar Regulatório (modelo DiarioOficialAlerta) ────────────
def _parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except Exception:
        return None


async def _criar_alerta(db, item: dict, termo: str) -> None:
    """Proposição nova → alerta no MESMO modelo do Radar Regulatório
    (diario_oficial_alertas): aparece no digest /v1/regulatorio/digest-semanal
    e na página RadarRegulatorio.tsx sem criar estrutura paralela. keyword_id/
    case_id ficam NULL (office-wide — visível a toda a equipe no filtro de
    ownership do Diário Oficial)."""
    from uuid import uuid4
    from app.models.diario_oficial import DiarioOficialAlerta

    rotulo = f"{item['tipo']} {item['numero']}/{item['ano']}"
    resumo = item["ementa"]
    if item.get("ultima_tramitacao"):
        resumo = f"{resumo}\nÚltima tramitação: {item['ultima_tramitacao']}"
    db.add(DiarioOficialAlerta(
        id=str(uuid4()),
        fonte=item["fonte"],                      # camara|senado|almg
        secao=item["tipo"][:10],
        titulo=f"{rotulo} — {item['ementa']}"[:500],
        resumo=resumo[:4000],
        link=item["url"],
        keyword_match=termo[:200],
        data_publicacao=_parse_data(item.get("data_apresentacao")),
    ))


# ── Job ───────────────────────────────────────────────────────────────────────
async def processar_fonte(
    db, fonte: str, termos: dict[str, list[str]], *,
    sleep_s: float = _SLEEP_ENTRE_TERMOS,
) -> int:
    """Varre TODOS os termos numa fonte, deduplica e cria alertas dos novos.
    Commit ao final da FONTE — falha de outra fonte não perde esta coleta."""
    await _ensure_tabela(db)
    buscar = _BUSCADORES[fonte]
    novos = 0
    for ramo, lista in termos.items():
        for termo in lista:
            detalhes = 0
            try:
                itens = await buscar(termo)
                for item in itens:
                    if await _ja_visto(db, fonte, item["id_externo"]):
                        continue
                    # Câmara: a lista não traz data/tramitação — completa só
                    # p/ novos, com teto (latência ~13s por chamada).
                    if (fonte == "camara" and detalhes < _MAX_DETALHES_POR_TERMO
                            and not item.get("data_apresentacao")):
                        detalhes += 1
                        try:
                            data_apr, tram = await detalhar_camara(item["id_externo"])
                            item["data_apresentacao"] = data_apr
                            item["ultima_tramitacao"] = tram
                        except Exception as e:
                            logger.warning(f"[camara] detalhe {item['id_externo']} falhou: {e}")
                    await _marcar_visto(db, item, termo)
                    await _criar_alerta(db, item, termo)
                    novos += 1
            except Exception as e:
                # Falha de UM termo não derruba os demais.
                logger.warning(f"[{fonte}] termo '{termo}' (ramo {ramo}) falhou: {e}")
            if sleep_s:
                await asyncio.sleep(sleep_s)
    await db.commit()
    return novos


async def _notificar_equipe(db, resumo: dict[str, int]) -> None:
    """Sino interno (best-effort) aos perfis advogado+ quando houve novidade."""
    total = sum(v for v in resumo.values() if isinstance(v, int))
    if total <= 0:
        return
    try:
        from sqlalchemy import text
        from app.services.notification_service import criar_notificacao_interna
        rows = (await db.execute(text(
            "SELECT id FROM users WHERE is_active = true "
            "AND role IN ('superadmin','admin','socio','advogado')"
        ))).scalars().all()
        detalhe = ", ".join(f"{f}: {n}" for f, n in resumo.items() if isinstance(n, int))
        for uid in rows:
            await criar_notificacao_interna(
                db, str(uid), "🏛️ Radar Legislativo",
                f"{total} nova(s) proposição(ões) monitorada(s) ({detalhe}).",
                tipo="diario_oficial", link="/radar-regulatorio",
            )
        await db.commit()
    except Exception as e:
        logger.warning(f"[radar-legislativo] notificação falhou (não-fatal): {e}")


async def executar_radar(db, *, sleep_s: float = _SLEEP_ENTRE_TERMOS) -> dict:
    """Executa a varredura nas 3 fontes. Cada fonte é isolada: exceção (ALMG
    fora do ar, p.ex.) vira contagem 'erro' no resumo e o job SEGUE."""
    termos = await termos_monitorados(db)
    resumo: dict[str, Any] = {}
    for fonte in FONTES:
        try:
            resumo[fonte] = await processar_fonte(db, fonte, termos, sleep_s=sleep_s)
        except Exception as e:
            logger.error(f"[radar-legislativo] fonte {fonte} falhou (segue): {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            resumo[fonte] = "erro"
    await _notificar_equipe(db, resumo)
    return resumo


async def job_radar_legislativo() -> None:
    """07h00 UTC — gate RADAR_LEGISLATIVO_ENABLED (default True: APIs públicas
    gratuitas, autorizado pelo dono)."""
    if not get_settings().RADAR_LEGISLATIVO_ENABLED:
        logger.info("[radar-legislativo] desabilitado (RADAR_LEGISLATIVO_ENABLED=false)")
        return
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            resumo = await executar_radar(db)
            logger.info(f"[radar-legislativo] concluído — novos por fonte: {resumo}")
    except Exception as e:
        logger.error(f"[radar-legislativo] falha no job: {e}")


# ── Consulta (endpoint) ───────────────────────────────────────────────────────
async def buscar_ao_vivo(termo: str, fontes: tuple[str, ...] = FONTES
                         ) -> tuple[list[dict], list[str]]:
    """Busca ao vivo nas fontes pedidas (paralela, tolerante).
    Retorna (itens, fontes_com_falha)."""
    tarefas = [_BUSCADORES[f](termo) for f in fontes]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)
    itens: list[dict] = []
    falhas: list[str] = []
    for fonte, res in zip(fontes, resultados):
        if isinstance(res, BaseException):
            logger.warning(f"[{fonte}] busca ao vivo falhou: {res}")
            falhas.append(fonte)
        else:
            itens.extend(res)
    return itens, falhas


async def historico_visto(db, fonte: str | None = None, termo: str | None = None,
                          limite: int = 50) -> list[dict]:
    """Histórico persistido (radar_legislativo_visto), filtros opcionais."""
    from sqlalchemy import text
    await _ensure_tabela(db)
    sql = ("SELECT fonte, id_externo, tipo, numero, ano, ementa, url, "
           "data_apresentacao, ultima_tramitacao, termo, criado_em "
           "FROM radar_legislativo_visto WHERE 1=1")
    params: dict[str, Any] = {"lim": max(1, min(limite, 200))}
    if fonte:
        sql += " AND fonte = :fonte"
        params["fonte"] = fonte
    if termo:
        sql += " AND (LOWER(ementa) LIKE :t OR LOWER(termo) LIKE :t)"
        params["t"] = f"%{termo.lower()}%"
    sql += " ORDER BY criado_em DESC LIMIT :lim"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return [
        {**dict(r), "criado_em": str(r["criado_em"]) if r["criado_em"] else None}
        for r in rows
    ]
