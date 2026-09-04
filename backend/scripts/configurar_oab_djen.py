#!/usr/bin/env python
# ── scripts/configurar_oab_djen.py ───────────────────────────────────────────
# Preenche `users.djen_oab_numero` / `users.djen_oab_uf` — os DOIS campos que o
# job diário de captura de intimações (`job_djen_intimacoes`, 06h30) lê para
# saber de quem monitorar publicações no DJEN/CNJ.
#
# POR QUE ESTE SCRIPT EXISTE
#
# A captura DJEN só enxerga advogado cujo `djen_oab_numero`+`djen_oab_uf` estão
# preenchidos (o job filtra `djen_oab_numero IS NOT NULL`). Preencher isso pela
# UI exige um PATCH /users/{id} por advogado; e um erro de digitação aqui não
# falha ruidosamente — ele monitora a inscrição de OUTRO advogado, ou monitora
# ninguém, sem alarme. Num sistema de prazos, silêncio custa prazo perdido.
#
# Por isso o script é conservador por construção:
#
#   • DRY-RUN por padrão; `--aplicar` exige confirmação digitada;
#   • casa o advogado por e-mail (exato) ou por fragmento de nome, e RECUSA
#     agir quando o fragmento casa 0 ou mais de 1 usuário — lista os candidatos
#     e sai sem escrever nada;
#   • valida a UF contra as 27 unidades federativas reais; a UF NUNCA é
#     inferida a partir do escritório (mesma regra de `oab_para_captura`);
#   • recusa atribuir uma OAB já vinculada a OUTRO usuário;
#   • é idempotente: rodar duas vezes com os mesmos argumentos não altera nada
#     na segunda vez, e diz isso;
#   • grava AuditLog (acao=UPDATE, entidade=users) por alteração;
#   • ao final, roda `--verificar` sozinho e mostra de quem o job VAI capturar.
#
# O par nome↔OAB é DADO OPERACIONAL, não código: entra por argumento de linha
# de comando e não fica versionado no repositório.
#
# Execução (container ejc_backend, na VPS — precisa de TTY por causa da
# confirmação digitada):
#
#     # 1) conferir o estado atual (não escreve nada)
#     docker exec -it ejc_backend python -m scripts.configurar_oab_djen --verificar
#
#     # 1b) provar que a fonte responde DESTE host (não escreve nada; faz uma
#     #     consulta real ao DJEN/CNJ por OAB monitorada)
#     docker exec -it ejc_backend python -m scripts.configurar_oab_djen --testar-fonte
#
#     # 2) simular (dry-run — não escreve nada)
#     docker exec -it ejc_backend python -m scripts.configurar_oab_djen \
#         --definir "Guilherme=252599/MG" \
#         --definir "Joao Pedro=251174/MG"
#
#     # 3) efetivar
#     docker exec -it ejc_backend python -m scripts.configurar_oab_djen \
#         --definir "Guilherme=252599/MG" \
#         --definir "Joao Pedro=251174/MG" --aplicar
#
# O identificador antes do "=" pode ser o e-mail do usuário (casamento exato,
# recomendado quando houver homônimos) ou um fragmento do nome, sem acento e
# sem distinção de maiúsculas.
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.ufs import UFS_BRASIL as UFS_VALIDAS
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services.djen_service import oab_para_captura

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.configurar_oab_djen")

PALAVRA_CONFIRMACAO = "CONFIRMO"



class EntradaInvalida(ValueError):
    """Argumento --definir malformado ou com UF/número inválido."""


@dataclass(slots=True)
class Definicao:
    identificador: str
    numero: str
    uf: str


@dataclass(slots=True)
class ItemPlano:
    definicao: Definicao
    user_id: str
    nome: str
    email: str
    numero_antes: str | None
    uf_antes: str | None
    oab_number_antes: str | None
    preenche_oab_number: bool

    @property
    def ja_configurado(self) -> bool:
        return (
            (self.numero_antes or "") == self.definicao.numero
            and (self.uf_antes or "").upper() == self.definicao.uf
            and not self.preenche_oab_number
        )


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )


