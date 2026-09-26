# ── app/services/saneamento/produtor.py ──────────────────────────────────────
# Produtor do módulo de saneamento — aciona as regras de negócio puras
# (deduplicar/avaliar_encerramento/reconciliar) sobre a base real do EJC e
# persiste os resultados. Sem isso as tabelas de saneamento ficam vazias para
# sempre (achado de revisão de código do PR #1318 — Codex, thread
# discussion_r3890868769 — e Issue #1319).
#
# DECISÃO DE ARQUITETURA que o PR #1318 deixou em aberto (`id_interno` era
# "string opaca da base interna", sem semântica fixada): `RegistroProcesso.
# id_interno` = `Case.id`. É o identificador que app/routers/saneamento.py
# já usa para resolver titularidade e é o mesmo que a fusão real de
# `aplicar_duplicata` (Issue #1319, item 2) precisa para saber qual Case
# absorve qual.
#
# FONTE DOS NÚMEROS INTERNOS: `Process.numero_cnj` (fonte canônica, cobre
# processo acessório) UNIDA a `Case.numero_processo` só para casos SEM
# nenhum Process cadastrado (dado legado) — mesma lógica de
# app/routers/saneamento.py::_match_numero_cnj, para não reintroduzir a
# lacuna já corrigida lá.
#
# CAMPOS SEM MAPEAMENTO CONFIRMADO (não inventados — deixados ausentes):
#   - `RegistroProcesso.grau` recebe `Process.instancia` (texto livre, ex.:
#     "1ª instância"). NÃO confirmado como o mesmo vocabulário do `grau` que
#     o DataJud retorna (G1/G2/...) — mas dedup.py só compara IGUALDADE
#     entre valores de grau para decidir "duplicata real" vs "relacionar",
#     nunca decodifica o valor. Divergência de vocabulário ainda produz o
#     resultado seguro (grau aparentemente diferente → relaciona, nunca
#     funde), nunca o inseguro. A VERIFICAR se algum dia o vocabulário
#     precisar bater exatamente com o do DataJud.
#   - reconciliar() espera `orgao_julgador` no registro interno — não existe
#     coluna com esse nome em Case/Process; usamos `Process.vara` (o juízo é,
#     na prática forense, o órgão julgador) como aproximação razoável, não
#     confirmada campo-a-campo. Documentado aqui, não escondido.
#   - reconciliar() também aceita `data_ajuizamento` — NÃO EXISTE hoje nenhum
#     campo em Case/Process para data de distribuição/ajuizamento do
#     processo (só há `data_encerramento`). Passamos None: reconciliar() já
#     trata ausência sem gerar falso positivo (a comparação é pulada, não
#     "corrigida" com um valor inventado).
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.case import Case
from app.models.process import Process
from app.models.saneamento import (
    DatajudSnapshot,
    Divergencia,
    ExcecaoNumero,
    Execucao,
    IndicativoEncerramento,
    PlanoDedup,
)
from app.services.datajud_service import (
    DataJudDesabilitadoError,
    TribunalNaoMapeadoError,
    buscar_documento_saneamento,
)
from app.services.saneamento.dedup import RegistroProcesso, deduplicar
from app.services.saneamento.encerramento import avaliar_encerramento, extrair_movimentos
from app.services.saneamento.reconciliacao import reconciliar
from app.services.saneamento.tpu import carregar_catalogo
from app.services.validators_service import normalizar_cnj

logger = logging.getLogger(__name__)

TIPO_DEDUP = "dedup"
TIPO_DATAJUD = "datajud"


