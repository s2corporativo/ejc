import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { SkillDTO } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const items = await db.skill.findMany({ orderBy: { name: "asc" } });
  const dtos: SkillDTO[] = items.map((s) => ({
    id: s.id,
    slug: s.slug,
    name: s.name,
    category: s.category,
    description: s.description,
    content: s.content,
    locked: s.locked,
  }));
  return NextResponse.json({ skills: dtos });
}
