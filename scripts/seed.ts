import { db } from "@/lib/db";

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
  { slug: "cnj-615-2025", name: "CNJ 615/2025 — IA no Judiciário", category: "civil", description: "Diretrizes da Resolução CNJ 615/2025 sobre uso de IA.", content: "A Resolução 615/2025 do CNJ estabelece princípios para uso de IA no Poder Judiciário: transparência, explicabilidade, imparcialidade, supervisão humana, responsabilidade, segurança e privacidade. As decisões proferidas com apoio de IA devem ser submetidas a revisão humana. Direito à explicação das decisões automatizadas." }
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
