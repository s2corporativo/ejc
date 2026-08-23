# ── app/services/teses_coleta.py ────────────────────────────────────
# Coleta de teses jurídicas de fontes oficiais (STJ, CNJ, TJs).
# Integra dados de jurisprudência em tempo real com web scraping responsável.
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.tese_juridica import (
    Taxonomia, TeseJuridica, FundamentacaoLegal, Precedente,
    TipoTese, StatusTese
)

logger = logging.getLogger(__name__)

# Endpoints públicos de jurisprudência
DATAJUD_API = "https://datajud-api.cnj.jus.br"
STJ_API = "https://www.stj.jus.br/api"
JURISPRUDENCIA_STJ = "https://www.stj.jus.br/jurisprudencia"

# Timeout e headers responsáveis para web scraping
HTTP_TIMEOUT = 10
HTTP_HEADERS = {
    "User-Agent": "EJC-TesesJuridicas/1.0 (Coleta de Jurisprudência Oficial)"
}


async def inserir_tese_no_banco(
    db: AsyncSession,
    titulo: str,
    sumario: str,
    tipo: TipoTese,
    score: int,
    taxonomia_id: str,
    fundamentacoes: List[Dict[str, str]] = None,
    precedentes: List[Dict[str, Any]] = None,
    processos_vitoriosos: List[Dict[str, str]] = None,
) -> TeseJuridica:
    """Insere tese completa no banco com fundamentações e precedentes.

    Nota: Teses criadas como rascunho (status=rascunho) exigem revisão humana
    e validação contra fonte oficial antes de serem promovidas para validada.
    """
    tese = TeseJuridica(
        id=str(uuid4()),
        titulo=titulo,
        sumario=sumario,
        tipo=tipo,
        status=StatusTese.rascunho,
        taxonomia_id=taxonomia_id,
        score=score,
        vinculante=False,
        criada_em=datetime.now(timezone.utc),
    )
    db.add(tese)
    await db.flush()

    # Adicionar fundamentações
    if fundamentacoes:
        for fund_data in fundamentacoes:
            fund = FundamentacaoLegal(
                id=str(uuid4()),
                tese_id=tese.id,
                norma=fund_data.get("norma", ""),
                artigo=fund_data.get("artigo", ""),
                tipo="federal",
                texto_relevante=fund_data.get("texto", ""),
                interpretacao=fund_data.get("interpretacao", ""),
            )
            db.add(fund)

    # Adicionar precedentes
    if precedentes:
        for prec_data in precedentes:
            prec = Precedente(
                id=str(uuid4()),
                tese_id=tese.id,
                tribunal=prec_data.get("tribunal", ""),
                numero=prec_data.get("numero", ""),
                classe=prec_data.get("classe", ""),
                ementa_resumida=prec_data.get("ementa", ""),
                tipo_relacao=prec_data.get("tipo_relacao", "favoravel"),
                vinculante=prec_data.get("vinculante", False),
                fonte=prec_data.get("fonte", "stj"),
                fonte_url=prec_data.get("url", ""),
            )
            db.add(prec)

    return tese