async def _registros_internos(db: AsyncSession) -> list[RegistroProcesso]:
    """Um RegistroProcesso por Process cadastrado, mais um por Case sem
    NENHUM Process (dado legado — só o espelho `numero_processo` existe)."""
    registros: list[RegistroProcesso] = []

    processos = (
        await db.execute(
            select(
                Process.case_id,
                Process.numero_cnj,
                Process.instancia,
                Process.classe,
                Process.vara,
                Process.data_ajuizamento,
            )
            .where(Process.numero_cnj.is_not(None))
        )
    ).all()
    casos_com_process: set[str] = set()
    for case_id, numero_cnj, instancia, classe, vara, data_ajuizamento in processos:
        casos_com_process.add(case_id)
        registros.append(
            RegistroProcesso(
                id_interno=case_id, numero=numero_cnj, grau=instancia,
                dados={
                    "origem": "process",
                    "classe": classe,
                    "vara": vara,
                    "data_ajuizamento": data_ajuizamento,
                },
            )
        )

    casos_legado = (
        await db.execute(
            select(Case.id, Case.numero_processo)
            .where(Case.numero_processo.is_not(None), Case.deleted_at.is_(None))
        )
    ).all()
    for case_id, numero_processo in casos_legado:
        if case_id in casos_com_process:
            continue  # já coberto pela fonte canônica acima
        registros.append(
            RegistroProcesso(
                id_interno=case_id, numero=numero_processo, grau=None,
                dados={"origem": "case_numero_processo_legado"},
            )
        )
    return registros


