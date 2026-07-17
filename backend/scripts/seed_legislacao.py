"""scripts/seed_legislacao.py — importador de LEGISLAÇÃO (lei seca) do Planalto.

Baixa o texto COMPILADO de cada diploma do catálogo (www.planalto.gov.br),
extrai o texto limpo (verbatim — lei não se resume nem se reescreve), divide
por ARTIGO e ingere pelo pipeline oficial `ingestion_service.upsert_documento`
(dedup por chave_origem, versionamento migration 068, chunks próprios).

Compatibilidade com o gate anti-alucinação (citation_check._existe_artigo):
cada chunk ABRE com um cabeçalho de localização "Art. N [· Art. M ...] — <lei>"
— o lookup ILIKE '%Art. N %' / '%Art. Nº%' encontra QUALQUER artigo do chunk
mesmo quando o texto oficial grafa "Art. 10." (ponto, não espaço). O corpo do
chunk é o texto oficial verbatim; texto RISCADO (revogado no compilado) é
removido preservando a anotação "(Revogado ...)" quando o próprio riscado a
contém.

Idempotente: chave_origem "legislacao:planalto:<sigla>"; 2ª execução sem
mudança → "inalterado" (não re-embeda). Alteração legislativa → NOVA VERSÃO
(histórico preservado). Falha de uma lei NÃO aborta as demais (relatório final;
exit code 1 se alguma falhou).

Uso (WORKDIR backend/):
    python -m scripts.seed_legislacao [--apenas cdc,lgpd] [--dry-run]
                                      [--com-embeddings] [--cache-dir DIR]

  --apenas          ingere só as siglas listadas (vírgula; case-insensitive)
  --dry-run         baixa e parseia, mostra artigos/chunks, NÃO grava no banco
  --com-embeddings  vetoriza inline (default: adia — o auto-reembed do
                    scheduler indexa os docs 'pendente' depois)
  --cache-dir       diretório com <sigla>.html — usa o arquivo local em vez de
                    baixar (reexecução offline / testes / rede bloqueada)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

# backend/ no sys.path quando rodado como script avulso.
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from bs4 import BeautifulSoup  # noqa: E402  (dep já usada por app/services/ingestors/planalto.py)

logger = logging.getLogger("ejc.seed_legislacao")

FONTE_SLUG = "legislacao_planalto"
DESCRICAO = "Legislação federal (lei seca) — texto compilado do Planalto, dividido por artigo"
CATEGORIA = "legislacao"          # a categoria que citation_check._existe_artigo consome
PREFIXO_CHAVE = "legislacao:planalto:"

MIN_TEXTO = 2000                  # página menor que isso não é um diploma — erro de download
MIN_ARTIGOS = 5                   # parser precisa achar artigos, senão a extração falhou

# ══════════════════════════════════════════════════════════════════════════
# Catálogo versionado — texto COMPILADO no Planalto (www.planalto.gov.br)
# ══════════════════════════════════════════════════════════════════════════
CATALOGO: list[dict] = [
    {"sigla": "cf88", "nome": "Constituição Federal de 1988", "area": "constitucional",
     "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm"},
    {"sigla": "cc", "nome": "Código Civil (Lei 10.406/2002)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    {"sigla": "cpc", "nome": "Código de Processo Civil (Lei 13.105/2015)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"},
    {"sigla": "clt", "nome": "Consolidação das Leis do Trabalho (Decreto-Lei 5.452/1943)", "area": "trabalhista",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm"},
    {"sigla": "cdc", "nome": "Código de Defesa do Consumidor (Lei 8.078/1990)", "area": "consumidor",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    {"sigla": "l9099", "nome": "Lei dos Juizados Especiais (Lei 9.099/1995)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"},
    {"sigla": "lgpd", "nome": "Lei Geral de Proteção de Dados Pessoais (Lei 13.709/2018)", "area": "digital",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"},
    {"sigla": "ctn", "nome": "Código Tributário Nacional (Lei 5.172/1966)", "area": "tributario",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"},
    {"sigla": "cp", "nome": "Código Penal (Decreto-Lei 2.848/1940)", "area": "penal",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm"},
    {"sigla": "cpp", "nome": "Código de Processo Penal (Decreto-Lei 3.689/1941)", "area": "processual_penal",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm"},
    # Bloco ambiental (skill agente-advocacia-ambiental / prática do escritório)
    {"sigla": "cflo", "nome": "Código Florestal (Lei 12.651/2012)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm"},
    {"sigla": "lca", "nome": "Lei de Crimes Ambientais (Lei 9.605/1998)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9605.htm"},
    {"sigla": "pnma", "nome": "Política Nacional do Meio Ambiente (Lei 6.938/1981)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l6938.htm"},
]


# ══════════════════════════════════════════════════════════════════════════
# Parser (funções puras — testáveis sem rede/DB)
# ══════════════════════════════════════════════════════════════════════════

# Anotação oficial de revogação dentro de trecho riscado — é a única parte do
# riscado que sobrevive (o teor revogado sai; a marcação "(Revogado ...)" fica).
_RE_REVOGADO = re.compile(r"\(\s*Revogad[oa][^)]*\)", re.IGNORECASE)

# Linhas de navegação/boilerplate do topo das páginas do Planalto (comparação
# por linha inteira, minúscula). Conservador: só o que é certamente navegação.
_BOILERPLATE = {
    "presidência da república",
    "casa civil",
    "secretaria-geral",
    "subchefia para assuntos jurídicos",
    "subchefia de assuntos jurídicos",
    "texto compilado",
    "texto compilado(vigência)",
    "(vigência)",
    "vigência",
    "mensagem de veto",
    "índice",
    "voltar ao início",
}
_RE_NAO_SUBSTITUI = re.compile(r"^este texto não substitui o publicado", re.IGNORECASE)

# Início de artigo em começo de linha: "Art. 1º", "Art. 5º-A", "Art. 10.",
# "Art. 1.022." (milhar com ponto). Grupos: número como grafado, ordinal, sufixo.
_RE_ART = re.compile(
    r"^Art\.\s*(\d{1,3}(?:\.\d{3})+|\d{1,4})\s*([ºo°])?\s*(-[A-Za-z]{1,3})?\s*[.\sº°]"
)


def extrair_texto_planalto(html: str) -> str:
    """HTML do Planalto → texto limpo VERBATIM, na ordem dos artigos.

    - Remove <script>/<style>.
    - Remove texto RISCADO (<strike>/<s>/<del> — teor revogado/alterado no
      compilado), preservando a anotação "(Revogado ...)" quando presente
      dentro do próprio riscado.
    - Remove linhas de navegação conhecidas; NÃO reescreve o texto legal.
    """
    from app.services.ingestion_service import normalizar

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(["strike", "s", "del"]):
        m = _RE_REVOGADO.search(tag.get_text(" ", strip=True))
        if m:
            tag.replace_with(m.group(0))
        else:
            tag.decompose()

    txt = soup.get_text("\n").replace("\xa0", " ")
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n[ \t]+", "\n", txt)

    linhas = []
    for ln in txt.split("\n"):
        chave = ln.strip().lower()
        if chave in _BOILERPLATE or _RE_NAO_SUBSTITUI.match(chave):
            continue
        linhas.append(ln)
    return normalizar("\n".join(linhas))


def _rotulo(m: re.Match) -> str:
    """Rótulo canônico do artigo ("Art. 6", "Art. 19-A", "Art. 1.022") —
    SEM ordinal, para casar com o ILIKE '%Art. N %' de _existe_artigo."""
    return f"Art. {m.group(1)}{(m.group(3) or '').upper()}"


def dividir_artigos(texto: str) -> list[tuple[str | None, str]]:
    """Divide o texto em blocos [(rotulo, bloco)] — rotulo=None para o
    preâmbulo/ementa (antes do Art. 1º) e trechos finais sem artigo.

    Cada bloco de artigo contém caput + parágrafos + incisos, verbatim, até o
    próximo artigo. Heurística anti-falso-positivo: um novo artigo só é aceito
    se o número progride (n > último), recomeça em 1 (ex.: ADCT na CF/88) ou é
    variante com sufixo do último (ex.: Art. 19-A após Art. 19).
    """
    blocos: list[tuple[str | None, str]] = []
    atual: list[str] = []
    rotulo: str | None = None
    ultimo = 0

    def fechar():
        corpo = "\n".join(atual).strip()
        if corpo:
            blocos.append((rotulo, corpo))

    for ln in texto.split("\n"):
        m = _RE_ART.match(ln.strip())
        if m:
            n = int(m.group(1).replace(".", ""))
            sufixo = bool(m.group(3))
            if n > ultimo or (n == ultimo and sufixo) or (n == 1 and ultimo > 1):
                fechar()
                atual = [ln]
                rotulo = _rotulo(m)
                ultimo = n
                continue
        atual.append(ln)
    fechar()
    return blocos


def montar_chunks(nome_lei: str, blocos: list[tuple[str | None, str]],
                  tamanho: int | None = None) -> list[str]:
    """Blocos por artigo → chunks do RAG, respeitando o limite do pipeline.

    - Agrupa artigos CONSECUTIVOS curtos até `tamanho` (CHUNK_TAMANHO).
    - Artigo maior que o limite é dividido (chunk_texto), cada parte reabrindo
      com o rótulo ("(continuação)" nas partes seguintes).
    - Todo chunk ABRE com o cabeçalho "Art. N [· Art. M ...] — <lei>", que
      enumera cada artigo contido — é isso que _existe_artigo encontra via
      ILIKE '%Art. N %', inclusive para "Art. 10." (grafia oficial com ponto).
    - O corpo permanece verbatim.
    """
    from app.services.ingestion_service import CHUNK_TAMANHO, chunk_texto

    tamanho = tamanho or CHUNK_TAMANHO
    chunks: list[str] = []
    grupo: list[tuple[str | None, str]] = []

    def flush():
        if not grupo:
            return
        rotulos = [r for r, _ in grupo if r]
        header = f"{' · '.join(rotulos)} — {nome_lei}" if rotulos else nome_lei
        corpo = "\n\n".join(t for _, t in grupo)
        chunks.append(f"{header}\n{corpo}")
        grupo.clear()

    for rot, corpo in blocos:
        if len(corpo) > tamanho:
            flush()
            partes = chunk_texto(corpo, tamanho=tamanho)
            for i, parte in enumerate(partes):
                pref = rot or nome_lei
                header = (f"{pref} — {nome_lei}" if i == 0 and rot
                          else f"{pref} (continuação) — {nome_lei}" if rot
                          else nome_lei)
                chunks.append(f"{header}\n{parte}")
            continue
        if grupo and sum(len(t) for _, t in grupo) + len(corpo) > tamanho:
            flush()
        grupo.append((rot, corpo))
    flush()
    return chunks


# ══════════════════════════════════════════════════════════════════════════
# Download + ingestão
# ══════════════════════════════════════════════════════════════════════════

async def obter_html(lei: dict, cache_dir: Path | None = None) -> str:
    """HTML da lei — do cache local (<sigla>.html) se existir, senão da rede."""
    if cache_dir:
        arq = Path(cache_dir) / f"{lei['sigla']}.html"
        if arq.exists():
            raw = arq.read_bytes()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
    from app.services.ingestion_service import fetch
    r = await fetch(lei["url"], timeout=60)
    # Planalto serve ISO-8859-1; httpx não tem apparent_encoding
    r.encoding = r.charset_encoding or "latin-1"
    return r.text


def preparar_lei(lei: dict, html: str) -> dict:
    """Parseia uma lei (puro). Retorna {texto, blocos, chunks, artigos}."""
    texto = extrair_texto_planalto(html)
    if len(texto) < MIN_TEXTO:
        raise ValueError(f"texto suspeito ({len(texto)} chars) — página errada/truncada?")
    blocos = dividir_artigos(texto)
    artigos = sum(1 for r, _ in blocos if r)
    if artigos < MIN_ARTIGOS:
        raise ValueError(f"apenas {artigos} artigos encontrados — parser não reconheceu a página")
    chunks = montar_chunks(lei["nome"], blocos)
    return {"texto": texto, "blocos": blocos, "chunks": chunks, "artigos": artigos}


async def seed_lei(db, lei: dict, *, embutir_vetores: bool = False,
                   cache_dir: Path | None = None) -> dict:
    """Baixa, parseia e ingere UMA lei pelo pipeline oficial (upsert)."""
    from app.services.ingestion_service import upsert_documento

    html = await obter_html(lei, cache_dir)
    prep = preparar_lei(lei, html)
    resultado = await upsert_documento(
        db,
        titulo=lei["nome"],
        categoria=CATEGORIA,
        conteudo=prep["texto"],
        chunks=prep["chunks"],
        chave_origem=f"{PREFIXO_CHAVE}{lei['sigla']}",
        fonte="planalto",
        extra={
            "sigla": lei["sigla"], "area": lei["area"],
            "fonte_url": lei["url"], "origem": "planalto",
            "artigos": prep["artigos"], "divisao": "por_artigo",
        },
        confianca="alta",              # fonte oficial — texto de lei compilado
        embutir_vetores=embutir_vetores,
    )
    return {"resultado": resultado, "artigos": prep["artigos"],
            "chunks": len(prep["chunks"]), "chars": len(prep["texto"])}


def _filtrar_catalogo(apenas: str | None) -> list[dict]:
    if not apenas:
        return CATALOGO
    siglas = {s.strip().lower() for s in apenas.split(",") if s.strip()}
    sel = [l for l in CATALOGO if l["sigla"] in siglas]
    desconhecidas = siglas - {l["sigla"] for l in sel}
    if desconhecidas:
        raise SystemExit(f"[seed-legislacao] siglas desconhecidas: {sorted(desconhecidas)} "
                         f"(válidas: {[l['sigla'] for l in CATALOGO]})")
    return sel


async def executar_seed_legislacao(
    db, *, apenas: str | None = None, embutir_vetores: bool = False,
    cache_dir: Path | None = None,
) -> dict:
    """Ingere o catálogo (idempotente). Falha de uma lei não aborta as demais."""
    from app.services.ingestion_service import marcar_execucao, registrar_fonte

    leis = _filtrar_catalogo(apenas)
    await registrar_fonte(db, FONTE_SLUG, DESCRICAO, categoria_rag=CATEGORIA)
    await db.commit()

    sucessos: dict[str, dict] = {}
    falhas: dict[str, str] = {}
    for lei in leis:
        try:
            r = await seed_lei(db, lei, embutir_vetores=embutir_vetores,
                               cache_dir=cache_dir)
            await db.commit()   # commit por lei — uma lei grande não trava as demais
            sucessos[lei["sigla"]] = r
            print(f"[seed-legislacao] {lei['sigla']:6s} {r['resultado']:10s} "
                  f"artigos={r['artigos']:5d} chunks={r['chunks']:5d} chars={r['chars']}")
        except Exception as e:
            await db.rollback()
            falhas[lei["sigla"]] = f"{type(e).__name__}: {e}"
            print(f"[seed-legislacao] {lei['sigla']:6s} FALHA — {falhas[lei['sigla']]}",
                  file=sys.stderr)

    novos = sum(1 for r in sucessos.values() if r["resultado"] in ("novo", "atualizado"))
    status = "sucesso" if not falhas else ("parcial" if sucessos else "erro")
    await marcar_execucao(
        db, FONTE_SLUG, status=status, novos=novos, total=len(leis),
        erro="; ".join(f"{s}: {e}" for s, e in falhas.items()) or None,
    )
    await db.commit()
    return {"sucessos": sucessos, "falhas": falhas, "total": len(leis)}


async def dry_run(apenas: str | None, cache_dir: Path | None) -> dict:
    """Baixa e parseia sem tocar no banco — relatório de artigos/chunks."""
    sucessos: dict[str, dict] = {}
    falhas: dict[str, str] = {}
    for lei in _filtrar_catalogo(apenas):
        try:
            prep = preparar_lei(lei, await obter_html(lei, cache_dir))
            sucessos[lei["sigla"]] = prep
            print(f"[seed-legislacao] {lei['sigla']:6s} DRY-RUN    "
                  f"artigos={prep['artigos']:5d} chunks={len(prep['chunks']):5d} "
                  f"chars={len(prep['texto'])}")
        except Exception as e:
            falhas[lei["sigla"]] = f"{type(e).__name__}: {e}"
            print(f"[seed-legislacao] {lei['sigla']:6s} FALHA — {falhas[lei['sigla']]}",
                  file=sys.stderr)
    return {"sucessos": sucessos, "falhas": falhas}


async def main(args) -> int:
    cache = Path(args.cache_dir) if args.cache_dir else None
    if args.dry_run:
        rel = await dry_run(args.apenas, cache)
    else:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rel = await executar_seed_legislacao(
                db, apenas=args.apenas,
                embutir_vetores=args.com_embeddings, cache_dir=cache,
            )
    ok, falhas = len(rel["sucessos"]), rel["falhas"]
    print(f"[seed-legislacao] concluído — {ok} ok / {len(falhas)} falha(s)"
          + (f": {sorted(falhas)}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed de legislação federal (Planalto, por artigo, idempotente)")
    parser.add_argument("--apenas", help="siglas separadas por vírgula (ex.: cdc,lgpd)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parseia e reporta sem gravar no banco")
    parser.add_argument("--com-embeddings", action="store_true",
                        help="vetoriza inline (default: adia p/ auto-reembed do scheduler)")
    parser.add_argument("--cache-dir", help="diretório com <sigla>.html locais (offline)")
    sys.exit(asyncio.run(main(parser.parse_args())))
