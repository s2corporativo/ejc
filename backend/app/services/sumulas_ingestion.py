# ── app/services/sumulas_ingestion.py ─────────────────────────────────────────
# Ingere súmulas dos tribunais superiores no banco de teses (RAG + pesquisa).
# Operação idempotente — verifica duplicatas antes de inserir.
# Fonte primária: dataset estático com verbetes STF/STJ/TST reconferidos
# individualmente contra fonte oficial (ver DATA_CONFERENCIA).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import get_settings

logger = logging.getLogger("ejc.sumulas")

# RECONSTRUÇÃO (auditoria RAG): o dataset anterior estava indexado com
# confianca="alta" mas continha texto de súmula juridicamente INCORRETO em
# 13 dos 27 verbetes (número certo com conteúdo de outra súmula, conteúdo
# desatualizado/revogado, ou situação — cancelada/suspensa — não sinalizada).
# Cada verbete abaixo foi reconferido individualmente contra fonte oficial
# (STF/STJ/TST ou publicação DJe) nesta data — ver `fonte_url`/`data_publicacao`
# por item. `situacao` distingue:
#   ativa    — jurisprudência vigente, indexável no RAG como fundamentação.
#   cancelada — superada por outra súmula; mantida só como referência histórica.
#   suspensa  — aplicação suspensa por decisão liminar (ex.: ADPF no STF);
#               mantida como referência histórica, NÃO indexada no RAG.
# Súmulas cancelada/suspensa viram registro em `teses` (status='arquivada',
# consultável na governança) mas NUNCA entram no RAG buscável — citar uma
# súmula cancelada/suspensa como direito vigente induziria a IA a erro.
DATA_CONFERENCIA = "2026-07-15"

# SEGUNDA LEVA (2026-07-17) — TENTADA E NÃO REALIZADA: a ampliação planejada
# (SVs do STF; STJ consumidor/bancário/dano moral/proc. civil; TST de alto uso)
# foi ABORTADA porque NENHUM portal oficial estava acessível no ambiente de
# execução — o proxy de egress da organização negou CONNECT (403, policy
# denial) para todos os hosts testados: tst.jus.br, www.tst.jus.br,
# www3.tst.jus.br, jurisprudencia.tst.jus.br, stf.jus.br, portal.stf.jus.br,
# www.stf.jus.br, jurisprudencia.stf.jus.br, stj.jus.br, www.stj.jus.br,
# scon.stj.jus.br e sumulas.stj.jus.br.
# REGRA DESTA CASA (não negociável): NENHUM texto de súmula entra escrito de
# memória de modelo — somente verbatim de fonte oficial baixada no ato, com
# fonte_url e situacao confirmadas. Sem fonte acessível, verbete não entra.
# Todos os verbetes abaixo são da leva conferida em DATA_CONFERENCIA
# (2026-07-15); nenhum verbete pertence à leva de 2026-07-17.
# Para ampliar: rodar em ambiente com egress liberado para *.jus.br e repetir
# o protocolo de conferência verbete a verbete.

