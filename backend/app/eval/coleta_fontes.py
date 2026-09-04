"""Coleta verificável de fontes oficiais para a curadoria do gold set (#1201).

O que este módulo faz e o que deliberadamente **não** faz.

Faz: busca o documento na fonte oficial, fixa o `sha256` dos bytes exatos
recebidos, extrai o texto literal dos artigos pedidos e registra a data da
consulta. É a parte mecânica da curadoria — a que erra quando é feita à mão
(artigo transcrito de memória, URL que mudou, versão que não se reconstrói).

Não faz: gabarito. Não decide tese, não escolhe citação, não preenche
`vigencia_conferida_em` e não assina `curador`. `HUMAN_GOLD_SET_BACKLOG.md` é
explícito — *"a IA pode ajudar a formatar um caso já curado, mas não pode criar
o fato jurídico nem atestar a correção do gabarito"*. Uma ferramenta que
preenchesse a atestação deixaria o gate verde sem que ninguém tivesse conferido
nada, que é exatamente o risco que o gate existe para cobrir.

Ponto de atenção sobre vigência: o Planalto (texto compilado) está inacessível
de alguns ambientes. `camara.leg.br` e `senado.leg.br` são oficiais e
alcançáveis, mas boa parte do acervo da Câmara é **publicação original**, que
prova o texto como publicado e não o texto em vigor hoje. Por isso cada fonte
carrega `natureza`, e o relatório separa o que serve de prova de vigência do
que não serve.

Uso:

    python -m app.eval.coleta_fontes                    # coleta o registro inteiro
    python -m app.eval.coleta_fontes --apelido cdc      # só uma fonte
    python -m app.eval.coleta_fontes --listar           # o que está registrado
"""

from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

BASE = Path(__file__).resolve().parent
REGISTRO = BASE / "fontes_registro.json"
SAIDA = BASE / "fontes_oficiais.json"

# Mesma política que `gold_governance._host_oficial` aceita — sufixo OU host
# exato. Coletar de domínio que o validador vai recusar depois é trabalho
# perdido, então a recusa acontece aqui, na coleta.
SUFIXOS_OFICIAIS = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
HOSTS_OFICIAIS = {
    "planalto.gov.br",
    "www.planalto.gov.br",
    "oab.org.br",
    "www.oab.org.br",
}

TIMEOUT_PADRAO = 30
UA = "EJC-curadoria-gold-set/1.0 (+https://github.com/s2corporativo/ejc)"


class ErroDeColeta(RuntimeError):
    """Falha que impede registrar a fonte com integridade."""


@dataclass
class Fonte:
    apelido: str
    titulo: str
    url: str
    artigos: list[str] = field(default_factory=list)
    observacao: str = ""
    verificar_texto: list[str] = field(default_factory=list)


def _host_oficial(url: str) -> bool:
    from urllib.parse import urlparse

    partes = urlparse(url)
    if partes.scheme != "https":
        return False
    host = (partes.hostname or "").lower()
    if host in HOSTS_OFICIAIS:
        return True
    return any(host == s.lstrip(".") or host.endswith(s) for s in SUFIXOS_OFICIAIS)