def parse_definicao(bruto: str) -> Definicao:
    """Converte "Guilherme=252599/MG" em Definicao, validando número e UF.

    Aceita o separador de UF em "/", "-", espaço ou "OAB/UF numero"; o que NÃO
    se aceita é ausência de UF: número de OAB sem UF é ambíguo no país inteiro
    e supor o estado do escritório monitoraria outra inscrição.
    """
    if "=" not in bruto:
        raise EntradaInvalida(
            f'--definir {bruto!r}: formato esperado "IDENTIFICADOR=NUMERO/UF" '
            '(ex.: "Guilherme=252599/MG" ou "guilherme@escritorio.adv.br=252599/MG").'
        )
    identificador, _, oab = bruto.partition("=")
    identificador = identificador.strip()
    if not identificador:
        raise EntradaInvalida(f"--definir {bruto!r}: identificador vazio antes do '='.")

    numeros = re.findall(r"\d+", oab)
    ufs = [m.upper() for m in re.findall(r"[A-Za-z]{2}", _sem_acento(oab))]
    ufs = [u for u in ufs if u in UFS_VALIDAS]
    if len(numeros) != 1 or not ufs:
        raise EntradaInvalida(
            f"--definir {bruto!r}: não consegui ler NUMERO e UF de {oab.strip()!r}. "
            "Use o formato 252599/MG. A UF precisa ser uma das 27 unidades "
            "federativas e NUNCA é deduzida."
        )
    if len(set(ufs)) > 1:
        raise EntradaInvalida(
            f"--definir {bruto!r}: mais de uma UF possível em {oab.strip()!r} ({sorted(set(ufs))})."
        )
    numero = numeros[0]
    if not 3 <= len(numero) <= 10:  # users.djen_oab_numero é String(10)
        raise EntradaInvalida(
            f"--definir {bruto!r}: número de OAB {numero!r} tem {len(numero)} dígitos; "
            "esperado entre 3 e 10."
        )
    return Definicao(identificador=identificador, numero=numero, uf=ufs[0])


async def _usuarios_ativos(db) -> list[User]:
    return list(
        (
            await db.execute(
                select(User)
                .where(User.deleted_at.is_(None))
                .order_by(User.full_name)
            )
        ).scalars().all()
    )


def localizar(usuarios: list[User], identificador: str) -> list[User]:
    """E-mail casa exato (sem distinção de caixa); qualquer outra coisa é
    fragmento de nome, sem acento e sem caixa."""
    alvo = identificador.strip().lower()
    if "@" in alvo:
        return [u for u in usuarios if (u.email or "").strip().lower() == alvo]
    frag = _sem_acento(alvo)
    return [u for u in usuarios if frag in _sem_acento((u.full_name or "").lower())]


