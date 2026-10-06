// /api/validate/peticao — Roda validadores determinísticos pré-geração.
import { NextRequest, NextResponse } from "next/server";
import { validatePeticao, summarizeIssues, type ValidationInput } from "@/lib/validators";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: ValidationInput;
  try {
    body = (await req.json()) as ValidationInput;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.area || !body.templateSlug) {
    return NextResponse.json({ error: "area e templateSlug obrigatórios" }, { status: 400 });
  }
  const issues = validatePeticao(body);
  return NextResponse.json({
    ok: issues.filter((i) => i.severity === "error").length === 0,
    issues,
    summary: summarizeIssues(issues),
  });
}