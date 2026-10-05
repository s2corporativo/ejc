// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
import { db } from "@/lib/db";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


const templates = [
  {
    slug: "peticao-inicial-civil",
    name: "Petição Inicial (Cível)",
    category: "peticao",
    description: "Petição inicial para processo cível — Ação Indenizatória, Cobrança, Execução etc.",
    icon: "FileText",
    prompt: `Você é um advogado brasileiro sênior redigindo uma petição inicial cível. Siga rigorosamente o Código de Processo Civil (Lei 13.105/2015). A petição deve conter: endereçamento ao juízo competente, qualificação das partes, fatos, fundamentos jurídicos, pedidos com seus requisitos (art. 319 do CPC), valor da causa e requerimentos finais. Use linguagem jurídica formal em português brasileiro.`,
    fields: JSON.stringify([
      { key: "tipoAcao", label: "Tipo de ação", type: "select", options: ["Indenização por danos morais", "Cobrança", "Execução de título extrajudicial", "Reintegração de posse", "Obrigação de fazer"] },
      { key: "competencia", label: "Juízo/Vara", type: "text", placeholder: "Ex: 1ª Vara Cível da Comarca de..." },
      { key: "autor", label: "Nome do autor (será anonimizado)", type: "text" },
      { key: "reu", label: "Nome do réu (será anonimizado)", type: "text" },
      { key: "fatos", label: "Fatos e fundamentos", type: "textarea", placeholder: "Descreva os fatos..." },
      { key: "pedidos", label: "Pedidos (linhas principais)", type: "textarea" },
      { key: "valorCausa", label: "Valor da causa (será anonimizado)", type: "text" }
    ])
  },
  {
    slug: "sentenca",
    name: "Sentença",
    category: "sentenca",
    description: "Minuta de sentença — dispositivo, fundamentação e parte dispositiva.",
    icon: "Gavel",
    prompt: `Você é um juiz brasileiro proferindo sentença. Siga o CPC (arts. 489 e 492). Estrutura: relatório, fundamentação (com análise de fatos e direito) e dispositivo. Indique se é procedente/improcedente/parcial. Use marcadores para dados sensíveis se necessário.`,
    fields: JSON.stringify([
      { key: "classe", label: "Classe processual", type: "text", placeholder: "Procedimento Comum Cível" },
      { key: "numeroProcesso", label: "Número do processo (anonimizado)", type: "text" },
      { key: "autor", label: "Nome do autor", type: "text" },
      { key: "reu", label: "Nome do réu", type: "text" },
      { key: "resumoFatos", label: "Resumo dos fatos", type: "textarea" },
      { key: "teses", label: "Teses das partes", type: "textarea" },
      { key: "decisao", label: "Direção do julgamento", type: "select", options: ["Procedente", "Improcedente", "Parcialmente procedente"] }
    ])
  },
  {
    slug: "recurso-apelacao",
    name: "Apelação",
    category: "recurso",
    description: "Razões de apelação cível com petições de interposição e razões.",
    icon: "Scale",
    prompt: `Você é um advogado recorrendo de sentença cível via apelação (CPC arts. 1.009 e seguintes). Estrutura: petição de interposição ao juízo a quo e razões dirigidas ao tribunal. Use fundamentação com teses de fato e direito.`,
    fields: JSON.stringify([
      { key: "numeroProcesso", label: "Número do processo", type: "text" },
      { key: "apelante", label: "Apelante", type: "text" },
      { key: "apelado", label: "Apelado", type: "text" },
      { key: "resumoSentenca", label: "Resumo da sentença recorrida", type: "textarea" },
      { key: "teseRecursal", label: "Tese recursal", type: "textarea" }
    ])
  },
  {
    slug: "contrato-prestacao-servicos",
    name: "Contrato de Prestação de Serviços",
    category: "contrato",
    description: "Minuta de contrato civil de prestação de serviços.",
    icon: "FileSignature",
    prompt: `Você é um advogado redigindo um contrato de prestação de serviços. Use o Código Civil. Cláusulas: qualificação, objeto, obrigação, valor, forma de pagamento, prazo, rescisão, foro. Linguagem formal.`,
    fields: JSON.stringify([
      { key: "contratante", label: "Contratante", type: "text" },
      { key: "contratada", label: "Contratada", type: "text" },
      { key: "objeto", label: "Objeto", type: "textarea" },
      { key: "valor", label: "Valor", type: "text" },
      { key: "prazo", label: "Prazo", type: "text" },
      { key: "foro", label: "Foro", type: "text" }
    ])
  },
  {
    slug: "parecer-juridico",
    name: "Parecer Jurídico",
    category: "parecer",
    description: "Parecer consultivo fundamentado com conclusão.",
    icon: "Lightbulb",
    prompt: `Você é um advogado consultivo emitindo parecer. Estrutura: ementa, relatório, fundamentação jurídica (legislação, jurisprudência e doutrina), conclusão. Use linguagem técnico-jurídica.`,
    fields: JSON.stringify([
      { key: "consultante", label: "Consultante", type: "text" },
      { key: "materia", label: "Matéria consultada", type: "textarea" },
      { key: "questionamentos", label: "Questionamentos", type: "textarea" }
    ])
  },
  {
    slug: "despacho",
    name: "Despacho / Decisão Interlocutória",
    category: "despacho",
    description: "Despacho ou decisão interlocutória em processo.",
    icon: "Stamp",
    prompt: `Você é um juiz proferindo decisão interlocutória (CPC art. 203). Estrutura: breve relato, fundamentação e dispositivo.`,
    fields: JSON.stringify([
      { key: "numeroProcesso", label: "Número do processo", type: "text" },
      { key: "pedido", label: "Pedido em análise", type: "textarea" },
      { key: "decisao", label: "Direção da decisão", type: "select", options: ["Deferimento", "Indeferimento", "Parcial"] }
    ])
  },
  {
    slug: "peticao-inicial-trabalhista",
    name: "Petição Inicial Trabalhista",
    category: "peticao",
    description: "Reclamação trabalhista (CLT) com pedidos verbas e anexo de documentos.",
    icon: "HardHat",
    prompt: `Você é um advogado trabalhista redigindo uma reclamação trabalhista (CLT art. 840, §1º c/c CPC art. 319). A petição deve conter: endereçamento à Vara do Trabalho, qualificação do reclamante e reclamada, fatos (relação de emprego, jornada, dispensa), fundamentos (verbas rescisórias, horas extras, danos morais), pedidos líquidos com valores, valor da causa e requerimentos. Use terminologia da CLT.`,
    fields: JSON.stringify([
      { key: "vara", label: "Vara do Trabalho", type: "text", placeholder: "Ex: 1ª Vara do Trabalho de..." },
      { key: "reclamante", label: "Nome do reclamante (anonimizado)", type: "text" },
      { key: "reclamada", label: "Nome da reclamada (anonimizado)", type: "text" },
      { key: "cargo", label: "Cargo/Função", type: "text" },
      { key: "salario", label: "Último salário (anonimizado)", type: "text" },
      { key: "periodo", label: "Período trabalhado", type: "text" },
      { key: "fatos", label: "Fatos (jornada, dispensa, verbas devidas)", type: "textarea" },
      { key: "pedidos", label: "Pedidos (horas extras, verbas rescisórias, dano moral)", type: "textarea" }
    ])
  },
  {
    slug: "queixa-crime",
    name: "Queixa-Crime (Ação Penal Privada)",
    category: "recurso",
    description: "Queixa-crime para crimes de ação penal privada (calúnia, difamação, injúria).",
    icon: "Shield",
    prompt: `Você é um advogado penalista redigindo uma queixa-crime (CPP art. 41 e 100, CP art. 145). Estrutura: endereçamento ao juízo criminal, qualificação do querelante e querelado, exposição do fato criminoso com circunstâncias, classificação jurídica do crime, rol de testemunhas e pedido de recebimento. Use CPP e CP.`,
    fields: JSON.stringify([
      { key: "vara", label: "Vara Criminal", type: "text" },
      { key: "querelante", label: "Nome do querelante (anonimizado)", type: "text" },
      { key: "querelado", label: "Nome do querelado (anonimizado)", type: "text" },
      { key: "crime", label: "Crime imputado", type: "select", options: ["Calúnia (art. 138 CP)", "Difamação (art. 139 CP)", "Injúria (art. 140 CP)", "Outro"] },
      { key: "fatos", label: "Exposição dos fatos criminosos", type: "textarea" },
      { key: "testemunhas", label: "Testemunhas (nomes)", type: "textarea" }
    ])
  },
  {
    slug: "defesa-fiscal",
    name: "Defesa Administrativa Fiscal",
    category: "parecer",
    description: "Defesa administrativa contra auto de infração fiscal (lançamento tributário).",
    icon: "Landmark",
    prompt: `Você é um advogado tributarista redigindo defesa administrativa contra auto de infração fiscal. Estrutura: endereçamento ao órgão julgador, qualificação do impugnante, exposição dos fatos, preliminares (nulidades), mérito (análise do fato gerador, base de cálculo, alíquota, isenções), jurisprudência e pedido de cancelamento total/parcial. Use CTN e legislação específica.`,
    fields: JSON.stringify([
      { key: "orgao", label: "Órgão julgador", type: "text", placeholder: "Ex: Delegacia de Julgamento da Receita Federal" },
      { key: "impugnante", label: "Nome do impugnante (anonimizado)", type: "text" },
      { key: "autoInfracao", label: "Auto de infração nº (anonimizado)", type: "text" },
      { key: "tributo", label: "Tributo", type: "select", options: ["IRPF", "IRPJ", "ICMS", "ISS", "IPTU", "Contribuições Previdenciárias", "Outro"] },
      { key: "valor", label: "Valor do auto (anonimizado)", type: "text" },
      { key: "fundamentos", label: "Fundamentos da defesa", type: "textarea" }
    ])
  },
  {
    slug: "carta-direito-imagem",
    name: "Carta — Exercício do Direito de Imagem",
    category: "contrato",
    description: "Carta/termo de autorização de uso de imagem (CC art. 20).",
    icon: "Image",
    prompt: `Você é um advogado redigindo um termo de autorização de uso de imagem (Código Civil art. 20 e Lei de Direitos Autorais). Estrutura: qualificação do cedente, finalidade do uso, prazo, mídia/veículos autorados, contraprestação (se houver), revogação, foro. Linguagem formal mas acessível.`,
    fields: JSON.stringify([
      { key: "cedente", label: "Nome do cedente (anonimizado)", type: "text" },
      { key: "cedida", label: "Nome da empresa cessionária (anonimizado)", type: "text" },
      { key: "finalidade", label: "Finalidade do uso da imagem", type: "textarea" },
      { key: "midias", label: "Mídias/veículos autorados", type: "textarea" },
      { key: "prazo", label: "Prazo de vigência", type: "text" },
      { key: "contraprestacao", label: "Contraprestação (valor, se houver)", type: "text" }
    ])
  },
  {
    slug: "carta-notificacao-extrajudicial",
    name: "Notificação Extrajudicial",
    category: "parecer",
    description: "Carta de notificação extrajudicial com intimação e prazo.",
    icon: "Mail",
    prompt: `Você é um advogado redigindo uma notificação extrajudicial. Estrutura: endereçamento ao notificado, qualificação do notificante, exposição dos fatos, fundamento legal/contratual, intimação com prazo, consequências do descumprimento, foro. Linguagem formal e assertiva. A notificação constitui marco interruptivo da prescrição (art. 202, VI, CC).`,
    fields: JSON.stringify([
      { key: "notificado", label: "Nome do notificado (anonimizado)", type: "text" },
      { key: "notificante", label: "Nome do notificante (anonimizado)", type: "text" },
      { key: "materia", label: "Matéria da notificação", type: "select", options: ["Cobrança", "Descumprimento contratual", "Rescisão", "Direito do consumidor", "Ação reparatória", "Outro"] },
      { key: "fatos", label: "Exposição dos fatos", type: "textarea" },
      { key: "prazo", label: "Prazo para resposta (dias)", type: "text" }
    ])
  }
];

