// ⚠️  DEPRECATED — NÃO RODAR EM PRODUÇÃO
// Este script popula o banco com dados fictícios (skills, fontes, advogados fake, etc.)
// Para produção, use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).
// Em desenvolvimento: pode rodar para popular a base de conhecimento,
// mas NÃO deve ser incluído em deploy scripts ou CI/CD.
import { db } from "@/lib/db";
import { createHash } from "crypto";

// ── GUARD: bloqueia execução em produção ──────────────────────────────────
if (process.env.NODE_ENV === "production") {
  console.error("❌ Este script de seed NÃO deve rodar em produção.");
  console.error("   Use apenas fontes REAIS oficiais (Planalto, CNJ, STJ, STF).");
  process.exit(1);
}


// ── Skills consumidor/bancário — estrutura jurídica completa ────────────────
// Cada skill tem: gatilhos, questões obrigatórias, provas, teses, contrateses,
// jurisprudência, legislação, riscos, pedidos, fontes, versão.

const SKILLS = [
  {
    slug: "fraude-bancaria",
    nome: "Fraude bancária e responsabilidade da instituição financeira",
    area: "consumer",
    gatilhos: ["fraude", "conta invadida", "transação não reconhecida", "movimentação indevida"],
    questoesObrigatorias: [
      "Houve falha de segurança do banco?",
      "O banco comunicou o risco ao cliente?",
      "Houve autorização expressa do cliente para a transação?",
      "Existe culpa exclusiva do correntista?",
      "O cliente adotou medidas de proteção (senha, 2FA)?",
    ],
    provas: ["extratos bancários", "boletim de ocorrência", "logs de acesso", "comunicações com o banco", "comprovante de notificação"],
    teses: ["Responsabilidade objetiva do banco (art. 14 CDC)", "Fortuito interno não exime o banco", "Falha no dever de segurança"],
    contrateses: ["Culpa exclusiva do consumidor (compartilhamento de senha)", "Fraude por engenharia social sem falha do banco", "Cas fortuito externo"],
    jurisprudencia: ["STJ - REsp 1.598.096 - fraude bancária", "STJ - REsp 1.579.746 - responsabilidade objetiva"],
    legislacao: ["CDC art. 14", "CC art. 927", "Lei 12.865/2013 (PIX)"],
    riscos: ["Culpa exclusiva do consumidor", "Ausência de boletim de ocorrência", "Demora na comunicação ao banco"],
    pedidos: ["Indenização material", "Indenização por danos morais", "Tutela de urgência para bloqueio", "Restituição dos valores"],
  },
  {
    slug: "pix-fraudulento",
    nome: "PIX fraudulento e responsabilidade da instituição",
    area: "consumer",
    gatilhos: ["PIX não reconhecido", "PIX fraudulento", "transferência indevida", "dinheiro sumido"],
    questoesObrigatorias: [
      "O cliente autorizou a transação PIX?",
      "Houve quebra de sigilo de senha/chave?",
      "O banco foi notificado imediatamente?",
      "Existe mecanismo de defesa do consumidor (MED - Mecanismo Especial de Devolução)?",
      "O cliente usou 2FA ou biometria?",
    ],
    provas: ["comprovante PIX", "boletim de ocorrência", "logs do app", "protocolo de comunicação ao banco"],
    teses: ["Responsabilidade objetiva (Lei 12.865/2013 art. 10)", "Dever de segurança da instituição", "Fortuito interno"],
    contrateses: ["Culpa exclusiva do cliente (senha compartilhada)", "Negligência do correntista", "Fraude por engenharia social"],
    jurisprudencia: ["STJ - PIX fraudulento - responsabilidade objetiva"],
    legislacao: ["Lei 12.865/2013 art. 10", "CDC art. 14", "Resolução BCB 32/2020"],
    riscos: ["Culpa exclusiva", "Demora na comunicação (>24h)", "Ausência de BO"],
    pedidos: ["Devolução em dobro", "Danos morais", "Tutela de urgência"],
  },
  {
    slug: "negativacao-indevida",
    nome: "Negativação indevida em cadastro de proteção ao crédito",
    area: "consumer",
    gatilhos: ["SERASA", "SPC", "inscrição indevida", "negativação", "cadastro de inadimplentes"],
    questoesObrigatorias: [
      "O débito foi quitado antes da inscrição?",
      "Houve comunicação prévia ao consumidor (art. 43 CDC)?",
      "O valor é contestado?",
      "Houve dano moral in re ipsa?",
    ],
    provas: ["comprovante de pagamento", "certidão do SERASA/SPC", "notificação de dívida", "extrato"],
    teses: ["Dano moral in re ipsa pela inscrição indevida", "Responsabilidade objetiva do credor", "Violação ao art. 43 CDC"],
    contrateses: ["Dívida existente e não quitada", "Comunicação prévia efetuada", "Culpa do devedor"],
    jurisprudencia: ["STJ Súmula 359 - negativação indevida", "STJ - dano moral in re ipsa"],
    legislacao: ["CDC art. 42", "CDC art. 43", "CC art. 186"],
    riscos: ["Dívida real que não foi quitada", "Comunicação prévia efetuada", "Decadência"],
    pedidos: ["Cancelamento da inscrição", "Indenização por danos morais", "Declaratória de inexistência de débito"],
  },
  {
    slug: "cobranca-indevida",
    nome: "Cobrança indevida e excessiva",
    area: "consumer",
    gatilhos: ["cobrança indevida", "cobrança abusiva", "tarifa indevida", "cobrança não autorizada"],
    questoesObrigatorias: [
      "O serviço foi efetivamente prestado?",
      "A cobrança foi autorizada?",
      "Houve devolução em dobro (art. 42 CDC)?",
      "A cobrança persistiu após contestação?",
    ],
    provas: ["fatura", "comprovante de pagamento", "contestação por escrito", "protocolo de reclamação"],
    teses: ["Devolução em dobro (art. 42 CDC parágrafo único)", "Cobrança abusiva", "Vício de serviço"],
    contrateses: ["Serviço efetivamente prestado", "Autorização do consumidor", "Ausência de vício"],
    jurisprudencia: ["STJ - devolução em dobro art. 42 CDC"],
    legislacao: ["CDC art. 42 parágrafo único", "CDC art. 20", "CDC art. 51"],
    riscos: ["Serviço efetivamente prestado", "Autorização do consumidor"],
    pedidos: ["Devolução em dobro", "Indenização por danos morais", "Tutela de urgência"],
  },
  {
    slug: "responsabilidade-objetiva-bancaria",
    nome: "Responsabilidade objetiva da instituição bancária",
    area: "consumer",
    gatilhos: ["banco", "instituição financeira", "responsabilidade objetiva", "falha do banco"],
    questoesObrigatorias: [
      "A relação é de consumo?",
      "Houve falha na prestação do serviço?",
      "Existe nexo causal entre a conduta e o dano?",
      "Houve caso fortuito externo?",
    ],
    provas: ["contrato", "extratos", "comunicações", "boletim de ocorrência"],
    teses: ["Responsabilidade objetiva (art. 14 CDC)", "Dever de segurança", "Fortuito interno não exime"],
    contrateses: ["Culpa exclusiva do consumidor", "Caso fortuito externo", "Fato de terceiro"],
    jurisprudencia: ["STJ Súmula 287 - responsabilidade objetiva", "STJ - fortuito interno"],
    legislacao: ["CDC art. 14", "CC art. 927 parágrafo único"],
    riscos: ["Culpa exclusiva do consumidor", "Caso fortuito externo comprovado"],
    pedidos: ["Indenização material", "Indenização por danos morais"],
  },
  {
    slug: "fortuito-interno",
    nome: "Fortuito interno e responsabilidade do fornecedor",
    area: "consumer",
    gatilhos: ["fortuito interno", "evento interno", "falha interna", "risco da atividade"],
    questoesObrigatorias: [
      "O evento estava dentro da esfera de risco da atividade do fornecedor?",
      "Houve impossibilidade de evitar o evento?",
      "O fornecedor demonstrou que não houve culpa?",
    ],
    provas: ["parecer técnico", "laudo", "logs do sistema", "comunicações internas"],
    teses: ["Fortuito interno não exime a responsabilidade objetiva", "Risco inerente à atividade"],
    contrateses: ["Caso fortuito externo", "Fato de terceiro", "Culpa exclusiva da vítima"],
    jurisprudencia: ["STJ - fortuito interno não exime responsabilidade objetiva"],
    legislacao: ["CDC art. 14 §3º", "CC art. 927 parágrafo único"],
    riscos: ["Demonstração de fortuito externo", "Culpa exclusiva do consumidor"],
    pedidos: ["Indenização material", "Indenização por danos morais"],
  },
  {
    slug: "dano-moral-consumerista",
    nome: "Dano moral consumerista",
    area: "consumer",
    gatilhos: ["dano moral", "abalo", "constrangimento", "humilhação", "dano à imagem"],
    questoesObrigatorias: [
      "O fato gerador está comprovado?",
      "Houve dano moral in re ipsa ( dispensa prova do abalo)?",
      "Qual o quantum adequado?",
      "Houve reiteração da conduta?",
    ],
    provas: ["comprovantes", "certidões", "testemunhas", "laudo psicológico (se necessário)"],
    teses: ["Dano moral in re ipsa (inscrição indevida, recusa indevida)", "Quantificação proporcional", "Reiteração agrava o dano"],
    contrateses: ["Mero aborrecimento", "Ausência de prova do abalo", "Culpa exclusiva do consumidor"],
    jurisprudencia: ["STJ - dano moral in re ipsa", "STJ - quantificação dano moral"],
    legislacao: ["CC art. 186", "CC art. 927", "CDC art. 6 VI"],
    riscos: ["Quantificação excessiva", "Mero aborrecimento", "Ausência de prova"],
    pedidos: ["Indenização por danos morais", "Indenização por danos materiais (se houve)"],
  },
  {
    slug: "inversao-onus-prova-consumerista",
    nome: "Inversão do ônus da prova no consumidor",
    area: "consumer",
    gatilhos: ["ônus da prova", "inversão", "hipossuficiência", "verossimilhança"],
    questoesObrigatorias: [
      "O consumidor é hipossuficiente?",
      "A alegação é verossímil?",
      "A prova está na esfera do fornecedor?",
    ],
    provas: ["documento que justifique a hipossuficiência", "indícios de verossimilhança"],
    teses: ["Inversão do ônus da prova (art. 6 VIII CDC)", "Hipossuficiência técnica", "Verossimilhança das alegações"],
    contrateses: ["Não há hipossuficiência", "Alegação não verossímil", "Prova acessível ao consumidor"],
    jurisprudencia: ["STJ - inversão do ônus da prova consumerista"],
    legislacao: ["CDC art. 6 VIII", "CDC art. 38"],
    riscos: ["Negação da hipossuficiência", "Alegação não verossímil"],
    pedidos: ["Inversão do ônus da prova"],
  },
  {
    slug: "tutela-urgencia-consumerista",
    nome: "Tutela de urgência consumerista",
    area: "consumer",
    gatilhos: ["tutela", "urgência", "liminar", "antecipação de tutela", "dano irreparável"],
    questoesObrigatorias: [
      "Há probabilidade do direito (fumus boni iuris)?",
      "Há perigo de dano ou risco ao resultado (periculum in mora)?",
      "A tutela é reversível?",
    ],
    provas: ["documentos que evidenciem probabilidade do direito", "indícios de urgência"],
    teses: ["Tutela de urgência antecipada (art. 300 CPC)", "Tutela de evidência (art. 311 CPC)"],
    contrateses: ["Ausência de perigo", "Direrito não provável", "Irreversibilidade"],
    jurisprudencia: ["STJ - tutela de urgência consumerista"],
    legislacao: ["CPC art. 300", "CPC art. 311", "CDC art. 84"],
    riscos: ["Ausência de periculum", "Irreversibilidade do provimento"],
    pedidos: ["Tutela de urgência", "Liminar"],
  },
  {
    slug: "repeticao-debito",
    nome: "Repetição de indébito",
    area: "consumer",
    gatilhos: ["repetição de indébito", "pagamento indevido", "devolução", "cobrança indevida"],
    questoesObrigatorias: [
      "O pagamento foi efetuado?",
      "A cobrança era indevida?",
      "Houve má-fé do credor?",
    ],
    provas: ["comprovante de pagamento", "fatura", "notificação de contestação"],
    teses: ["Repetição simples ou em dobro (art. 42 CDC)", "Enriquecimento sem causa"],
    contrateses: ["Dívida existente", "Pagamento espontâneo de dívida válida"],
    jurisprudencia: ["STJ - repetição de indébito art. 42 CDC"],
    legislacao: ["CDC art. 42 parágrafo único", "CC art. 876"],
    riscos: ["Dívida válida", "Pagamento espontâneo"],
    pedidos: ["Devolução simples", "Devolução em dobro", "Indenização por danos morais"],
  },
];

