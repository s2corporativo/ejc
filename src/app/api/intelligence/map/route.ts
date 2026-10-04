import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";
import { db } from "@/lib/db";
import { mapCaseDeterministic, validateMapperOutput, identifyIssues, type CaseMapperOutput } from "@/lib/legal_brain";
import { canonicalHash } from "@/lib/evidence";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

// POST /api/intelligence/map — executa Case Mapper (determinístico + LLM)
export async function POST(req: NextRequest) {
  let body: { facts?: string; caseId?: string } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  const facts = (body.facts || "").trim();
  const caseId = body.caseId || "default-case";

  if (facts.length < 30) {
    return NextResponse.json({ error: "Texto insuficiente (mín. 30 caracteres)" }, { status: 400 });
  }

  // Cria AgentRun
  const inputHash = canonicalHash({ facts, caseId });
  const run = await db.agentRun.create({
    data: {
      caseId,
      agentSlug: "case_mapper",
      taskType: "map",
      status: "running",
      inputHash,
      contractVersion: "case_mapper_v1",
      startedAt: new Date(),
    },
  });

  // ── Etapa 1: Case Mapper determinístico (sem LLM) ──────────────────────
  let deterministicOutput: CaseMapperOutput;
  let evidenceRefs: Awaited<ReturnType<typeof mapCaseDeterministic>>["evidence"];

  try {
    const det = await mapCaseDeterministic(caseId, facts);
    deterministicOutput = det.output;
    evidenceRefs = det.evidence;

    await db.agentRunStep?.create?.({
      data: { runId: run.id, stepNo: 1, kind: "deterministic_map", status: "done" },
    }).catch(() => {}); // AgentRunStep não existe no schema ainda, ignora se falhar
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro determinístico";
    // Princípio 18: falha do LLM não destrói o determinístico — mas aqui falhou o próprio determinístico
    await db.agentRun.update({
      where: { id: run.id },
      data: { status: "failed", errorCode: msg, finishedAt: new Date() },
    });
    return NextResponse.json({ error: msg }, { status: 500 });
  }

  // ── Etapa 2: Enriquecimento por LLM (governado) ────────────────────────
  let llmOutput: CaseMapperOutput | null = null;
  let tokensUsed = 0;

  try {
    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: "system",
          content: `Você é o extrator jurídico verificável do sistema. Sua função NÃO é decidir o caso. Organize informações APENAS a partir das evidências autorizadas.

REGRAS:
1. Não invente fatos, datas, pessoas, valores, leis ou jurisprudência.
2. Cada fato deve possuir evidence_ref_ids.
3. Use somente IDs presentes em allowed_evidence.
4. Diferencie fato de inferência (kind: fact vs inference).
5. Registre ausência de informação como gap.
6. Nunca marque item como confirmado.
7. Responda APENAS no schema JSON.

{"facts":[{"text":"...","evidence_ref_ids":["ev_xxx"],"confidence":0.0-1.0}],"events":[{"description":"...","date":null,"date_status":"unknown","evidence_ref_ids":["ev_xxx"]}],"assertions":[{"text":"...","kind":"fact|inference|gap|risk|rule|precedent","evidence_ref_ids":["ev_xxx"],"support_status":"supported|partial|absent"}],"warnings":["..."]}`,
        },
        {
          role: "user",
          content: `## Evidências autorizadas\n${JSON.stringify(evidenceRefs.map((e) => ({ id: e.id, quote: e.quote.slice(0, 200), source_kind: e.sourceKind })))}\n\n## Texto do caso\n${facts}\n\n## Rascunho determinístico\n${JSON.stringify(deterministicOutput)}`,
        },
      ],
      thinking: { type: "disabled" },
      temperature: 0.3,
      max_tokens: 1500,
    });

    const raw = completion.choices[0]?.message?.content || "";
    const match = raw.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]) as CaseMapperOutput;
      // Valida que todos os evidence_ref_ids existem (Princípio 7)
      llmOutput = await validateMapperOutput(caseId, parsed, evidenceRefs);
    }

    tokensUsed = (completion as unknown as { usage?: { total_tokens?: number } }).usage?.total_tokens || 0;
  } catch {
    // Princípio 18: falha do LLM não destrói o resultado determinístico
    llmOutput = null;
  }

  // ── Etapa 3: Merge (determinístico + LLM validado) ──────────────────────
  const merged: CaseMapperOutput = llmOutput
    ? {
        facts: [...deterministicOutput.facts, ...llmOutput.facts],
        events: [...deterministicOutput.events, ...llmOutput.events],
        assertions: [...deterministicOutput.assertions, ...llmOutput.assertions],
        warnings: [...deterministicOutput.warnings, ...llmOutput.warnings],
      }
    : deterministicOutput;

  // ── Etapa 4: Questões jurídicas (Issue Engine determinístico) ──────────
  const issues = identifyIssues(facts, null);

  // ── Etapa 5: Persiste assertions no DB ─────────────────────────────────
  for (const assertion of merged.assertions) {
    await db.legalAssertion.create({
      data: {
        caseId,
        text: assertion.text,
        kind: assertion.kind,
        supportStatus: assertion.supportStatus,
        reviewStatus: "pending",
        createdByAi: true,
        createdByRunId: run.id,
        evidenceIds: JSON.stringify(assertion.evidenceRefIds),
      },
    });
  }

  // ── Etapa 6: Persiste GraphNodes (fatos, eventos, regras) ─────────────
  for (const fact of merged.facts) {
    await db.graphNode.create({
      data: {
        caseId,
        nodeType: "fact",
        label: fact.text.slice(0, 200),
        confidence: fact.confidence,
        status: "candidate",
        sourceEvidenceId: fact.evidenceRefIds[0] || null,
        createdByRunId: run.id,
      },
    });
  }
  for (const issue of issues) {
    await db.graphNode.create({
      data: {
        caseId,
        nodeType: "rule",
        label: issue.title,
        description: issue.question,
        confidence: 0.8,
        status: "candidate",
        createdByRunId: run.id,
        payload: JSON.stringify({ key: issue.key, risks: issue.risks, requiredEvidence: issue.requiredEvidence }),
      },
    });
  }

  // ── Etapa 7: Cria snapshot (append-only) ───────────────────────────────
  const lastVersion = await db.intelligenceSnapshot.findFirst({
    where: { caseId },
    orderBy: { version: "desc" },
  });
  const snapshot = await db.intelligenceSnapshot.create({
    data: {
      caseId,
      version: (lastVersion?.version || 0) + 1,
      payload: JSON.stringify({ merged, issues, evidenceCount: evidenceRefs.length, llmUsed: llmOutput !== null }),
      isDraft: true,
    },
  });

  // Completa o AgentRun
  await db.agentRun.update({
    where: { id: run.id },
    data: {
      status: "completed",
      tokensOut: tokensUsed,
      resultSnapshotId: snapshot.id,
      providerSnapshot: JSON.stringify({ provider: "zai", tokens: tokensUsed }),
      finishedAt: new Date(),
    },
  });

  await logAuditEvent({
    action: "intelligence_map",
    resource: "case",
    resourceId: caseId,
    metadata: { runId: run.id, snapshotId: snapshot.id, factsCount: merged.facts.length, issuesCount: issues.length, llmUsed: llmOutput !== null, tokens: tokensUsed },
  });

  return NextResponse.json({
    runId: run.id,
    snapshotId: snapshot.id,
    snapshotVersion: snapshot.version,
    evidence: evidenceRefs,
    facts: merged.facts,
    events: merged.events,
    assertions: merged.assertions,
    issues,
    warnings: merged.warnings,
    llmUsed: llmOutput !== null,
    tokensUsed,
  });
}

