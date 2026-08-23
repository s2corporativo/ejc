"""
seed_banco_teses.py
───────────────────────────────────────────────────────────────────────
Script de seed para popular o Banco Nacional de Teses Jurídicas.
Popula taxonomias, teses iniciais e precedentes de exemplo.

Executar: python backend/seeds/seed_banco_teses.py
"""
import asyncio
import json
from uuid import uuid4
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, '/home/user/ejc/backend')

from app.core.database import Base, DATABASE_URL
from app.models.tese_juridica import (
    Taxonomia, TeseJuridica, FundamentacaoLegal, Precedente,
    TipoTese, StatusTese
)


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

# Teses de exemplo (ataque/defesa)
TESES_EXEMPLO = [
    {
        "titulo": "Responsabilidade objetiva da instituição financeira por fraude decorrente de fortuito interno",
        "sumario": "Bancos são responsáveis por fraudes e delitos praticados por terceiros em operações bancárias.",
        "tipo": TipoTese.ataque,
        "parte_favorecida": "Consumidor",
        "procedimento": "Ação ordinária",
        "instancia": "1ª Instância",
        "tese_texto": "Instituições financeiras respondem objetivamente pelos danos gerados por fortuito interno relativo a fraudes e delitos praticados por terceiros em operações bancárias.",
        "argumento": "O fortuito interno é evento inerente ao risco da atividade financeira. CDC arts. 2º e 3º estabelecem responsabilidade objetiva do fornecedor de serviço. Súmula 479/STJ consolidou o entendimento.",
        "pressupostos": "Vítima é consumidor da instituição. Fraude foi cometida em operação bancária. Banco não provou culpa exclusiva do cliente.",
        "excecoes": "Se houver prova de fortuito externo (evento sem relação com atividade bancária) ou culpa exclusiva do cliente (art. 14, §3º CDC).",
        "estrategia": "Enfatizar falhas de segurança do banco, ausência de notificações, diferenças fundamentais entre fortuito interno e externo.",
        "taxonomia_index": 4,
        "score": 85,
        "precedente_chave": {
            "tribunal": "STJ",
            "numero": "1197929",
            "classe": "REsp",
            "ementa_resumida": "Tema Repetitivo 466 — Responsabilidade objetiva por fortuito interno",
            "tipo_relacao": "favoravel",
            "vinculante": True,
        }
    },
    {
        "titulo": "Dano moral por inclusão indevida em cadastro restritivo com anotação anterior legítima",
        "sumario": "Exceção à Súmula 385/STJ quando inscrições anteriores também são contestadas.",
        "tipo": TipoTese.ataque,
        "parte_favorecida": "Consumidor",
        "procedimento": "Ação ordinária",
        "instancia": "1ª Instância",
        "tese_texto": "É cabível indenização por dano moral decorrente da inscrição indevida em cadastro restritivo, ainda que exista anotação prévia legítima, quando as inscrições anteriores forem contestadas judicialmente.",
        "argumento": "Flexibilização jurisprudencial da Súmula 385/STJ em casos de círculo vicioso: consumidor fica impossibilitado de se livrar da restrição.",
        "pressupostos": "Consumidor anotado indevidamente. Existem inscrições preexistentes. O consumidor contesta judicialmente as dívidas anteriores.",
        "excecoes": "Se há inscrição anterior legitimamente reconhecida em decisão transitada em julgado.",
        "estrategia": "Caracterizar círculo vicioso; demonstrar que consumidor agiu com boa-fé ao questionar dívidas.",
        "taxonomia_index": 1,
        "score": 55,
        "precedente_chave": {
            "tribunal": "STJ",
            "numero": "1704002",
            "classe": "REsp",
            "ementa_resumida": "Afastamento da Súmula 385 em situações excepcionais",
            "tipo_relacao": "favoravel",
            "vinculante": False,
        }
    },
    {
        "titulo": "Revisão de contrato bancário por juros abusivos e capitalização de juros",
        "sumario": "Juros remuneratórios acima de 2% a.m. e capitalização são passíveis de revisão.",
        "tipo": TipoTese.ataque,
        "parte_favorecida": "Devedor/Consumidor",
        "procedimento": "Ação revisional",
        "instancia": "1ª Instância",
        "tese_texto": "Contrato bancário com juros remuneratórios acima de 2% a.m. é presumivelmente abusivo e passível de revisão judicial.",
        "argumento": "Súmula 532/STJ: taxa de juros remuneratórios superior a 2% a.m. é abusiva. Capitalização de juros é vedada (Lei 11.977/2009 art. 5º).",
        "pressupostos": "Contrato bancário de crédito. Taxa acima de 2% a.m. comprovada. Capitalização mensal ou diária.",
        "excecoes": "Contrato anterior a lei. Operações de crédito pessoal (juros mais altos são permitidos).",
        "estrategia": "Compilar extratos bancários mostrando capitalização. Demonstrar taxa média supera 2%.",
        "taxonomia_index": 8,
        "score": 75,
        "precedente_chave": {
            "tribunal": "STJ",
            "numero": "532",
            "classe": "Súmula",
            "ementa_resumida": "Súmula 532/STJ — Taxa de juros remuneratórios acima de 2% a.m. é abusiva",
            "tipo_relacao": "favoravel",
            "vinculante": True,
        }
    },
]


