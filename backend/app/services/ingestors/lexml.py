# ── app/services/ingestors/lexml.py ──────────────────────────────────────────
# Ingestor FEDERADO LexML → RAG (legislação + jurisprudência, agendado por temas).
#
# Por que LexML como VEÍCULO de volume: o LexML.gov.br (Rede de Informação
# Legislativa e Jurídica, mantida pelo Senado) é o federador oficial que expõe,
# NUMA ÚNICA fonte pública, legislação federal/ESTADUAL (ALMG)/MUNICIPAL (Betim)
# e jurisprudência de TJ/TRT/TRF/TST/STJ/STF. Em vez de escrever um scraper
# dedicado (e não-testável aqui) para cada portal heterogêneo — ALMG, Câmara de
# Betim, TRT-3, TRF-6 diretos —, este ingestor reaproveita o caminho JÁ PROVADO
# `jurisprudencia_externa.buscar_lexml` (API pública, keyword-based) e federa
# tudo por PALAVRAS que miram as autoridades e as áreas do escritório (Betim/MG).
#
# ESPELHA a estrutura do ingestor TJMG (tjmg.py): catálogo de temas curados →
# busca best-effort por tema → upsert idempotente com dedup por chave_origem →
# métricas (novos, total). Falha de rede/fonte NUNCA derruba a execução.
#
# COBERTURA (honesta): a busca do LexML é por TERMOS (não há parâmetro de
# "autoridade" na assinatura de buscar_lexml). Miramos os tribunais/casas/
# localidades pelas próprias PALAVRAS do tema (ex.: "TRT-3 horas extras",
# "ALMG lei estadual Minas Gerais", "Betim lei municipal"). O que o federador
# devolve é exatamente o que entra — nada é fabricado. Portais DEDICADOS (ALMG,
# leis municipais de Betim, TRT/TRF diretos) exigiriam build verificável com
# .gov liberado e ficam como follow-up documentado (.env.example) — não se
# inventa endpoint aqui.
#
# GOVERNANÇA / CITATION GATE: jurisprudência entra em categoria "jurisprudencia"
# (conteúdo público/global, client_id/case_id = NULL). A legislação federada
# entra em categoria "referencia_legislativa" — deliberadamente FORA do prefixo
# "legislacao%" —, porque o gate anti-alucinação de citações
# (citation_check._existe_artigo) confia em `categoria LIKE 'legislacao%'` como
# prova de que um ARTIGO existe: os registros do LexML são EMENTAS/índices de
# norma (título + resumo), não a lei seca verbatim, e alimentá-los ali afrouxaria
# o gate (números de artigo passariam a "existir" via ementa alheia). A busca
# semântica default (categorias=None) varre TODAS as categorias, então esses
# documentos seguem recuperáveis normalmente — só não contaminam o gate.
#
# VIGÊNCIA (Issue #636) — LIMITAÇÃO DA FONTE: o feed Atom do federador não
# expõe campo de situação normativa, então este ingestor NÃO declara vigência
# por ausência de marcação; só propaga `extra.legal_status='revogada'` quando o
# próprio TÍTULO do registro afirma a revogação (ver `situacao_juridica`). O
# resumo/ementa pode mencionar OUTRA norma revogada e, por isso, não é usado
# como prova da situação do item atual. O restante permanece
# 'vigencia_nao_verificada' na governança — e, com
# RAG_EXIGIR_VIGENCIA_VERIFICADA ligada, fora da recuperação até curadoria.
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.ingestion_service import upsert_documento
from app.services.jurisprudencia_externa import LexMLBloqueadoError, buscar_lexml

logger = logging.getLogger("ejc.ingestao.lexml")

# Endpoint público de consulta do federador LexML (mesma base que
# jurisprudencia_externa.buscar_lexml usa). Toda URL que este ingestor GERA
# aponta para cá; validada contra a allowlist oficial antes de gravar.
LEXML_CONSULTA_BASE = "https://www.lexml.gov.br/busca/pesquisa"