SUMULAS_SEED = [
    # ── TST — Trabalhista ──────────────────────────────────────────────────────
    {"tribunal":"TST","numero":"12",
     "texto":"As anotações apostas pelo empregador na carteira profissional do empregado não geram presunção juris et de jure, mas apenas juris tantum.",
     "area":"trabalhista","tema":"carteira profissional presunção relativa",
     "situacao":"ativa","data_publicacao":"1973 (mantida Res. 121/2003, DJ 19-21.11.2003)",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"47",
     "texto":"O trabalho executado em condições insalubres, em caráter intermitente, não afasta, só por essa circunstância, o direito à percepção do respectivo adicional.",
     "area":"trabalhista","tema":"adicional de insalubridade trabalho intermitente",
     "situacao":"ativa","data_publicacao":"mantida Res. 121/2003, DJ 19-21.11.2003 (original RA 41/1973)",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"85",
     "texto":("I - A compensação de jornada de trabalho deve ser ajustada por acordo individual escrito, "
              "acordo coletivo ou convenção coletiva. "
              "II - O acordo individual para compensação de horas é válido, salvo se houver norma coletiva "
              "em sentido contrário. "
              "III - O mero não atendimento das exigências legais para a compensação de jornada, inclusive "
              "quando encetada mediante acordo tácito, não implica a repetição do pagamento das horas "
              "excedentes à jornada normal diária, se não dilatada a jornada máxima semanal, sendo devido "
              "apenas o respectivo adicional. "
              "IV - A prestação de horas extras habituais descaracteriza o acordo de compensação de jornada. "
              "Nesta hipótese, as horas que ultrapassarem a jornada semanal normal deverão ser pagas como "
              "horas extraordinárias e, quanto àquelas destinadas à compensação, deverá ser pago a mais "
              "apenas o adicional por trabalho extraordinário. "
              "V - As disposições contidas nesta súmula não se aplicam ao regime compensatório na modalidade "
              "banco de horas, que somente pode ser instituído por negociação coletiva. "
              "VI - Não é válido acordo de compensação de jornada em atividade insalubre, ainda que "
              "estipulado em norma coletiva, sem a necessária inspeção prévia e permissão da autoridade "
              "competente, na forma do art. 60 da CLT."),
     "area":"trabalhista","tema":"compensação de jornada banco de horas",
     "situacao":"ativa","data_publicacao":"redação vigente — ver tst.jus.br/sumulas",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"139",
     "texto":"Enquanto percebido, o adicional de insalubridade integra a remuneração para todos os efeitos legais.",
     "area":"trabalhista","tema":"adicional de insalubridade integração remuneração",
     "situacao":"ativa","data_publicacao":"ex-OJ 102 SBDI-1, inserida 10.01.1997",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"132",
     "texto":("I - O adicional de periculosidade, pago em caráter permanente, integra o cálculo de indenização "
              "e de horas extras. "
              "II - Durante as horas de sobreaviso, o empregado não se encontra em condições de risco, razão "
              "pela qual é incabível a integração do adicional de periculosidade sobre as mencionadas horas."),
     "area":"trabalhista","tema":"adicional de periculosidade integração",
     "situacao":"ativa","data_publicacao":"Res. 129/2005, DJ 20,22,25.04.2005",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"256",
     "texto":("Salvo os casos previstos nas Leis nºs 6.019, de 03.01.1974, e 7.102, de 20.06.1983, é ilegal "
              "a contratação de trabalhadores por empresa interposta, formando-se o vínculo empregatício "
              "diretamente com o tomador dos serviços."),
     "area":"trabalhista","tema":"vínculo empregatício terceirização (histórico)",
     "situacao":"cancelada","situacao_obs":"Cancelada pela Res. 121/2003 (DJ 19-21.11.2003) — substituída pela Súmula 331/TST.",
     "data_publicacao":"cancelada em 2003","fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"264",
     "texto":"A remuneração do serviço suplementar é composta do valor da hora normal, integrado por parcelas de natureza salarial e acrescido do adicional previsto em lei, contrato, acordo, convenção coletiva ou sentença normativa.",
     "area":"trabalhista","tema":"horas extras cálculo",
     "situacao":"ativa","data_publicacao":"mantida Res. 121/2003, DJ 19-21.11.2003",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"277",
     "texto":("As cláusulas normativas de acordos coletivos ou convenções coletivas integram os contratos "
              "individuais de trabalho e somente poderão ser modificadas ou suprimidas mediante negociação "
              "coletiva de trabalho."),
     "area":"trabalhista","tema":"ultratividade norma coletiva",
     "situacao":"suspensa",
     "situacao_obs":("Redação de 2012 (Res. 185/2012), oposta à anterior. Aplicação SUSPENSA por decisão "
                      "liminar do STF na ADPF 323/DF — não citar como direito vigente sem checar o status "
                      "atual do processo."),
     "data_publicacao":"Res. 185/2012, alterada da redação original de 2003",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"331",
     "texto":("Contrato de Prestação de Serviços. Legalidade. "
              "I - A contratação de trabalhadores por empresa interposta é ilegal, formando-se o vínculo "
              "diretamente com o tomador dos serviços, salvo no caso de trabalho temporário (Lei nº 6.019, "
              "de 03.01.1974) (item cancelado por perda de eficácia a partir de 11.11.2017, por força da "
              "Lei nº 13.467/2017). "
              "II - A contratação irregular de trabalhador, mediante empresa interposta, não gera vínculo "
              "de emprego com os órgãos da Administração Pública direta, indireta ou fundacional (art. 37, "
              "II, da CF/1988). "
              "III - Não forma vínculo de emprego com o tomador a contratação de serviços de vigilância "
              "(Lei nº 7.102, de 20.06.1983) e de conservação e limpeza, bem como a de serviços "
              "especializados ligados à atividade-meio do tomador, desde que inexistente a pessoalidade e "
              "a subordinação direta. "
              "IV - O inadimplemento das obrigações trabalhistas, por parte do empregador, implica a "
              "responsabilidade subsidiária do tomador de serviços."),
     "area":"trabalhista","tema":"terceirização responsabilidade subsidiária",
     "situacao":"ativa",
     "situacao_obs":"Item I cancelado por perda de eficácia (Lei 13.467/2017 — Reforma Trabalhista); itens II a VI vigentes.",
     "data_publicacao":"revisada — ver tst.jus.br/sumulas para redação completa (itens V e VI)",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"347",
     "texto":("O cálculo do valor das horas extras habituais, para efeito de reflexos em verbas "
              "trabalhistas, observará o número de horas efetivamente prestadas e a ele aplica-se o valor "
              "do salário-hora da época do pagamento daquelas verbas."),
     "area":"trabalhista","tema":"horas extras habituais apuração média física",
     "situacao":"ativa","data_publicacao":"mantida Res. 121/2003, DJ 19-21.11.2003",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"363",
     "texto":("A contratação de servidor público, após a CF/1988, sem prévia aprovação em concurso público, "
              "encontra óbice no respectivo art. 37, II e § 2º, somente lhe conferindo direito ao pagamento "
              "da contraprestação pactuada, em relação ao número de horas trabalhadas, respeitado o valor "
              "da hora do salário mínimo, e dos valores referentes aos depósitos do FGTS."),
     "area":"trabalhista","tema":"servidor concurso público contrato nulo",
     "situacao":"ativa","data_publicacao":"revisada Res. 121/2003",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    {"tribunal":"TST","numero":"443",
     "texto":("Presume-se discriminatória a despedida de empregado portador do vírus HIV ou de outra doença "
              "grave que suscite estigma ou preconceito. Inválido o ato, o empregado tem direito à "
              "reintegração no emprego."),
     "area":"trabalhista","tema":"dispensa discriminatória HIV doença grave",
     "situacao":"ativa","data_publicacao":"2012",
     "fonte_url":"https://www.tst.jus.br/sumulas"},
    # ── STJ — Civil / Consumidor / Bancário ────────────────────────────────────
    {"tribunal":"STJ","numero":"54",
     "texto":"Os juros moratórios fluem a partir do evento danoso, em caso de responsabilidade extracontratual.",
     "area":"civil","tema":"juros moratórios responsabilidade extracontratual",
     "situacao":"ativa","data_publicacao":"julgada 24.09.1992, publicada 01.10.1992",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"297",
     "texto":"O Código de Defesa do Consumidor é aplicável às instituições financeiras.",
     "area":"consumidor","tema":"CDC aplicabilidade instituições financeiras",
     "situacao":"ativa","data_publicacao":"julgada 12.05.2004, DJ 08.09.2004 p.129",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"302",
     "texto":"É abusiva a cláusula contratual de plano de saúde que limita no tempo a internação hospitalar do segurado.",
     "area":"consumidor","tema":"plano de saúde limitação internação",
     "situacao":"ativa","data_publicacao":"DJ 22.11.2004 p.425",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"327",
     "texto":"Nas ações referentes ao Sistema Financeiro da Habitação, a Caixa Econômica Federal tem legitimidade como sucessora do Banco Nacional da Habitação.",
     "area":"bancario","tema":"SFH legitimidade CEF sucessora BNH",
     "situacao":"ativa","data_publicacao":"publicada 07.06.2006",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"381",
     "texto":"Nos contratos bancários, é vedado ao julgador conhecer, de ofício, da abusividade das cláusulas.",
     "area":"bancario","tema":"cláusulas abusivas banco conhecimento de ofício",
     "situacao":"ativa","data_publicacao":"aprovada 2009",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"404",
     "texto":"É dispensável o Aviso de Recebimento (AR) na carta de comunicação ao consumidor sobre a negativação de seu nome em bancos de dados e cadastros.",
     "area":"consumidor","tema":"negativação cadastros aviso de recebimento",
     "situacao":"ativa","data_publicacao":"julgada 28.10.2009, DJe 24.11.2009",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"477",
     "texto":"A decadência do art. 26 do CDC não é aplicável à prestação de contas para obter esclarecimentos sobre cobrança de taxas, tarifas e encargos bancários.",
     "area":"consumidor","tema":"prestação de contas bancária decadência",
     "situacao":"ativa","data_publicacao":"julgada 13.06.2012, DJe 19.06.2012",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"549",
     "texto":"É válida a penhora de bem de família pertencente a fiador de contrato de locação.",
     "area":"civil","tema":"bem de família fiador locação",
     "situacao":"ativa","data_publicacao":"aprovada 14.10.2015, publicada 19.10.2015",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"563",
     "texto":"O Código de Defesa do Consumidor é aplicável às entidades abertas de previdência complementar, não incidindo nos contratos previdenciários celebrados com entidades fechadas.",
     "area":"consumidor","tema":"CDC previdência complementar entidades abertas",
     "situacao":"ativa","data_publicacao":"publicada DJe 29.02.2016 — substitui a Súmula 321/STJ",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    # ── STF — Constitucional / Vinculante ──────────────────────────────────────
    {"tribunal":"STF","numero_vinculante":"1",
     "texto":"Ofende a garantia constitucional do ato jurídico perfeito a decisão que, sem ponderar as circunstâncias do caso concreto, desconsidera a validez e a eficácia de acordo constante de termo de adesão instituído pela Lei Complementar nº 110/2001.",
     "area":"tributario","tema":"FGTS LC 110/2001 ato jurídico perfeito",
     "situacao":"ativa","data_publicacao":"DJe 06.06.2007",
     "fonte_url":"https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"},
    {"tribunal":"STF","numero_vinculante":"17",
     "texto":"Durante o período previsto no parágrafo 1º do artigo 100 da Constituição, não incidem juros de mora sobre os precatórios que nele sejam pagos.",
     "area":"administrativo","tema":"precatório juros mora",
     "situacao":"ativa",
     "situacao_obs":"Referência ao §1º do art. 100 deve ser lida como §5º após a EC 62/2009, posterior à aprovação da súmula.",
     "data_publicacao":"aprovada 29.10.2009, DJe 10.11.2009",
     "fonte_url":"https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"},
    {"tribunal":"STF","numero_vinculante":"37",
     "texto":"Não cabe ao Poder Judiciário, que não tem função legislativa, aumentar vencimentos de servidores públicos sob o fundamento de isonomia.",
     "area":"administrativo","tema":"isonomia vencimentos servidores",
     "situacao":"ativa","data_publicacao":"publicada 23.10.2014 (conversão da antiga Súmula 339/STF)",
     "fonte_url":"https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"},
    # ── STJ — Ambiental ───────────────────────────────────────────────────────
    {"tribunal":"STJ","numero":"613",
     "texto":"Não se admite a aplicação da teoria do fato consumado em tema de Direito Ambiental.",
     "area":"ambiental","tema":"fato consumado ambiental",
     "situacao":"ativa","data_publicacao":"ver scon.stj.jus.br",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"618",
     "texto":"A inversão do ônus da prova aplica-se às ações de degradação ambiental.",
     "area":"ambiental","tema":"inversão ônus prova ambiental",
     "situacao":"ativa","data_publicacao":"julgada 24.10.2018, DJe 30.10.2018",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
    {"tribunal":"STJ","numero":"623",
     "texto":"As obrigações ambientais possuem natureza propter rem, sendo admissível cobrá-las do proprietário ou possuidor atual e/ou dos anteriores, à escolha do credor.",
     "area":"ambiental","tema":"obrigações ambientais propter rem",
     "situacao":"ativa","data_publicacao":"julgada 12.12.2018, DJe 17.12.2018",
     "fonte_url":"https://scon.stj.jus.br/SCON/sumstj/"},
]


def _titulo(s: dict) -> str:
    numero = str(s.get("numero") or s.get("numero_vinculante", ""))
    if s.get("numero_vinculante"):
        return f"Súmula Vinculante STF nº {numero}"
    return f"Súmula {s.get('tribunal', '')} nº {numero}"


async def ingerir_sumulas_seed(db: AsyncSession) -> dict:
    """
    Ingere o dataset de súmulas na tabela `teses` (+ RAG quando `situacao='ativa'`).
    Idempotente — ignora súmulas já existentes pelo título+tribunal.

    RAG_SUMULAS_SEED_ENABLED=False desativa a ingestão inteira (early return),
    para permitir suspender rapidamente caso um erro seja encontrado após esta
    reconstrução, sem precisar reverter código.
    """
    settings = get_settings()
    if not settings.RAG_SUMULAS_SEED_ENABLED:
        logger.warning(
            "Seed de súmulas DESATIVADO (RAG_SUMULAS_SEED_ENABLED=false). "
            "Nada foi inserido."
        )
        return {
            "inseridas": 0,
            "ignoradas": 0,
            "total_seed": len(SUMULAS_SEED),
            "quarentena": True,
            "motivo": "RAG_SUMULAS_SEED_ENABLED=false — seed desativado.",
        }

    inseridas = 0
    ignoradas  = 0
    indexadas_rag = 0

    for s in SUMULAS_SEED:
        tribunal = s.get("tribunal", "")
        numero   = str(s.get("numero") or s.get("numero_vinculante", ""))
        texto    = s.get("texto", "")
        area     = s.get("area", "geral")
        tema     = s.get("tema", "")
        situacao = s.get("situacao", "ativa")
        situacao_obs = s.get("situacao_obs", "")
        titulo = _titulo(s)

        # Idempotência
        existe = (await db.execute(text(
            "SELECT id FROM teses WHERE titulo = :t AND tribunal = :tr AND deleted_at IS NULL"
        ), {"t": titulo, "tr": tribunal})).scalar()
        if existe:
            ignoradas += 1
            continue

        # status da tabela `teses` é um Enum restrito (rascunho|ativa|arquivada) —
        # cancelada/suspensa mapeiam para 'arquivada' (não é "vigente" para uso).
        status_tese = "ativa" if situacao == "ativa" else "arquivada"

        obs_partes = ["Ingestão automática — banco de súmulas EJC",
                     f"Situação: {situacao}"]
        if situacao_obs:
            obs_partes.append(situacao_obs)
        obs_partes.append(f"Conferido em {DATA_CONFERENCIA} contra fonte oficial: {s.get('fonte_url', '')}")

        tese_id = str(uuid4())
        await db.execute(text("""
            INSERT INTO teses (
                id, titulo, descricao, fundamentacao, area_juridica, area_direito,
                tribunal, tags, observacoes, tipo, status,
                vezes_usada, vezes_venceu, vezes_perdeu,
                created_at, updated_at
            ) VALUES (
                :id, :titulo, :descricao, :fundamentacao, :area, :area,
                :tribunal, :tags, :obs, 'jurisprudencia', :status,
                0, 0, 0, NOW(), NOW()
            )
        """), {
            "id":          tese_id,
            "titulo":      titulo,
            "descricao":   texto,
            "fundamentacao": f"Área: {area} | Tema: {tema} | Data: {s.get('data_publicacao', '')}",
            "area":        area,
            "tribunal":    tribunal,
            "tags":        tema,
            "status":      status_tese,
            "obs":         " | ".join(obs_partes),
        })

        # Indexar no RAG (knowledge_chunks) SOMENTE quando situacao='ativa' —
        # súmula cancelada/suspensa nunca deve virar fundamentação citável pela
        # IA (fica só como registro histórico em `teses`/governança).
        if situacao == "ativa":
            try:
                from app.services.ingestion_service import upsert_documento
                await upsert_documento(
                    db=db,
                    titulo=titulo,
                    conteudo=f"{titulo}\n\nTribunal: {tribunal} | Área: {area} | Tema: {tema}\n\n{texto}",
                    categoria=area,
                    fonte="sumula",
                    tribunal=tribunal,
                    # Chave determinística (auditoria RAG) — antes era
                    # f"sumula:{uuid4()}" (aleatória, sem dedup real por verbete).
                    chave_origem=f"sumula:{tribunal.lower()}:{numero}",
                    extra={
                        "referencia_id": tese_id,
                        "conferido": True,
                        "situacao": situacao,
                        "data_conferencia": DATA_CONFERENCIA,
                        "fonte_url": s.get("fonte_url", ""),
                        "data_publicacao": s.get("data_publicacao", ""),
                    },
                    # confianca="media" (não "alta"): verbete conferido por busca
                    # textual nesta sessão, não por confronto de hash com PDF
                    # oficial primário — curadoria humana pode elevar para "alta".
                    confianca="media",
                )
                indexadas_rag += 1
            except Exception as exc:
                logger.error("Falha ao indexar súmula no RAG (%s): %s", titulo, exc)

        inseridas += 1

    await db.commit()
    logger.info("Súmulas: %d inseridas (%d indexadas no RAG), %d já existiam.",
               inseridas, indexadas_rag, ignoradas)
    return {
        "inseridas": inseridas,
        "indexadas_rag": indexadas_rag,
        "ignoradas":  ignoradas,
        "total_seed": len(SUMULAS_SEED),
    }
