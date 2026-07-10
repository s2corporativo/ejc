# ── app/services/system_prompts/padrao_ouro.py ───────────────────────────────
# Padrão-ouro de redação de peças — regras estruturais extraídas da petição
# inicial de referência do escritório (JEC consumidor, "padrão-ouro").
#
# Módulo próprio (e não em peca_service/minutas) de propósito: a constante é
# compartilhada pela ETAPA 7 do pipeline de peças (services/peca_service.py) e
# pelo PROMPT_MINUTAS (system_prompts/minutas.py) — importar de um lado no outro
# criaria import circular via services/__init__/ai_gateway. Mantê-la ao lado de
# base.py segue o padrão do pacote: prompts são dados, services são fluxo.
PADRAO_OURO_PECA = """
## PADRÃO-OURO DE REDAÇÃO (estrutura obrigatória da peça)
1. DOS FATOS em parágrafos NUMERADOS (1., 2., 3., ...), em narrativa cronológica,
   com as datas destacadas em **negrito**. CADA fato relevante deve ser ancorado
   à prova que o comprova com a notação "(doc. NN)", usando a RELAÇÃO DE PROVAS
   fornecida. Fato relevante sem prova correspondente: indicar "[prova a juntar]"
   — NUNCA inventar documento ou numeração de prova inexistente.
2. Quando houver elementos FORNECIDOS sobre a parte contrária (multas aplicadas,
   decisões administrativas, notícias regulatórias, histórico de conduta
   reiterada), reúna-os em seção própria intitulada "DO CONTEXTO E DA CONDUTA
   REITERADA DA PARTE CONTRÁRIA". NUNCA invente esses elementos; sem material
   fornecido, omita a seção por completo.
3. DO DIREITO dividido em SUBSEÇÕES numeradas (ex.: IV.1, IV.2, IV.3...), com UMA
   tese jurídica por subseção; cada subseção deve CONECTAR o dispositivo legal ao
   fato concreto narrado (nunca citar lei em abstrato). Lei citada por extenso na
   1ª menção (ex.: "artigo 14 do Código de Defesa do Consumidor (Lei 8.078/1990)").
4. DANO MORAL (quando pleiteado): fundamentar a quantificação com fatores
   agravantes enumerados ((i), (ii), (iii)...) extraídos dos fatos narrados.
5. TUTELA DE URGÊNCIA (quando pleiteada): demonstrar fumus boni iuris e periculum
   in mora com referência EXPRESSA aos fatos numerados e às provas "(doc. NN)" —
   nunca com alegações genéricas; especificar prazo de cumprimento, multa diária
   e teto da multa.
6. DOS PEDIDOS escalonados em letras (a, b, c, ...), com subitens (ex.: e.1,
   e.2...) quando um pedido tiver desdobramentos; cada pedido condenatório deve
   indicar valor, índice de correção monetária e termo inicial dos juros.
7. VALOR DA CAUSA com memória de soma EXPLÍCITA dos pedidos econômicos
   (art. 292 do Código de Processo Civil).
8. Ao final da peça, seção "RELAÇÃO DE DOCUMENTOS ANEXOS": para cada prova do
   caso, uma linha "Doc. NN — descrição — o que comprova". Incluir entradas
   "[A ser anexado pelo cliente]" para os documentos pessoais padrão (RG/CPF,
   comprovante de residência) quando fizer sentido para o tipo de ação.
"""
