import { NextRequest, NextResponse } from "next/server";
import { anonymize, detect } from "@/lib/anonymize";

export const dynamic = "force-dynamic";

interface Body {
  text: string;
}

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body || typeof body.text !== "string") {
    return NextResponse.json({ error: "Campo 'text' obrigatório" }, { status: 400 });
  }

  const result = anonymize(body.text);
  const detection = detect(body.text);

  return NextResponse.json({
    original: body.text,
    anonymized: result.text,
    markers: result.markers,
    counts: result.counts,
    total: result.total,
    detection,
  });
}
