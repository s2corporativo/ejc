import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { createEvidence, quoteHash, normalizeQuote } from "@/lib/evidence";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// POST /api/upload — recebe arquivo (PDF/DOCX/TXT), extrai texto, cria EvidenceRefs
export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("file") as File | null;
  const caseId = (formData.get("caseId") as string) || "default-case";

  if (!file) {
    return NextResponse.json({ error: "Arquivo não enviado" }, { status: 400 });
  }

  if (file.size > 10 * 1024 * 1024) {
    return NextResponse.json({ error: "Arquivo muito grande (máx 10MB)" }, { status: 413 });
  }

  const fileName = file.name;
  const ext = fileName.split(".").pop()?.toLowerCase();
  let extractedText = "";
  let extractionMethod = "";

  try {
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    if (ext === "pdf") {
      // PDF extraction
      const pdfParse = (await import("pdf-parse")).default;
      const pdfData = await pdfParse(buffer);
      extractedText = pdfData.text;
      extractionMethod = "pdf_text_extraction";
    } else if (ext === "docx") {
      // DOCX extraction
      const mammoth = await import("mammoth");
      const result = await mammoth.extractRawText({ buffer });
      extractedText = result.value;
      extractionMethod = "docx_text_extraction";
    } else if (ext === "txt" || ext === "md") {
      // Plain text
      extractedText = buffer.toString("utf8");
      extractionMethod = "plain_text";
    } else {
      return NextResponse.json({ error: `Formato '${ext}' não suportado. Use PDF, DOCX ou TXT.` }, { status: 415 });
    }

    if (!extractedText || extractedText.trim().length < 10) {
      return NextResponse.json({ error: "Não foi possível extrair texto do arquivo (pode ser imagem/scanned)" }, { status: 422 });
    }

    // Limita o texto extraído a 10.000 caracteres para performance
    const maxChars = 10000;
    const truncated = extractedText.length > maxChars;
    const textContent = truncated ? extractedText.slice(0, maxChars) + "\n... [texto truncado]" : extractedText;

    // Cria EvidenceRef para o documento inteiro
    const docHash = quoteHash(textContent.slice(0, 500));
    const evidence = await createEvidence({
      caseId,
      documentId: fileName,
      quote: textContent.slice(0, 500), // primeiros 500 chars como trecho de referência
      sourceKind: "document",
      retrievalMethod: extractionMethod,
      documentHash: docHash,
      metadata: { fileName, fileSize: file.size, truncated, totalLength: extractedText.length },
    });

    // Cria EvidenceRefs para trechos significativos (parágrafos com >50 chars)
    const paragraphs = extractedText.split(/\n\s*\n/).filter((p) => p.trim().length > 50);
    const chunkEvidences = [];
    for (let i = 0; i < Math.min(paragraphs.length, 20); i++) {
      const para = normalizeQuote(paragraphs[i]);
      if (para.length < 50) continue;
      try {
        const ev = await createEvidence({
          caseId,
          documentId: fileName,
          quote: para,
          pageNumber: i + 1,
          sectionLabel: `Parágrafo ${i + 1}`,
          sourceKind: "document",
          retrievalMethod: extractionMethod,
        });
        chunkEvidences.push({ id: ev.id, quote: para.slice(0, 80), page: i + 1 });
      } catch {
        // Skip duplicates
      }
    }

    await logAuditEvent({
      action: "upload_document",
      resource: "document",
      resourceId: fileName,
      metadata: {
        fileName, fileSize: file.size, extractionMethod,
        textLength: extractedText.length, truncated,
        evidenceCount: chunkEvidences.length + 1,
      },
    });

    return NextResponse.json({
      fileName,
      extractionMethod,
      textLength: extractedText.length,
      truncated,
      text: textContent,
      evidenceId: evidence.id,
      chunkEvidences,
      totalEvidence: chunkEvidences.length + 1,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao processar arquivo";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
