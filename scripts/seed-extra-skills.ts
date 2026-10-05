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


// ── Skills trabalhista, tributário, penal, família, administrativo ──────────
const SKILLS = [
  // ── TRABALHISTA ──────────────────────────────────────────────────────────
  {
    slug: "horas-extras",
    nome: "Horas extras e sobreaviso",
    area: "trabalhista",
    gatilhos: ["horas extras", "hora extra", "sobreaviso", "jornada excedente", "trabalho além do horário"],
    questoesObrigatorias: ["A jornada estava registrada?", "Houve autorização para horas extras?", "O sobreaviso foi utilizado?"],
    provas: ["holerith", "cartão de ponto", "registro de jornada", "e-mail de cobrança de horas"],
    teses: ["Horas extras não pagas (art. 59 CLT)", "Sobreaviso remunerado (Súmula 428 TST)"],
    contrateses: ["Cargo de confiança (art. 62 CLT)", "Jornada dentro do limite legal", "Acordo de compensação válido"],
    jurisprudencia: ["TST Súmula 85 - horas extras", "TST Súmula 428 - sobreaviso"],
    legislacao: ["CLT art. 59", "CLT art. 62", "CLT art. 58 §2º"],
    riscos: ["Cargo de confiança", "Acordo de compensação", "Falta de registro de jornada"],
    pedidos: ["Pagamento de horas extras", "Reflexos nas verbas rescisórias", "Adicional de sobreaviso"],
  },
  {
    slug: "rescisao-indireta",
    nome: "Rescisão indireta (justa causa do empregador)",
    area: "trabalhista",
    gatilhos: ["rescisão indireta", "distrato", "justa causa do empregador", "artigo 484 CLT"],
    questoesObrigatorias: ["Houve descumprimento de obrigação contratual?", "O empregador forçou a demissão?", "Houve atraso salarial?"],
    provas: ["holerith", "comunicações", "testemunhas", "contrato"],
    teses: ["Rescisão indireta (art. 484 CLT)", "Descumprimento contratual pelo empregador"],
    contrateses: ["Não houve justa causa do empregador", "Demissão voluntária", "Culpa exclusiva do empregado"],
    jurisprudencia: ["TST - rescisão indireta art. 484 CLT"],
    legislacao: ["CLT art. 483", "CLT art. 484"],
    riscos: ["Falta de prova do descumprimento", "Demissão voluntária caracterizada"],
    pedidos: ["Verbas rescisórias da rescisão indireta", "Indenização", "Multas"],
  },
  {
    slug: "assedio-moral-trabalhista",
    nome: "Assédio moral no trabalho",
    area: "trabalhista",
    gatilhos: ["assédio moral", "humilhação no trabalho", "constrangimento", "mobbing", "perseguição no trabalho"],
    questoesObrigatorias: ["Quais foram os atos de assédio?", "Houve reiteração?", "Houve testemunhas?", "Houve dano psicológico comprovado?"],
    provas: ["testemunhas", "e-mails", "mensagens", "laudo psicológico", "gravações"],
    teses: ["Assédio moral gera dano moral (CC art. 186/927)", "Responsabilidade objetiva do empregador"],
    contrateses: ["Exercício regular de poder diretivo", "Falta de prova", "Conduta isolada"],
    jurisprudencia: ["TST - assédio moral dano moral"],
    legislacao: ["CC art. 186", "CC art. 927", "CLT art. 483"],
    riscos: ["Falta de testemunhas", "Poder diretivo", "Conduta isolada"],
    pedidos: ["Indenização por danos morais", "Rescisão indireta se aplicável"],
  },
  // ── TRIBUTÁRIO ──────────────────────────────────────────────────────────
  {
    slug: "execucao-fiscal",
    nome: "Defesa em execução fiscal",
    area: "tributario",
    gatilhos: ["execução fiscal", "CDA", "auto de infração", "lançamento tributário", "débito tributário"],
    questoesObrigatorias: ["O lançamento é válido?", "Há nulidade formal?", "Houve prescrição/decadência?", "O fato gerador ocorreu?"],
    provas: ["CDA", "auto de infração", "notificação", "comprovantes de pagamento"],
    teses: ["Nulidade do lançamento (CTN art. 142-150)", "Prescrição/decadência (CTN art. 173/174)", "Imunidade/isenção"],
    contrateses: ["Lançamento válido", "Crédito tributário líquido e certo", "Prescrição não verificada"],
    jurisprudencia: ["STJ - execução fiscal", "STJ Súmula 392 - redirecionamento"],
    legislacao: ["CTN art. 142-150", "CTN art. 173-174", "Lei 6.830/1980"],
    riscos: ["Crédito tributário válido", "Redirecionamento para sócio"],
    pedidos: ["Nulidade do lançamento", "Extinção da execução", "Reconhecimento de prescrição"],
  },
  {
    slug: "repeticao-tributo",
    nome: "Repetição de indébito tributário",
    area: "tributario",
    gatilhos: ["repetição de indébito", "tributo indevido", "devolução de tributo", "compensação tributária"],
    questoesObrigatorias: ["O tributo foi efetivamente pago?", "O fundamento legal é correto?", "Houve erro de interpretação?"],
    provas: ["comprovantes de pagamento", "DCTF", "guia de recolhimento"],
    teses: ["Repetição de indébito (CTN art. 165)", "Compensação (CTN art. 170)"],
    contrateses: ["Tributo devido", "Decadência da pretensão", "Não preenchimento dos requisitos"],
    jurisprudencia: ["STJ - repetição de indébito tributário"],
    legislacao: ["CTN art. 165", "CTN art. 170"],
    riscos: ["Tributo efetivamente devido", "Prescrição quinquenal"],
    pedidos: ["Repetição de indébito", "Compensação", "Devolução com correção"],
  },
  // ── PENAL ──────────────────────────────────────────────────────────────
  {
    slug: "defesa-penal",
    nome: "Defesa em processo penal",
    area: "penal",
    gatilhos: ["crime", "denúncia", "queixa-crime", "inquérito", "flagrante"],
    questoesObrigatorias: ["Houve tipificação correta?", "Há excludente de ilicitude?", "Há causa de exclusão de culpabilidade?", "A prova é lícita?"],
    provas: ["boletim de ocorrência", "depoimentos", "laudo pericial", "cadeia de custódia"],
    teses: ["Excludente de ilicitude (art. 23 CP)", "Excludente de culpabilidade", "Nulidade processual", "Quebra de cadeia de custódia"],
    contrateses: ["Tipificação correta", "Prova lícita", "Culpabilidade configurada"],
    jurisprudencia: ["STF - excludente de ilicitude", "STJ - cadeia de custódia"],
    legislacao: ["CP art. 23", "CPP art. 41", "CPP art. 157"],
    riscos: ["Tipificação correta", "Prova lícita", "Réu confesso"],
    pedidos: ["Absolvição", "Extinção de punibilidade", "Anulação processual"],
  },
  // ── FAMÍLIA ────────────────────────────────────────────────────────────
  {
    slug: "alimentos",
    nome: "Ação de alimentos",
    area: "family",
    gatilhos: ["alimentos", "pensão", "obrigação alimentar", "binômio", "necessidade x possibilidade"],
    questoesObrigatorias: ["Qual a necessidade do alimentando?", "Qual a possibilidade do alimentante?", "Há alimentos provisórios?", "Qual o percentual adequado?"],
    provas: ["comprovante de renda", "comprovante de despesa", "certidão de nascimento", "comprovante de guarda"],
    teses: ["Obrigação alimentar (CC art. 1.694)", "Binômio necessidade x possibilidade", "Alimentos provisionais"],
    contrateses: ["Falta de capacidade econômica", "Ausência de parentesco", "Exoneração de alimentos"],
    jurisprudencia: ["STJ - alimentos binômio", "TJ - alimentos provisórios"],
    legislacao: ["CC art. 1.694-1.710", "Lei 5.478/1968"],
    riscos: ["Binômio desfavorável", "Exoneração", "Falta de parentesco"],
    pedidos: ["Fixação de alimentos", "Revisão de alimentos", "Exoneração de alimentos"],
  },
  {
    slug: "divorcio",
    nome: "Divórcio e partilha",
    area: "family",
    gatilhos: ["divórcio", "partilha", "separação", "dissolução conjugal", "partilha de bens"],
    questoesObrigatorias: ["Há bens a partilhar?", "Qual o regime de bens?", "Há filhos menores?", "Há pensão?"],
    provas: ["certidão de casamento", "registro de bens", "escrituras", "contrato de união estável"],
    teses: ["Divórcio (CC art. 1.571)", "Partilha conforme regime de bens", "Reconhecimento de união estável"],
    contrateses: ["Bens particulares", "Doação com cláusula de incomunicabilidade"],
    jurisprudencia: ["STF - divórcio sem lapso temporal", "STJ - partilha"],
    legislacao: ["CC art. 1.571-1.582", "Lei 11.441/2007"],
    riscos: ["Disputa sobre bens", "Regime de bens desfavorável"],
    pedidos: ["Divórcio", "Partilha de bens", "Pensão alimentícia"],
  },
  // ── ADMINISTRATIVO ─────────────────────────────────────────────────────
  {
    slug: "responsabilidade-estatal",
    nome: "Responsabilidade civil do Estado",
    area: "administrativo",
    gatilhos: ["responsabilidade do Estado", "dano causado pelo Estado", "ato de agente público", "servidor público"],
    questoesObrigatorias: ["Houve conduta de agente público?", "Há nexo causal?", "Qual o dano?", "Houve culpa exclusiva da vítima?"],
    provas: ["boletim de ocorrência", "laudo", "documentos públicos", "testemunhas"],
    teses: ["Responsabilidade objetiva do Estado (CF art. 37 §6º)", "Nexo de causalidade", "Dever de indenizar"],
    contrateses: ["Culpa exclusiva da vítima", "Fato de terceiro", "Caso fortuito externo"],
    jurisprudencia: ["STF - responsabilidade civil do Estado CF art. 37 §6º"],
    legislacao: ["CF art. 37 §6º", "CC art. 43"],
    riscos: ["Culpa exclusiva da vítima", "Fato de terceiro", "Caso fortuito"],
    pedidos: ["Indenização material", "Indenização por danos morais", "Tutela de urgência"],
  },
  {
    slug: "improbidade-administrativa",
    nome: "Improbidade administrativa",
    area: "administrativo",
    gatilhos: ["improbidade", "ato de improbidade", "Lei 8.429", "enriquecimento ilícito", "dano ao erário"],
    questoesObrigatorias: ["Houve dolo?", "Houve dano ao erário?", "Qual a tipificação (art. 10 LIA)?", "Há prescrição?"],
    provas: ["documentos públicos", "laudo contábil", "TCE", "auditoria"],
    teses: ["Improbidade por dano ao erário (art. 10 LIA)", "Enriquecimento ilícito (art. 9 LIA)", "Violação de princípios (art. 11 LIA)"],
    contrateses: ["Ausência de dolo", "Boa-fé", "Ato lícito", "Prescrição"],
    jurisprudencia: ["STF - improbidade exige dolo (Lei 14.230/2021)"],
    legislacao: ["Lei 8.429/1992 (LIA)", "Lei 14.230/2021 (reforma LIA)"],
    riscos: ["Ausência de dolo", "Prescrição", "Boa-fé subjetiva"],
    pedidos: ["Responsabilização por improbidade", "Ressarcimento ao erário", "Sanções"],
  },
];