const skills = [
  { slug: "cpc-estrutura-peticao", name: "CPC — Estrutura da Petição Inicial", category: "civil", description: "Diretrizes do art. 319 do CPC para petição inicial.", content: "Toda petição inicial deve conter: (I) o juízo a que é dirigida; (II) os nomes, prenomes, estado civil, profissão, CPF, endereço do autor e do réu; (III) o fato e os fundamentos jurídicos do pedido; (IV) o pedido com suas especificações; (V) o valor da causa; (VI) as provas que o autor pretende produzir; (VII) a opção pela audiência de conciliação." },
  { slug: "cpc-juizo-competente", name: "CPC — Juízo Competente", category: "civil", description: "Diretrizes para endereçamento ao juízo competente.", content: "Verificar competência em razão da matéria (art. 42 e seguintes do CPC) e do valor (art. 44 e seguintes). Regra geral: foro do domicílio do réu (art. 46). Exceções legais devem ser identificadas." },
  { slug: "dano-moral-parameters", name: "Dano Moral — Parâmetros", category: "civil", description: "Parâmetros de arbitramento de dano moral.", content: "O arbitramento da indenização por dano moral deve ser razoável, proporcional ao grau de afetação, à gravidade da conduta e à condição econômica das partes. Recorrer à jurisprudência do STJ para parâmetros de quantum em casos análogos (inscrição indevida em cadastros, atraso em serviço de telefonia, etc.)." },
  { slug: "lgpd-dados-sensiveis", name: "LGPD — Dados Sensíveis", category: "civil", description: "Identificação de dados sensíveis para anonimização.", content: "Dados sensíveis (art. 5º II da LGPD): origem racial, convicção religiosa, opinião política, saúde, vida sexual, dado genético/biométrico. Em processos, informações sobre saúde, filiação sindical, biométricas. Devem ser marcados como [DADO_SENSIVEL_XXXX] antes do envio à IA." },
  { slug: "cp-legitimacao", name: "CP — Legitimação e Tipificação", category: "penal", description: "Diretrizes para denúncia e tipificação penal.", content: "A denúncia deve conter a descrição do fato com todas as suas circunstâncias (art. 41 do CPP), a qualificação do acusado, a classificação do crime e o rol de testemunhas. Verificar tipificação adequada no Código Penal, exclusão de ilicitude e causas de aumento/diminuição." },
  { slug: "clt-peticao-inicial-trabalhista", name: "CLT — Petição Inicial Trabalhista", category: "trabalhista", description: "Diretrizes da CLT para petição inicial trabalhista.", content: "A petição inicial trabalhista (art. 840, § 1º, CLT e art. 319 do CPC) deve conter: juízo, qualificação, fatos, fundamentos, pedidos, valor da causa e opção por audiência. Indicar o objeto litigioso e especificar o valor pretendido para cada pedido." },
  { slug: "ctn-lancamento-tributario", name: "CTN — Lançamento Tributário", category: "tributario", description: "Diretrizes sobre lançamento e constituição do crédito tributário.", content: "O crédito tributário é constituído pelo lançamento (arts. 142-150 do CTN). Verificar modalidade (por declaração, diretamente ou por homologação), decadência e prescrição. Para defesa, examinar nulidades do lançamento, fato gerador, base de cálculo, alíquota e sujeito passivo." },
  { slug: "cdc-defesa-consumer", name: "CDC — Defesa do Consumidor", category: "consumer", description: "Diretrizes para defesa do consumidor (Lei 8.078/90).", content: "Aplicar a hipossuficiência do consumidor (art. 4º I CDC), inversão do ônus da prova (art. 6º VIII), responsabilidade objetiva do fornecedor (art. 12-14), decadência (art. 26) e prescrição (art. 27). Pedidos típicos: devolução, indenização material e moral, tutela coletiva." },
  { slug: "cc-responsabilidade-civil", name: "CC — Responsabilidade Civil", category: "civil", description: "Diretrizes da responsabilidade civil no Código Civil.", content: "Verificar modalidade: subjetiva (art. 927 CC, com dolo/culpa) ou objetiva (art. 927 parágrafo único, atividades de risco). Elementos: conduta, nexo causal, dano e (quando subjetiva) culpa. Causas de exclusão: culpa exclusiva da vítima, fato de terceiro, caso fortuito/força maior." },
  { slug: "familia-alimentos", name: "Família — Alimentos", category: "family", description: "Diretrizes para ação de alimentos (Lei 5.478/68 e Lei 13.058/2014).", content: "A ação de alimentos pode ser proposta pelo representante legal ou pelo próprio alimentando. Verificar proporcionalidade (Binômio/Trinômio: necessidade x possibilidade), alimentos provisórios, fixação em percentual de salário-mínimo ou em valor, prisão civil em caso de inadimplemento voluntário e inescusável (art. 528, CPC)." },
  { slug: "cnj-615-2025", name: "CNJ 615/2025 — IA no Judiciário", category: "civil", description: "Diretrizes da Resolução CNJ 615/2025 sobre uso de IA.", content: "A Resolução 615/2025 do CNJ estabelece princípios para uso de IA no Poder Judiciário: transparência, explicabilidade, imparcialidade, supervisão humana, responsabilidade, segurança e privacidade. As decisões proferidas com apoio de IA devem ser submetidas a revisão humana. Direito à explicação das decisões automatizadas." },
  { slug: "inss-tempo-contribuicao", name: "INSS — Tempo de Contribuição", category: "previdenciario", description: "Diretrizes para ação previdenciária de tempo de contribuição.", content: "Para comprovar tempo de contribuição: CTC, CNIS, carnês, hollerith com descontos previdenciários. Diferenciar tempo comum, especial e rural. Aplicar fator previdenciário e fórmula 60/60 (EC 103/2019) quando aplicável. Verificar idade mínima e pedágio para transição." },
  { slug: "tutela-urgencia", name: "CPC — Tutela de Urgência e Evidência", category: "civil", description: "Diretrizes para pedido de tutela antecipada.", content: "Tutela de urgência antecipada (CPC art. 300): probabilidade do direito + perigo de dano ou risco ao resultado útil do processo. Tutela de evidência (art. 311): independe de perigo, funda-se em fatos incontroversos, vinculados, tese firmada em julgamento de casos repetitivos. Contracautela: caução, defesa em 15 dias." },
  { slug: "audiencia-conciliacao", name: "CPC — Audiência de Conciliação", category: "civil", description: "Diretrizes sobre opção por audiência de conciliação.", content: "Art. 319, VII do CPC: a petição inicial deve informar a opção (ou não) pela audiência de conciliação. Se não houver opção, presume-se a recusa. Para réu revel que não optou, o juiz deve convocar audiência. Conciliação homologada por sentença faz coisa julgada material e é título executivo judicial." },
  { slug: "juros-correcao-monetaria", name: "Juros e Correção Monetária", category: "civil", description: "Diretrizes para cálculo de juros e correção.", content: "Correção monetária: INPC (tabela prática do TJ), IPCA-E em casos de IPCA. Juros de mora: 1% ao mês (art. 406 CC) ou 0,5% (Súmula 482 STJ) conforme a relação jurídica. Em débitos trabalhistas: 1% ao mês até a Súmula 381 TST e ND a partir de 30/06/2009. Juros simples salvo previsão contratual de compostos." },
  { slug: "oab-estatuto-advocacia", name: "OAB — Estatuto da Advocacia", category: "civil", description: "Diretrizes do Estatuto da OAB (Lei 8.906/94).", content: "O advogado é indispensável à administração da justiça (art. 133 CF). Honorários de sucumbência: 10-20% sobre o proveito econômico (art. 85 CPC) ou 5-15% sobre o valor atualizado. Imunidade profissional para atos de ofício (art. 7º §2º EOAB). Sigilo profissional é direito e dever (art. 7º II)." },
  { slug: "consumidor-pratica-abusiva", name: "CDC — Cláusulas Abusivas", category: "consumer", description: "Diretrizes sobre nulidade de cláusulas abusivas.", content: "São nulas de pleno direito as cláusulas abusivas (art. 51 CDC), como: renúncia a direitos, multas desproporcionais, cláusula de adesão que impede rebut de prova, autorização para entrada no domicílio sem consentimento, inversão abusiva de ônus. Lista exemplificativa do §1º. Nulidade de pleno direito não precisa ser arguida expressamente." }
];

