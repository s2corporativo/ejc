from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redesign import ModuleHelp


DEFAULT_HELP_TOPICS: list[dict[str, object]] = [
    {
        "module_key": "clientes",
        "titulo": "Como usar o módulo Clientes",
        "conteudo_md": "Use este módulo para cadastrar clientes, consultar dados básicos e iniciar a organização do relacionamento. Antes de criar um caso, confira nome, CPF/CNPJ, contato e possível conflito de interesses.",
        "ordem": 10,
    },
    {
        "module_key": "casos",
        "titulo": "Como usar o módulo Casos",
        "conteudo_md": "Use este módulo para criar, acompanhar e organizar casos judiciais, extrajudiciais e consultivos. Mantenha área jurídica, parte contrária, responsável, status e documentos sempre atualizados.",
        "ordem": 10,
    },
    {
        "module_key": "documentos",
        "titulo": "Como usar o módulo Documentos",
        "conteudo_md": "Use este módulo para enviar, consultar e organizar documentos. Arquivos com OCR podem alimentar a análise jurídica por IA. Sempre revise os dados extraídos antes de usar em peças ou decisões internas.",
        "ordem": 10,
    },
    {
        "module_key": "prazos",
        "titulo": "Como usar o módulo Prazos",
        "conteudo_md": "Use este módulo para acompanhar vencimentos processuais e tarefas com data. Confira prazos críticos diariamente e registre ciência, responsável e conclusão quando aplicável.",
        "ordem": 10,
    },
    {
        "module_key": "tarefas",
        "titulo": "Como usar o módulo Tarefas",
        "conteudo_md": "Use este módulo para organizar atividades internas do escritório. Toda tarefa deve ter responsável, prazo, prioridade e vínculo com caso ou cliente quando possível.",
        "ordem": 10,
    },
    {
        "module_key": "financeiro",
        "titulo": "Como usar o módulo Financeiro",
        "conteudo_md": "Use este módulo para acompanhar receitas, despesas, honorários, recebimentos e pendências. A boa prática é vincular lançamentos a clientes, casos e competência correta.",
        "ordem": 10,
    },
    {
        "module_key": "honorarios",
        "titulo": "Como usar Honorários",
        "conteudo_md": "Use este módulo para cadastrar contratos, parcelas, êxito, sucumbência e controle de recebimentos. Sugestões de valores devem ser revisadas conforme tabela aplicável e decisão do advogado responsável.",
        "ordem": 10,
    },
    {
        "module_key": "ia",
        "titulo": "Como usar a IA Jurídica",
        "conteudo_md": "Use a IA como apoio analítico para triagem, estratégia, resumo e revisão. Toda resposta deve ser revisada por humano antes de virar peça, orientação ao cliente ou decisão profissional.",
        "ordem": 10,
    },
    {
        "module_key": "conhecimento",
        "titulo": "Como usar a Base de Conhecimento",
        "conteudo_md": "Use a base de conhecimento para alimentar o RAG com teses, leis, jurisprudência, peças e materiais internos. Conteúdo bem classificado melhora a qualidade das respostas da IA.",
        "ordem": 10,
    },
    {
        "module_key": "auditoria",
        "titulo": "Como usar Auditoria",
        "conteudo_md": "Use a auditoria para rastrear ações relevantes no sistema, como criação, edição, exclusão, download, login e uso de IA. Este módulo apoia governança, LGPD e controle interno.",
        "ordem": 10,
    },
    {
        "module_key": "usuarios",
        "titulo": "Como administrar Usuários",
        "conteudo_md": "Use este módulo para gerir acessos, papéis e permissões. Conceda apenas o nível necessário para cada função e revise usuários periodicamente.",
        "ordem": 10,
    },
    {
        "module_key": "autofix",
        "titulo": "Como usar o Diagnóstico do Sistema",
        "conteudo_md": "Use o diagnóstico para identificar módulos sem manual, rotas críticas e pontos que exigem revisão técnica. Nesta fase, o recurso é somente leitura e não altera dados ou código.",
        "ordem": 10,
    },
]


async def seed_module_help_minimo(db: AsyncSession, user_id: str | None = None) -> dict[str, int]:
    criados = 0
    existentes = 0

    for item in DEFAULT_HELP_TOPICS:
        module_key = str(item["module_key"])
        titulo = str(item["titulo"])
        existente = (await db.execute(
            select(ModuleHelp).where(
                ModuleHelp.module_key == module_key,
                ModuleHelp.titulo == titulo,
            )
        )).scalar_one_or_none()
        if existente:
            existentes += 1
            continue
        db.add(ModuleHelp(
            id=str(uuid4()),
            atualizado_por=user_id,
            module_key=module_key,
            titulo=titulo,
            conteudo_md=str(item["conteudo_md"]),
            ordem=int(item.get("ordem", 10)),
            ativo=True,
        ))
        criados += 1

    if criados:
        await db.commit()

    return {"criados": criados, "existentes": existentes, "total": len(DEFAULT_HELP_TOPICS)}
