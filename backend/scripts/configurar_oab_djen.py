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
#         --definir "<e-mail ou fragmento do nome>=<numero>/<UF>" \
#         --definir "<e-mail ou fragmento do nome>=<numero>/<UF>"
#
#     # 3) efetivar (o operador vai para o AuditLog)
#     docker exec -it ejc_backend python -m scripts.configurar_oab_djen \
#         --definir "<e-mail ou fragmento do nome>=<numero>/<UF>" \
#         --aplicar --operador nome@escritorio.adv.br
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

from sqlalchemy import func, select

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
    # `oab_number` (o campo do PERFIL) é deliberadamente NÃO escrito por este
    # script: ele sai impresso na assinatura das peças geradas, e um script de
    # configuração de captura não deve alterar o que vai assinado num documento
    # jurídico. Quando está vazio, o plano avisa — preenchê-lo é ato do próprio
    # advogado, no perfil dele.
    perfil_vazio: bool

    @property
    def ja_configurado(self) -> bool:
        return (
            (self.numero_antes or "") == self.definicao.numero
            and (self.uf_antes or "").upper() == self.definicao.uf
        )


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )


def parse_definicao(bruto: str) -> Definicao:
    """Converte "<identificador>=<numero>/<UF>" em Definicao, validando os dois.

    Aceita o separador de UF em "/", "-", espaço ou "OAB/UF numero"; o que NÃO
    se aceita é ausência de UF: número de OAB sem UF é ambíguo no país inteiro
    e supor o estado do escritório monitoraria outra inscrição.
    """
    if "=" not in bruto:
        raise EntradaInvalida(
            f'--definir {bruto!r}: formato esperado "IDENTIFICADOR=NUMERO/UF" '
            '(ex.: "Silva=123456/MG" ou "silva@escritorio.adv.br=123456/MG").'
        )
    identificador, _, oab = bruto.partition("=")
    identificador = identificador.strip()
    if not identificador:
        raise EntradaInvalida(f"--definir {bruto!r}: identificador vazio antes do '='.")

    numeros = re.findall(r"[0-9]+", oab)
    # `\b...\b`: sem as bordas, "SEP" (typo de SP) casaria o pedaço "SE" e o
    # script gravaria uma inscrição em Sergipe sem acusar nada.
    ufs = [m.upper() for m in re.findall(r"\b[A-Za-z]{2}\b", _sem_acento(oab))]
    ufs = [u for u in ufs if u in UFS_VALIDAS]
    if len(numeros) != 1 or not ufs:
        raise EntradaInvalida(
            f"--definir {bruto!r}: não consegui ler NUMERO e UF de {oab.strip()!r}. "
            "Use o formato 123456/MG. A UF precisa ser uma das 27 unidades "
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
    """Espelha exatamente o filtro do job (`is_active` + `deleted_at`).

    Sem `is_active`, um usuário desativado com OAB aparecia como "CAPTURA" no
    relatório e não era capturado — falso verde no próprio verificador.
    """
    return list(
        (
            await db.execute(
                select(User)
                .where(User.deleted_at.is_(None), User.is_active.is_(True))
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


def _divergencia_com_o_perfil(perfil: str, d: Definicao) -> str | None:
    """Descreve a divergência entre a OAB do perfil e a que se quer gravar.

    Comparar só o par resolvido por `oab_para_captura` falhava ABERTO: perfil
    sem UF legível ("111111") resolve para ("", ""), o que era lido como
    "sem divergência" — e o script gravava a inscrição nova ao lado de um perfil que
    diz 111111, exatamente o dano que ele existe para impedir. Por isso o
    número é comparado mesmo quando a UF do perfil é indeterminável.
    """
    if not perfil:
        return None
    num_perfil, uf_perfil = oab_para_captura(
        type("_P", (), {"djen_oab_numero": "", "djen_oab_uf": "", "oab_number": perfil})()
    )
    if num_perfil and uf_perfil:
        if (num_perfil, uf_perfil) == (d.numero, d.uf):
            return None
        return f"resolve para {num_perfil}/{uf_perfil}"

    digitos = re.sub(r"\D", "", perfil)
    if digitos and digitos != d.numero:
        return f"número {digitos}, sem UF determinável"
    return None


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
        divergencia = _divergencia_com_o_perfil(perfil_atual, d)
        if divergencia:
            erros.append(
                f"{u.full_name}: o perfil traz OAB {perfil_atual!r} ({divergencia}), "
                f"diferente de {d.numero}/{d.uf}. Divergência de dado cadastral: "
                "confirme com o titular antes de gravar."
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
                perfil_vazio=not perfil_atual,
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
            "  (perfil sem OAB — preencha no perfil, é o que assina as peças)"
            if item.perfil_vazio else "",
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


async def executar(
    definicoes: list[Definicao], aplicar: bool, operador: str | None = None
) -> int:
    # Sessão 1 — LEITURA. Fecha antes do prompt: manter a transação aberta
    # durante um `input()` deixa a conexão `idle in transaction` pelo tempo que
    # o operador levar para digitar, segurando VACUUM e um slot do pool do
    # mesmo banco que atende a aplicação.
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

    # Sessão 2 — ESCRITA. Recarrega cada usuário: o plano foi montado numa
    # leitura anterior e o banco pode ter mudado nesse meio-tempo.
    async with AsyncSessionLocal() as db:
        ator_id = await _resolver_operador(db, operador)
        gravados = 0
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
            }
            u.djen_oab_numero = item.definicao.numero
            u.djen_oab_uf = item.definicao.uf
            depois = {
                "djen_oab_numero": u.djen_oab_numero,
                "djen_oab_uf": u.djen_oab_uf,
            }
            await criar_audit_log(
                db,
                user_id=ator_id,
                user_role="sistema",
                acao="UPDATE",
                entidade="users",
                registro_id=u.id,
                detalhes=(
                    "scripts.configurar_oab_djen — vínculo de OAB para captura "
                    f"DJEN; operador declarado: {operador}"
                ),
                dados_antes=antes,
                dados_depois=depois,
            )
            gravados += 1
        await db.commit()
        logger.info("Aplicado: %d usuário(s) atualizado(s).", gravados)

    await verificar()
    return 0


async def _resolver_operador(db, operador: str | None) -> str | None:
    """Casa o `--operador` declarado com um usuário, para o AuditLog ter ator.

    Sem isto o registro guarda bem o QUÊ (antes/depois) e não guarda o QUEM: a
    alteração por shell fica indistinguível de ação automática do sistema,
    enquanto a mesma alteração pela API grava o id de quem a fez. O texto
    declarado vai para `detalhes` de qualquer forma; o id só é preenchido
    quando o casamento é inequívoco.
    """
    if not operador:
        return None
    alvo = operador.strip().lower()
    if "@" not in alvo:
        return None
    linha = (
        await db.execute(
            select(User.id).where(
                func.lower(User.email) == alvo, User.deleted_at.is_(None)
            )
        )
    ).first()
    return linha[0] if linha else None


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
            'par advogado↔OAB, repetível. Ex.: --definir "Silva=123456/MG". '
            "O identificador é o e-mail (exato) ou um fragmento do nome (que "
            "precisa casar exatamente um usuário)."
        ),
    )
    ap.add_argument(
        "--aplicar",
        action="store_true",
        help="efetiva a gravação (exige confirmação digitada e --operador)",
    )
    ap.add_argument(
        "--operador",
        metavar="EMAIL",
        help=(
            "quem está executando (e-mail institucional, de preferência). "
            "Vai para o AuditLog — obrigatório com --aplicar, para a alteração "
            "não ficar indistinguível de uma ação automática do sistema."
        ),
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

    if args.aplicar and not (args.operador or "").strip():
        logger.error(
            "--aplicar exige --operador (quem responde por esta alteração). "
            "Ex.: --operador nome@escritorio.adv.br"
        )
        return 2

    return asyncio.run(
        executar(definicoes, aplicar=args.aplicar, operador=args.operador)
    )


if __name__ == "__main__":
    raise SystemExit(main())