def montar_plano(usuarios: list[User], definicoes: list[Definicao]) -> tuple[list[ItemPlano], list[str]]:
    """Devolve (plano, erros). Qualquer erro aborta a execução inteira — meio
    plano aplicado é pior que nenhum, porque parece configurado."""
    plano: list[ItemPlano] = []
    erros: list[str] = []
    escolhidos: dict[str, str] = {}  # user_id -> identificador que o escolheu

    for d in definicoes:
        candidatos = localizar(usuarios, d.identificador)
        if not candidatos:
            erros.append(
                f"{d.identificador!r}: nenhum usuário ativo casa com esse "
                "e-mail/fragmento de nome. Rode --verificar para ver a lista."
            )
            continue
        if len(candidatos) > 1:
            nomes = ", ".join(f"{u.full_name} <{u.email}>" for u in candidatos[:8])
            erros.append(
                f"{d.identificador!r}: casa {len(candidatos)} usuários ({nomes}). "
                "Ambíguo — repita usando o e-mail exato."
            )
            continue
        u = candidatos[0]

        if u.id in escolhidos and escolhidos[u.id] != d.identificador:
            erros.append(
                f"{d.identificador!r} e {escolhidos[u.id]!r} apontam para o mesmo "
                f"usuário ({u.full_name}). Uma OAB por usuário."
            )
            # A definição anterior deixa de ser confiável também: qual das duas
            # OABs é a certa é justamente o que está em dúvida.
            plano[:] = [i for i in plano if i.user_id != u.id]
            continue
        escolhidos[u.id] = d.identificador

        conflito = [
            o for o in usuarios
            if o.id != u.id
            and (o.djen_oab_numero or "") == d.numero
            and (o.djen_oab_uf or "").upper() == d.uf
        ]
        if conflito:
            outros = ", ".join(f"{o.full_name} <{o.email}>" for o in conflito)
            erros.append(
                f"OAB {d.numero}/{d.uf} já está vinculada a {outros}. "
                "Limpe o vínculo antigo antes de reatribuir."
            )
            continue

        perfil_atual = (u.oab_number or "").strip()
        num_perfil, uf_perfil = oab_para_captura(
            type("_P", (), {"djen_oab_numero": "", "djen_oab_uf": "", "oab_number": perfil_atual})()
        )
        if perfil_atual and (num_perfil, uf_perfil) not in {("", ""), (d.numero, d.uf)}:
            erros.append(
                f"{u.full_name}: o perfil já traz OAB {perfil_atual!r}, que resolve para "
                f"{num_perfil}/{uf_perfil} — diferente de {d.numero}/{d.uf}. "
                "Divergência de dado cadastral: confirme com o titular antes de gravar."
            )
            continue

        plano.append(
            ItemPlano(
                definicao=d,
                user_id=u.id,
                nome=u.full_name,
                email=u.email,
                numero_antes=u.djen_oab_numero,
                uf_antes=u.djen_oab_uf,
                oab_number_antes=u.oab_number,
                preenche_oab_number=not perfil_atual,
            )
        )
    return plano, erros


def imprimir_plano(plano: list[ItemPlano]) -> None:
    for item in plano:
        d = item.definicao
        antes = (
            f"{item.numero_antes}/{item.uf_antes}"
            if item.numero_antes else "— (não configurado)"
        )
        marca = "JÁ CONFIGURADO" if item.ja_configurado else "GRAVAR"
        logger.info(
            "  %-14s %s <%s>  djen: %s → %s%s",
            marca,
            item.nome,
            item.email,
            antes,
            f"{d.numero}/{d.uf}",
            "  (+ preenche oab_number do perfil)" if item.preenche_oab_number else "",
        )


async def verificar() -> int:
    """Read-only: mostra, para cada usuário ativo, o que o job DJEN vai fazer."""
    async with AsyncSessionLocal() as db:
        usuarios = await _usuarios_ativos(db)

    monitorados = 0
    logger.info("")
    logger.info("=== Prontidão da captura DJEN (%d usuários ativos) ===", len(usuarios))
    for u in usuarios:
        numero, uf = oab_para_captura(u)
        alcancado_pelo_job = bool((u.djen_oab_numero or "").strip())
        if numero and uf and alcancado_pelo_job:
            estado = f"CAPTURA  {numero}/{uf}"
            monitorados += 1
        elif numero and uf:
            estado = (
                f"FORA DO JOB  (perfil traz {numero}/{uf}, mas o job seleciona por "
                "djen_oab_numero — preencha com --definir)"
            )
        else:
            estado = "sem OAB utilizável"
        logger.info("  %-58s %s", f"{u.full_name} <{u.email}>", estado)

    logger.info("")
    logger.info(
        "RESUMO: %d advogado(s) serão consultados pelo job diário de intimações.",
        monitorados,
    )
    if monitorados == 0:
        logger.warning(
            "NENHUM advogado monitorado — o job das 06h30 vai rodar e capturar zero, "
            "sem erro aparente. Configure com --definir."
        )
    return 0


