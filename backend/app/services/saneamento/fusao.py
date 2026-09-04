# ── app/services/saneamento/fusao.py ─────────────────────────────────────────
# Fusão real de casos duplicados (PR #1318, achado de revisão de código —
# Codex, thread discussion_r3890868744 — e Issue #1319, item 2). Antes,
# `POST /saneamento/duplicatas/{id}/aplicar` só marcava `aplicado=true` sem
# fundir nada; nenhum handler de fusão existia em lugar nenhum do EJC.
#
# ESCOPO AUTORIZADO EXPLICITAMENTE PELO TITULAR (AskUserQuestion, opção
# "Fusão completa das 51 tabelas"): reatribui TODAS as tabelas com FK para
# `cases.id` — calculado dinamicamente via `information_schema`, nunca
# hardcoded, para não desatualizar conforme o schema evolui (eram 51 no
# momento da implementação; CLAUDE.md avisa que ~30 tabelas do EJC são
# raw-SQL sem model, então uma lista Python seria incompleta por design).
#
# CONFLITO EM TABELA "1 LINHA POR CASO": quando uma tabela impõe (por
# UNIQUE real no banco, ou por convenção de aplicação — ver
# _TABELAS_AREA_UM_POR_CASO) no máximo uma linha por case_id, e tanto
# principal quanto absorvido já têm linha, a do absorvido é DESCARTADA
# (nunca mesclada campo a campo) — decisão explícita do titular. A escolha
# de qual sobrevive já foi feita antes: `RegistroProcesso.completude()`
# escolhe o "principal" do grupo de deduplicação por ser o mais completo
# (dedup.py), então esta função só honra essa escolha.
#
# NUNCA faz DROP/DELETE do caso em si — vira `status=arquivado` +
# `archived_at`/`archive_reason` (mesmos campos que POST /cases/{id}/arquivar
# já usa — não uma convenção nova), auditável e reversível manualmente (não
# há "desfundir" automático). Roda inteira na transação do `db` recebido:
# erro no meio desfaz tudo (nem fusão parcial nem arquivamento acontecem) —
# o chamador decide quando `commit()`.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Tabelas de "área jurídica" (civel_cases, penal_cases, ...): uma linha por
# caso por CONVENÇÃO DE APLICAÇÃO — o schema não impõe UNIQUE(case_id) nelas
# (verificado em information_schema), então ficam explícitas aqui em vez de
# infligidas por heurística de nome de tabela (frágil, poderia classificar
# errado uma tabela genuinamente 1:N). Tabela de área nova que também deva
# ser 1:1 por caso precisa ser adicionada aqui conscientemente.
_TABELAS_AREA_UM_POR_CASO = frozenset({
    "admin_cases", "bancario_cases", "civel_cases", "contratos_societarios",
    "empresarial_cases", "environmental_cases", "penal_cases", "trabalhista_cases",
})


@dataclass(slots=True)
class RelatorioFusao:
    reatribuidas: dict[str, int] = field(default_factory=dict)
    descartadas: dict[str, int] = field(default_factory=dict)
    processos_colapsados: int = 0
    absorvido_ja_arquivado: bool = False


def _ident(nome: str) -> str:
    """Quoting de identificador — `nome` vem sempre de information_schema
    (catálogo do Postgres) ou da whitelist `_TABELAS_AREA_UM_POR_CASO`,
    nunca de entrada do usuário; ainda assim aspeamos por disciplina (nunca
    interpolar identificador sem aspas numa string SQL)."""
    return '"' + nome.replace('"', '""') + '"'


