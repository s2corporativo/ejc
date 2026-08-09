# ── app/services/ingestors/planalto.py ───────────────────────────────────────
# Ingestor ÚNICO de legislação federal (lei seca) do Planalto — escritor único
# do corpus categoria='legislacao' com chaves `planalto:<slug>` (as MESMAS já
# existentes em produção; mudar a chave duplicaria o corpus).
#
# Consolida os dois importadores antigos (este módulo + scripts/seed_legislacao):
#   • catálogo ampliado (códigos-núcleo + juizados/LGPD + bloco ambiental);
#   • extração VERBATIM (lei não se resume): remove <script>/<style>, texto
#     RISCADO do compilado (preservando a anotação "(Revogado ...)") e linhas
#     de navegação conhecidas;
#   • chunking POR ARTIGO: cada chunk abre com o cabeçalho
#     "Art. N [· Art. M ...] — <lei>", compatível com o lookup ILIKE de
#     citation_check._existe_artigo (inclusive grafia oficial "Art. 10.");
#   • upsert idempotente pelo pipeline oficial (dedup por chave_origem, hash
#     sobre `conteudo`, versionamento migration 068, chunks pré-computados);
#   • vigência lida da fonte gravada em `extra.legal_status` (Issue #636): sem
#     isso o documento entra como 'vigencia_nao_verificada' na governança e o
#     gate de situação jurídica do RAG o exclui. Ver `situacao_juridica` — a
#     marcação vem do PREÂMBULO do texto compilado e o fragmento vem VAZIO
#     quando a página não permite afirmar nada. Como o upsert mescla `extra`
#     mesmo no atalho "inalterado", UMA execução do job/seed já regrava a
#     vigência do acervo existente (sem nova versão) — exceto onde um curador
#     já decidiu, que `upsert_documento` preserva.
#
# Migração de chunking (deploy único): docs vigentes gravados pelo formato
# antigo (extra sem divisao='por_artigo') têm o MESMO conteúdo (mesmo hash),
# então o atalho "inalterado" do upsert os deixaria para sempre com chunks
# genéricos. `_rechunk_pendente` detecta esse caso e passa
# `forcar_nova_versao=True` ao upsert → UMA nova versão re-chunkada por
# artigo; a partir daí extra.divisao == 'por_artigo' e as execuções seguintes
# voltam a "inalterado" (idempotente).
#
# Consumidores: scheduler (job semanal `ing_planalto`, dom 3h) chama
# `ingerir(db)`; scripts/seed_legislacao.py é um wrapper CLI fino sobre
# `ingerir_diploma` (--apenas/--dry-run/--cache-dir/--com-embeddings).
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ejc.ingestao.planalto")

CATEGORIA = "legislacao"          # a categoria que citation_check._existe_artigo consome
PREFIXO_CHAVE = "planalto:"       # chave legada de produção — NÃO mudar

MIN_TEXTO = 2000                  # página menor que isso não é um diploma — erro de download
MIN_ARTIGOS = 5                   # parser precisa achar artigos, senão a extração falhou

