// scripts/audit-fictitious.ts — Audita todas as tabelas e identifica dados fictícios.
// Run with: bun run scripts/audit-fictitious.ts

import { PrismaClient } from "@prisma/client";

const db = new PrismaClient();

// Heurísticas para identificar dados fictícios:
// - Users: emails com "juridia.com.br" + nomes como "Maria Silva", "Carlos Lima", "João Pereira", "Ana Santos", "Pedro Mendes", "Beatriz"
// - Clients: nomes com "Teste", "Anonimizado", "da Silva Teste"
// - Cases: titles com "teste", "SERASA", "indenizatória teste"
// - Documents: titles com "Teste", "Inscrição indevida SERASA"
// - AuditEvents: actions with "test_" prefix, or audit entries from test scripts

async function audit() {
  console.log("🔍 AUDITORIA DE DADOS FICTÍCIOS\n");
  console.log("=".repeat(70));

  // ── Tabelas principais (count) ────────────────────────────────────────────
  const [
    users, clients, cases, documents, audiencias, prazos,
    movements, auditEvents, skills, templates, legalSources, news,
    caseAnalysis, jurisprudenceSearch, agentRuns, evidenceRefs, legalAssertions,
    graphNodes, graphEdges, intelligenceSnapshots, skillVersions, brainAnalyses,
    precedentStatuses, normVersions, proofMatrices, caseDeadlines, judgeSimulations,
    moldeChanges,
  ] = await Promise.all([
    db.user.count(),
    db.client.count(),
    db.case.count(),
    db.document.count(),
    db.caseHearing.count(),
    db.caseDeadline.count(),
    db.caseMovement.count(),
    db.auditEvent.count(),
    db.skill.count(),
    db.template.count(),
    db.legalSource.count(),
    db.newsItem.count(),
    db.caseAnalysis.count(),
    db.jurisprudenceSearch.count(),
    db.agentRun.count(),
    db.evidenceRef.count(),
    db.legalAssertion.count(),
    db.graphNode.count(),
    db.graphEdge.count(),
    db.intelligenceSnapshot.count(),
    db.skillVersion.count(),
    db.brainAnalysis.count(),
    db.precedentStatus.count(),
    db.normVersion.count(),
    db.proofMatrix.count(),
    db.caseDeadline.count(),
    db.judgeSimulation.count(),
    db.moldeChange.count(),
  ]);

  const counts: Record<string, number> = {
    users, clients, cases, documents, audiencias, prazos,
    movements, auditEvents, skills, templates, legalSources, news,
    caseAnalysis, jurisprudenceSearch, agentRuns, evidenceRefs, legalAssertions,
    graphNodes, graphEdges, intelligenceSnapshots, skillVersions, brainAnalyses,
    precedentStatuses, normVersions, proofMatrices, caseDeadlines, judgeSimulations,
    moldeChanges,
  };

  console.log("\n📊 Contagem por tabela:");
  for (const [k, v] of Object.entries(counts)) {
    const flag = v > 0 ? "" : " (empty)";
    console.log(`  ${k.padEnd(28)} ${String(v).padStart(6)}${flag}`);
  }

  // ── Identificar fictícios ────────────────────────────────────────────────
  console.log("\n" + "=".repeat(70));
  console.log("\n🔍 Identificando dados FICTÍCIOS:\n");

  // Users fictícios (todos exceto o demo)
  const fictitiousUsers = await db.user.findMany({
    where: { email: { not: "demo@juridia.com.br" } },
    select: { id: true, name: true, email: true, oabNumero: true, oabEstado: true },
  });
  console.log(`👤 Users fictícios (não-demo): ${fictitiousUsers.length}`);
  fictitiousUsers.slice(0, 10).forEach(u => console.log(`   - ${u.name} (${u.email}) OAB/${u.oabEstado || "?"} ${u.oabNumero || "?"}`));

  // Clients
  const allClients = await db.client.findMany({ select: { id: true, name: true } });
  const fictitiousClients = allClients.filter(c =>
    /Teste|Anonimiz|Cliente \d+|João da Silva Teste/i.test(c.name)
  );
  console.log(`\n👥 Clients fictícios: ${fictitiousClients.length}`);
  fictitiousClients.forEach(c => console.log(`   - ${c.name}`));

  // Cases
  const allCases = await db.case.findMany({ select: { id: true, title: true, number: true } });
  const fictitiousCases = allCases.filter(c =>
    /teste|Teste|SERASA|indenizat[óo]ria teste|demonstra/i.test(c.title || "")
  );
  console.log(`\n💼 Cases fictícios: ${fictitiousCases.length}`);
  fictitiousCases.forEach(c => console.log(`   - ${c.title} (${c.number || "s/n"})`));

  // Documents
  const allDocs = await db.document.findMany({ select: { id: true, title: true, rawFacts: true } });
  const fictitiousDocs = allDocs.filter(d =>
    /Teste| teste |demonstr|Insrição indevida|Inscrição indevida SERASA/i.test(d.title || "") ||
    /teste|SERASA|João da Silva/i.test(d.rawFacts || "")
  );
  console.log(`\n📄 Documents fictícios: ${fictitiousDocs.length}`);
  fictitiousDocs.slice(0, 5).forEach(d => console.log(`   - ${d.title}`));

  // Movimentações (test seed)
  const testMovements = await db.caseMovement.findMany({
    where: { descricao: { contains: "teste" } },
    select: { id: true, tipo: true, descricao: true },
    take: 5,
  });
  console.log(`\n📜 Movimentações de teste: ${testMovements.length}`);
  testMovements.forEach(m => console.log(`   - ${m.tipo}: ${m.descricao?.slice(0, 60)}`));

  // AuditEvents (test queries)
  const testAuditEvents = await db.auditEvent.findMany({
    where: { OR: [
      { action: { startsWith: "test_" } },
      { metadata: { contains: "teste" } },
    ] },
    select: { id: true, action: true },
    take: 5,
  });
  console.log(`\n📝 AuditEvents de teste: ${testAuditEvents.length}`);

  // BrainAnalysis (test runs)
  const brainAnalysesAll = await db.brainAnalysis.findMany({
    select: { id: true, title: true, factsInput: true },
    take: 5,
  });
  console.log(`\n🧠 BrainAnalysis (test runs): ${brainAnalysesAll.length}`);
  brainAnalysesAll.forEach(b => console.log(`   - ${b.title} (fatos: ${b.factsInput?.slice(0, 50)}...)`));

  // AgentRuns
  const agentRunsAll = await db.agentRun.findMany({
    select: { id: true, agentSlug: true, status: true },
    take: 5,
  });
  console.log(`\n🤖 AgentRuns: ${agentRunsAll.length}`);
  agentRunsAll.forEach(a => console.log(`   - ${a.agentSlug} (${a.status})`));

  // Skills com "fictício" ou "demonstração" no description
  const fictitiousSkills = await db.skill.findMany({
    where: { OR: [
      { description: { contains: "fictíci" } },
      { description: { contains: "demonstr" } },
      { content: { contains: "fictíci" } },
      { content: { contains: "FICTÍCI" } },
    ] },
    select: { id: true, slug: true, name: true },
  });
  console.log(`\n📚 Skills marcadas como fictícias: ${fictitiousSkills.length}`);
  fictitiousSkills.forEach(s => console.log(`   - ${s.slug}: ${s.name}`));

  // Precedents + Norms (from seed-knowledge)
  const precedents = await db.precedentStatus.findMany({
    select: { id: true, sourceLabel: true, status: true },
  });
  console.log(`\n⚖️ PrecedentStatus (todos): ${precedents.length}`);
  precedents.slice(0, 5).forEach(p => console.log(`   - ${p.sourceLabel} (${p.status})`));

  const norms = await db.normVersion.findMany({
    select: { id: true, diploma: true, numero: true },
  });
  console.log(`\n📖 NormVersion (todos): ${norms.length}`);
  norms.slice(0, 5).forEach(n => console.log(`   - ${n.diploma} ${n.numero}`));

  console.log("\n" + "=".repeat(70));
  console.log("\n✅ Auditoria concluída. Use scripts/clean-fictitious.ts para remover.");

  await db.$disconnect();
}

audit()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
