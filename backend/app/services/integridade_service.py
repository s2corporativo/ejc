"""Diagnóstico de integridade referencial — SOMENTE LEITURA.

Torna observável aquilo que hoje só aparece como número errado numa tela: peças,
documentos, prazos e tarefas que sobreviveram à exclusão lógica do caso pai, e
divergências entre contadores agregados e listagens.

Contrato inegociável deste módulo:

* **Não corrige nada.** Só executa `SELECT`. Nenhuma função aqui faz UPDATE,
  DELETE, commit ou flush. Decidir o que fazer com um achado é ato humano.
* **Não vaza PII.** Devolve apenas identificadores técnicos (UUID) e contagens.
  Nunca nome de cliente, título de caso, CPF/CNPJ, número de processo ou
  conteúdo de peça — o relatório é feito para virar log e ticket.
* **Não confunde estado legítimo com defeito.** Documento sem `case_id` pode ser
  caixa de entrada, triagem, GED institucional ou documento ainda não
  classificado. Só é "órfão inválido" o que não tem NENHUMA âncora: nem caso,
  nem cliente, nem quem subiu.

Sobre orfandade FÍSICA: `legal_docs.case_id`, `documents.case_id`,
`deadlines.case_id` e `tasks.case_id` têm FK real para `cases.id` (sem
`ON DELETE`), então o banco impede apontar para caso inexistente. As checagens
correspondentes existem mesmo assim, como sentinela: se alguém dropar uma FK
numa migration futura, o diagnóstico acusa em vez de o sintoma reaparecer como
contador errado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Teto de IDs listados por achado. Evita relatório gigante e log caro; o
#: campo `total` continua exato e `truncado` avisa que a lista foi cortada.
LIMITE_IDS = 100


async def _achado(
    db: AsyncSession,
    *,
    tipo: str,
    sql: str,
    entidade: str,
    entidade_pai: str | None,
    estado_pai: str | None,
    severidade: str,
    acao_recomendada: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Executa UMA consulta de diagnóstico e formata o achado.

    `sql` deve projetar exatamente uma coluna `id`. A contagem é feita sobre o
    conjunto completo; a lista de ids é truncada em `LIMITE_IDS`.
    """
    rows = (await db.execute(text(sql), params or {})).scalars().all()
    ids = [str(r) for r in rows]
    return {
        "tipo": tipo,
        "entidade": entidade,
        "entidade_pai": entidade_pai,
        "estado_pai": estado_pai,
        "severidade": severidade,
        "total": len(ids),
        "ids": ids[:LIMITE_IDS],
        "truncado": len(ids) > LIMITE_IDS,
        "acao_recomendada": acao_recomendada,
    }


# ── Consultas de dependente órfão lógico ─────────────────────────────────────
# Padrão: filho vivo (deleted_at IS NULL) cujo caso pai foi excluído
# logicamente. O JOIN é obrigatório — é exatamente o vínculo que faltava nas
# agregações e produzia os falsos positivos.

def _sql_dependente_de_caso_excluido(tabela: str) -> str:
    return f"""
        SELECT f.id FROM {tabela} f
        JOIN cases c ON c.id = f.case_id
        WHERE f.deleted_at IS NULL AND c.deleted_at IS NOT NULL
        ORDER BY f.id
    """


def _sql_dependente_de_caso_inexistente(tabela: str) -> str:
    return f"""
        SELECT f.id FROM {tabela} f
        LEFT JOIN cases c ON c.id = f.case_id
        WHERE f.deleted_at IS NULL AND f.case_id IS NOT NULL AND c.id IS NULL
        ORDER BY f.id
    """


