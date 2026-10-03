import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { DocumentDTO } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const docs = await db.document.findMany({
    orderBy: { updatedAt: "desc" },
    take: 100,
  });
  const dtos: DocumentDTO[] = docs.map((d) => ({
    id: d.id,
    title: d.title,
    templateSlug: d.templateSlug,
    templateName: d.templateName,
    anonymizedFacts: d.anonymizedFacts,
    generatedContent: d.generatedContent,
    skillSlugs: safeParseArr(d.skillSlugs),
    status: d.status,
    batchId: d.batchId,
    createdAt: d.createdAt.toISOString(),
    updatedAt: d.updatedAt.toISOString(),
  }));
  return NextResponse.json({ documents: dtos });
}

export async function DELETE(req: NextRequest) {
  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  if (!id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });
  await db.document.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}

export async function PATCH(req: NextRequest) {
  const body = (await req.json().catch(() => null)) as { id?: string; content?: string; title?: string } | null;
  if (!body?.id) return NextResponse.json({ error: "id obrigatório" }, { status: 400 });
  const data: { generatedContent?: string; title?: string } = {};
  if (typeof body.content === "string") data.generatedContent = body.content;
  if (typeof body.title === "string") data.title = body.title;
  const updated = await db.document.update({
    where: { id: body.id },
    data,
  });
  return NextResponse.json({ ok: true, document: { id: updated.id, title: updated.title } });
}

function safeParseArr(raw: string | null): string[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw) as string[];
  } catch {
    return [];
  }
}