async function seedConsumerSkills() {
  console.log("🌱 Criando skills consumidor/bancário...");
  let created = 0;
  let skipped = 0;

  for (const s of SKILLS) {
    const content = [
      `# ${s.nome}`,
      `\n## Área: ${s.area}`,
      `\n## Gatilhos\n${s.gatilhos.map((g) => `- ${g}`).join("\n")}`,
      `\n## Questões obrigatórias\n${s.questoesObrigatorias.map((q) => `- ${q}`).join("\n")}`,
      `\n## Provas necessárias\n${s.provas.map((p) => `- ${p}`).join("\n")}`,
      `\n## Teses\n${s.teses.map((t) => `- ${t}`).join("\n")}`,
      `\n## Contrateses\n${s.contrateses.map((c) => `- ${c}`).join("\n")}`,
      `\n## Jurisprudência\n${s.jurisprudencia.map((j) => `- ${j}`).join("\n")}`,
      `\n## Legislação\n${s.legislacao.map((l) => `- ${l}`).join("\n")}`,
      `\n## Riscos\n${s.riscos.map((r) => `- ${r}`).join("\n")}`,
      `\n## Pedidos\n${s.pedidos.map((p) => `- ${p}`).join("\n")}`,
    ].join("\n");

    const contentHash = createHash("sha256").update(content, "utf8").digest("hex");

    const existing = await db.skillVersion.findFirst({
      where: { slug: s.slug },
      orderBy: { version: "desc" },
    });

    if (existing && existing.contentHash === contentHash) {
      skipped++;
      continue;
    }

    const nextVersion = (existing?.version || 0) + 1;

    try {
      await db.skillVersion.create({
        data: {
          slug: s.slug,
          version: nextVersion,
          area: s.area,
          description: s.nome,
          content,
          triggers: JSON.stringify({ keywords: s.gatilhos }),
          rules: JSON.stringify(s.teses),
          exceptions: JSON.stringify(s.contrateses),
          forbiddenClaims: JSON.stringify(["promessa_resultado", "lei_inventada"]),
          allowedTools: JSON.stringify([]),
          outputSchema: JSON.stringify({ type: "text" }),
          status: "approved",
          contentHash,
          approvedBy: "curador-juridico",
          approvedAt: new Date(),
        },
      });
      created++;
      console.log(`  ✓ ${s.slug} v${nextVersion} → approved`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("Unique constraint")) {
        skipped++;
      } else {
        console.error(`  ✗ ${s.slug}:`, msg);
      }
    }
  }

  console.log(`\n✅ ${created} skills criadas, ${skipped} já existiam`);
  console.log(`📊 Total SkillVersions: ${await db.skillVersion.count()}`);
  console.log(`📊 Consumer approved: ${await db.skillVersion.count({ where: { status: "approved", area: "consumer" } })}`);
}

seedConsumerSkills()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