async def diagnosticar_integridade(db: AsyncSession) -> dict[str, Any]:
    """Relatório completo de integridade. Somente leitura.

    Devolve `{gerado_em, achados: [...], contadores: {...}, resumo: {...}}`.
    Cada achado traz tipo, entidade, entidade pai, estado do pai, severidade,
    total, ids (truncados) e ação recomendada.
    """
    achados: list[dict[str, Any]] = []

    # 1-4. Dependentes vivos de caso excluído logicamente — a causa dos
    # contadores fantasma. NÃO devem ser apagados: a correção é de
    # visibilidade (core/status_caso.py), não de dados.
    for tabela, tipo, entidade, severidade, acao in (
        ("legal_docs", "peca_de_caso_excluido", "legal_docs", "alta",
         "Nenhuma exclusão. A peça deve herdar a invisibilidade do caso nas "
         "superfícies operacionais; restaurar o caso a traz de volta."),
        ("documents", "documento_de_caso_excluido", "documents", "alta",
         "Nenhuma exclusão. Avaliar se o documento deve ser reclassificado "
         "para o GED geral ou seguir a visibilidade do caso."),
        ("deadlines", "prazo_de_caso_excluido", "deadlines", "critica",
         "Nenhuma exclusão. Prazo vivo de caso excluído pode gerar alerta "
         "fantasma OU esconder prazo real — exige conferência humana."),
        ("tasks", "tarefa_de_caso_excluido", "tasks", "media",
         "Nenhuma exclusão. Reatribuir ou encerrar a tarefa conforme decisão "
         "do responsável."),
    ):
        achados.append(await _achado(
            db, tipo=tipo, sql=_sql_dependente_de_caso_excluido(tabela),
            entidade=entidade, entidade_pai="cases", estado_pai="excluido",
            severidade=severidade, acao_recomendada=acao,
        ))

    # 5-8. Sentinela de orfandade FÍSICA. Esperado zero enquanto as FKs
    # existirem; qualquer valor > 0 indica FK removida ou dado carregado por
    # fora do ORM, e é achado grave.
    for tabela, tipo in (
        ("legal_docs", "peca_com_caso_inexistente"),
        ("documents", "documento_com_case_id_invalido"),
        ("deadlines", "prazo_com_case_id_invalido"),
        ("tasks", "tarefa_com_referencia_invalida"),
    ):
        achados.append(await _achado(
            db, tipo=tipo, sql=_sql_dependente_de_caso_inexistente(tabela),
            entidade=tabela, entidade_pai="cases", estado_pai="inexistente",
            severidade="critica",
            acao_recomendada=(
                "Esperado zero: há FK real para cases.id. Valor diferente de "
                "zero indica FK ausente ou carga fora do ORM — investigar a "
                "migration mais recente antes de qualquer correção de dados."
            ),
        ))

    # 9. Caso vivo cujo cliente foi excluído logicamente.
    achados.append(await _achado(
        db, tipo="caso_com_cliente_excluido",
        sql="""
            SELECT c.id FROM cases c
            JOIN clients cl ON cl.id = c.client_id
            WHERE c.deleted_at IS NULL AND cl.deleted_at IS NOT NULL
            ORDER BY c.id
        """,
        entidade="cases", entidade_pai="clients", estado_pai="excluido",
        severidade="alta",
        acao_recomendada=(
            "Nenhuma exclusão. Caso ativo sem cliente visível trava atendimento "
            "e cobrança — restaurar o cliente ou reatribuir a titularidade."
        ),
    ))

    # 10. Caso vivo apontando para cliente inexistente (sentinela de FK).
    achados.append(await _achado(
        db, tipo="caso_com_cliente_inexistente",
        sql="""
            SELECT c.id FROM cases c
            LEFT JOIN clients cl ON cl.id = c.client_id
            WHERE c.deleted_at IS NULL AND cl.id IS NULL
            ORDER BY c.id
        """,
        entidade="cases", entidade_pai="clients", estado_pai="inexistente",
        severidade="critica",
        acao_recomendada=(
            "Esperado zero: cases.client_id é NOT NULL com FK para clients.id."
        ),
    ))

    # 11. Documento SEM âncora nenhuma. Aqui mora a distinção que o relatório
    # de auditoria não fazia: documento sem `case_id` é, na esmagadora maioria,
    # legítimo — caixa de entrada, triagem, GED institucional, não classificado.
    # Só vira achado quando não há caso, NEM cliente, NEM quem subiu: aí não há
    # como devolvê-lo a ninguém.
    achados.append(await _achado(
        db, tipo="documento_orfao_invalido",
        sql="""
            SELECT d.id FROM documents d
            WHERE d.deleted_at IS NULL
              AND d.case_id IS NULL
              AND d.client_id IS NULL
              AND (d.uploaded_by IS NULL OR d.uploaded_by = '')
            ORDER BY d.id
        """,
        entidade="documents", entidade_pai=None, estado_pai=None,
        severidade="media",
        acao_recomendada=(
            "Nenhuma exclusão. Documento sem caso, sem cliente e sem autor: "
            "classificar manualmente ou mover para o GED institucional. "
            "Documento sem caso mas COM cliente ou autor é triagem legítima e "
            "não aparece aqui."
        ),
    ))

    contadores = await _conferir_contadores(db)
    if contadores["divergente"]:
        achados.append({
            "tipo": "divergencia_contador_agregado_vs_listagem",
            "entidade": "cases",
            "entidade_pai": None,
            "estado_pai": None,
            "severidade": "alta",
            "total": 1,
            "ids": [],
            "truncado": False,
            "acao_recomendada": (
                "Dashboard e listagem devem derivar de core/status_caso.py. "
                "Divergência aqui significa que alguma agregação voltou a "
                "definir 'ativo' por conta própria."
            ),
            "detalhe": contadores,
        })

    total_achados = sum(a["total"] for a in achados)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "somente_leitura": True,
        "achados": achados,
        "contadores": contadores,
        "resumo": {
            "tipos_com_achado": [a["tipo"] for a in achados if a["total"]],
            "total_registros_afetados": total_achados,
            "integro": total_achados == 0,
        },
    }


