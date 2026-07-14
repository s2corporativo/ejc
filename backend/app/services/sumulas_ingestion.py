# ── app/services/sumulas_ingestion.py ─────────────────────────────────────────
# Ingere súmulas dos tribunais superiores no banco de teses (RAG + pesquisa).
# Operação idempotente — verifica duplicatas antes de inserir.
# Fonte primária: dataset estático com 30+ súmulas STF/STJ/TST curadas.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import get_settings

logger = logging.getLogger("ejc.sumulas")

# QUARENTENA: conteúdo não conferido com fontes oficiais — ver auditoria RAG.
# Este dataset foi indexado com confianca="alta" mas contém texto de súmula
# juridicamente INCORRETO/desatualizado. A ingestão está desativada por padrão
# (RAG_SUMULAS_SEED_ENABLED=False) e a recuperação em quarentena
# (RAG_SUMULAS_QUARENTENA=True). NÃO reabilitar sem reconferir cada verbete
# com STF/STJ/TST. Mantido apenas como referência para a futura curadoria.
SUMULAS_SEED = [
    # ── TST — Trabalhista ──────────────────────────────────────────────────────
    {"tribunal":"TST","numero":"12","texto":"O cômputo do percentual de 40% (quarenta por cento) sobre os depósitos do FGTS, na hipótese de despedida arbitrária ou sem justa causa, deve tomar por base a totalidade dos recolhimentos efetuados durante a vigência do contrato de trabalho.","area":"trabalhista","tema":"FGTS multa 40%"},
    {"tribunal":"TST","numero":"47","texto":"O trabalho prestado nos domingos e feriados, não compensado, deve ser pago em dobro, sem prejuízo da remuneração relativa ao repouso semanal.","area":"trabalhista","tema":"horas extras domingo"},
    {"tribunal":"TST","numero":"85","texto":"A responsabilidade solidária do tomador de serviços, prevista no art. 16 da Lei 6.019/74, abrange todos os direitos trabalhistas dos empregados das empresas de trabalho temporário.","area":"trabalhista","tema":"terceirização responsabilidade"},
    {"tribunal":"TST","numero":"116","texto":"O adicional de insalubridade, pago em grau máximo, integra a remuneração para todos os efeitos legais.","area":"trabalhista","tema":"adicional insalubridade"},
    {"tribunal":"TST","numero":"132","texto":"O adicional de horas extras remunera o período acrescido que ultrapassa a jornada normal. Assim sendo, o cálculo das horas extras habituais, para efeito de reflexo em outras parcelas, observará o número de horas efetivamente prestadas.","area":"trabalhista","tema":"horas extras reflexo"},
    {"tribunal":"TST","numero":"256","texto":"Salvo os casos previstos na CLT, é ilegal a contratação de trabalhadores por empresa interposta, formando-se o vínculo empregatício diretamente com o tomador dos serviços.","area":"trabalhista","tema":"vínculo empregatício terceirização"},
    {"tribunal":"TST","numero":"264","texto":"A remuneração do serviço suplementar é composta do valor da hora normal, integrado por parcelas de natureza salarial e acrescido do adicional previsto em lei, contrato, acordo, convenção coletiva ou sentença normativa.","area":"trabalhista","tema":"horas extras cálculo"},
    {"tribunal":"TST","numero":"277","texto":"As condições de trabalho alcançadas por força de sentença normativa, convenção ou acordos coletivos vigoram no prazo assinado, não integrando, de forma definitiva, os contratos individuais de trabalho.","area":"trabalhista","tema":"convenção coletiva vigência"},
    {"tribunal":"TST","numero":"331","texto":"Contrato de prestação de serviços. Legalidade. I - A contratação de trabalhadores por empresa interposta é ilegal, formando-se o vínculo diretamente com o tomador dos serviços, salvo no caso de trabalho temporário (Lei nº 6.019, de 03.01.1974).","area":"trabalhista","tema":"terceirização"},
    {"tribunal":"TST","numero":"347","texto":"É ilícita a prestação de serviços por intermédio de cooperativas formadas para burlar a legislação trabalhista.","area":"trabalhista","tema":"cooperativa fraude"},
    {"tribunal":"TST","numero":"363","texto":"A contratação de servidor público, após a CF/1988, sem prévia aprovação em concurso público, encontra óbice no respectivo art. 37, II e § 2.º, somente lhe conferindo direito ao pagamento da contraprestação pactuada.","area":"trabalhista","tema":"servidor concurso público"},
    {"tribunal":"TST","numero":"443","texto":"Presume-se discriminatória a despedida de empregado portador do vírus HIV ou de outra doença grave que suscite estigma ou preconceito.","area":"trabalhista","tema":"dispensa discriminatória HIV"},
    # ── STJ — Civil / Consumidor / Bancário ────────────────────────────────────
    {"tribunal":"STJ","numero":"54","texto":"Os juros moratórios fluem a partir do evento danoso, em caso de responsabilidade extracontratual.","area":"civil","tema":"juros moratórios responsabilidade extracontratual"},
    {"tribunal":"STJ","numero":"297","texto":"O plano de saúde deve indicar, por ocasião da contratação, as doenças e lesões cobertas e as excluídas, sob pena de presumir-se integral a cobertura.","area":"consumidor","tema":"plano de saúde cobertura"},
    {"tribunal":"STJ","numero":"302","texto":"É abusiva a cláusula contratual de plano de saúde que limita no tempo a internação hospitalar do segurado.","area":"consumidor","tema":"plano de saúde internação"},
    {"tribunal":"STJ","numero":"327","texto":"Na ação de inversão do ônus da prova em relação à saúde suplementar, o consumidor não precisa demonstrar a culpa do fornecedor.","area":"consumidor","tema":"inversão ônus prova"},
    {"tribunal":"STJ","numero":"381","texto":"Nos contratos bancários, é vedado ao julgador conhecer, de ofício, da abusividade das cláusulas.","area":"bancario","tema":"cláusulas abusivas banco"},
    {"tribunal":"STJ","numero":"404","texto":"É dispensável o Aviso de Recebimento (AR) na carta de comunicação ao consumidor sobre a negativação de seu nome em bancos de dados e cadastros.","area":"consumidor","tema":"negativação cadastros"},
    {"tribunal":"STJ","numero":"477","texto":"A condenação por danos morais em decorrência de negativação indevida prescinde da demonstração de prejuízo, sendo presumido (dano in re ipsa).","area":"consumidor","tema":"dano moral negativação"},
    {"tribunal":"STJ","numero":"549","texto":"É válida a penhora de bem de família pertencente a fiador de contrato de locação.","area":"civil","tema":"bem de família fiador"},
    {"tribunal":"STJ","numero":"563","texto":"O Código de Defesa do Consumidor é aplicável às entidades abertas de previdência complementar, não incidindo nos contratos previdenciários celebrados com entidades fechadas.","area":"consumidor","tema":"CDC previdência complementar"},
    # ── STF — Constitucional / Vinculante ──────────────────────────────────────
    {"tribunal":"STF","numero_vinculante":"1","texto":"Ofende a garantia constitucional do ato jurídico perfeito a decisão que, sem ponderar as circunstâncias do caso concreto, desconsidera a validez e a eficácia de acordo constante de termo de adesão instituído pela Lei Complementar nº 110/2001.","area":"tributario","tema":"FGTS LC 110/2001 ato jurídico perfeito"},
    {"tribunal":"STF","numero_vinculante":"17","texto":"Durante o período previsto no parágrafo 1º do artigo 100 da Constituição, não incidem juros de mora sobre os precatórios que nele sejam pagos.","area":"administrativo","tema":"precatório juros mora"},
    {"tribunal":"STF","numero_vinculante":"37","texto":"Não cabe ao Poder Judiciário, que não tem função legislativa, aumentar vencimentos de servidores públicos sob o fundamento de isonomia.","area":"administrativo","tema":"isonomia servidores"},
    # ── STJ — Ambiental ───────────────────────────────────────────────────────
    {"tribunal":"STJ","numero":"618","texto":"A inversão do ônus da prova aplica-se às ações de degradação ambiental.","area":"ambiental","tema":"inversão ônus prova ambiental"},
    {"tribunal":"STJ","numero":"623","texto":"As obrigações ambientais possuem natureza propter rem, sendo admissível cobrá-las do proprietário ou possuidor atual e/ou dos anteriores, à escolha do credor.","area":"ambiental","tema":"obrigações ambientais propter rem"},
    {"tribunal":"STJ","numero":"628","texto":"A teoria do fato consumado não pode ser aplicada em ações que visam à regularização ambiental.","area":"ambiental","tema":"fato consumado ambiental"},
]