async def seed_banco_teses():
    """Popula taxonomias e teses iniciais."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Limpar dados existentes (APENAS EM DEV)
        # await session.execute("TRUNCATE TABLE teses_juridicas CASCADE")
        # await session.commit()

        print("📚 Seeding Banco de Teses Jurídicas...")

        # 1. Criar taxonomias
        print(f"  → Criando {len(TAXONOMIAS_INICIAIS)} taxonomias...")
        taxonomias_map = {}
        for tax_data in TAXONOMIAS_INICIAIS:
            stmt = select(Taxonomia).where(
                Taxonomia.area == tax_data["area"],
                Taxonomia.subarea == tax_data["subarea"],
                Taxonomia.tema == tax_data["tema"],
            )
            existente = await session.scalar(stmt)
            if existente:
                taxonomias_map[f"{tax_data['area']}/{tax_data['subarea']}/{tax_data['tema']}"] = existente.id
            else:
                tax = Taxonomia(**tax_data)
                session.add(tax)
                await session.flush()
                taxonomias_map[f"{tax_data['area']}/{tax_data['subarea']}/{tax_data['tema']}"] = tax.id

        await session.commit()
        print(f"    ✓ {len(taxonomias_map)} taxonomias criadas/atualizadas")

        # 2. Criar teses de exemplo
        print(f"  → Criando {len(TESES_EXEMPLO)} teses de exemplo...")
        for i, tese_data in enumerate(TESES_EXEMPLO):
            taxonomia_id = list(taxonomias_map.values())[tese_data["taxonomia_index"]]
            precedente_data = tese_data.pop("precedente_chave")

            tese = TeseJuridica(
                **{k: v for k, v in tese_data.items() if k != "taxonomia_index"},
                taxonomia_id=taxonomia_id,
                status=StatusTese.validada,
            )
            session.add(tese)
            await session.flush()

            # Adicionar fundamentações
            fund1 = FundamentacaoLegal(
                tese_id=tese.id,
                norma="CDC",
                artigo="2",
                tipo="federal",
                texto_relevante="Consumidor é toda pessoa física ou jurídica que adquire ou utiliza produto ou serviço.",
                interpretacao="Consumidor é protegido pelas normas do CDC.",
            )
            fund2 = FundamentacaoLegal(
                tese_id=tese.id,
                norma="CDC",
                artigo="14",
                tipo="federal",
                texto_relevante="O fornecedor de serviços responde, independentemente de culpa, pela reparação dos danos causados...",
                interpretacao="Responsabilidade objetiva do fornecedor.",
            )
            session.add(fund1)
            session.add(fund2)

            # Adicionar precedente chave
            precedente = Precedente(
                tese_id=tese.id,
                tribunal=precedente_data["tribunal"],
                numero=precedente_data["numero"],
                classe=precedente_data["classe"],
                ementa_resumida=precedente_data["ementa_resumida"],
                tipo_relacao=precedente_data["tipo_relacao"],
                vinculante=precedente_data["vinculante"],
                fonte="stj",
                fonte_url="https://www.stj.jus.br",  # URL será preenchida com scraping real
            )
            session.add(precedente)
            await session.flush()

        await session.commit()
        print(f"    ✓ {len(TESES_EXEMPLO)} teses criadas")

        # 3. Estatísticas
        stmt = select(func.count(Taxonomia.id))
        tax_count = await session.scalar(stmt)
        stmt = select(func.count(TeseJuridica.id))
        tese_count = await session.scalar(stmt)

        print(f"\n✅ Seed concluído!")
        print(f"   Taxonomias: {tax_count}")
        print(f"   Teses: {tese_count}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_banco_teses())