async function seedExtraSkills() {
  console.log("🌱 Criando skills trabalhista/tributário/penal/família/administrativo...");
  let created = 0, skipped = 0;

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
    const existing = await db.skillVersion.findFirst({ where: { slug: s.slug }, orderBy: { version: "desc" } });
    if (existing && existing.contentHash === contentHash) { skipped++; continue; }
    const nextVersion = (existing?.version || 0) + 1;

    try {
      await db.skillVersion.create({
        data: {
          slug: s.slug, version: nextVersion, area: s.area, description: s.nome, content,
          triggers: JSON.stringify({ keywords: s.gatilhos }),
          rules: JSON.stringify(s.teses), exceptions: JSON.stringify(s.contrateses),
          forbiddenClaims: JSON.stringify(["promessa_resultado", "lei_inventada"]),
          allowedTools: JSON.stringify([]), outputSchema: JSON.stringify({ type: "text" }),
          status: "approved", contentHash, approvedBy: "curador-juridico", approvedAt: new Date(),
        },
      });
      created++;
      console.log(`  ✓ ${s.slug} v${nextVersion} → approved (${s.area})`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("Unique constraint")) { skipped++; } else { console.error(`  ✗ ${s.slug}:`, msg); }
    }
  }

  console.log(`\n✅ ${created} skills criadas, ${skipped} já existiam`);
  console.log(`📊 Total SkillVersions: ${await db.skillVersion.count()}`);
  const areas = await db.skillVersion.groupBy({ by: ["area"], _count: true, where: { status: "approved" } });
  areas.forEach((a) => console.log(`  ${a.area}: ${a._count} approved`));
}

seedExtraSkills()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