async def _upsert_excecao(db: AsyncSession, *, id_interno: str, numero_bruto: str, motivo: str) -> bool:
    """Não empilha a mesma exceção pendente a cada execução — atualiza
    motivo/numero_bruto se já existe uma linha não resolvida para este
    id_interno. Retorna True se inseriu uma linha nova."""
    existente = (
        await db.execute(
            select(ExcecaoNumero).where(
                ExcecaoNumero.id_interno == id_interno,
                ExcecaoNumero.resolvido.is_(False),
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        existente.numero_bruto = numero_bruto
        existente.motivo = motivo
        return False
    db.add(ExcecaoNumero(id_interno=id_interno, numero_bruto=numero_bruto, motivo=motivo))
    return True


async def _upsert_plano(db: AsyncSession, *, numero_cnj: str, principal: str, absorvidos: list[str], tipo: str) -> bool:
    """Não empilha o mesmo plano pendente a cada execução. Um plano JÁ
    aplicado nunca é tocado de novo (append-only sobre decisão humana)."""
    existente = (
        await db.execute(
            select(PlanoDedup).where(
                PlanoDedup.numero_cnj == numero_cnj,
                PlanoDedup.tipo == tipo,
                PlanoDedup.aplicado.is_(False),
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        existente.id_interno_principal = principal
        existente.ids_absorvidos = absorvidos
        return False
    db.add(PlanoDedup(
        numero_cnj=numero_cnj, id_interno_principal=principal,
        ids_absorvidos=absorvidos, tipo=tipo,
    ))
    return True


async def executar_varredura_dedup(db: AsyncSession) -> Execucao:
    """Roda deduplicar() sobre a base real (Case/Process) e persiste
    PlanoDedup (duplicata/multi_grau) + ExcecaoNumero. Sem dependência
    externa — roda sempre, independente de DATAJUD_ENABLED."""
    execucao = Execucao(tipo=TIPO_DEDUP)
    db.add(execucao)
    await db.flush()

    processados = 0
    falhas = 0
    novos_planos = 0
    novas_excecoes = 0
    try:
        registros = await _registros_internos(db)
        resultado = deduplicar(registros)
        processados = len(registros)

        for exc in resultado.excecoes:
            if await _upsert_excecao(
                db, id_interno=exc.registro.id_interno,
                numero_bruto=exc.registro.numero, motivo=exc.motivo,
            ):
                novas_excecoes += 1

        for grupo in resultado.duplicatas:
            if await _upsert_plano(
                db, numero_cnj=grupo.numero_canonico,
                principal=grupo.principal.id_interno,
                absorvidos=[r.id_interno for r in grupo.absorvidos],
                tipo="duplicata",
            ):
                novos_planos += 1

        for numero, grupo in resultado.graus_relacionados.items():
            ordenado = sorted(grupo, key=lambda r: r.completude(), reverse=True)
            if await _upsert_plano(
                db, numero_cnj=numero, principal=ordenado[0].id_interno,
                absorvidos=[r.id_interno for r in ordenado[1:]],
                tipo="multi_grau",
            ):
                novos_planos += 1

        execucao.status = "sucesso"
    except Exception as e:  # noqa: BLE001 — job precisa registrar QUALQUER falha, não engolir
        falhas = 1
        execucao.status = "falha"
        logger.exception("Falha na varredura de deduplicação do saneamento")
        execucao.detalhe = {"erro": str(e)}
    finally:
        execucao.finalizado_em = datetime.now(timezone.utc)
        execucao.processados = processados
        execucao.falhas = falhas
        execucao.detalhe = {
            **(execucao.detalhe or {}),
            "novos_planos": novos_planos, "novas_excecoes": novas_excecoes,
        }
        await db.commit()
        await db.refresh(execucao)
    return execucao


async def executar_varredura_datajud(db: AsyncSession, *, limite: int = 50) -> Execucao:
    """Consulta o DataJud para até `limite` numero_cnj internos, grava
    DatajudSnapshot, e roda avaliar_encerramento + reconciliar sobre o que
    foi coletado nesta execução. No-op gracioso se DATAJUD_ENABLED/
    DATAJUD_API_KEY estiverem ausentes (mesmo padrão de degradação do resto
    do EJC) — não é falha, é configuração."""
    execucao = Execucao(tipo=TIPO_DATAJUD)
    db.add(execucao)
    await db.flush()

    s = get_settings()
    if not s.DATAJUD_ENABLED or not s.DATAJUD_API_KEY:
        execucao.status = "sucesso"
        execucao.finalizado_em = datetime.now(timezone.utc)
        execucao.detalhe = {"motivo": "DATAJUD_ENABLED/DATAJUD_API_KEY ausente — nenhuma consulta feita"}
        await db.commit()
        await db.refresh(execucao)
        return execucao

    processados = 0
    falhas = 0
    catalogo = await carregar_catalogo(db)
    interno_por_numero: dict[str, dict] = {}
    documentos_por_numero: dict[str, list[dict]] = defaultdict(list)

    try:
        registros = await _registros_internos(db)
        resultado = deduplicar(registros)

        # Só números VÁLIDOS entram na consulta externa — os inválidos já
        # foram para a fila de exceção pela própria deduplicar() acima (não
        # persistidos aqui: essa é responsabilidade de executar_varredura_dedup).
        # Um representante por numero_cnj: o principal de cada grupo
        # (duplicata/multi-grau) ou o registro único.
        vistos: set[str] = set()
        candidatos: list[tuple[str, RegistroProcesso]] = []
        todos_validos: list[RegistroProcesso] = list(resultado.unicos)
        for g in resultado.duplicatas:
            todos_validos.append(g.principal)
        for g in resultado.graus_relacionados.values():
            todos_validos.extend(g)

        for reg in todos_validos:
            numero_norm = normalizar_cnj(reg.numero)
            if numero_norm in vistos:
                continue
            vistos.add(numero_norm)
            candidatos.append((numero_norm, reg))
            if len(candidatos) >= limite:
                break

        for numero_cnj, reg in candidatos:
            interno_por_numero[numero_cnj] = {
                "classe": reg.dados.get("classe"),
                "orgao_julgador": reg.dados.get("vara"),
                "data_ajuizamento": reg.dados.get("data_ajuizamento"),
            }
            try:
                doc = await buscar_documento_saneamento(numero_cnj)
            except (DataJudDesabilitadoError, TribunalNaoMapeadoError) as e:
                falhas += 1
                logger.info("Saneamento/DataJud: %s — %s", numero_cnj, e)
                continue
            except Exception:
                falhas += 1
                logger.exception("Saneamento/DataJud: falha consultando %s", numero_cnj)
                continue

            processados += 1
            if doc is None:
                continue

            grau_doc = str(doc.get("grau") or "")
            classe_codigo = (doc.get("classe") or {}).get("codigo") if isinstance(doc.get("classe"), dict) else None
            orgao_codigo = (doc.get("orgaoJulgador") or {}).get("codigo") if isinstance(doc.get("orgaoJulgador"), dict) else None
            nivel_sigilo = int(doc.get("nivelSigilo") or 0)
            data_ajuizamento = None
            data_ajuizamento_raw = str(doc.get("dataAjuizamento") or "")[:10]
            if data_ajuizamento_raw:
                try:
                    data_ajuizamento = date.fromisoformat(data_ajuizamento_raw)
                except ValueError:
                    data_ajuizamento = None
            # UNIQUE(numero_cnj, grau) — upsert, não INSERT cego: a segunda
            # varredura do mesmo processo violaria a constraint (achado ao
            # rodar o teste de idempotência duas vezes seguidas).
            snapshot_existente = (
                await db.execute(
                    select(DatajudSnapshot).where(
                        DatajudSnapshot.numero_cnj == numero_cnj,
                        DatajudSnapshot.grau == grau_doc,
                    )
                )
            ).scalar_one_or_none()
            if snapshot_existente is not None:
                snapshot_existente.tribunal = doc.get("tribunal")
                snapshot_existente.classe_codigo = classe_codigo
                snapshot_existente.orgao_codigo = orgao_codigo
                snapshot_existente.nivel_sigilo = nivel_sigilo
                snapshot_existente.data_ajuizamento = data_ajuizamento
                snapshot_existente.payload = doc
                snapshot_existente.coletado_em = datetime.now(timezone.utc)
            else:
                db.add(DatajudSnapshot(
                    numero_cnj=numero_cnj, grau=grau_doc, tribunal=doc.get("tribunal"),
                    classe_codigo=classe_codigo, orgao_codigo=orgao_codigo,
                    data_ajuizamento=data_ajuizamento,
                    nivel_sigilo=nivel_sigilo, payload=doc,
                ))
            documentos_por_numero[numero_cnj].append(doc)

            movimentos = extrair_movimentos(doc)
            indicativo = avaliar_encerramento(numero_cnj, movimentos, catalogo)
            pendente = (
                await db.execute(
                    select(IndicativoEncerramento).where(
                        IndicativoEncerramento.numero_cnj == numero_cnj,
                        IndicativoEncerramento.decisao.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if pendente is not None:
                pendente.candidato = indicativo.candidato
                pendente.confianca = indicativo.confianca.value
                pendente.motivos = indicativo.motivos
                pendente.dias_de_silencio = indicativo.dias_de_silencio
                pendente.movimento_terminativo = (
                    indicativo.movimento_terminativo.codigo if indicativo.movimento_terminativo else None
                )
                pendente.avaliado_em = datetime.now(timezone.utc)
            else:
                db.add(IndicativoEncerramento(
                    numero_cnj=numero_cnj, candidato=indicativo.candidato,
                    confianca=indicativo.confianca.value, motivos=indicativo.motivos,
                    dias_de_silencio=indicativo.dias_de_silencio,
                    movimento_terminativo=(
                        indicativo.movimento_terminativo.codigo
                        if indicativo.movimento_terminativo else None
                    ),
                ))

        if documentos_por_numero:
            relatorio = reconciliar(interno_por_numero, documentos_por_numero)
            for div in relatorio.divergencias:
                existente = (
                    await db.execute(
                        select(Divergencia).where(
                            Divergencia.numero_cnj == div.numero,
                            Divergencia.tipo == div.tipo.value,
                            Divergencia.tratada.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existente is not None:
                    existente.valor_interno = div.valor_interno
                    existente.valor_datajud = div.valor_datajud
                    existente.observacao = div.observacao
                else:
                    db.add(Divergencia(
                        numero_cnj=div.numero, tipo=div.tipo.value,
                        valor_interno=div.valor_interno, valor_datajud=div.valor_datajud,
                        observacao=div.observacao,
                    ))

        execucao.status = "sucesso"
    except Exception as e:  # noqa: BLE001
        execucao.status = "falha"
        logger.exception("Falha na varredura DataJud do saneamento")
        execucao.detalhe = {"erro": str(e)}
    finally:
        execucao.finalizado_em = datetime.now(timezone.utc)
        execucao.processados = processados
        execucao.falhas = falhas
        execucao.detalhe = {**(execucao.detalhe or {}), "consultados": processados}
        await db.commit()
        await db.refresh(execucao)
    return execucao
