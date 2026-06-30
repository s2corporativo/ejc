# app/services/ia_defensiva_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai_gateway import chat
from app.services.sanitizer import sanitizar_pii

NivelInteligencia = Literal["padrao", "alto", "maximo"]

EtapaDefensiva = Literal[
    "analise_inicial",
    "fragilidades",
    "teses_defensivas",
    "provas_comparativas",
    "esqueleto_contestacao",
    "redigir_contestacao",
    "jec_triagem_minuta",
    "fluxo_completo",
]

AVISO_REVISAO = (
    "REVISAO HUMANA OBRIGATORIA: resultado gerado por IA para apoio interno. "
    "Nao protocolar, enviar ao cliente ou usar em autos sem validacao do advogado responsavel."
)



NIVEL_INSTRUCOES: dict[str, str] = {
    "padrao": "Execute a analise juridica com profundidade adequada, objetividade e foco pratico.",
    "alto": """
Ative modo de alta inteligencia juridica:
- decomponha o problema em fatos, direito, prova, risco, estrategia e pedido;
- confronte a narrativa do autor com onus da prova, coerencia interna e documentos;
- procure teses ocultas, contradicoes, omissoes e alternativas subsidiarias;
- classifique o que e fato, inferencia, risco e providencia;
- apresente conclusoes acionaveis para contestacao, sem inventar fontes.
""".strip(),
    "maximo": """
Ative modo de inteligencia maxima, com raciocinio juridico senior:
- faca leitura adversarial completa da peticao inicial;
- teste hipoteses concorrentes antes de concluir;
- avalie preliminares, merito, prova, quantum, acordo, reconvencao e risco reputacional;
- use matriz criticidade x probabilidade x impacto;
- explicite dados faltantes que impedem conclusao segura;
- antes da resposta final, realize uma autocritica: quais conclusoes dependem de prova, fonte ou decisao humana;
- nao revele cadeia de pensamento interna, entregue apenas analise final organizada e verificavel.
""".strip(),
}

SYSTEM_BASE = """
Atue como advogado do escritorio De Paula Teixeira Advogados Associados.
Voce trabalha para o reu/defesa quando houver peticao inicial contra cliente do escritorio,
ou para estruturacao JEC quando a etapa indicada for jec_triagem_minuta.

Regras absolutas:
1. Nao invente fatos, documentos, leis, sumulas, jurisprudencia, numero de acordao, relator ou data.
2. Se nao houver certeza sobre jurisprudencia real, escreva exatamente: verificar fonte.
3. Separe fato comprovado, fato alegado, inferencia e lacuna.
4. Use linguagem juridica formal, precisa e objetiva.
5. Nunca faca negativa geral. A impugnacao deve ser especifica e individualizada.
6. Todo resultado e rascunho interno sujeito a revisao humana obrigatoria.
7. Quando faltarem dados, use [DADO NAO INFORMADO] ou [VERIFICAR].
8. Em documentos finais, evite caracteres especiais decorativos e mantenha padrao juridico limpo.
9. Para prazos, indique o fundamento e condicione ao rito informado e a data de citacao/intimacao quando ausente.
10. Para prescricao/decadencia, somente conclua com datas precisas; sem datas, indique hipotese e dados faltantes.
""".strip()