// GET /api/intelligence/map — lista snapshots de um caso
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId") || "default-case";

  const snapshots = await db.intelligenceSnapshot.findMany({
    where: { caseId },
    orderBy: { version: "desc" },
    take: 20,
  });

  const assertions = await db.legalAssertion.findMany({
    where: { caseId },
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  const nodes = await db.graphNode.findMany({
    where: { caseId },
    orderBy: { createdAt: "desc" },
    take: 100,
  });

  return NextResponse.json({
    snapshots: snapshots.map((s) => ({
      id: s.id,
      version: s.version,
      isDraft: s.isDraft,
      approvedBy: s.approvedBy,
      approvedAt: s.approvedAt?.toISOString(),
      createdAt: s.createdAt.toISOString(),
      payload: JSON.parse(s.payload),
    })),
    assertions: assertions.map((a) => ({
      id: a.id,
      text: a.text,
      kind: a.kind,
      supportStatus: a.supportStatus,
      reviewStatus: a.reviewStatus,
      evidenceIds: JSON.parse(a.evidenceIds),
      createdByAi: a.createdByAi,
      reviewedBy: a.reviewedBy,
    })),
    nodes: nodes.map((n) => ({
      id: n.id,
      nodeType: n.nodeType,
      label: n.label,
      status: n.status,
      confidence: n.confidence,
      sourceEvidenceId: n.sourceEvidenceId,
    })),
  });
}