async def _conferir_contadores(db: AsyncSession) -> dict[str, Any]:
    """Compara as definições de contagem de casos. Somente leitura.

    `ativos_agregado` replica a definição canônica (status abertos) e
    `ativos_por_subtracao` replica a antiga (`total - fechados`). Enquanto o
    enum tiver exatamente estes seis valores, as duas coincidem — a checagem
    existe para acusar o dia em que um status novo entrar e alguma agregação
    voltar a classificá-lo como ativo por omissão.
    """
    from app.core.status_caso import STATUS_ABERTOS, STATUS_FECHADOS

    abertos = [s.value for s in STATUS_ABERTOS]
    fechados = [s.value for s in STATUS_FECHADOS]

    linha = (await db.execute(text("""
        SELECT
          COUNT(*)                                              AS total,
          COUNT(*) FILTER (WHERE status = ANY(:abertos))        AS ativos,
          COUNT(*) FILTER (WHERE status = ANY(:fechados))       AS fechados,
          COUNT(*) FILTER (WHERE status = 'arquivado')          AS arquivados
        FROM cases WHERE deleted_at IS NULL
    """), {"abertos": abertos, "fechados": fechados})).one()

    excluidos = (await db.execute(
        text("SELECT COUNT(*) FROM cases WHERE deleted_at IS NOT NULL")
    )).scalar() or 0
    listagem_padrao = (await db.execute(text(
        "SELECT COUNT(*) FROM cases WHERE deleted_at IS NULL "
        "AND status <> 'arquivado'"
    ))).scalar() or 0

    total, ativos, fechados_n, arquivados = linha
    por_subtracao = total - fechados_n
    return {
        "total_geral": total,
        "total_ativo": ativos,
        "total_arquivado": arquivados,
        "total_excluido": excluidos,
        "total_listagem_padrao": listagem_padrao,
        "ativos_agregado": ativos,
        "ativos_por_subtracao": por_subtracao,
        "divergente": ativos != por_subtracao,
    }