# Categorias RAG por tipo LexML. Ver nota de GOVERNANÇA no topo: legislação
# federada é "referencia_legislativa" (NÃO 'legislacao%') para não afrouxar o
# citation gate; jurisprudência é 'jurisprudencia' (o gate de súmula usa
# 'sumula%', então não há colisão).
_CATEGORIA = {"legislacao": "referencia_legislativa", "jurisprudencia": "jurisprudencia"}
_TIPO_FONTE = {"legislacao": "legislacao_referencia", "jurisprudencia": "jurisprudencia_oficial"}

# Os dois tipos que o federador cobre e que este ingestor varre por tema.
TIPOS = ("legislacao", "jurisprudencia")

# ══════════════════════════════════════════════════════════════════════════
# Catálogo de TEMAS/autoridades — palavras-chave que miram as jurisdições-alvo
# do escritório (Betim/MG) e suas áreas. Cada tema é buscado para tipo=
# 'legislacao' E tipo='jurisprudencia' (temas de tribunal rendem mais na
# jurisprudência; temas de casa/localidade rendem mais na legislação — a busca
# degrada graciosamente quando um tipo não casa). Sobrescrevível via
# LEXML_INGEST_TEMAS (.env, CSV).
# ══════════════════════════════════════════════════════════════════════════
TEMAS_PADRAO = [
    # ── Tribunais estaduais/regionais MG (jurisdição direta do escritório) ──
    "TJMG dano moral consumidor",
    "TJMG usucapião imóvel",
    "TRT-3 horas extras verbas rescisórias",          # trabalhista MG
    "TRT-3 vínculo empregatício reconhecimento",
    "TRF-6 benefício previdenciário INSS",            # federal MG (6ª região)
    "TRF-1 servidor público federal concurso",        # federal (1ª região)
    # ── Tribunais superiores ──
    "TST justa causa rescisão contrato de trabalho",
    "STJ recurso repetitivo direito do consumidor",
    "STF repercussão geral direito administrativo",
    # ── Juizados especiais (JEC / JEF) ──
    "juizado especial cível negativação indevida",
    "juizado especial federal previdenciário revisão",
    # ── Legislação estadual (ALMG) e municipal (Betim) via localidade ──
    "ALMG lei estadual Minas Gerais servidor público",
    "Minas Gerais ICMS lei estadual tributária",
    "Betim lei municipal",
    "Betim plano diretor código de obras município",
    "lei municipal IPTU ISS código tributário municipal",
    # ── Áreas nucleares do escritório (federa federal + estadual + municipal) ──
    "improbidade administrativa licitação contrato público",
    "meio ambiente licenciamento infração ambiental",
    "direito do consumidor plano de saúde negativa de cobertura",
    "família alimentos guarda divórcio partilha",
    "recuperação judicial falência empresarial",
    "aposentadoria revisão benefício previdenciário",
    "locação despejo imobiliário",
    "responsabilidade civil indenização dano moral",
]


def _temas(cfg) -> list[str]:
    csv = (getattr(cfg, "LEXML_INGEST_TEMAS", "") or "").strip()
    if csv:
        return [t.strip() for t in csv.split(",") if t.strip()]
    return TEMAS_PADRAO


# ══════════════════════════════════════════════════════════════════════════
# Federação EXPLÍCITA por jurisdição (esfera/localidade/autoridade no esquema
# URN LexML). Enquanto TEMAS_PADRAO varre ÁREAS por palavra-chave nos dois
# tipos, este catálogo mira JURISDIÇÕES nominais que antes só apareciam por
# tema genérico — legislação estadual de MG (ALMG), municipal de Betim, e
# jurisprudência de TRT-3/TRF-6/juizados. Cada jurisdição declara sua
# localidade/autoridade no padrão URN LexML (urn:lex:br;<localidade>:<autoridade>),
# de onde derivam (a) uma consulta explícita para buscar_lexml e (b) um prefixo
# URN bem-formado gravado no metadado. Roda sob o MESMO gate LEXML_INGEST_ENABLED
# (via ingerir); nao introduz flag nova.
# ══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class JurisdicaoLexML:
    slug: str          # id estável (metadado/dedup)
    rotulo: str        # rótulo humano
    tipo: str          # 'legislacao' | 'jurisprudencia' → define a categoria RAG
    esfera: str        # federal | estadual | municipal | trabalhista | juizado_especial
    localidade: str    # localidade no URN LexML (ex.: 'minas.gerais', 'minas.gerais;betim')
    autoridade: str    # autoridade no URN LexML (ex.: 'assembleia.legislativa')
    consulta: str      # palavras-chave explícitas para buscar_lexml


