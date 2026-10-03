import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { NewsDTO } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const items = await db.newsItem.findMany({ orderBy: { date: "desc" } });
  const dtos: NewsDTO[] = items.map((n) => ({
    id: n.id,
    slug: n.slug,
    title: n.title,
    summary: n.summary,
    body: n.body,
    category: n.category,
    date: n.date.toISOString(),
  }));
  return NextResponse.json({ news: dtos });
}