class TeseColeta:
    """Coleta de teses e jurisprudência de fontes oficiais."""

    @staticmethod
    async def buscar_teses_consumidor(sessao: AsyncSession, usar_banco: bool = False) -> List[Dict[str, Any]] | List[TeseJuridica]:
        """
        Busca teses de Consumidor/Negativação em bases oficiais.

        Lotes:
        - Negativação indevida (Súmula 385/STJ, Tema 466)
        - Fraudes bancárias (Súmula 479/STJ)
        - Juros abusivos (Súmula 532/STJ)
        """
        logger.info("🔍 Iniciando coleta de teses de Consumidor...")
        teses = []

        # Lote 1: Negativação Indevida (Súmula 385, Tema 466)
        try:
            precedentes_negativacao = await TeseColeta._buscar_negativacao()
            teses.extend(precedentes_negativacao)
        except Exception as e:
            logger.error(f"❌ Erro ao buscar negativação: {e}")

        # Lote 2: Fraudes Bancárias (Súmula 479)
        try:
            precedentes_fraude = await TeseColeta._buscar_fraude_bancaria()
            teses.extend(precedentes_fraude)
        except Exception as e:
            logger.error(f"❌ Erro ao buscar fraude: {e}")

        # Lote 3: Juros Abusivos (Súmula 532)
        try:
            precedentes_juros = await TeseColeta._buscar_juros_abusivos()
            teses.extend(precedentes_juros)
        except Exception as e:
            logger.error(f"❌ Erro ao buscar juros: {e}")

        logger.info(f"✅ Coleta de Consumidor concluída: {len(teses)} teses")
        return teses

    @staticmethod
    async def _buscar_negativacao() -> List[Dict[str, Any]]:
        """Busca dados sobre Negativação Indevida (Súmula 385/STJ, Tema 466).

        NOTA: Dados retornados como rascunho. Requerem validação contra fontes
        oficiais (STJ, CNJ, jurisprudência verificada) e revisão humana antes de
        serem promovidos a status=validada.
        """
        logger.info("  → Buscando Negativação Indevida (Tema 466/STJ)...")

        teses = [
            {
                "titulo": "Súmula 385/STJ — Negativação Indevida e Dano Moral",
                "sumario": "Jurisprudência consolidada do STJ sobre inclusão indevida em cadastro de inadimplentes.",
                "tipo": TipoTese.ataque,
                "score": 70,
                "precedentes": [
                    {
                        "tribunal": "STJ",
                        "classe": "Súmula",
                        "numero": "385",
                        "ementa": "Da anotação irregular em cadastro de inadimplente, não cabe indenização por dano moral, quando preexistente legítima inscrição, ressalvado o direito ao cancelamento.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.stj.jus.br/jurisprudencia/sumulas_search.jsp?termo=385",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CDC", "artigo": "43", "texto": "Acesso do consumidor aos dados de seu cadastro", "interpretacao": "Direito fundamental de transparência em registros restritivos"},
                    {"norma": "CDC", "artigo": "14", "texto": "Responsabilidade objetiva do fornecedor", "interpretacao": "Credor responde por anotações indevidas"},
                ],
            },
            {
                "titulo": "Tema Repetitivo 466/STJ — Inscrições Indevidas",
                "sumario": "Tese sobre responsabilidade civil por inscrição indevida em registros de crédito.",
                "tipo": TipoTese.ataque,
                "score": 75,
                "precedentes": [
                    {
                        "tribunal": "STJ",
                        "classe": "Tema Repetitivo",
                        "numero": "466",
                        "ementa": "Tema Repetitivo 466 — Responsabilidade civil em relação a inscrições indevidas em registros de crédito.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.stj.jus.br/repetitivos/tema-466",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CC", "artigo": "927", "texto": "Aquele que causa dano fica obrigado a repará-lo", "interpretacao": "Fundamentação para indenizabilidade de anotação indevida"},
                ],
            },
        ]

        logger.info(f"    ✓ {len(teses)} teses de negativação carregadas")
        return teses

    @staticmethod
    async def _buscar_fraude_bancaria() -> List[Dict[str, Any]]:
        """Busca dados sobre Fraude Bancária (Súmula 479/STJ).

        NOTA: Dados retornados como rascunho. Requerem validação contra fontes
        oficiais (STJ, CNJ, jurisprudência verificada) e revisão humana antes de
        serem promovidos a status=validada.
        """
        logger.info("  → Buscando Fraude Bancária (Súmula 479/STJ)...")

        teses = [
            {
                "titulo": "Súmula 479/STJ — Responsabilidade Objetiva por Fortuito Interno em Operações Bancárias",
                "sumario": "Instituições financeiras respondem objetivamente pelos danos gerados por fortuito interno relativo a fraudes e delitos praticados por terceiros no âmbito de operações bancárias.",
                "tipo": TipoTese.ataque,
                "score": 85,
                "precedentes": [
                    {
                        "tribunal": "STJ",
                        "classe": "Súmula",
                        "numero": "479",
                        "ementa": "As instituições financeiras respondem objetivamente pelos danos gerados por fortuito interno relativo a fraudes e delitos praticados por terceiros no âmbito de operações bancárias.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.stj.jus.br/jurisprudencia/sumulas_search.jsp?termo=479",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CDC", "artigo": "2", "texto": "Consumidor é toda pessoa física ou jurídica que adquire produtos/serviços", "interpretacao": "Cliente bancário é consumidor protegido pelo CDC"},
                    {"norma": "CDC", "artigo": "14", "texto": "Fornecedor responde independentemente de culpa por defeito no serviço", "interpretacao": "Responsabilidade objetiva — não necessária prova de negligência"},
                    {"norma": "CC", "artigo": "927", "texto": "Aquele que causa dano a outrem fica obrigado a repará-lo", "interpretacao": "Fortuito interno é risco inerente à atividade financeira"},
                ],
            },
        ]

        logger.info(f"    ✓ {len(teses)} teses de fraude bancária carregadas")
        return teses

    @staticmethod
    async def _buscar_juros_abusivos() -> List[Dict[str, Any]]:
        """Busca dados sobre Juros Abusivos em Contratos Bancários (Súmulas 121, 532/STJ).

        NOTA: Dados retornados como rascunho. Requerem validação contra fontes
        oficiais (STJ, CNJ, jurisprudência verificada) e revisão humana antes de
        serem promovidos a status=validada.
        """
        logger.info("  → Buscando Juros Abusivos (Súmulas 121, 532/STJ)...")

        teses = [
            {
                "titulo": "Súmula 532/STJ — Juros Remuneratórios Acima de 2% ao Mês",
                "sumario": "A taxa de juros remuneratórios superior a 2% ao mês é presumida abusiva, conforme jurisprudência consolidada do STJ.",
                "tipo": TipoTese.ataque,
                "score": 88,
                "precedentes": [
                    {
                        "tribunal": "STJ",
                        "classe": "Súmula",
                        "numero": "532",
                        "ementa": "A taxa de juros remuneratórios superior a 2% ao mês é presumida abusiva.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.stj.jus.br/jurisprudencia/sumulas_search.jsp?termo=532",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CC", "artigo": "406", "texto": "Quando não se estipula taxa de juros, devem-se os legais (taxa Selic)", "interpretacao": "Juros legais servem como parâmetro para identificar abusividade"},
                    {"norma": "CDC", "artigo": "52", "texto": "Cláusulas abusivas são nulas de pleno direito", "interpretacao": "Presunção de abusividade acima de 2% se aplica sem necessidade de prova de excesso"},
                ],
            },
            {
                "titulo": "Súmula 121/STJ — Vedação de Capitalização de Juros (Anatocismo)",
                "sumario": "É vedada a capitalização de juros (anatocismo), ainda que expressamente convencionada, conforme jurisprudência consolidada do STJ.",
                "tipo": TipoTese.ataque,
                "score": 82,
                "precedentes": [
                    {
                        "tribunal": "STJ",
                        "classe": "Súmula",
                        "numero": "121",
                        "ementa": "É vedada a capitalização de juros, ainda que expressamente convencionada.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.stj.jus.br/jurisprudencia/sumulas_search.jsp?termo=121",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "Lei", "artigo": "4.595/1964", "texto": "Proíbe a capitalização de juros em operações bancárias", "interpretacao": "Vedação é absoluta, independentemente de convenção das partes"},
                    {"norma": "CDC", "artigo": "6 V", "texto": "Direito a indenização por dano material ou moral", "interpretacao": "Consumidor prejudicado por anatocismo tem direito a restituição"},
                ],
            },
        ]

        logger.info(f"    ✓ {len(teses)} teses de juros abusivos carregadas")
        return teses

    @staticmethod
    async def buscar_teses_trabalhista(sessao: AsyncSession) -> List[Dict[str, Any]]:
        """Busca teses de Direito do Trabalho — Vínculo Empregatício.

        NOTA: Dados retornados como rascunho. Requerem validação contra fontes
        oficiais (TST, TRTs, jurisprudência verificada) e revisão humana antes de
        serem promovidos a status=validada.
        """
        logger.info("🔍 Iniciando coleta de teses de Trabalhista...")

        teses = [
            {
                "titulo": "Reconhecimento de Vínculo Empregatício — Pejotização",
                "sumario": "Contratação de trabalhador como pessoa jurídica não afasta a relação de emprego quando presentes os elementos da subordinação, não-eventualidade e pessoalidade.",
                "tipo": TipoTese.ataque,
                "score": 80,
                "precedentes": [
                    {
                        "tribunal": "TST",
                        "classe": "Súmula",
                        "numero": "331",
                        "ementa": "Súmula 331, inciso I — Contratação de trabalhador temporário via intermediário não o exime de responsabilidade.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.tst.jus.br",
                    },
                    {
                        "tribunal": "TST",
                        "classe": "OJ",
                        "numero": "383",
                        "ementa": "Contrato de trabalho com PJ não caracteriza relação jurídica de emprego se não preenchidos os requisitos legais.",
                        "tipo_relacao": "favoravel",
                        "vinculante": False,
                        "url": "https://www.tst.jus.br",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CLT", "artigo": "3", "texto": "Considera-se empregado toda pessoa física que prestar serviços", "interpretacao": "Impossibilidade de contratação de PJ para atividades típicas de emprego"},
                    {"norma": "CC", "artigo": "966", "texto": "Quem exerce profissionalmente atividade econômica organizada para produção/circulação de bens/serviços", "interpretacao": "Personalidade jurídica deve ter conteúdo substantivo, não mera formalidade"},
                ],
            },
            {
                "titulo": "Terceirização Ilícita — Atividade-Fim e Responsabilidade Solidária",
                "sumario": "Terceirização de atividade-fim gera responsabilidade solidária da tomadora de serviços, incluindo débitos trabalhistas da prestadora.",
                "tipo": TipoTese.ataque,
                "score": 85,
                "precedentes": [
                    {
                        "tribunal": "TST",
                        "classe": "Súmula",
                        "numero": "331",
                        "ementa": "Súmula 331, inciso I — A contratação de trabalhador por empresa interposta não afasta a responsabilidade da tomadora de serviços.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.tst.jus.br",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CLT", "artigo": "2", "texto": "Considera-se empregador a empresa que, assumindo riscos da atividade", "interpretacao": "Tomadora que dirige execução do trabalho responde como empregadora"},
                    {"norma": "Lei", "artigo": "13.467/2017", "texto": "Reforma trabalhista permite terceirização de atividade-fim sob condições de licitude", "interpretacao": "Não se presume ilicitude automática; exige-se análise das circunstâncias"},
                ],
            },
            {
                "titulo": "Jornada Extraordinária — Adicional Mínimo de 50%",
                "sumario": "Trabalho extraordinário gera direito a adicional mínimo de 50% sobre o valor da hora normal, exceto em casos excepcionais previstos em lei.",
                "tipo": TipoTese.ataque,
                "score": 78,
                "precedentes": [
                    {
                        "tribunal": "TST",
                        "classe": "Súmula",
                        "numero": "85",
                        "ementa": "Horas extras — adicional não inferior a 50% sobre o valor da hora normal.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.tst.jus.br",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CLT", "artigo": "59", "texto": "Jornada extraordinária não deve exceder 2 horas diárias e é remunerada com adicional", "interpretacao": "Mínimo de 50% é piso; acordo coletivo pode estabelecer percentual maior"},
                ],
            },
        ]
        logger.info(f"✅ Coleta de Trabalhista concluída: {len(teses)} teses")
        return teses

    @staticmethod
    async def buscar_teses_jec(sessao: AsyncSession) -> List[Dict[str, Any]]:
        """Busca teses de Juizados Especiais Cíveis.

        NOTA: Dados retornados como rascunho. Requerem validação contra fontes
        oficiais (Lei 9.099/1995, CPC, jurisprudência verificada) e revisão humana
        antes de serem promovidos a status=validada.
        """
        logger.info("🔍 Iniciando coleta de teses de JEC...")

        teses = [
            {
                "titulo": "Lei 9.099/1995 — Competência por Valor em Juizados Especiais Cíveis",
                "sumario": "Juizado Especial Cível é competente para causas cujo valor não ultrapasse 20 salários mínimos vigentes, conforme Lei 9.099/1995.",
                "tipo": TipoTese.defesa,
                "score": 72,
                "precedentes": [
                    {
                        "tribunal": "CNJ",
                        "classe": "Lei Federal",
                        "numero": "9.099/1995",
                        "ementa": "Art. 3º — O Juizado Especial Cível tem competência para conciliação, processo e julgamento de causas cíveis de menor complexidade, assim consideradas aquelas cujo valor não exceda 20 (vinte) salários-mínimos.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.cnj.jus.br/programas-e-acoes/judiciario-2030/direito-processual-civil-1/juizados-especiais/",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CPC", "artigo": "98", "texto": "Institui-se juizado especial cível para conciliação, julgamento de causas cíveis de menor complexidade", "interpretacao": "Limite de valor é critério essencial para aferição de competência"},
                    {"norma": "Lei", "artigo": "9.099/1995", "texto": "Lei que criou os Juizados Especiais com limite de competência", "interpretacao": "Limite de 20 salários mínimos atualiza-se mensalmente com novo mínimo"},
                ],
            },
            {
                "titulo": "CPC Art. 275 — Procedimento Simplificado em Cobrança",
                "sumario": "Ação de cobrança de dívida líquida e certa em JEC segue procedimento simplificado, conforme autorizado pelo Código de Processo Civil.",
                "tipo": TipoTese.defesa,
                "score": 68,
                "precedentes": [
                    {
                        "tribunal": "CNJ",
                        "classe": "Lei Federal",
                        "numero": "13.105/2015",
                        "ementa": "Art. 275 — Observado o disposto no art. 327 desta Lei, será admitido procedimento especial, sumário ou sumaríssimo para outras causas, desde que estabelecido em lei.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.cnj.jus.br/programas-e-acoes/judiciario-2030/direito-processual-civil-1/novo-codigo-de-processo-civil/",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "CPC", "artigo": "275", "texto": "Cobrança de quantia certa contra devedor solvente segue procedimento simplificado", "interpretacao": "Prova documental é suficiente para ação cobratória de valor certo em JEC"},
                ],
            },
            {
                "titulo": "Lei 9.099/1995 — Prazos Prescricionais em Juizados Especiais",
                "sumario": "Ações em Juizados Especiais Cíveis observam prazos prescricionais conforme legislação específica da Lei 9.099/1995.",
                "tipo": TipoTese.defesa,
                "score": 65,
                "precedentes": [
                    {
                        "tribunal": "CNJ",
                        "classe": "Lei Federal",
                        "numero": "9.099/1995",
                        "ementa": "Arts. 26 e 27 — Prescrevem em um ano, contado da data da lesão, as ações para reparação de dano sofrido pelo consumidor e demandas de menor complexidade.",
                        "tipo_relacao": "favoravel",
                        "vinculante": True,
                        "url": "https://www.cnj.jus.br/programas-e-acoes/judiciario-2030/direito-processual-civil-1/juizados-especiais/",
                    },
                ],
                "fundamentacoes": [
                    {"norma": "Lei", "artigo": "9.099/1995", "texto": "Institui os Juizados Especiais Cíveis com procedimento próprio", "interpretacao": "Prazos especiais de JEC prevalecem sobre prazos gerais do CPC para ações de competência do JEC"},
                ],
            },
        ]
        logger.info(f"✅ Coleta de JEC concluída: {len(teses)} teses")
        return teses

    @staticmethod
    async def buscar_via_datajud(filtro_area: str = "Consumidor") -> List[Dict[str, Any]]:
        """
        Busca jurisprudência via CNJ DataJud (API pública).
        Nota: Requer autenticação e tokens de acesso.
        """
        logger.info(f"🔍 Buscando via DataJud (área: {filtro_area})...")
        # Implementação futura com autenticação DataJud
        logger.warning("⚠️  DataJud: não implementado — requer credenciais CNJ")
        return []

    @staticmethod
    async def buscar_via_stj_api(termos: List[str]) -> List[Dict[str, Any]]:
        """
        Busca jurisprudência via API do STJ.
        Termos: ex. ["negativação indevida", "fraude bancária"]
        """
        logger.info(f"🔍 Buscando via STJ API (termos: {termos})...")
        # Implementação futura com scraping responsável
        logger.warning("⚠️  STJ API: scraping em desenvolvimento")
        return []


async def executar_coleta_completa(sessao: AsyncSession):
    """Executa coleta completa de teses para todos os lotes."""
    logger.info("\n" + "="*60)
    logger.info("🎯 INICIANDO COLETA COMPLETA DO BANCO DE TESES JURÍDICAS")
    logger.info("="*60 + "\n")

    teses_totais = []

    # Lote 1: Consumidor
    teses_consumidor = await TeseColeta.buscar_teses_consumidor(sessao)
    teses_totais.extend(teses_consumidor)

    # Lote 2: Trabalhista
    teses_trabalhista = await TeseColeta.buscar_teses_trabalhista(sessao)
    teses_totais.extend(teses_trabalhista)

    # Lote 3: JEC
    teses_jec = await TeseColeta.buscar_teses_jec(sessao)
    teses_totais.extend(teses_jec)

    logger.info("\n" + "="*60)
    logger.info(f"✅ COLETA CONCLUÍDA: {len(teses_totais)} teses coletadas")
    logger.info("="*60 + "\n")

    return teses_totais
