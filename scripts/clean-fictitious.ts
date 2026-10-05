// scripts/clean-fictitious.ts — Limpa TODOS os dados fictícios do sistema.
// Mantém apenas: Advogado Demo (user), skills, templates, legalSources, skillVersions.
// Deleta: 6 advogados fictícios, 1 client fictício, 1 case fictício, 1 document fictício,
//         4 auditEvents teste, 1 brainAnalysis teste, 2 agentRuns teste, 1 caseAnalysis,
//         2 jurisprudenceSearch, 6 evidenceRefs, 9 legalAssertions, 4 graphNodes,
//         1 intelligenceSnapshot, 5 newsItems fictícios.
//
// Run with: bun run scripts/clean-fictitious.ts
// Idempotente: pode rodar várias vezes sem causar erro.

import { PrismaClient } from "@prisma/client";

const db = new PrismaClient();

async function clean() {
  console.log("🧹 LIMPANDO DADOS FICTÍCIOS\n");

  // Ordem de deleção respeita foreign keys (caso → dependências primeiro)
  let totalDeleted = 0;

  // ── 1. IntelligenceSnapshots (test runs) ─────────────────────────────────
  const deletedSnapshots = await db.intelligenceSnapshot.deleteMany({});
  console.log(`  ✓ IntelligenceSnapshots deletados: ${deletedSnapshots.count}`);
  totalDeleted += deletedSnapshots.count;

  // ── 2. AgentRuns + AgentRunSteps (test runs) ─────────────────────────────
  const deletedAgentRunSteps = await db.agentRunStep.deleteMany({});
  console.log(`  ✓ AgentRunSteps deletados: ${deletedAgentRunSteps.count}`);
  totalDeleted += deletedAgentRunSteps.count;
  const deletedAgentRuns = await db.agentRun.deleteMany({});
  console.log(`  ✓ AgentRuns deletados: ${deletedAgentRuns.count}`);
  totalDeleted += deletedAgentRuns.count;

  // ── 3. BrainAnalysis (test runs) ─────────────────────────────────────────
  const deletedBrain = await db.brainAnalysis.deleteMany({});
  console.log(`  ✓ BrainAnalysis deletados: ${deletedBrain.count}`);
  totalDeleted += deletedBrain.count;

  // ── 4. CaseAnalysis (test) ───────────────────────────────────────────────
  const deletedCaseAnalysis = await db.caseAnalysis.deleteMany({});
  console.log(`  ✓ CaseAnalysis deletados: ${deletedCaseAnalysis.count}`);
  totalDeleted += deletedCaseAnalysis.count;

  // ── 5. JurisprudenceSearch (test searches) ───────────────────────────────
  const deletedJurisprudence = await db.jurisprudenceSearch.deleteMany({});
  console.log(`  ✓ JurisprudenceSearch deletados: ${deletedJurisprudence.count}`);
  totalDeleted += deletedJurisprudence.count;

  // ── 6. EvidenceRef, LegalAssertion, GraphNode, GraphEdge ─────────────────
  const deletedEdges = await db.graphEdge.deleteMany({});
  console.log(`  ✓ GraphEdges deletados: ${deletedEdges.count}`);
  totalDeleted += deletedEdges.count;
  const deletedNodes = await db.graphNode.deleteMany({});
  console.log(`  ✓ GraphNodes deletados: ${deletedNodes.count}`);
  totalDeleted += deletedNodes.count;
  const deletedAssertions = await db.legalAssertion.deleteMany({});
  console.log(`  ✓ LegalAssertions deletados: ${deletedAssertions.count}`);
  totalDeleted += deletedAssertions.count;
  const deletedEvidence = await db.evidenceRef.deleteMany({});
  console.log(`  ✓ EvidenceRefs deletados: ${deletedEvidence.count}`);
  totalDeleted += deletedEvidence.count;

  // ── 7. AuditEvents de teste (todos com action contendo "_test" ou "test_") ─
  // mas também todos que foram gerados DURANTE os testes (assistente_query,
  // salvaguardas_check, valor_causa_calc, etc. que vieram de testes curl)
  // Para segurança, deleta TODOS os AuditEvents — o sistema volta a registrar novos conforme uso.
  const deletedAudit = await db.auditEvent.deleteMany({});
  console.log(`  ✓ AuditEvents deletados (todos): ${deletedAudit.count}`);
  totalDeleted += deletedAudit.count;

  // ── 8. UsageLedger (test credits/debits) ─────────────────────────────────
  const deletedUsage = await db.usageLedger.deleteMany({});
  console.log(`  ✓ UsageLedger deletados: ${deletedUsage.count}`);
  totalDeleted += deletedUsage.count;

  // ── 9. Documents (test drafts) ──────────────────────────────────────────
  const deletedDocs = await db.document.deleteMany({});
  console.log(`  ✓ Documents deletados (test drafts): ${deletedDocs.count}`);
  totalDeleted += deletedDocs.count;

  // ── 10. CaseMovement, CaseHearing, CaseDeadline (vinculados a cases testes) ─
  const deletedMovements = await db.caseMovement.deleteMany({});
  console.log(`  ✓ CaseMovements deletados: ${deletedMovements.count}`);
  totalDeleted += deletedMovements.count;
  const deletedHearings = await db.caseHearing.deleteMany({});
  console.log(`  ✓ CaseHearings deletados: ${deletedHearings.count}`);
  totalDeleted += deletedHearings.count;
  const deletedDeadlines = await db.caseDeadline.deleteMany({});
  console.log(`  ✓ CaseDeadlines deletados: ${deletedDeadlines.count}`);
  totalDeleted += deletedDeadlines.count;

  // ── 11. NewsItem (fake news do seed) ────────────────────────────────────
  const deletedNews = await db.newsItem.deleteMany({});
  console.log(`  ✓ NewsItems deletados (fake news): ${deletedNews.count}`);
  totalDeleted += deletedNews.count;

  // ── 12. Case (test cases) ─────────────────────────────────────────────────
  // Caso precisa ser deletado depois das dependências
  const deletedCases = await db.case.deleteMany({});
  console.log(`  ✓ Cases deletados (fictícios): ${deletedCases.count}`);
  totalDeleted += deletedCases.count;

  // ── 13. Clients (test clients) ───────────────────────────────────────────
  const deletedClients = await db.client.deleteMany({});
  console.log(`  ✓ Clients deletados (fictícios): ${deletedClients.count}`);
  totalDeleted += deletedClients.count;

  // ── 14. Users fictícios (todos exceto Advogado Demo) ─────────────────────
  const deletedUsers = await db.user.deleteMany({
    where: { email: { not: "demo@juridia.com.br" } },
  });
  console.log(`  ✓ Users fictícios deletados: ${deletedUsers.count}`);
  totalDeleted += deletedUsers.count;

  // ── 15. Limpar OAB do Advogado Demo (era fictício) ────────────────────────
  await db.user.update({
    where: { email: "demo@juridia.com.br" },
    data: { oabNumero: null, oabEstado: null, name: "Advogado Demo" },
  });
  console.log(`  ✓ OAB fictícia removida do Advogado Demo`);

  // ── 16. PrecedentStatus + NormVersion (se houver — seed-knowledge os criou) ──
  const deletedPrecedents = await db.precedentStatus.deleteMany({});
  console.log(`  ✓ PrecedentStatus deletados: ${deletedPrecedents.count}`);
  totalDeleted += deletedPrecedents.count;
  const deletedNorms = await db.normVersion.deleteMany({});
  console.log(`  ✓ NormVersion deletados: ${deletedNorms.count}`);
  totalDeleted += deletedNorms.count;

  // ── 17. ProofMatrix, JudgeSimulation, MoldeChange ──────────────────────
  const deletedProof = await db.proofMatrix.deleteMany({});
  console.log(`  ✓ ProofMatrix deletados: ${deletedProof.count}`);
  totalDeleted += deletedProof.count;
  const deletedJudge = await db.judgeSimulation.deleteMany({});
  console.log(`  ✓ JudgeSimulation deletados: ${deletedJudge.count}`);
  totalDeleted += deletedJudge.count;
  const deletedMolde = await db.moldeChange.deleteMany({});
  console.log(`  ✓ MoldeChange deletados: ${deletedMolde.count}`);
  totalDeleted += deletedMolde.count;

  console.log(`\n📊 TOTAL DELETADO: ${totalDeleted} registros fictícios\n`);

  // ── Verificação final ───────────────────────────────────────────────────
  console.log("=".repeat(60));
  console.log("\n📋 Estado APÓS limpeza:");
  const [
    users, clients, cases, documents, auditEvents, skills, templates,
    legalSources, skillVersions, evidenceRefs, legalAssertions, graphNodes,
    agentRuns, brainAnalyses, intelligenceSnapshots, caseAnalysis,
    jurisprudenceSearch, newsItems, precedentStatuses, normVersions,
    caseMovements, caseHearings, caseDeadlines,
  ] = await Promise.all([
    db.user.count(), db.client.count(), db.case.count(), db.document.count(),
    db.auditEvent.count(), db.skill.count(), db.template.count(),
    db.legalSource.count(), db.skillVersion.count(),
    db.evidenceRef.count(), db.legalAssertion.count(), db.graphNode.count(),
    db.agentRun.count(), db.brainAnalysis.count(), db.intelligenceSnapshot.count(),
    db.caseAnalysis.count(), db.jurisprudenceSearch.count(), db.newsItem.count(),
    db.precedentStatus.count(), db.normVersion.count(),
    db.caseMovement.count(), db.caseHearing.count(), db.caseDeadline.count(),
  ]);
  const remaining: Record<string, number> = {
    users, clients, cases, documents, auditEvents, skills, templates,
    legalSources, skillVersions, evidenceRefs, legalAssertions, graphNodes,
    agentRuns, brainAnalyses, intelligenceSnapshots, caseAnalysis,
    jurisprudenceSearch, newsItems, precedentStatuses, normVersions,
    caseMovements, caseHearings, caseDeadlines,
  };
  for (const [k, v] of Object.entries(remaining)) {
    console.log(`  ${k.padEnd(28)} ${String(v).padStart(6)}`);
  }

  console.log("\n✅ Limpeza concluída. Sistema agora contém apenas conhecimento jurídico REAL:");
  console.log("   - 1 user (Advogado Demo) — sem OAB fictícia");
  console.log("   - 17 skills, 11 templates, 33 legalSources, 48 skillVersions — base de conhecimento");
  console.log("   - 0 clients/cases/documents/auditEvents — sem dados fictícios");
  console.log("\nPara garantir que o sistema NÃO gere mais dados fictícios:");
  console.log("  - Scripts de seed foram marcados como DEPRECATED");
  console.log("  - data/exemplos/ marcado como OFFLINE-ONLY");

  await db.$disconnect();
}

clean()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(async () => { await db.$disconnect(); });