PROMPTS: dict[str, str] = {
    "analise_inicial": """
Analise integralmente a peticao inicial e extraia, organizando por relevancia:

1. IDENTIFICACAO
- Rito processual: comum / sumario / JEC / CLT / penal / outro
- Valor da causa e competencia do juizo
- Qualificacao completa das partes

2. FATOS ALEGADOS
- Fatos essenciais que sustentam a pretensao
- Fatos secundarios ou complementares
- Lacunas factuais relevantes

3. PEDIDOS FORMULADOS
- Principal e subsidiarios
- Tutela provisoria, urgencia ou evidencia
- Grau de especificidade: especifico ou generico, com referencia ao art. 324 do CPC quando aplicavel

4. FUNDAMENTOS JURIDICOS
- Dispositivos legais invocados
- Jurisprudencia citada, apontando se deve ser verificada ou se parece inexistente/incompleta
- Doutrina referenciada

5. PROVAS APRESENTADAS
- Documentos juntados e forca probante
- Provas requeridas mas nao produzidas
- Ausencias probatorias relevantes

6. SINTESE ESTRATEGICA
- O que efetivamente sustenta a pretensao
- O que depende de prova ainda nao produzida
- Prazo para contestacao conforme rito, condicionado aos dados disponiveis
""".strip(),
    "fragilidades": """
Com base na peticao inicial e nos documentos informados, identifique e classifique todas as fragilidades por criticidade.

CRITICO: ausencia de prova do fato constitutivo, pedido juridicamente impossivel, prescricao ou decadencia consumada, ilegitimidade manifesta, incompetencia absoluta, ineptia da inicial.
ELEVADO: contradicoes internas, documentos que contradizem os fatos, ausencia de nexo causal, quantum nao provado ou excessivo, jurisprudencia favoravel a re nao enfrentada.
MEDIO: pedidos genericos, fundamentacao insuficiente, provas indiretas tratadas como diretas, omissoes relevantes.
BAIXO: inconsistencias menores, exagero retorico, jurisprudencia desatualizada/minoritaria/inaplicavel.

Para cada fragilidade informe:
a) dispositivo legal, sumula ou base normativa aplicavel;
b) estrategia de exploracao na contestacao;
c) prova ou argumento necessario para sustentar a impugnacao.
""".strip(),
    "teses_defensivas": """
Mapeie todas as teses defensivas disponiveis.

Para cada tese informe:
- Denominacao
- Natureza: PRINCIPAL, SUBSIDIARIA ou ALTERNATIVA
- Fundamento legal: artigo, lei e sumula/precedente vinculante se houver certeza real
- Fatos que sustentam
- Provas disponiveis
- Probabilidade de exito: ALTA, MEDIA ou BAIXA, com justificativa
- Risco de rejeicao sumaria: SIM ou NAO, com motivo

Categorias obrigatorias:
1. Preliminares processuais do art. 337 do CPC aplicaveis
2. Impugnacao ao valor da causa, art. 293 do CPC
3. Negativa especifica dos fatos, art. 341 do CPC
4. Excludentes de responsabilidade civil: fato exclusivo da vitima, fortuito/forca maior, culpa concorrente, fato de terceiro
5. Merito direto: inexistencia do fato, ato, dano ou nexo
6. Reduc?ao do quantum
7. Prescricao ou decadencia, apenas com datas precisas
8. Reconvecao: cabimento e vantagem estrategica

Ao final, indique a combinacao recomendada: tese principal + subsidiarias.
""".strip(),
    "provas_comparativas": """
Realize analise comparativa entre os documentos do autor e as provas disponiveis para a defesa.

Para cada documento/prova do autor:
- O que o autor pretende provar
- Analise critica: suficiente, insuficiente, contradiz os fatos ou favoravel a re
- Documento da defesa que confronta ou enfraquece
- Argumento de impugnacao
- Base legal, especialmente arts. 408 a 429 do CPC quando aplicavel

Consolidacao final:
1. Documentos que efetivamente provam o alegado pelo autor
2. Documentos do autor que contradizem total ou parcialmente os fatos narrados
3. Omissoes documentais relevantes
4. Documentos da defesa que contradizem a versao do autor
5. Documentos que comprovam fatos extintivos, modificativos ou impeditivos do direito do autor, art. 373, II, CPC
6. Provas complementares necessarias: pericial, testemunhal, inspecao judicial ou outras
""".strip(),
    "esqueleto_contestacao": """
Com base nas analises anteriores, estruture o esqueleto completo da contestacao.

Estrutura obrigatoria:
I. Enderecamento e qualificacao
II. Sintese dos fatos pela defesa
III. Preliminares processuais, art. 337 do CPC, em ordem estrategica
IV. Impugnacao especifica dos fatos, art. 341 do CPC
V. Merito: tese principal, teses subsidiarias e impugnacao ao quantum
VI. Provas requeridas
VII. Reconvecao, se aplicavel
VIII. Pedidos
IX. Fechamento

Inclua alertas de dados faltantes e pontos que precisam de decisao do advogado.
""".strip(),
    "redigir_contestacao": """
Redija a contestacao completa com base nas informacoes fornecidas.

Parametros tecnicos:
- Linguagem juridica formal e precisa
- Cada paragrafo deve conter afirmacao, fundamento e prova/argumento quando possivel
- Impugnacao especifica e individualizada dos fatos, nunca generica
- Jurisprudencia apenas se houver fonte certa; caso contrario, escrever verificar fonte
- Artigos de lei com diploma legal preciso
- Itens numerados para facilitar referencia nos autos

Parametros formais De Paula Teixeira:
- Cabecalho: Exmo. Sr. Dr. Juiz de Direito da [X] Vara [Civel/Trabalhista/Criminal]...
- Qualificacao do reu com dados informados
- Referencia ao numero do processo e partes
- Fechamento com Dr. Clovis Jose Soares de Paula Teixeira, OAB/MG [DADO NAO INFORMADO], De Paula Teixeira Advogados Associados, [endereco], [email], [WhatsApp]

Inclua ao final: REVISAO HUMANA OBRIGATORIA antes do protocolo.
""".strip(),
    "jec_triagem_minuta": """
Fluxo AcioneJus: analise, triagem e estruturacao JEC.

ETAPA 1 - TRIAGEM DE VIABILIDADE
Analise relato e documentos. Identifique:
- Competencia do JEC: valor, materia e parte, art. 8 da Lei 9.099/95
- Fato gerador da pretensao: negativacao indevida, cobranca indevida, vicio de produto, falha de servico, recusa indevida ou outro
- Documentos disponiveis versus necessarios
- Prescricao: CDC art. 27 quando aplicavel; CC art. 206 conforme o caso
- Probabilidade de exito: ALTA, MEDIA ou BAIXA, com justificativa
- Recomendacao: AJUIZAR, NAO AJUIZAR ou TENTATIVA EXTRAJUDICIAL ANTES

ETAPA 2 - ESTRUTURACAO DA MINUTA
Se viavel, estruture peticao JEC com:
- Qualificacao das partes
- Fatos claros e simples, art. 14 da Lei 9.099/95
- Direito: CDC e demais bases aplicaveis
- Pedidos: material e moral, sem inventar parametros jurisprudenciais; indicar verificar TJMG quando necessario
- Documentos a juntar
- Requerimento de audiencia de conciliacao

Regra OAB: minuta apenas para revisao do advogado Dr. Clovis. Nao enviar ao usuario sem validacao profissional.
""".strip(),
}

