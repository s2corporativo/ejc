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

# Mesma lista de sufixos que `gold_governance._host_oficial` aceita. Coletar de
# domínio que o validador vai recusar depois é trabalho perdido, então a recusa
# acontece aqui, na coleta.
SUFIXOS_OFICIAIS = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")

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


def _host_oficial(url: str) -> bool:
    from urllib.parse import urlparse

    partes = urlparse(url)
    if partes.scheme != "https":
        return False
    host = (partes.hostname or "").lower()
    return any(host == s.lstrip(".") or host.endswith(s) for s in SUFIXOS_OFICIAIS)


def baixar(url: str, *, timeout: int = TIMEOUT_PADRAO) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL validada acima
        return resp.read()


def html_para_texto(bruto: bytes) -> str:
    """HTML → texto corrido, preservando o que importa para transcrever artigo."""
    txt = bruto.decode("utf-8", errors="replace")
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", txt)
    txt = re.sub(r"(?i)<br\s*/?>", "\n", txt)
    txt = re.sub(r"(?i)</p>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    txt = txt.replace("\xa0", " ")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    return txt.strip()


def _marcadores_de_artigo(texto: str) -> list[tuple[int, str]]:
    """Posições de todo 'Art. N' do texto, na ordem em que aparecem."""
    achados = []
    for m in re.finditer(r"\bArt\.?\s*(\d+)(?:[-\s]*[ºo°])?", texto):
        achados.append((m.start(), m.group(1)))
    return achados


def extrair_artigos(texto: str, numeros: Iterable[str]) -> dict[str, str]:
    """Texto literal de cada artigo pedido, do marcador até o artigo seguinte.

    Casa o número exato: pedir o 14 não pode devolver o 140. O corte é no
    próximo marcador de artigo, sem tentar entender parágrafo ou inciso — o
    objetivo é transcrição fiel para conferência humana, não parsing jurídico.
    """
    marcadores = _marcadores_de_artigo(texto)
    saida: dict[str, str] = {}
    for numero in numeros:
        alvo = str(numero).strip()
        for i, (pos, num) in enumerate(marcadores):
            if num != alvo:
                continue
            fim = marcadores[i + 1][0] if i + 1 < len(marcadores) else len(texto)
            trecho = texto[pos:fim].strip()
            # Um "Art. 14" citado de passagem no meio de outro dispositivo
            # produziria um trecho curto e sem corpo; o primeiro casamento que
            # tem corpo é o dispositivo em si.
            if len(trecho) < 40 and saida.get(alvo):
                continue
            saida[alvo] = trecho
            if len(trecho) >= 40:
                break
    return saida


def natureza_do_documento(url: str, texto: str) -> str:
    """Distingue o que prova vigência do que só prova o texto publicado.

    Decide pela URL, não pelo corpo da página. A primeira versão desta função
    varria os primeiros 4 mil caracteres do texto e classificou como
    `texto_compilado` duas páginas de **publicação original** do portal da
    Câmara: a palavra "compilado" aparece no menu de navegação do portal, não
    no documento. O efeito seria `prova_vigencia=true` numa fonte que não prova
    vigência nenhuma — o oposto do que este campo existe para fazer.

    Que o risco é concreto, o próprio acervo mostra: a publicação original do
    Código Penal traz, no art. 155, pena de multa "de quinhentos mil réis a dez
    contos de réis", substituída pela reforma de 1984. Texto autêntico, fonte
    oficial, e ainda assim gabarito errado.

    Por isso a classificação falha fechada: sem sinal inequívoco na URL, o
    retorno é `indeterminada` e `prova_vigencia` fica falso.
    """
    alvo = url.lower()
    if "publicacaooriginal" in alvo or "publicacao-original" in alvo:
        return "publicacao_original"
    if "compilado" in alvo or "consolidado" in alvo:
        return "texto_compilado"
    return "indeterminada"


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
        # Preenchimento humano. A ferramenta não atesta vigência nem assina
        # curadoria — ver docstring do módulo.
        "vigencia_conferida_em": None,
        "conferida_por": None,
    }


def carregar_registro(caminho: Path = REGISTRO) -> list[Fonte]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [
        Fonte(
            apelido=d["apelido"],
            titulo=d["titulo"],
            url=d["url"],
            artigos=[str(a) for a in d.get("artigos", [])],
            observacao=d.get("observacao", ""),
        )
        for d in dados["fontes"]
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
            print(f"      artigos não localizados: {', '.join(registro['artigos_nao_encontrados'])}")

    if coletadas:
        args.saida.write_text(
            json.dumps(
                {"gerado_em": date.today().isoformat(), "fontes": coletadas},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n{len(coletadas)} fonte(s) em {args.saida}")

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
    return 1 if falhas and not coletadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