const news = [
  { slug: "geracao-lote", title: "Geração em Lote com Etapas", summary: "Aprove a primeira minuta do lote e saiba como serão todas as outras.", body: "Para as demandas repetitivas, a Geração em Lote ganhou a Geração em etapas: a IA gera primeiro a minuta de um processo escolhido como modelo, você a revisa e aprova no editor, e ela passa a servir de molde para as demais. Todo o lote segue a estrutura, a tese, a jurisprudência e o estilo aprovados.", category: "recurso", date: new Date("2026-10-03T00:00:00Z") },
  { slug: "novo-editor", title: "Novo Editor: a minuta virou um documento de verdade", summary: "Páginas reais com timbrado, cabeçalho, rodapé, numeração, notas de rodapé, comentários e histórico.", body: "Apresentamos o novo editor de minutas. Páginas de verdade, com timbrado, cabeçalho, rodapé, numeração e notas de rodapé na tela; comentários e histórico de versões; tabelas, localizar e substituir, sumário; e uma IA que sugere em vez de reescrever: cada edição chega como sugestão, você aceita ou rejeita.", category: "recurso", date: new Date("2026-09-17T00:00:00Z") },
  { slug: "prints-processo", title: "Prints do Processo: a prova entra como imagem", summary: "A IA decide quando um trecho vale mais como figura do que como descrição.", body: "Com um clique, a IA passa a enxergar onde estão as imagens do processo e decide quando um extrato, uma foto, um comprovante ou uma assinatura vale mais como figura do que como descrição. Ela recorta o trecho exato da página e o insere na minuta com legenda numerada e a página de origem.", category: "recurso", date: new Date("2026-09-09T00:00:00Z") },
  { slug: "habilidades-skills", title: "Habilidades (skills): o entendimento jurídico da IA", summary: "2.000 pacotes de conhecimento jurídico, escritos pela equipe, abertos para ler, auditar e editar.", body: "Apresentamos as Habilidades (skills): pacotes de conhecimento jurídico que orientam cada geração como texto legível. Você vê quais participaram de cada peça, lê a íntegra do que chegou ao modelo, fixa as inegociáveis com #, edita com o seu entendimento e recebe as atualizações do catálogo sem perder as suas mudanças.", category: "recurso", date: new Date("2026-07-13T00:00:00Z") },
  { slug: "jurisprudenciaia", title: "JurisprudênciaIA: nova forma de pesquisar jurisprudência", summary: "Site público para encontrar jurisprudência conversando com uma IA.", body: "No Modo IA, você descreve o caso em linguagem natural e a IA combina busca por palavra (BM25) e busca por significado (embeddings) para encontrar o precedente certo, com a ementa na íntegra.", category: "novoproduto", date: new Date("2026-06-10T00:00:00Z") }
];

async function seed() {
  console.log("🌱 Seeding JuridIA...");

  for (const t of templates) {
    await db.template.upsert({ where: { slug: t.slug }, update: t, create: t });
    console.log("  ✓ template:", t.slug);
  }

  for (const s of skills) {
    await db.skill.upsert({ where: { slug: s.slug }, update: s, create: s });
    console.log("  ✓ skill:", s.slug);
  }

  for (const n of news) {
    await db.newsItem.upsert({ where: { slug: n.slug }, update: n, create: n });
    console.log("  ✓ news:", n.slug);
  }

  const existing = await db.user.findUnique({ where: { email: "demo@juridia.com.br" } });
  if (!existing) {
    await db.user.create({
      data: { email: "demo@juridia.com.br", name: "Advogado Demo", plan: "individual_2", minutasUsed: 47, minutasLimit: 200 }
    });
    console.log("  ✓ demo user created");
  }

  console.log("✅ Seed done");
}

seed()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
