import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { createHash } from "crypto";

export const dynamic = "force-dynamic";

// GET: lista SkillVersions (com filtros status, area, slug)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const status = url.searchParams.get("status");
  const area = url.searchParams.get("area");
  const slug = url.searchParams.get("slug");

  const where: { status?: string; area?: string; slug?: string } = {};
  if (status) where.status = status;
  if (area) where.area = area;
  if (slug) where.slug = slug;

  // Se filtrando por slug, pega apenas a versão mais recente de cada um
  if (slug) {
    const versions = await db.skillVersion.findMany({
      where: { slug },
      orderBy: { version: "desc" },
    });
    return NextResponse.json({ versions: versions.map(toDTO) });
  }

  const skills = await db.skillVersion.findMany({
    where,
    orderBy: [{ status: "asc" }, { area: "asc" }, { slug: "asc" }],
    take: 200,
  });

  // Se quiser apenas approved, retorna só as mais recentes approved
  if (status === "approved") {
    const bySlug = new Map<string, typeof skills[0]>();
    for (const s of skills) {
      const existing = bySlug.get(s.slug);
      if (!existing || s.version > existing.version) {
        bySlug.set(s.slug, s);
      }
    }
    return NextResponse.json({ skills: Array.from(bySlug.values()).map(toDTO) });
  }

  return NextResponse.json({ skills: skills.map(toDTO) });
}

// POST: cria nova SkillVersion (sempre começa como draft)
export async function POST(req: NextRequest) {
  let body: {
    slug?: string; version?: number; area?: string; description?: string;
    content?: string; triggers?: Record<string, unknown>; rules?: string[];
    exceptions?: string[]; forbiddenClaims?: string[]; allowedTools?: string[];
  } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.slug || !body.content) {
    return NextResponse.json({ error: "slug e content obrigatórios" }, { status: 400 });
  }

  // Determina próxima versão
  const last = await db.skillVersion.findFirst({
    where: { slug: body.slug },
    orderBy: { version: "desc" },
  });
  const nextVersion = (last?.version || 0) + 1;

  const contentHash = createHash("sha256").update(body.content, "utf8").digest("hex");

  try {
    const skill = await db.skillVersion.create({
      data: {
        slug: body.slug,
        version: nextVersion,
        area: body.area || "civil",
        description: body.description || "",
        content: body.content,
        triggers: JSON.stringify(body.triggers || {}),
        rules: JSON.stringify(body.rules || []),
        exceptions: JSON.stringify(body.exceptions || []),
        forbiddenClaims: JSON.stringify(body.forbiddenClaims || []),
        allowedTools: JSON.stringify(body.allowedTools || []),
        status: "draft",
        contentHash,
      },
    });

    await logAuditEvent({
      action: "create_skill_version",
      resource: "skill_version",
      resourceId: skill.id,
      metadata: { slug: body.slug, version: nextVersion },
    });

    return NextResponse.json({ id: skill.id, slug: skill.slug, version: skill.version, status: skill.status });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao criar SkillVersion";
    if (msg.includes("Unique constraint")) {
      return NextResponse.json({ error: "Versão já existe" }, { status: 409 });
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// PATCH: aprova/rejeita/retira uma SkillVersion
export async function PATCH(req: NextRequest) {
  let body: { id?: string; action?: "approve" | "review" | "retire" } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.id || !body.action) {
    return NextResponse.json({ error: "id e action obrigatórios" }, { status: 400 });
  }

  const newStatus = body.action === "approve" ? "approved" : body.action === "review" ? "review" : "retired";
  const reviewer = "advogado";

  const updated = await db.skillVersion.update({
    where: { id: body.id },
    data: {
      status: newStatus,
      ...(body.action === "approve" ? { approvedBy: reviewer, approvedAt: new Date() } : {}),
    },
  });

  await logAuditEvent({
    action: `${body.action}_skill_version`,
    resource: "skill_version",
    resourceId: body.id,
    metadata: { slug: updated.slug, version: updated.version, newStatus },
  });

  return NextResponse.json({ ok: true, status: newStatus });
}

function toDTO(s: {
  id: string; slug: string; version: number; area: string; description: string;
  content: string; status: string; contentHash: string; approvedBy: string | null;
  approvedAt: Date | null; createdAt: Date; updatedAt: Date;
}) {
  return {
    id: s.id, slug: s.slug, version: s.version, area: s.area,
    description: s.description, content: s.content, status: s.status,
    contentHash: s.contentHash.slice(0, 16), approvedBy: s.approvedBy,
    approvedAt: s.approvedAt?.toISOString(), createdAt: s.createdAt.toISOString(),
  };
}