def baixar(url: str, *, timeout: int = TIMEOUT_PADRAO) -> bytes:
    """Baixa e exige que o host FINAL, após redirecionamentos, siga oficial."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL validada acima
        final = resp.geturl()
        if final != url and not _host_oficial(final):
            raise ErroDeColeta(
                f"redirecionamento para fora de domínio oficial: {url} -> {final}"
            )
        return resp.read()


def html_para_texto(bruto: bytes) -> str:
    """HTML → texto preservando limites de blocos relevantes.

    Cabeçalhos de artigos só contam no início de linha para não confundir uma
    remissão interna ("nos termos do Art. 20") com o dispositivo seguinte.
    Portanto tags de bloco precisam virar quebras de linha antes da remoção da
    marcação. Isso cobre páginas oficiais que estruturam o texto com `div`,
    listas ou tabelas em vez de apenas `p`/`br`.
    """
    txt = bruto.decode("utf-8", errors="replace")
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", txt)
    txt = re.sub(r"(?i)<br\s*/?>", "\n", txt)
    txt = re.sub(
        r"(?i)</?(?:p|div|li|tr|td|th|h[1-6]|section|article|blockquote|pre)"
        r"(?:\s[^>]*)?>",
        "\n",
        txt,
    )
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    txt = txt.replace("\xa0", " ")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def _normalizar_id_artigo(bruto: str) -> str:
    """`1.022` e `1022` são o mesmo artigo; `170-A` não é `170`."""
    ident = bruto.strip().upper().replace(".", "").replace(" ", "")
    ident = re.sub(r"[ºª°]|(?<=\d)O(?=-)", "", ident)
    return re.sub(r"[-–—]+", "-", ident)


def _marcadores_de_artigo(texto: str) -> list[tuple[int, str]]:
    """Posições de todo cabeçalho `Art. N`, com identificador completo."""
    achados = []
    padrao = r"(?m)^\s*Art\.?\s*(\d[\d.]*)\s*(?:[ºªo°]\s*)?(-\s*[A-Za-z])?"
    for m in re.finditer(padrao, texto):
        ident = m.group(1) + (m.group(2) or "")
        achados.append((m.start(), _normalizar_id_artigo(ident)))
    return achados


def extrair_artigos(texto: str, numeros: Iterable[str]) -> dict[str, str]:
    """Texto literal de cada artigo pedido, do marcador até o artigo seguinte."""
    marcadores = _marcadores_de_artigo(texto)
    saida: dict[str, str] = {}
    rotulo = {_normalizar_id_artigo(str(x)): str(x).strip() for x in numeros}
    for numero in numeros:
        alvo = _normalizar_id_artigo(str(numero))
        for i, (pos, num) in enumerate(marcadores):
            if num != alvo:
                continue
            fim = marcadores[i + 1][0] if i + 1 < len(marcadores) else len(texto)
            trecho = texto[pos:fim].strip()
            if len(trecho) < 40 and saida.get(rotulo.get(alvo, alvo)):
                continue
            saida[rotulo.get(alvo, alvo)] = trecho
            if len(trecho) >= 40:
                break
    return saida


def natureza_do_documento(url: str, texto: str) -> str:
    """Distingue o que prova vigência do que só prova o texto publicado."""
    alvo = url.lower()
    if "publicacaooriginal" in alvo or "publicacao-original" in alvo:
        return "publicacao_original"
    if "compilado" in alvo or "consolidado" in alvo:
        return "texto_compilado"
    return "indeterminada"


def _linha_titulo_identificada(texto: str, marcadores: Iterable[str]) -> str | None:
    """Confirma a identidade na linha estrutural que DECLARA o ato.

    Não basta número/data aparecerem nos primeiros caracteres: uma lei
    alteradora normalmente cita a norma-alvo na ementa. O primeiro marcador do
    registro (`LEI N`, `DECRETO-LEI N` etc.) precisa iniciar a própria linha e
    todos os demais marcadores precisam coexistir nessa mesma linha-título.
    Assim uma ementa "Altera a Lei nº X..." não pode se passar pela Lei X.
    """
    esperados = [
        re.sub(r"\s+", " ", str(m).strip()).casefold()
        for m in marcadores
        if str(m).strip()
    ]
    if not esperados:
        return None
    primeiro = esperados[0]
    linhas = [
        re.sub(r"\s+", " ", linha).strip()
        for linha in texto.splitlines()
        if linha.strip()
    ]
    # O título oficial aparece no início do documento útil. Limitar a janela de
    # linhas impede que uma citação tardia seja promovida a identidade.
    for linha in linhas[:40]:
        norm = linha.casefold()
        if not norm.startswith(primeiro):
            continue
        if all(marcador in norm for marcador in esperados):
            return linha
    return None


def coletar_fonte(
    fonte: Fonte,
    *,
    hoje: date | None = None,
    baixador: Callable[[str], bytes] = baixar,
) -> dict:
    if not _host_oficial(fonte.url):
        raise ErroDeColeta(
            f"{fonte.apelido}: {fonte.url} não é HTTPS em domínio oficial "
            f"({', '.join(SUFIXOS_OFICIAIS)}) — o validador do gold set recusaria."
        )
    bruto = baixador(fonte.url)
    if not bruto:
        raise ErroDeColeta(f"{fonte.apelido}: resposta vazia.")

    texto = html_para_texto(bruto)
    if fonte.verificar_texto:
        linha_titulo = _linha_titulo_identificada(texto, fonte.verificar_texto)
        if linha_titulo is None:
            raise ErroDeColeta(
                f"{fonte.apelido}: o documento em {fonte.url} não contém uma "
                "linha-título compatível com todos os marcadores de identidade "
                f"{fonte.verificar_texto!r}. Pode ser outro ato que apenas cita "
                "a norma-alvo, ou a página mudou. Confira a URL antes de registrar."
            )

    artigos = extrair_artigos(texto, fonte.artigos)
    faltando = [a for a in fonte.artigos if a not in artigos]
    natureza = natureza_do_documento(fonte.url, texto)

    return {
        "apelido": fonte.apelido,
        "titulo": fonte.titulo,
        "url": fonte.url,
        "consultada_em": (hoje or date.today()).isoformat(),
        "hash_sha256": hashlib.sha256(bruto).hexdigest(),
        "bytes": len(bruto),
        "natureza": natureza,
        "prova_vigencia": natureza == "texto_compilado",
        "artigos": artigos,
        "artigos_nao_encontrados": faltando,
        "observacao": fonte.observacao,
        "verificado_contem": list(fonte.verificar_texto),
        "vigencia_conferida_em": None,
        "conferida_por": None,
    }


def carregar_registro(caminho: Path = REGISTRO) -> list[Fonte]:
    """Carrega o registro, recusando entrada sem marcador de identidade."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("fontes"), list):
        raise ErroDeColeta("registro de fontes inválido: `fontes` deve ser lista")
    sem_marcador = [
        d.get("apelido", "?")
        for d in dados["fontes"]
        if not [str(t) for t in d.get("verificar_texto", []) if str(t).strip()]
    ]
    if sem_marcador:
        raise ErroDeColeta(
            f"fontes sem `verificar_texto` não vazio: {', '.join(sem_marcador)}. "
            "Declare trechos que identifiquem a norma (tipo do ato, número e data)."
        )
    return [
        Fonte(
            apelido=d["apelido"],
            titulo=d["titulo"],
            url=d["url"],
            artigos=[str(a) for a in d.get("artigos", [])],
            observacao=d.get("observacao", ""),
            verificar_texto=[str(t) for t in d.get("verificar_texto", [])],
        )
        for d in dados["fontes"]
    ]


