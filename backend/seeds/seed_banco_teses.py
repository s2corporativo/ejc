"""
seed_banco_teses.py
───────────────────────────────────────────────────────────────────────
Script de seed para popular o Banco Nacional de Teses Jurídicas.
Popula taxonomias, teses iniciais e precedentes de exemplo.

Executar: python backend/seeds/seed_banco_teses.py
"""
import asyncio
import logging
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, '/home/user/ejc/backend')

from app.core.config import get_settings
from app.models.tese_juridica import (
    Taxonomia, TeseJuridica, FundamentacaoLegal, Precedente,
    TipoTese, StatusTese
)
from app.services.teses_coleta import TeseColeta, inserir_tese_no_banco

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Dados iniciais de taxonomias
TAXONOMIAS_INICIAIS = [
    # Consumidor
    {"area": "Consumidor", "subarea": "Crédito", "tema": "Negativação Indevida", "subtema": None},
    {"area": "Consumidor", "subarea": "Crédito", "tema": "Dano Moral por Negativação", "subtema": None},
    {"area": "Consumidor", "subarea": "Crédito", "tema": "Juros e Multa Abusiva", "subtema": None},
    {"area": "Consumidor", "subarea": "Bancário", "tema": "Fraude Bancária - Responsabilidade", "subtema": None},
    {"area": "Consumidor", "subarea": "Bancário", "tema": "Fortuito Interno do Banco", "subtema": None},

    # Bancário
    {"area": "Bancário", "subarea": "Contratos", "tema": "Revisão de Juros", "subtema": None},
    {"area": "Bancário", "subarea": "Contratos", "tema": "Capitalização de Juros", "subtema": None},
    {"area": "Bancário", "subarea": "Contratos", "tema": "Comissão de Permanência Abusiva", "subtema": None},

    # Juizados Especiais
    {"area": "Juizados Especiais", "subarea": "Cobranças", "tema": "Cobrança em JEC", "subtema": None},
    {"area": "Juizados Especiais", "subarea": "Cobranças", "tema": "Valor da Causa em JEC", "subtema": None},

    # Civil
    {"area": "Civil", "subarea": "Contratos", "tema": "Vício Redibitório", "subtema": None},
    {"area": "Civil", "subarea": "Contratos", "tema": "Revisão por Onerosidade Excessiva", "subtema": None},

    # Trabalhista
    {"area": "Trabalhista", "subarea": "Vínculo", "tema": "Reconhecimento Vínculo PJ", "subtema": None},
    {"area": "Trabalhista", "subarea": "Vínculo", "tema": "Grupo Econômico", "subtema": None},
    {"area": "Trabalhista", "subarea": "Vínculo", "tema": "Pejotização", "subtema": None},
]

# Teses de exemplo — Dados de exemplo com ADVERTÊNCIA
# ⚠️  ESTAS TESES SÃO RASCUNHO E PRECISAM DE VALIDAÇÃO HUMANA
# Nenhuma delas é promovida automaticamente a status=validada.
# Antes de qualquer uso em jurisprudência ou aconselhamento, confirme contra fontes oficiais.

TESES_EXEMPLO = []  # Seed não popula mais teses de exemplo — use apenas TeseColeta.buscar_* methods


async def criar_taxonomia(session: AsyncSession, area: str, subarea: str, tema: str) -> str:
    """Cria ou recupera taxonomia existente."""
    stmt = select(Taxonomia).where(
        Taxonomia.area == area,
        Taxonomia.subarea == subarea,
        Taxonomia.tema == tema,
    )
    existente = await session.scalar(stmt)
    if existente:
        return existente.id

    taxa = Taxonomia(
        id=str(uuid4()),
        area=area,
        subarea=subarea,
        tema=tema,
        subtema=None,
        criada_em=datetime.now(timezone.utc),
    )
    session.add(taxa)
    await session.flush()
    return taxa.id


async def popular_dominio(
    session: AsyncSession,
    area: str,
    subarea: str,
    tema: str,
    coleta_func,
) -> int:
    """Popula um domínio específico de teses."""
    taxa_id = await criar_taxonomia(session, area, subarea, tema)
    teses = await coleta_func(session)

    count = 0
    for tese_dict in teses:
        try:
            await inserir_tese_no_banco(
                db=session,
                titulo=tese_dict.get("titulo"),
                sumario=tese_dict.get("sumario", ""),
                tipo=tese_dict.get("tipo", TipoTese.ataque),
                score=tese_dict.get("score", 50),
                taxonomia_id=taxa_id,
                fundamentacoes=tese_dict.get("fundamentacoes", []),
                precedentes=tese_dict.get("precedentes", []),
            )
            count += 1
            logger.info(f"  ✓ {tese_dict.get('titulo')}")
        except Exception as e:
            logger.error(f"  ❌ Erro ao inserir {tese_dict.get('titulo')}: {e}")

    await session.commit()
    return count


async def seed_banco_teses():
    """Popula taxonomias e teses de todos os domínios."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        logger.info("\n" + "="*70)
        logger.info("🎯 INICIANDO SEED DO BANCO NACIONAL DE TESES JURÍDICAS")
        logger.info("="*70 + "\n")

        # 1. Criar taxonomias base
        logger.info("📚 Criando taxonomias...")
        for tax_data in TAXONOMIAS_INICIAIS:
            await criar_taxonomia(session, tax_data["area"], tax_data["subarea"], tax_data["tema"])
        await session.commit()
        logger.info(f"  ✓ {len(TAXONOMIAS_INICIAIS)} taxonomias criadas\n")

        # 2. Popular domínios via TeseColeta
        logger.info("📖 Populando teses de Consumidor...")
        count = await popular_dominio(
            session,
            "Consumidor",
            "Negativação/Bancário",
            "Jurisprudência STJ",
            TeseColeta.buscar_teses_consumidor,
        )
        logger.info(f"  ✅ {count} teses de Consumidor carregadas\n")

        logger.info("📖 Populando teses de Trabalhista...")
        count = await popular_dominio(
            session,
            "Trabalhista",
            "Vínculo/Terceirização",
            "Jurisprudência TST",
            TeseColeta.buscar_teses_trabalhista,
        )
        logger.info(f"  ✅ {count} teses de Trabalhista carregadas\n")

        logger.info("📖 Populando teses de Juizados Especiais...")
        count = await popular_dominio(
            session,
            "Juizados Especiais",
            "JEC Cível",
            "Jurisprudência Estadual",
            TeseColeta.buscar_teses_jec,
        )
        logger.info(f"  ✅ {count} teses de JEC carregadas\n")

        # 3. Estatísticas finais
        stmt = select(func.count(Taxonomia.id))
        tax_count = await session.scalar(stmt)
        stmt = select(func.count(TeseJuridica.id))
        tese_count = await session.scalar(stmt)
        stmt = select(func.count(Precedente.id))
        prec_count = await session.scalar(stmt)

        logger.info("="*70)
        logger.info("✅ SEED CONCLUÍDO COM SUCESSO")
        logger.info("="*70)
        logger.info(f"  Taxonomias: {tax_count}")
        logger.info(f"  Teses: {tese_count}")
        logger.info(f"  Precedentes: {prec_count}\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_banco_teses())