JURISDICOES_FEDERADAS: list[JurisdicaoLexML] = [
    # ── Legislação ESTADUAL de Minas Gerais (ALMG) → referencia_legislativa ──
    JurisdicaoLexML(
        slug="mg_estadual_almg", tipo="legislacao", esfera="estadual",
        rotulo="Legislação estadual de Minas Gerais (ALMG)",
        localidade="minas.gerais", autoridade="assembleia.legislativa",
        consulta="Minas Gerais lei estadual ALMG assembleia legislativa",
    ),
    # ── Legislação MUNICIPAL de Betim/MG → referencia_legislativa ──
    JurisdicaoLexML(
        slug="betim_municipal", tipo="legislacao", esfera="municipal",
        rotulo="Legislação municipal de Betim/MG",
        localidade="minas.gerais;betim", autoridade="camara.municipal",
        consulta="Betim Minas Gerais lei municipal câmara municipal",
    ),
    # ── Jurisprudência TRT-3 (trabalhista MG) → jurisprudencia ──
    JurisdicaoLexML(
        slug="trt3_jurisprudencia", tipo="jurisprudencia", esfera="trabalhista",
        rotulo="Jurisprudência TRT-3 (Tribunal Regional do Trabalho da 3ª Região)",
        localidade="minas.gerais", autoridade="tribunal.regional.trabalho.regiao.3",
        consulta="TRT-3 Tribunal Regional do Trabalho 3 regiao acordao Minas Gerais",
    ),
    # ── Jurisprudência TRF-6 (federal MG) → jurisprudencia ──
    JurisdicaoLexML(
        slug="trf6_jurisprudencia", tipo="jurisprudencia", esfera="federal",
        rotulo="Jurisprudência TRF-6 (Tribunal Regional Federal da 6ª Região)",
        localidade="minas.gerais", autoridade="tribunal.regional.federal.regiao.6",
        consulta="TRF-6 Tribunal Regional Federal 6 regiao acordao Minas Gerais",
    ),
    # ── Jurisprudência dos JUIZADOS ESPECIAIS (JEC/JEF, turmas recursais) ──
    JurisdicaoLexML(
        slug="juizados_especiais", tipo="jurisprudencia", esfera="juizado_especial",
        rotulo="Juizados especiais (JEC/JEF) — turmas recursais",
        localidade="minas.gerais", autoridade="turma.recursal",
        consulta="juizado especial civel federal turma recursal enunciado acordao",
    ),
]


# URN LexML bem-formada: urn:lex:br(;localidade)*:autoridade (minúsculas,
# dígitos, ponto e hífen). NÃO é URL (não tem esquema/host), então é validada
# por forma, não pela allowlist de domínio.
_URN_RE = re.compile(r"^urn:lex:br(;[a-z0-9.\-]+)+:[a-z0-9.\-]+$")


def urn_prefixo(j: JurisdicaoLexML) -> str:
    """Prefixo URN LexML da jurisdição: urn:lex:br;<localidade>:<autoridade>."""
    return f"urn:lex:br;{j.localidade}:{j.autoridade}"


def _urn_bem_formada(urn: str) -> bool:
    return bool(_URN_RE.match(urn or ""))


def consulta_url(consulta: str, tipo: str) -> str:
    """URL de consulta pública no federador LexML (domínio oficial lexml.gov.br).
    Toda URL GERADA por este ingestor sai daqui e passa a allowlist oficial."""
    return f"{LEXML_CONSULTA_BASE}?" + urlencode({"palavras": consulta, "tipo": tipo})


def _url_oficial(url: str | None) -> bool:
    """Valida a URL contra a allowlist canônica de domínios oficiais — a MESMA
    função exercida por test_urls_nao_oficiais_ou_burla_rejeitadas
    (ia_governanca._fonte_oficial: https + hostname exato, à prova de bypass).
    Import tardio para não criar ciclo serviço↔router no carregamento do módulo.
    Fonte única de verdade do controle: não duplicamos a lista de domínios aqui."""
    from app.routers.ia_governanca import _fonte_oficial
    return _fonte_oficial(url)