async def testar_fonte(dias: int = 7) -> int:
    """Consulta o DJEN/CNJ de verdade, por OAB monitorada. Somente leitura.

    Cadastro correto e captura funcionando são coisas diferentes: a API do
    Comunica/CNJ (`comunicaapi.pje.jus.br`) fica atrás de uma distribuição
    CloudFront com RESTRIÇÃO GEOGRÁFICA — de fora do país ela devolve 403 em
    qualquer rota, inclusive `/swagger`. Um host errado deixa o job "verde"
    (heartbeat classifica como `http_4xx`) sem que ninguém saiba que o motivo
    é a localização do servidor, não a OAB. Este modo responde a pergunta no
    host onde o job realmente roda.
    """
    from app.services.djen_service import consultar_oab

    async with AsyncSessionLocal() as db:
        usuarios = await _usuarios_ativos(db)

    alvos = []
    for u in usuarios:
        if not (u.djen_oab_numero or "").strip():
            continue  # o job seleciona por este campo
        numero, uf = oab_para_captura(u)
        if numero and uf:
            alvos.append((u, numero, uf))

    if not alvos:
        logger.error(
            "Nenhuma OAB monitorada — não há o que testar. Cadastre com --definir."
        )
        return 2

    logger.info("=== Consulta real ao DJEN/CNJ (janela de %d dias) ===", dias)
    falhas = 0
    codigos = set()
    for u, numero, uf in alvos:
        resultado = await consultar_oab(numero, uf, dias=dias)
        if resultado.fonte_ok:
            logger.info(
                "  OK       %s — %s/%s: %d comunicação(ões) na janela (%d página[s])",
                u.full_name, numero, uf, resultado.recebidas, resultado.paginas,
            )
        else:
            falhas += 1
            codigos.add(resultado.erro or "desconhecido")
            logger.error(
                "  FALHA    %s — %s/%s: %s",
                u.full_name, numero, uf, resultado.erro,
            )

    logger.info("")
    if not falhas:
        logger.info(
            "Fonte respondeu para todas as %d OAB(s). "
            "`fonte_ok` com zero comunicações é resposta válida — significa que "
            "não houve publicação na janela, não que ninguém perguntou.",
            len(alvos),
        )
        return 0

    logger.error("%d de %d OAB(s) falharam (%s).", falhas, len(alvos), ", ".join(sorted(codigos)))
    if "http_4xx" in codigos:
        logger.error(
            "http_4xx no Comunica/CNJ costuma ser RESTRIÇÃO GEOGRÁFICA da "
            "distribuição CloudFront: de fora do Brasil a API devolve 403 em "
            "qualquer rota. Confirme com uma requisição crua neste mesmo host:\n"
            "    curl -s -o /dev/null -w '%{http_code}\\n' "
            "https://comunicaapi.pje.jus.br/swagger\n"
            "403 aqui = o servidor não consegue falar com o DJEN de onde está, "
            "e nenhum ajuste de cadastro resolve isso."
        )
    return 1