# ══════════════════════════════════════════════════════════════════════════
# Catálogo versionado — texto COMPILADO no Planalto (www.planalto.gov.br)
# (slug curto p/ chave_origem · título canônico · área · URL compilada)
# ══════════════════════════════════════════════════════════════════════════
CATALOGO: list[dict] = [
    {"slug": "cf88", "titulo": "Constituição Federal de 1988", "area": "constitucional",
     "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm"},
    {"slug": "cc", "titulo": "Código Civil (Lei 10.406/2002)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm"},
    {"slug": "cpc", "titulo": "Código de Processo Civil (Lei 13.105/2015)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm"},
    {"slug": "clt", "titulo": "Consolidação das Leis do Trabalho (DL 5.452/1943)", "area": "trabalhista",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm"},
    {"slug": "cdc", "titulo": "Código de Defesa do Consumidor (Lei 8.078/1990)", "area": "consumidor",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"},
    {"slug": "cp", "titulo": "Código Penal (DL 2.848/1940)", "area": "penal",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm"},
    {"slug": "cpp", "titulo": "Código de Processo Penal (DL 3.689/1941)", "area": "processual_penal",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm"},
    {"slug": "eca", "titulo": "Estatuto da Criança e do Adolescente (Lei 8.069/1990)", "area": "infancia_juventude",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8069compilado.htm"},
    {"slug": "ctn", "titulo": "Código Tributário Nacional (Lei 5.172/1966)", "area": "tributario",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm"},
    {"slug": "l9099", "titulo": "Lei dos Juizados Especiais (Lei 9.099/1995)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9099.htm"},
    {"slug": "lgpd", "titulo": "Lei Geral de Proteção de Dados Pessoais (Lei 13.709/2018)", "area": "digital",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"},
    # Bloco ambiental (skill agente-advocacia-ambiental / prática do escritório)
    {"slug": "cflo", "titulo": "Código Florestal (Lei 12.651/2012)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm"},
    {"slug": "lca", "titulo": "Lei de Crimes Ambientais (Lei 9.605/1998)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9605.htm"},
    {"slug": "pnma", "titulo": "Política Nacional do Meio Ambiente (Lei 6.938/1981)", "area": "ambiental",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l6938.htm"},
    # ── Ampliação de volume 2026 — diplomas federais core das áreas do escritório
    # (todas URLs COMPILADAS/oficiais do planalto.gov.br, mesmos padrões acima).
    # NOTA OPERACIONAL: estas URLs seguem os padrões já comprovados das entradas
    # acima, mas NÃO puderam ser verificadas ao vivo no ambiente de dev (o proxy
    # de egresso bloqueia planalto.gov.br). Após o deploy, confira em
    # /ia-governanca/fontes que cada slug ingeriu (status ok, não "erro"); uma URL
    # incorreta falha graciosamente (nunca fabrica texto) — basta corrigi-la aqui.
    # Bloco processual/administrativo
    {"slug": "l14133", "titulo": "Lei de Licitações e Contratos Administrativos (Lei 14.133/2021)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"},
    {"slug": "l8429", "titulo": "Lei de Improbidade Administrativa (Lei 8.429/1992)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8429.htm"},
    {"slug": "l12846", "titulo": "Lei Anticorrupção (Lei 12.846/2013)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"},
    {"slug": "l12016", "titulo": "Lei do Mandado de Segurança (Lei 12.016/2009)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2009/lei/l12016.htm"},
    # Bloco cível/família
    {"slug": "lindb", "titulo": "Lei de Introdução às Normas do Direito Brasileiro (DL 4.657/1942)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del4657compilado.htm"},
    {"slug": "l8245", "titulo": "Lei de Locações / Inquilinato (Lei 8.245/1991)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8245.htm"},
    {"slug": "l13146", "titulo": "Estatuto da Pessoa com Deficiência (Lei 13.146/2015)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm"},
    {"slug": "l5478", "titulo": "Lei de Alimentos (Lei 5.478/1968)", "area": "familia",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l5478.htm"},
    # Bloco penal
    {"slug": "maria_penha", "titulo": "Lei Maria da Penha (Lei 11.340/2006)", "area": "penal",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm"},
    {"slug": "l11343", "titulo": "Lei de Drogas (Lei 11.343/2006)", "area": "penal",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11343.htm"},
    {"slug": "lep", "titulo": "Lei de Execução Penal (Lei 7.210/1984)", "area": "penal",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l7210.htm"},
    # Bloco empresarial/previdenciário
    {"slug": "l11101", "titulo": "Lei de Recuperação Judicial e Falências (Lei 11.101/2005)", "area": "empresarial",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2005/lei/l11101.htm"},
    {"slug": "lcp123", "titulo": "Estatuto Nacional da ME e EPP / Simples Nacional (LC 123/2006)", "area": "empresarial",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm"},
    {"slug": "l8213", "titulo": "Planos de Benefícios da Previdência Social (Lei 8.213/1991)", "area": "previdenciario",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8213cons.htm"},
    # Bloco advocacia/trânsito
    {"slug": "l8906", "titulo": "Estatuto da Advocacia e da OAB (Lei 8.906/1994)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8906.htm"},
    {"slug": "ctb", "titulo": "Código de Trânsito Brasileiro (Lei 9.503/1997)", "area": "transito",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9503compilado.htm"},
    # ── Ampliação 2026-07 — federação de fontes (complementa a busca LexML de
    # legislação estadual/municipal com mais lei seca federal core das áreas do
    # escritório). MESMA NOTA OPERACIONAL do bloco acima: URLs seguem os padrões
    # comprovados do planalto.gov.br mas NÃO foram verificadas ao vivo aqui (o
    # proxy bloqueia planalto.gov.br) — conferir em /ia-governanca/fontes após
    # o deploy (status ok, não "erro"); URL incorreta falha graciosamente.
    # Servidor público federal (l8112cons.htm — mesmo padrão "cons" de l8213cons).
    {"slug": "l8112", "titulo": "Regime Jurídico dos Servidores Públicos Federais (Lei 8.112/1990)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l8112cons.htm"},
    # Estatuto do Idoso (Lei 10.741/2003 — pasta /leis/2003/, grafia com ponto).
    {"slug": "idoso", "titulo": "Estatuto da Pessoa Idosa (Lei 10.741/2003)", "area": "civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741.htm"},
    # Lei da Ação Civil Pública / tutela coletiva (Lei 7.347/1985).
    {"slug": "lacp", "titulo": "Lei da Ação Civil Pública (Lei 7.347/1985)", "area": "processual_civil",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l7347orig.htm"},
    # Processo Administrativo no âmbito da Administração Federal (Lei 9.784/1999).
    {"slug": "l9784", "titulo": "Lei do Processo Administrativo Federal (Lei 9.784/1999)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9784.htm"},
    # Lei de Acesso à Informação (Lei 12.527/2011).
    {"slug": "lai", "titulo": "Lei de Acesso à Informação (Lei 12.527/2011)", "area": "administrativo",
     "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm"},
    # Controle concentrado de constitucionalidade — ADI/ADC (Lei 9.868/1999).
    {"slug": "l9868", "titulo": "Lei da ADI e ADC (Lei 9.868/1999)", "area": "constitucional",
     "url": "https://www.planalto.gov.br/ccivil_03/leis/l9868.htm"},
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


# Revogação do DIPLOMA INTEIRO, como o Planalto a publica no cabeçalho/ementa
# do texto compilado: "(Revogada pela Lei nº 14.133, de 2021)", "(Revogado pelo
# Decreto nº ...)", "Revogada a partir de ...", "Vigência encerrada", e a
# anotação SOLTA "(Revogada)" — que no preâmbulo só pode ser do próprio diploma.
# É a forma PASSIVA — "Revoga a Lei nº X" (a norma que revoga OUTRA) não casa,
# porque exige o particípio seguido de agente/termo inicial ou de parêntese.
_RE_DIPLOMA_REVOGADO = re.compile(
    r"(?:revogad[oa]s?\s+(?:integralmente\s+|expressamente\s+|tacitamente\s+|"
    r"parcialmente\s+)?(?:pel[ao]s?\b|a\s+partir\b|em\s+\d)"
    r"|\(\s*revogad[oa]s?\s*\)"
    r"|vig[êe]ncia\s+encerrada)",
    re.IGNORECASE,
)

# Tamanho mínimo para aceitar um bloco como PREÂMBULO de fato. O preâmbulo de
# um diploma do Planalto traz epígrafe + ementa + fórmula de promulgação, muito
# acima disso; o piso existe só para rejeitar bloco vazio/residual — sobre o
# qual a busca por marcação de revogação não significaria nada.
MIN_PREAMBULO = 80


def _preambulo(blocos: list[tuple[str | None, str]]) -> str | None:
    """Preâmbulo IDENTIFICÁVEL, ou None quando a página não expõe um.

    `dividir_artigos` usa rotulo=None para o preâmbulo E para trechos finais sem
    artigo (assinaturas, anexos). Só o PRIMEIRO bloco pode ser o preâmbulo: se a
    página começa direto no Art. 1º, o primeiro rotulo=None é um bloco final e
    lê-lo como cabeçalho seria procurar a marcação no lugar errado.
    """
    if not blocos or blocos[0][0] is not None:
        return None
    corpo = blocos[0][1].strip()
    return corpo if len(corpo) >= MIN_PREAMBULO else None


def situacao_juridica(blocos: list[tuple[str | None, str]]) -> dict:
    """Fragmento de `extra` com a vigência que a FONTE permite afirmar
    (vocabulário de knowledge_governance.LEGAL_STATUS_VALUES). Devolve `{}`
    quando não permite afirmar nada — e aí a chave é OMITIDA, para a governança
    marcar 'vigencia_nao_verificada' e o gate do RAG excluir o documento até que
    alguém confira. FAIL-CLOSED: o erro de detecção aperta, nunca afrouxa.

    O que o Planalto entrega: as URLs do CATALOGO apontam para o texto
    COMPILADO, que é a consolidação oficial da redação EM VIGOR, e o próprio
    Planalto anota a revogação do diploma inteiro no cabeçalho/ementa (antes do
    Art. 1º). Três desfechos:

      • marcação de revogação no PREÂMBULO → 'revogada'. É leitura POSITIVA da
        fonte, então carimba `legal_status_verificado_em`.
      • preâmbulo identificável SEM marcação → 'vigente'. Isto é INFERÊNCIA POR
        AUSÊNCIA, não declaração explícita: carimba `legal_status_inferido_em`,
        chave distinta que não afirma conferência. Quem audita consegue separar
        o que a fonte disse do que se concluiu do silêncio dela.
      • sem preâmbulo identificável (página sem cabeçalho, markup mudou,
        extração falhou) → `{}`. Antes este ramo devolvia 'vigente', ou seja,
        uma falha de detecção declarava vigência — era fail-OPEN e é o oposto do
        que lexml.py faz.

    O escopo é deliberadamente o preâmbulo: o corpo do compilado tem anotações
    "(Revogado ...)" de ARTIGOS individuais (preservadas por
    `extrair_texto_planalto`), e lê-las como revogação do diploma marcaria todo
    código como revogado.
    """
    preambulo = _preambulo(blocos)
    if preambulo is None:
        return {}
    base = {"legal_status_origem": "planalto:texto_compilado"}
    agora = datetime.now(timezone.utc).isoformat()
    if _RE_DIPLOMA_REVOGADO.search(preambulo):
        return {**base, "legal_status": "revogada", "legal_status_verificado_em": agora}
    return {**base, "legal_status": "vigente", "legal_status_inferido_em": agora}


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


def preparar_diploma(diploma: dict, html: str) -> dict:
    """Parseia um diploma (puro). Retorna {texto, blocos, chunks, artigos}."""
    texto = extrair_texto_planalto(html)
    if len(texto) < MIN_TEXTO:
        raise ValueError(f"texto suspeito ({len(texto)} chars) — página errada/truncada?")
    blocos = dividir_artigos(texto)
    artigos = sum(1 for r, _ in blocos if r)
    if artigos < MIN_ARTIGOS:
        raise ValueError(f"apenas {artigos} artigos encontrados — parser não reconheceu a página")
    chunks = montar_chunks(diploma["titulo"], blocos)
    return {"texto": texto, "blocos": blocos, "chunks": chunks, "artigos": artigos,
            "vigencia": situacao_juridica(blocos)}


# ══════════════════════════════════════════════════════════════════════════
# Download + ingestão
# ══════════════════════════════════════════════════════════════════════════

async def obter_html(diploma: dict, cache_dir: Path | None = None) -> str:
    """HTML do diploma — do cache local (<slug>.html) se existir, senão da rede."""
    if cache_dir:
        arq = Path(cache_dir) / f"{diploma['slug']}.html"
        if arq.exists():
            raw = arq.read_bytes()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")
    from app.services.ingestion_service import fetch
    r = await fetch(diploma["url"], timeout=60)
    # Planalto serve ISO-8859-1; httpx não tem apparent_encoding
    r.encoding = r.charset_encoding or "latin-1"
    return r.text


async def _rechunk_pendente(db: AsyncSession, chave_origem: str) -> bool:
    """True se a versão VIGENTE da chave foi gravada com o chunking antigo
    (genérico por tamanho — extra sem divisao='por_artigo'). Nesse caso o
    conteúdo pode ser idêntico (mesmo hash) e o atalho "inalterado" do upsert
    nunca re-chunkaria; forçamos UMA nova versão por-artigo (migração única)."""
    from app.models.rag import KnowledgeDoc

    # Seleciona (id, extra) — não só extra — para distinguir "sem doc vigente"
    # de "doc vigente com extra NULL" (este último PRECISA de re-chunk).
    linha = (await db.execute(
        select(KnowledgeDoc.id, KnowledgeDoc.extra).where(
            KnowledgeDoc.chave_origem == chave_origem,
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
        )
    )).one_or_none()
    if linha is None:                  # sem doc vigente → upsert normal ("novo")
        return False
    return (linha.extra or {}).get("divisao") != "por_artigo"


async def ingerir_diploma(
    db: AsyncSession, diploma: dict, *,
    embutir_vetores: bool = True, cache_dir: Path | None = None,
) -> dict:
    """Baixa, parseia e ingere UM diploma pelo pipeline oficial (upsert).

    Chave `planalto:<slug>` (a mesma de produção) — seed CLI e job semanal
    escrevem no MESMO documento; rodar ambos nunca duplica.
    """
    from app.services.ingestion_service import upsert_documento

    html = await obter_html(diploma, cache_dir)
    prep = preparar_diploma(diploma, html)
    chave = f"{PREFIXO_CHAVE}{diploma['slug']}"
    resultado = await upsert_documento(
        db,
        titulo=diploma["titulo"],
        categoria=CATEGORIA,
        conteudo=prep["texto"],
        chunks=prep["chunks"],
        chave_origem=chave,
        fonte=diploma["url"],
        extra={
            "slug": diploma["slug"], "area": diploma["area"],
            "fonte_url": diploma["url"], "origem": "planalto",
            "artigos": prep["artigos"], "divisao": "por_artigo",
            # Curadoria (governança RAG da main): fonte oficial nasce aprovada
            # e tipada — nunca entra em quarentena.
            "rag_status": "aprovado", "tipo_fonte": "legislacao_oficial",
            # Vigência lida da FONTE (Issue #636): sem isto o documento entra
            # como 'vigencia_nao_verificada' na governança e — com o gate de
            # situação jurídica — sai da recuperação. `*_origem` registra DE
            # ONDE veio a marcação, para auditoria/curadoria. O fragmento vem
            # VAZIO quando a página não permite afirmar nada; a chave então é
            # omitida, e o merge do upsert não apaga curadoria já registrada.
            **prep["vigencia"],
        },
        confianca="alta",              # fonte oficial — texto de lei compilado
        embutir_vetores=embutir_vetores,
        forcar_nova_versao=await _rechunk_pendente(db, chave),
    )
    return {"resultado": resultado, "artigos": prep["artigos"],
            "chunks": len(prep["chunks"]), "chars": len(prep["texto"])}


async def ingerir(db: AsyncSession, cache_dir: Path | None = None) -> tuple[int, int]:
    """Ingere/atualiza todo o catálogo no RAG. Retorna (novos, total).

    Entrypoint do scheduler (job semanal `ing_planalto`). Falha de um diploma
    não aborta os demais; commit incremental por diploma.
    """
    novos = total = 0
    for diploma in CATALOGO:
        total += 1
        try:
            r = await ingerir_diploma(db, diploma, cache_dir=cache_dir)
            if r["resultado"] in ("novo", "atualizado"):
                novos += 1
            # commit incremental: um diploma grande não bloqueia os demais
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"Planalto {diploma['slug']}: {type(e).__name__}: {e}")
    return novos, total