def _plano_federacao(cfg) -> list[tuple[str, str, JurisdicaoLexML | None]]:
    """Constrói o plano de federação como itens (consulta, tipo, jurisdicao):
    (a) jurisdições EXPLÍCITAS (JURISDICOES_FEDERADAS), cada uma no seu tipo;
    (b) temas genéricos (_temas), varridos nos DOIS tipos.
    Um único laço em ingerir() consome o plano — dedup por chave_origem cobre
    qualquer sobreposição entre as duas faces."""
    plano: list[tuple[str, str, JurisdicaoLexML | None]] = []
    for j in JURISDICOES_FEDERADAS:
        plano.append((j.consulta, j.tipo, j))
    for tema in _temas(cfg):
        for tipo in TIPOS:
            plano.append((tema, tipo, None))
    return plano


def _chave(item: dict, tipo: str) -> str:
    """Chave de dedup idempotente, namespaced por tipo (leg/jur) para que um
    mesmo URN não colida entre a face legislação e a face jurisprudência.
    Prefere o identificador do LexML (URN, já sem o prefixo 'urn:lex:br:' e
    limitado a 80 chars por buscar_lexml); sem ele, usa hash estável de
    título+ementa (mesmo registro não duplica entre execuções)."""
    ns = tipo[:3]                                   # 'leg' | 'jur'
    ident = (item.get("numero_acordao") or "").strip()
    if ident:
        return f"lexml:{ns}:{ident}"[:120]
    base = ((item.get("titulo") or "") + "|" + (item.get("ementa") or ""))[:500]
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"lexml:{ns}:{h}"


# ── Vigência declarada no registro LexML (Issue #636) ─────────────────────────
# LIMITAÇÃO HONESTA da fonte: o feed Atom do federador (o que
# jurisprudencia_externa.buscar_lexml consome) traz title/summary/link/author/
# published/id — NÃO há campo estruturado de situação normativa (vigente /
# revogada). Logo NÃO se declara vigência por ausência de marcação: um registro
# sem marcação continua sem `legal_status` e a governança o classifica como
# 'vigencia_nao_verificada' (o lado seguro), o que exige curadoria manual.
#
# Para evitar falsa autorrevogação, somente o TÍTULO do item é aceito como
# evidência positiva. O resumo/ementa frequentemente descreve relações entre
# normas e pode conter frases como "Lei 8.666 revogada pela Lei 14.133" dentro
# do registro da própria Lei 14.133. Usar esse texto para classificar o item
# atual faria uma referência histórica revogar a norma errada. Perder uma
# marcação que apareça apenas na ementa é fail-closed: o item segue sem status
# positivo e exige curadoria.
_RE_ATO_REVOGADO = re.compile(
    r"(?:"
    r"revogad[oa]s?\s+(?:integralmente\s+|expressamente\s+|tacitamente\s+)?pel[ao]s?\b"
    r"|\(\s*revogad[oa]s?\s*\)"
    r"|(?:^|[—–\-]\s*)revogad[oa]s?\s*$"
    r")",
    re.IGNORECASE,
)


def situacao_juridica(item: dict, tipo: str) -> str | None:
    """Retorna `revogada` só quando o TÍTULO da legislação declara a própria
    revogação.

    A ementa/resumo não é prova de autorrevogação porque pode mencionar outra
    norma revogada. Ausência de declaração mantém `None`, que a governança trata
    como vigência não verificada. Jurisprudência nunca herda status normativo.
    """
    if tipo != "legislacao":
        return None
    titulo = str(item.get("titulo") or "").strip()
    return "revogada" if _RE_ATO_REVOGADO.search(titulo) else None


