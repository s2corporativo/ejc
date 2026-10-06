// /api/export/docx — Converte markdown para .docx (peça jurídica formatada).
//
// Recebe o conteúdo markdown (de qualquer peça gerada pelo Tribunal, debate,
// pipeline, etc) e devolve o .docx para download.

import { NextRequest, NextResponse } from "next/server";
import { buildDocx } from "@/lib/docx_export";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

interface Body {
  markdown: string;
  titulo?: string;
  autor?: string;
  oab?: string;
  filename?: string;
}

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!body.markdown || body.markdown.trim().length < 20) {
    return NextResponse.json(
      { error: "markdown obrigatório (mínimo 20 caracteres)" },
      { status: 400 },
    );
  }

  try {
    const blob = await buildDocx(body.markdown, {
      titulo: body.titulo,
      autor: body.autor,
      oab: body.oab,
    });
    const buffer = Buffer.from(await blob.arrayBuffer());

    await logAuditEvent({
      action: "export_docx",
      resource: "docx_export",
      resourceId: null,
      metadata: { filename: body.filename, bytes: buffer.length },
    });

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": `attachment; filename="${(body.filename || "minuta-juridica").replace(/[^a-zA-Z0-9-_.]/g, "_")}.docx"`,
        "Content-Length": String(buffer.length),
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Falha ao gerar .docx", detail: (err as Error).message },
      { status: 500 },
    );
  }
}