FLUXO_COMPLETO = [
    "analise_inicial",
    "fragilidades",
    "teses_defensivas",
    "provas_comparativas",
    "esqueleto_contestacao",
]


@dataclass
class IaDefensivaInput:
    etapa: EtapaDefensiva
    peticao_inicial: str
    rito: str | None = None
    area: str | None = None
    documentos_autor: list[str] | None = None
    documentos_defesa: list[str] | None = None
    analises_anteriores: str | None = None
    dados_formais: dict | None = None
    case_id: str | None = None
    momento: str | None = None
    nivel_inteligencia: NivelInteligencia = "alto"


def _formatar_lista(titulo: str, itens: list[str] | None) -> str:
    if not itens:
        return f"{titulo}: [NAO INFORMADO]"
    linhas = [f"{titulo}:"]
    linhas.extend(f"- {item}" for item in itens if item)
    return "\n".join(linhas)


def _formatar_dados_formais(dados: dict | None) -> str:
    if not dados:
        return "DADOS FORMAIS: [NAO INFORMADO]"
    linhas = ["DADOS FORMAIS:"]
    for chave, valor in dados.items():
        linhas.append(f"- {chave}: {valor}")
    return "\n".join(linhas)


def _montar_user_prompt(payload: IaDefensivaInput, etapa: str) -> str:
    instrucao = PROMPTS[etapa]
    return "\n\n".join([
        f"ETAPA SOLICITADA: {etapa}",
        f"RITO: {payload.rito or '[INFORME]'}",
        f"AREA: {payload.area or '[INFORME]'}",
        f"MOMENTO DO CASO: {payload.momento or '[NAO INFORMADO]'}",
        f"NIVEL DE INTELIGENCIA: {payload.nivel_inteligencia}",
        f"PROTOCOLO COGNITIVO:\n{NIVEL_INSTRUCOES.get(payload.nivel_inteligencia, NIVEL_INSTRUCOES['alto'])}",
        _formatar_dados_formais(payload.dados_formais),
        _formatar_lista("DOCUMENTOS DO AUTOR", payload.documentos_autor),
        _formatar_lista("DOCUMENTOS DISPONIVEIS PARA A DEFESA", payload.documentos_defesa),
        f"ANALISES ANTERIORES:\n{payload.analises_anteriores or '[NAO INFORMADO]'}",
        f"PETICAO INICIAL / RELATO BASE:\n{payload.peticao_inicial}",
        f"INSTRUCAO DA ETAPA:\n{instrucao}",
        AVISO_REVISAO,
    ])