async def executar(definicoes: list[Definicao], aplicar: bool) -> int:
    async with AsyncSessionLocal() as db:
        usuarios = await _usuarios_ativos(db)
        plano, erros = montar_plano(usuarios, definicoes)

        if erros:
            for e in erros:
                logger.error("ERRO: %s", e)
            logger.error(
                "Nada foi alterado — %d problema(s) acima. Corrija os argumentos e repita.",
                len(erros),
            )
            return 2

        logger.info("=== Plano ===")
        imprimir_plano(plano)

        pendentes = [i for i in plano if not i.ja_configurado]
        if not pendentes:
            logger.info("")
            logger.info("Tudo já está como pedido — nenhuma alteração necessária.")
            await verificar()
            return 0

        logger.info("")
        logger.info("%d alteração(ões) pendente(s).", len(pendentes))
        if not aplicar:
            logger.info("DRY-RUN — nada foi alterado. Use --aplicar para efetivar.")
            return 0

        if not sys.stdin.isatty():
            logger.error(
                "--aplicar exige confirmação digitada e o stdin não é um terminal. "
                "Rode com `docker exec -it ...`."
            )
            return 2
        confirmacao = input(f'Digite "{PALAVRA_CONFIRMACAO}" para confirmar: ').strip()
        if confirmacao != PALAVRA_CONFIRMACAO:
            logger.warning("Confirmação incorreta — abortado sem alterar nada.")
            return 1

        for item in pendentes:
            u = (
                await db.execute(select(User).where(User.id == item.user_id))
            ).scalars().first()
            if u is None:  # removido entre o plano e a escrita
                logger.error("Usuário %s sumiu durante a execução — pulado.", item.user_id)
                continue
            antes = {
                "djen_oab_numero": u.djen_oab_numero,
                "djen_oab_uf": u.djen_oab_uf,
                "oab_number": u.oab_number,
            }
            u.djen_oab_numero = item.definicao.numero
            u.djen_oab_uf = item.definicao.uf
            if item.preenche_oab_number:
                u.oab_number = f"{item.definicao.numero}/{item.definicao.uf}"
            depois = {
                "djen_oab_numero": u.djen_oab_numero,
                "djen_oab_uf": u.djen_oab_uf,
                "oab_number": u.oab_number,
            }
            await criar_audit_log(
                db,
                user_id=None,
                user_role="sistema",
                acao="UPDATE",
                entidade="users",
                registro_id=u.id,
                detalhes="scripts.configurar_oab_djen — vínculo de OAB para captura DJEN",
                dados_antes=antes,
                dados_depois=depois,
            )
        await db.commit()
        logger.info("Aplicado: %d usuário(s) atualizado(s).", len(pendentes))

    await verificar()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Configura a OAB usada pela captura automática de intimações do DJEN "
            "(users.djen_oab_numero/djen_oab_uf). Dry-run por padrão."
        )
    )
    ap.add_argument(
        "--definir",
        action="append",
        default=[],
        metavar="IDENTIFICADOR=NUMERO/UF",
        help=(
            'par advogado↔OAB, repetível. Ex.: --definir "Guilherme=252599/MG". '
            "O identificador é o e-mail (exato) ou um fragmento do nome (que "
            "precisa casar exatamente um usuário)."
        ),
    )
    ap.add_argument(
        "--aplicar",
        action="store_true",
        help="efetiva a gravação (exige confirmação digitada)",
    )
    ap.add_argument(
        "--verificar",
        action="store_true",
        help="somente leitura: mostra de quem o job DJEN vai capturar hoje",
    )
    ap.add_argument(
        "--testar-fonte",
        action="store_true",
        help=(
            "somente leitura: consulta o DJEN/CNJ de verdade por OAB "
            "monitorada e diz se a fonte responde DESTE host"
        ),
    )
    args = ap.parse_args(argv)

    if (args.verificar or args.testar_fonte) and args.definir:
        logger.error(
            "--verificar e --testar-fonte são somente leitura; não combine com --definir."
        )
        return 2
    if args.verificar and args.testar_fonte:
        logger.error("Rode um modo de cada vez.")
        return 2
    if args.testar_fonte:
        return asyncio.run(testar_fonte())
    if args.verificar:
        return asyncio.run(verificar())
    if not args.definir:
        ap.print_help()
        logger.error("")
        logger.error("Informe ao menos um --definir, ou use --verificar.")
        return 2

    try:
        definicoes = [parse_definicao(b) for b in args.definir]
    except EntradaInvalida as exc:
        logger.error("%s", exc)
        return 2

    return asyncio.run(executar(definicoes, aplicar=args.aplicar))


if __name__ == "__main__":
    raise SystemExit(main())
