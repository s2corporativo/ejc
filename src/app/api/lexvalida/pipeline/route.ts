import { NextRequest, NextResponse } from "next/server";
import { runPipeline } from "@/lib/lexvalida_pipeline";

export const dynamic = "force-dynamic";
export const maxDuration = 300; // 5 min — pipeline completo de 8 etapas

export async function POST(req: NextRequest) {
  let body: { pedido?: string; tipoPeca?: string; autos?: string; caseId?: string } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  if (!body.pedido?.trim() || body.pedido.trim().length < 10) {
    return NextResponse.json({ error: "pedido obrigatório (mín. 10 caracteres)" }, { status: 400 });
  }
  if (!body.tipoPeca?.trim()) {
    return NextResponse.json({ error: "tipoPeca obrigatório" }, { status: 400 });
  }

  try {
    const result = await runPipeline({
      pedido: body.pedido,
      tipoPeca: body.tipoPeca,
      autos: body.autos || "",
      caseId: body.caseId,
    });
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Erro no pipeline" }, { status: 500 });
  }
}