def _carregar_saida_incremental(caminho: Path) -> list[dict]:
    """Lê a saída existente sem permitir perda silenciosa no modo seletivo."""
    try:
        payload = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ErroDeColeta(
            f"saída existente inválida/ilegível em {caminho}: {exc}"
        ) from exc
    fontes = payload.get("fontes") if isinstance(payload, dict) else None
    if not isinstance(fontes, list) or any(
        not isinstance(item, dict) or not str(item.get("apelido") or "").strip()
        for item in fontes
    ):
        raise ErroDeColeta(
            f"saída existente inválida em {caminho}: `fontes` deve ser lista de objetos com apelido"
        )
    return fontes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--registro", type=Path, default=REGISTRO)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--apelido", action="append", help="coletar só estas fontes")
    ap.add_argument("--listar", action="store_true", help="listar o registro e sair")
    args = ap.parse_args(argv)

    fontes = carregar_registro(args.registro)
    if args.apelido:
        alvo = set(args.apelido)
        fontes = [f for f in fontes if f.apelido in alvo]
        if not fontes:
            print(f"nenhuma fonte com apelido em {sorted(alvo)}", file=sys.stderr)
            return 2

    if args.listar:
        for f in fontes:
            print(f"{f.apelido:12s} arts={','.join(f.artigos) or '-':20s} {f.url}")
        return 0

    coletadas, falhas = [], []
    for f in fontes:
        try:
            registro = coletar_fonte(f)
        except Exception as exc:  # rede, HTTP, domínio recusado
            falhas.append((f.apelido, str(exc)))
            print(f"FALHA {f.apelido}: {exc}", file=sys.stderr)
            continue
        coletadas.append(registro)
        marca = "vigência" if registro["prova_vigencia"] else "SÓ TEXTO PUBLICADO"
        print(
            f"OK    {f.apelido:12s} {registro['hash_sha256'][:12]}… "
            f"arts={len(registro['artigos'])}/{len(f.artigos)} [{marca}]"
        )
        if registro["artigos_nao_encontrados"]:
            print(
                "      artigos não localizados: "
                + ", ".join(registro["artigos_nao_encontrados"])
            )

    if falhas:
        print(
            f"\n{len(falhas)} fonte(s) falharam: {', '.join(ap for ap, _ in falhas)}.\n"
            f"{args.saida} NÃO foi alterado — registro parcial seria lido como completo.\n"
            "Corrija a causa e rode de novo, ou use --apelido para coletar só o que falta.",
            file=sys.stderr,
        )
        return 1

    # Coleta completa SEM fontes também precisa publicar o estado vazio. Senão
    # uma retirada total do registro deixaria fontes antigas sobrevivendo na
    # saída com exit code 0.
    if coletadas or not args.apelido:
        existentes: list[dict] = []
        if args.apelido and args.saida.exists():
            try:
                existentes = _carregar_saida_incremental(args.saida)
            except ErroDeColeta as exc:
                print(
                    f"FALHA: {exc}. {args.saida} NÃO foi alterado.",
                    file=sys.stderr,
                )
                return 1

        por_apelido = {f["apelido"]: f for f in existentes}
        por_apelido.update({f["apelido"]: f for f in coletadas})
        args.saida.write_text(
            json.dumps(
                {
                    "gerado_em": date.today().isoformat(),
                    "fontes": list(por_apelido.values()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"\n{len(coletadas)} fonte(s) coletadas; "
            f"{len(por_apelido)} no total em {args.saida}"
        )

    sem_vigencia = [c["apelido"] for c in coletadas if not c["prova_vigencia"]]
    if sem_vigencia:
        print(
            "\nATENÇÃO: estas fontes não provam vigência atual, só o texto publicado — "
            f"{', '.join(sem_vigencia)}.\nConfira em texto compilado antes de preencher "
            "`vigencia_conferida_em` no caso do gold set."
        )
    print(
        "\nEste arquivo NÃO é gold set. Nenhum caso foi curado: gabarito, vigência e "
        "assinatura de curador são atos humanos (ver HUMAN_GOLD_SET_BACKLOG.md)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
