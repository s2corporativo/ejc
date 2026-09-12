# ── app/services/ai_core_hardening_patch.py ──────────────────────────────────
"""Hardening aditivo do núcleo de IA/RAG carregado no startup.

Correções transitórias de compatibilidade:
1. conexão do ProviderRegistry único ao runtime;
2. resolução de provedores fail-closed para todos os aliases legados de `chat`;
3. resolução server-side do escopo de precedentes de encerramento cuja chave
   canônica é `caso:<id>`, fluxo legado que não passava client_id ao RAG;
4. listagem de KnowledgeDoc escopada, evitando exposição de títulos/fontes de
   peças internas a usuários sem acesso ao caso ou cliente correspondente;
5. HyDE estritamente local: a expansão da consulta nunca usa provedor externo,
   inclusive quando o caller não propagou o escopo de sigilo do caso.

As correções operam em primitivas consultadas em runtime, alcançando call sites
que importaram funções antes do startup. A convergência definitiva deve eliminar
os adapters ao centralizar contratos de provider, ingestão e ownership.
"""
from __future__ import annotations

import functools
import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger("ejc.ai.core.hardening")
_INSTALADO = False


def _instalar_provider_registry() -> None:
    """Conecta a fonte única de providers antes de instalar o fail-closed."""
    from app.services.ai.provider_registry_runtime import instalar
    instalar()


def _instalar_resolver_provedores() -> None:
    from app.services import ai_gateway

    if getattr(ai_gateway, "_ejc_fail_closed_resolver_installed", False):
        return

    original = ai_gateway._resolver_cadeia

    def resolver_fail_closed(
        task_type: str,
        provider_force: str | None,
        model_override: str | None,
        provider_preferido: str | None = None,
        model_preferido: str | None = None,
    ) -> list[tuple[str, str | None]]:
        cadeia = original(
            task_type,
            provider_force,
            model_override,
            provider_preferido,
            model_preferido,
        )
        seguros = [
            (provider, model)
            for provider, model in cadeia
            if ai_gateway._provider_elegivel(provider)
        ]
        if cadeia and not seguros:
            logger.warning(
                "Cadeia de IA esvaziada pelo gate de elegibilidade "
                "(task=%s); nenhum provider será chamado.",
                task_type,
            )
        return seguros

    ai_gateway._resolver_cadeia = resolver_fail_closed
    ai_gateway._ejc_fail_closed_resolver_installed = True


def _instalar_resolucao_escopo_rag() -> None:
    """Protege o precedente interno cuja identidade canônica é ``caso:<id>``.

    Para esse padrão, o próprio ``Case`` carregado server-side é a única fonte
    de verdade do escopo. ``client_id``/``case_id`` ausentes são preenchidos;
    valores explícitos só são aceitos quando coincidem exatamente com o caso.
    Caso inexistente, deletado ou sem cliente é recusado antes do upsert — nunca
    há fallback global nem possibilidade de criar precedente órfão/cross-client.

    O precedente do encerramento é memória institucional ACESSÓRIA: uma falha de
    embedding/RAG não pode transformar em HTTP 500 um encerramento juridicamente
    válido. Depois de validar o escopo canônico, o upsert roda em SAVEPOINT
    (``begin_nested``). Se ele falhar, só o trabalho do RAG é revertido; a
    transação externa continua apta a registrar movimento, auditoria e commit.
    Chaves não canônicas permanecem submetidas ao comportamento normal do
    ``ingestion_service`` e não recebem tolerância ou escopo inventado.
    """
    from app.services import ingestion_service

    if getattr(ingestion_service, "_ejc_scope_resolver_installed", False):
        return

    original = ingestion_service.upsert_documento

    # functools.wraps preserva a assinatura ORIGINAL para inspect.signature
    # (via __wrapped__) — o wrapper usa **kwargs mas repassa tudo (inclusive
    # `confianca`) ao original; sem isso a introspecção da assinatura some.
    @functools.wraps(original)
    async def upsert_com_escopo_canonico(db, **kwargs):
        categoria = kwargs.get("categoria")
        chave = str(kwargs.get("chave_origem") or "")
        escopo_canonico_resolvido = False

        if categoria == "precedente_interno" and chave.startswith("caso:"):
            case_id_chave = chave.removeprefix("caso:").strip()
            if not case_id_chave:
                raise ValueError("chave canônica de precedente sem identificador de caso")

            from app.models.case import Case

            case = await db.get(Case, case_id_chave)
            if case is None or case.deleted_at is not None or not case.client_id:
                raise ValueError("caso canônico inválido para precedente interno")

            client_id_canonico = str(case.client_id)
            case_id_canonico = str(case.id)
            client_id_informado = kwargs.get("client_id")
            case_id_informado = kwargs.get("case_id")

            if client_id_informado is not None and str(client_id_informado) != client_id_canonico:
                raise ValueError("client_id divergente do caso canônico")
            if case_id_informado is not None and str(case_id_informado) != case_id_canonico:
                raise ValueError("case_id divergente da chave canônica")

            kwargs["client_id"] = client_id_canonico
            kwargs["case_id"] = case_id_canonico
            escopo_canonico_resolvido = True
            logger.info("Escopo RAG canônico resolvido para precedente interno")

        if not escopo_canonico_resolvido:
            # Chave não canônica não ganha escopo nem semântica tolerante.
            return await original(db, **kwargs)

        try:
            # SAVEPOINT: erro de RAG não invalida a transação externa do
            # encerramento. O SQLAlchemy reverte somente este bloco.
            async with db.begin_nested():
                return await original(db, **kwargs)
        except Exception as exc:
            # Não logar conteúdo, chave, cliente, caso, prompt ou mensagem bruta
            # da exceção. A trilha técnica precisa apenas da classe do erro.
            logger.warning(
                "Precedente interno não persistido no encerramento; "
                "transação principal preservada (erro=%s)",
                type(exc).__name__,
            )
            return "falha_acessoria"

    ingestion_service.upsert_documento = upsert_com_escopo_canonico
    ingestion_service._ejc_scope_resolver_installed = True