# Aviso de proveniência gravado NO CONTEÚDO, não só no `extra`.
#
# O LexML devolve ementa/resumo e metadados — NUNCA o inteiro teor. Sem este
# aviso, o trecho recuperado pelo RAG chega ao modelo indistinguível de um
# documento lido por inteiro, e a IA pode afirmar o que a decisão "decidiu" ou
# o que a norma "dispõe" tendo visto apenas a ementa. Ementa é resumo redigido
# pelo tribunal: ela indica o julgado, não o substitui.
#
# O aviso vai no conteúdo (e não apenas em metadado) porque é o conteúdo que
# entra no contexto do modelo; metadado em `extra` não é lido por ele.
_AVISO_PROVENIENCIA = (
    "[PROVENIÊNCIA — LEXML: EMENTA E METADADOS, NÃO É O INTEIRO TEOR. "
    "Este registro traz o resumo oficial e os dados de identificação do "
    "documento. Não afirme o conteúdo integral da decisão ou da norma a partir "
    "daqui: consulte o inteiro teor na fonte oficial indicada em 'fonte' antes "
    "de fundamentar.]"
)


def _monta_conteudo(item: dict, tipo: str) -> str:
    """Concatena as partes citáveis do registro LexML (título + metadados +
    ementa/resumo), com o aviso de proveniência à frente.

    Não inventa texto: usa só o que o federador retornou.
    """
    partes: list[str] = [_AVISO_PROVENIENCIA]
    if item.get("titulo"):
        partes.append(item["titulo"])
    if tipo == "jurisprudencia" and item.get("tribunal"):
        partes.append(f"Tribunal: {item['tribunal']}")
    if item.get("relator"):
        rotulo = "Relator(a)/Autor" if tipo == "jurisprudencia" else "Autoridade/Autor"
        partes.append(f"{rotulo}: {item['relator']}")
    if item.get("data_julgamento"):
        partes.append(f"Data: {item['data_julgamento']}")
    if item.get("area_juridica"):
        partes.append(f"Área: {item['area_juridica']}")
    if item.get("ementa"):
        partes.append(f"\n{item['ementa']}")
    return "\n".join(partes)


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Executa a federação LexML → RAG a partir do plano (jurisdições explícitas
    + temas genéricos, cada consulta no seu tipo). Retorna (novos,
    total_processados) — assinatura exigida por `ingestion_service.executar_ingestao`.

    Governança: legislação → categoria 'referencia_legislativa' (NUNCA 'legislacao%',
    p/ não afrouxar o citation gate); jurisprudência → 'jurisprudencia'. Toda URL
    GRAVADA passa a allowlist oficial (_url_oficial); URN da jurisdição é validada
    por forma. Best-effort: erro de rede/fonte numa consulta é logado e pulado
    (nunca derruba a execução). Commit por item + dedup intra-execução por chave.
    """
    cfg = get_settings()
    max_item = int(getattr(cfg, "LEXML_INGEST_MAX_POR_TEMA", 20) or 20)

    novos = total = 0
    vistas: set[str] = set()   # dedup intra-execução (mesmo registro em 2 consultas)

    consultas = 0
    bloqueadas = 0
    falhas_tecnicas = 0

    for consulta, tipo, jur in _plano_federacao(cfg):
        consultas += 1
        try:
            itens = await buscar_lexml(consulta, tipo=tipo, por_pagina=max_item)
        except LexMLBloqueadoError as e:
            # Contado à parte: bloqueio anti-bot não é "não achei nada", é "não
            # perguntei". Se TODAS as consultas forem bloqueadas, a execução
            # inteira falha ao final em vez de reportar (0, 0) como sucesso.
            bloqueadas += 1
            logger.warning("LexML %s %r bloqueado: %s", tipo, consulta, e)
            continue
        except Exception as e:   # rede/XML — nunca derruba a execução inteira
            # Contado junto com os bloqueios: consulta que ESTOUROU também não
            # é "não achei nada". Sem este contador, uma queda de rede em 100%
            # do plano ainda devolveria (0, 0) como execução bem-sucedida — o
            # mesmo silêncio que a correção do anti-bot fechou por um lado e
            # deixou aberto pelo outro.
            falhas_tecnicas += 1
            logger.warning("LexML %s %r: %s: %s", tipo, consulta, type(e).__name__, e)
            continue

        categoria = _CATEGORIA[tipo]
        # URL de consulta oficial (federador) — sempre passa a allowlist; é o
        # fallback de 'fonte' quando o item não traz link_original oficial.
        url_consulta = consulta_url(consulta, tipo)
        urn_jur = urn_prefixo(jur) if jur else None
        n_consulta = 0
        for it in itens:
            ementa = it.get("ementa") or ""
            if len(ementa) < 50:
                continue   # sem valor semântico
            chave = _chave(it, tipo)
            if chave in vistas:
                continue
            vistas.add(chave)

            # Defesa em profundidade: só grava como 'fonte' uma URL de domínio
            # oficial. O link do item entra se for oficial; senão, cai para a URL
            # de consulta do federador (também oficial). Nunca persiste link solto.
            link = it.get("link_original") or ""
            fonte = link if _url_oficial(link) else url_consulta

            # Vigência: só grava quando a FONTE declara (ver situacao_juridica).
            # A chave é OMITIDA quando não há declaração — `upsert_documento`
            # mescla `extra` a cada re-feed, e gravar None apagaria uma decisão
            # de curadoria já registrada no documento.
            extra_vigencia: dict = {}
            legal_status = situacao_juridica(it, tipo)
            if legal_status:
                extra_vigencia = {
                    "legal_status": legal_status,
                    "legal_status_origem": "lexml:titulo",
                }

            try:
                res = await upsert_documento(
                    db,
                    titulo=(it.get("titulo") or f"LexML {tipo}")[:500],
                    categoria=categoria,
                    conteudo=_monta_conteudo(it, tipo),
                    chave_origem=chave,
                    fonte=fonte,
                    # tribunal só na face jurisprudência (metadado do julgado)
                    tribunal=(it.get("tribunal") or None) if tipo == "jurisprudencia" else None,
                    extra={
                        "tipo_lexml": tipo,
                        "tribunal": it.get("tribunal") if tipo == "jurisprudencia" else None,
                        "relator": it.get("relator"),
                        "data": it.get("data_julgamento"),
                        "area_juridica": it.get("area_juridica"),
                        "link": it.get("link_original"),
                        "urn": it.get("numero_acordao"),
                        "tema_busca": consulta,
                        "consulta_lexml": url_consulta,
                        # Metadados da federação EXPLÍCITA (None p/ temas genéricos)
                        "jurisdicao": jur.slug if jur else None,
                        "esfera": jur.esfera if jur else None,
                        "localidade": jur.localidade if jur else None,
                        "autoridade": jur.autoridade if jur else None,
                        "urn_lex_prefixo": urn_jur,
                        "origem": "lexml",
                        "rag_status": "aprovado",
                        "tipo_fonte": _TIPO_FONTE[tipo],
                        # Proveniência explícita: o LexML federa ementa e
                        # metadados, nunca o inteiro teor. Marcado também aqui
                        # (além do aviso no conteúdo) para que painéis, gate de
                        # citações e curadoria possam filtrar por isso sem
                        # precisar reprocessar texto.
                        "inteiro_teor": False,
                        "natureza_conteudo": "ementa_e_metadados",
                        "consultar_inteiro_teor_em": it.get("link_original") or fonte,
                        **extra_vigencia,
                    },
                    confianca="alta",   # federador oficial (Senado/LexML)
                )
                # Commit por item: métricas contam só o persistido; um erro
                # isolado dá rollback APENAS do item falho.
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.warning("LexML upsert %r: %s: %s", chave, type(e).__name__, e)
                continue

            total += 1
            if res in ("novo", "atualizado"):
                novos += 1
                n_consulta += 1

        alvo = jur.slug if jur else "tema"
        logger.info("LexML %s %r [%s]: %d novos / %d itens",
                    tipo, consulta, alvo, n_consulta, len(itens))

    # Toda consulta bloqueada = a federação não rodou. Devolver (0, 0) aqui
    # marcaria a execução como bem-sucedida no registro de fontes, escondendo
    # que o LexML deixou de responder — foi assim que a ingestão passou a
    # entregar zero sem ninguém perceber.
    if consultas and bloqueadas == consultas:
        raise LexMLBloqueadoError(
            f"LexML bloqueou as {consultas} consultas do plano (desafio "
            "anti-bot). Nenhuma ingestão foi executada."
        )
    if consultas and (bloqueadas + falhas_tecnicas) == consultas:
        raise RuntimeError(
            f"LexML: as {consultas} consultas do plano falharam "
            f"({bloqueadas} bloqueadas, {falhas_tecnicas} por erro técnico). "
            "Nenhuma ingestão foi executada."
        )

    return novos, total