async def ingerir_sumulas_seed(db: AsyncSession) -> dict:
    """
    Ingere o dataset de súmulas na tabela `teses`.
    Idempotente — ignora súmulas já existentes pelo título+tribunal.

    QUARENTENA (auditoria RAG): enquanto RAG_SUMULAS_SEED_ENABLED=False (padrão)
    a função retorna cedo SEM inserir nada — o conteúdo do seed não foi conferido
    com as fontes oficiais e não deve ser persistido nem indexado no RAG.
    """
    settings = get_settings()
    if not settings.RAG_SUMULAS_SEED_ENABLED:
        logger.warning(
            "Seed de súmulas DESATIVADO (RAG_SUMULAS_SEED_ENABLED=false) — "
            "quarentena da auditoria RAG: conteúdo não reconferido com fontes "
            "oficiais (STF/STJ/TST). Nada foi inserido."
        )
        return {
            "inseridas": 0,
            "ignoradas": 0,
            "total_seed": len(SUMULAS_SEED),
            "quarentena": True,
            "motivo": "Seed em quarentena — conteúdo não conferido com fontes oficiais.",
        }

    inseridas = 0
    ignoradas  = 0

    for s in SUMULAS_SEED:
        tribunal = s.get("tribunal", "")
        numero   = str(s.get("numero") or s.get("numero_vinculante", ""))
        texto    = s.get("texto", "")
        area     = s.get("area", "geral")
        tema     = s.get("tema", "")

        if s.get("numero_vinculante"):
            titulo = f"Súmula Vinculante STF nº {numero}"
        else:
            titulo = f"Súmula {tribunal} nº {numero}"

        # Idempotência
        existe = (await db.execute(text(
            "SELECT id FROM teses WHERE titulo = :t AND tribunal = :tr AND deleted_at IS NULL"
        ), {"t": titulo, "tr": tribunal})).scalar()
        if existe:
            ignoradas += 1
            continue

        tese_id = str(uuid4())
        await db.execute(text("""
            INSERT INTO teses (
                id, titulo, descricao, fundamentacao, area_juridica, area_direito,
                tribunal, tags, observacoes, tipo, status,
                vezes_usada, vezes_venceu, vezes_perdeu,
                created_at, updated_at
            ) VALUES (
                :id, :titulo, :descricao, :fundamentacao, :area, :area,
                :tribunal, :tags, :obs, 'jurisprudencia', 'ativa',
                0, 0, 0, NOW(), NOW()
            )
        """), {
            "id":          tese_id,
            "titulo":      titulo,
            "descricao":   texto,
            "fundamentacao": f"Área: {area} | Tema: {tema}",
            "area":        area,
            "tribunal":    tribunal,
            "tags":        tema,
            "obs":         "Ingestão automática — banco de súmulas EJC",
        })

        # Indexar no RAG (knowledge_chunks) via serviço existente
        try:
            from app.services.ingestion_service import upsert_documento
            await upsert_documento(
                db=db,
                titulo=titulo,
                conteudo=f"{titulo}\n\nTribunal: {tribunal} | Área: {area} | Tema: {tema}\n\n{texto}",
                categoria=area,
                fonte="sumula",
                tribunal=tribunal,
                chave_origem=f"sumula:{tese_id}",
                extra={"referencia_id": tese_id},
                confianca="alta",
            )
        except Exception as exc:
            # Robustez (auditoria RAG): falha de indexação NÃO pode ser silenciosa
            # — a tese fica sem lastro no RAG. Logar em ERROR para visibilidade.
            # (Atomicidade tese+doc RAG exigiria mudar ingestion_service.py — fora
            # do escopo deste arquivo; ver relatório da auditoria.)
            logger.error("Falha ao indexar súmula no RAG (%s): %s", titulo, exc)

        inseridas += 1

    await db.commit()
    logger.info("Súmulas: %d inseridas, %d já existiam.", inseridas, ignoradas)
    return {
        "inseridas": inseridas,
        "ignoradas":  ignoradas,
        "total_seed": len(SUMULAS_SEED),
    }