async def _tabelas_com_fk_para_cases(db: AsyncSession) -> list[tuple[str, str]]:
    """(tabela, coluna) para toda FK que referencia cases(id)."""
    rows = (await db.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND ccu.table_name = 'cases' AND ccu.column_name = 'id'
        ORDER BY tc.table_name, kcu.column_name
    """))).all()
    return [(r[0], r[1]) for r in rows]


async def _constraints_unique_com(db: AsyncSession, tabela: str, coluna: str) -> list[list[str]]:
    """Cada constraint UNIQUE de `tabela` que inclui `coluna`, como a lista
    completa de colunas daquela constraint (uma sozinha = [coluna]; composta
    = [coluna, outra_coluna, ...])."""
    rows = (await db.execute(text("""
        SELECT tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'UNIQUE'
          AND tc.table_schema = 'public' AND tc.table_name = :tabela
          AND tc.constraint_name IN (
              SELECT constraint_name FROM information_schema.key_column_usage
              WHERE table_schema = 'public' AND table_name = :tabela AND column_name = :coluna
          )
        ORDER BY tc.constraint_name, kcu.ordinal_position
    """), {"tabela": tabela, "coluna": coluna})).all()
    agrupado: dict[str, list[str]] = {}
    for nome, col in rows:
        agrupado.setdefault(nome, []).append(col)
    return list(agrupado.values())


async def _reatribuir_tabela(
    db: AsyncSession, relatorio: RelatorioFusao, *,
    tabela: str, coluna: str, principal_id: str, absorvido_id: str,
) -> None:
    constraints = await _constraints_unique_com(db, tabela, coluna)
    unica_sozinha = any(c == [coluna] for c in constraints)
    composta = next((c for c in constraints if c != [coluna] and coluna in c), None)

    chave = f"{tabela}.{coluna}"
    if unica_sozinha or tabela in _TABELAS_AREA_UM_POR_CASO:
        existe_no_principal = (await db.execute(
            text(f"SELECT 1 FROM {_ident(tabela)} WHERE {_ident(coluna)} = :p LIMIT 1"),
            {"p": principal_id},
        )).first() is not None
        if existe_no_principal:
            resultado = await db.execute(
                text(f"DELETE FROM {_ident(tabela)} WHERE {_ident(coluna)} = :a"),
                {"a": absorvido_id},
            )
            if resultado.rowcount:
                relatorio.descartadas[chave] = resultado.rowcount
            return
        resultado = await db.execute(
            text(f"UPDATE {_ident(tabela)} SET {_ident(coluna)} = :p WHERE {_ident(coluna)} = :a"),
            {"p": principal_id, "a": absorvido_id},
        )
        if resultado.rowcount:
            relatorio.reatribuidas[chave] = resultado.rowcount
        return

    if composta is not None:
        # Unicidade composta (ex.: case_id+etiqueta_id): linha a linha —
        # reatribui só quando não colide com uma linha que o principal já
        # tem para a mesma combinação das outras colunas da constraint.
        outras = [c for c in composta if c != coluna]
        condicao = " AND ".join(
            f"ppl.{_ident(c)} IS NOT DISTINCT FROM abs.{_ident(c)}" for c in outras
        )
        resultado = await db.execute(text(f"""
            UPDATE {_ident(tabela)} AS abs
            SET {_ident(coluna)} = :p
            WHERE abs.{_ident(coluna)} = :a
              AND NOT EXISTS (
                  SELECT 1 FROM {_ident(tabela)} AS ppl
                  WHERE ppl.{_ident(coluna)} = :p AND ({condicao})
              )
        """), {"p": principal_id, "a": absorvido_id})
        if resultado.rowcount:
            relatorio.reatribuidas[chave] = resultado.rowcount
        # Sobrou linha do absorvido que colidiu (não pôde ser reatribuída
        # sem violar a constraint) — descarta, mesma regra "principal vence".
        descarte = await db.execute(
            text(f"DELETE FROM {_ident(tabela)} WHERE {_ident(coluna)} = :a"),
            {"a": absorvido_id},
        )
        if descarte.rowcount:
            relatorio.descartadas[chave] = descarte.rowcount
        return

    # 1:N normal (documents, tasks, deadlines, fees, time_entries,
    # processes, ...) — toda linha do absorvido passa a apontar pro principal.
    resultado = await db.execute(
        text(f"UPDATE {_ident(tabela)} SET {_ident(coluna)} = :p WHERE {_ident(coluna)} = :a"),
        {"p": principal_id, "a": absorvido_id},
    )
    if resultado.rowcount:
        relatorio.reatribuidas[chave] = resultado.rowcount


async def _colapsar_processos_duplicados(
    db: AsyncSession, relatorio: RelatorioFusao, *, case_id: str, numero_cnj: str,
) -> None:
    """Depois da reatribuição genérica, o `case_id` principal pode ter mais
    de um `Process` com o MESMO numero_cnj (o que a própria fusão devia
    resolver — não faz sentido sobrar dois processos idênticos sob o mesmo
    caso). Mantém o mais completo (mais colunas preenchidas — mesmo
    critério de RegistroProcesso.completude()), arquiva os demais via
    `Process.archived_at`/`archive_reason` (nunca DELETE — mesmo padrão de
    preservação de processo já usado pelo resto do EJC)."""
    linhas = (await db.execute(text("""
        SELECT id, tribunal, comarca, vara, classe, fase, valor_causa, instancia
        FROM processes
        WHERE case_id = :cid AND regexp_replace(numero_cnj, '\\D', '', 'g') = :n
          AND archived_at IS NULL
    """), {"cid": case_id, "n": numero_cnj})).mappings().all()
    if len(linhas) <= 1:
        return

    def completude(linha) -> int:
        return sum(1 for k, v in linha.items() if k != "id" and v not in (None, "", []))

    ordenadas = sorted(linhas, key=completude, reverse=True)
    sobrevivente = ordenadas[0]
    ids_arquivar = [str(l["id"]) for l in ordenadas[1:]]
    if not ids_arquivar:
        return
    agora = datetime.now(timezone.utc)
    resultado = await db.execute(text("""
        UPDATE processes SET archived_at = :agora,
               archive_reason = :motivo
        WHERE id = ANY(:ids)
    """), {
        "agora": agora, "ids": ids_arquivar,
        "motivo": f"Duplicata do mesmo numero_cnj colapsada na fusão de casos "
                  f"(saneamento de base processual) — sobrevivente: {sobrevivente['id']}",
    })
    relatorio.processos_colapsados = resultado.rowcount


async def fundir_casos(
    db: AsyncSession, *, principal_id: str, absorvido_id: str,
    numero_cnj_gatilho: str, ator_id: str,
) -> RelatorioFusao:
    """Reatribui toda referência ao caso absorvido para o principal e
    arquiva o absorvido. Não commita — o chamador decide quando."""
    relatorio = RelatorioFusao()

    absorvido = (await db.execute(
        text("SELECT id, status, deleted_at FROM cases WHERE id = :id"),
        {"id": absorvido_id},
    )).mappings().one_or_none()
    if absorvido is None or absorvido["deleted_at"] is not None or absorvido["status"] == "arquivado":
        # Já fundido/excluído por uma aplicação anterior do mesmo plano
        # (ou de outro que compartilhava o par) — idempotente, não repete.
        relatorio.absorvido_ja_arquivado = True
        return relatorio

    for tabela, coluna in await _tabelas_com_fk_para_cases(db):
        if tabela == "cases":
            continue
        await _reatribuir_tabela(
            db, relatorio, tabela=tabela, coluna=coluna,
            principal_id=principal_id, absorvido_id=absorvido_id,
        )

    await _colapsar_processos_duplicados(
        db, relatorio, case_id=principal_id, numero_cnj=numero_cnj_gatilho,
    )

    agora = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE cases
        SET status_anterior = CASE WHEN status <> 'encerrado' THEN status::text ELSE status_anterior END,
            status = 'arquivado', archived_at = :agora,
            archive_reason = :motivo
        WHERE id = :id
    """), {
        "agora": agora, "id": absorvido_id,
        "motivo": f"Fundido no caso {principal_id} — plano de deduplicação de saneamento processual "
                  f"(numero_cnj {numero_cnj_gatilho}), aplicado por {ator_id}.",
    })
    await db.execute(text("""
        INSERT INTO case_movimentos (id, case_id, tipo, descricao, created_by)
        VALUES (:id, :case_id, 'saneamento', :descricao, :ator)
    """), {
        "id": str(uuid4()), "case_id": principal_id, "ator": ator_id,
        "descricao": f"Absorveu o caso {absorvido_id} (duplicata do mesmo numero_cnj "
                     f"{numero_cnj_gatilho}) via saneamento de base processual.",
    })

    return relatorio