def _instalar_hyde_local_fail_closed() -> None:
    """Impõe piso LOCAL_COMPLETO a toda expansão HyDE.

    HyDE recebe a própria consulta jurídica do usuário. Como alguns call sites
    históricos não propagam o sigilo do caso até a função de expansão, tentar
    decidir aqui entre externo/local seria fail-open. O hardening escolhe a
    política conservadora: HyDE é sempre local. Se o provider local estiver
    indisponível, a expansão falha graciosamente e a busca usa a consulta
    original; nunca há fallback externo.
    """
    from app.services import ai_service
    from app.services.ai.sanitization_policy import ModoSanitizacao

    if getattr(ai_service, "_ejc_hyde_local_only_installed", False):
        return

    original = ai_service._hyde_expandir

    @functools.wraps(original)
    async def hyde_local_only(consulta: str) -> str:
        if not getattr(ai_service.settings, "RAG_HYDE_ENABLED", False) or not (
            consulta or ""
        ).strip():
            return consulta
        try:
            resp = await ai_service.gw_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um assistente juridico. Escreva UM paragrafo curto "
                            "(max. 3 frases) que responderia hipoteticamente a consulta, "
                            "no vocabulario tecnico-juridico brasileiro (dispositivos, "
                            "teses, termos). NAO invente numero de processo, sumula ou "
                            "lei especificos — use linguagem doutrinaria generica."
                        ),
                    },
                    {"role": "user", "content": consulta[:1000]},
                ],
                task_type="resumo",
                temperature=0.3,
                max_tokens=256,
                nivel_inteligencia="padrao",
                modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO,
            )
            hipotese = (getattr(resp, "texto", "") or "").strip()
            return f"{consulta}\n{hipotese}" if hipotese else consulta
        except Exception as exc:
            # Não registrar consulta, conteúdo do caso ou mensagem bruta da exceção.
            logger.warning(
                "HyDE local indisponivel; consulta original preservada (erro=%s)",
                type(exc).__name__,
            )
            return consulta

    ai_service._hyde_expandir = hyde_local_only
    ai_service._ejc_hyde_local_only_installed = True


async def _listar_docs_escopado(
    page: int = 1,
    page_size: int = 20,
    categoria: str | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Contrato seguro de GET /rag/docs.

    Gestão (sócio+) mantém visão integral para curadoria. Demais usuários veem:
    conteúdo público; conteúdo do próprio cliente externo; e documentos ligados
    a casos nos quais são responsável/auxiliar ou que permanecem sem atribuição,
    exatamente conforme a salvaguarda do ownership canônico.
    """
    from sqlalchemy import and_, func as sqlfunc, or_, select
    from app.core.ownership import is_gestao
    from app.models.case import Case
    from app.models.rag import KnowledgeDoc

    q = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    if not is_gestao(cu):
        visibilidade = [KnowledgeDoc.client_id.is_(None)]
        client_id = getattr(cu, "client_id", None)
        if client_id:
            visibilidade.append(KnowledgeDoc.client_id == client_id)

        casos_permitidos = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == getattr(cu, "id", None),
                Case.advogado_auxiliar_id == getattr(cu, "id", None),
                and_(
                    Case.advogado_responsavel_id.is_(None),
                    Case.advogado_auxiliar_id.is_(None),
                ),
            ),
        )
        visibilidade.append(KnowledgeDoc.case_id.in_(casos_permitidos))
        q = q.where(or_(*visibilidade))

    if categoria:
        q = q.where(KnowledgeDoc.categoria == categoria)
    q = q.order_by(KnowledgeDoc.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {
                "id": d.id,
                "titulo": d.titulo,
                "categoria": d.categoria,
                "fonte": d.fonte,
                "tribunal": d.tribunal,
                "status_indexacao": d.status_indexacao,
                "created_at": d.created_at,
            }
            for d in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _instalar_listagem_rag_escopada() -> None:
    """Substitui o callable da rota antes de o router ser incluído no FastAPI.

    IMPORTANTE: apenas trocar route.endpoint/remove o analisador de
    dependências (Depends) do endpoint original, deixando `db` e `cu` como
    `None` em runtime (bug que derrubava GET /rag/docs com 500). Por isso
    o endpoint substituto declara explicitamente as mesmas dependências
    (get_db e get_current_user) no topo do módulo.
    """
    from app.routers import rag

    if getattr(rag.router, "_ejc_docs_scope_installed", False):
        return

    encontrada = False
    for route in rag.router.routes:
        if getattr(route, "name", "") == "listar_docs":
            route.endpoint = _listar_docs_escopado
            if route.dependant is not None:
                route.dependant.call = _listar_docs_escopado
            encontrada = True
            break
    if not encontrada:
        raise RuntimeError("Rota listar_docs do RAG não localizada para hardening")

    setattr(rag.router, "_ejc_docs_scope_installed", True)
    logger.info("Listagem de KnowledgeDoc protegida por escopo de acesso")


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    _instalar_provider_registry()
    _instalar_resolver_provedores()
    _instalar_resolucao_escopo_rag()
    _instalar_hyde_local_fail_closed()
    _instalar_listagem_rag_escopada()
    _INSTALADO = True
    logger.info("Hardening do núcleo de IA/RAG instalado")