def _task_type(etapa: str, nivel: str) -> str:
    if etapa == "redigir_contestacao":
        return "elaboracao_peca"
    if nivel in {"alto", "maximo"}:
        return "estrategia"
    return "analise_juridica"


def _max_tokens(etapa: str, nivel: str) -> int:
    if nivel == "maximo":
        return 7200 if etapa in {"redigir_contestacao", "esqueleto_contestacao"} else 5600
    if nivel == "alto":
        return 6200 if etapa in {"redigir_contestacao", "esqueleto_contestacao"} else 4600
    return 5200 if etapa == "redigir_contestacao" else 3600


def _temperature(nivel: str) -> float:
    if nivel == "maximo":
        return 0.08
    if nivel == "alto":
        return 0.1
    return 0.15


async def executar_ia_defensiva(
    payload: IaDefensivaInput,
    db: AsyncSession,
    user_id: str,
) -> dict:
    if len(payload.peticao_inicial.strip()) < 50:
        raise ValueError("Informe a peticao inicial, relato ou base factual com ao menos 50 caracteres.")

    etapas = FLUXO_COMPLETO if payload.etapa == "fluxo_completo" else [payload.etapa]
    resultados: list[dict] = []
    acumulado = payload.analises_anteriores or ""
    total_input = 0
    total_output = 0
    modelo = ""
    provedor = ""

    for etapa in etapas:
        user_prompt = _montar_user_prompt(
            IaDefensivaInput(
                **{**payload.__dict__, "etapa": etapa, "analises_anteriores": acumulado or payload.analises_anteriores}
            ),
            etapa,
        )
        resp = await chat(
            messages=[
                {"role": "system", "content": SYSTEM_BASE + "\n\n" + NIVEL_INSTRUCOES.get(payload.nivel_inteligencia, NIVEL_INSTRUCOES["alto"])},
                {"role": "user", "content": user_prompt},
            ],
            task_type=_task_type(etapa, payload.nivel_inteligencia),
            temperature=_temperature(payload.nivel_inteligencia),
            max_tokens=_max_tokens(etapa, payload.nivel_inteligencia),
        )
        modelo = resp.modelo
        provedor = resp.provedor
        total_input += resp.input_tokens or 0
        total_output += resp.output_tokens or 0
        resultados.append({
            "etapa": etapa,
            "conteudo": resp.texto,
            "modelo": resp.modelo,
            "provedor": resp.provedor,
            "fallback_ativado": resp.fallback_ativado,
        })
        acumulado = (acumulado + "\n\n" if acumulado else "") + f"## {etapa}\n{resp.texto}"

    prompt_log, pii = sanitizar_pii(_montar_user_prompt(payload, etapas[0]))
    resposta_final = "\n\n".join(f"# {r['etapa']}\n\n{r['conteudo']}" for r in resultados)
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=payload.case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=modelo[:50] or "ai_gateway",
        prompt_sanitizado=prompt_log[:8000],
        pii_removida=pii,
        resposta=resposta_final,
        tokens_input=total_input or None,
        tokens_output=total_output or None,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id": log.id,
        "case_id": payload.case_id,
        "etapa": payload.etapa,
        "nivel_inteligencia": payload.nivel_inteligencia,
        "resultados": resultados,
        "resposta": resposta_final,
        "modelo": modelo,
        "provedor": provedor,
        "tokens_input": total_input,
        "tokens_output": total_output,
        "is_rascunho": True,
        "requer_revisao": True,
        "aviso": AVISO_REVISAO,
    }
