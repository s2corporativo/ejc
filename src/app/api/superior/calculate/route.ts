import { NextRequest, NextResponse } from "next/server";
import { calculateDeadline, calculateCorrection, calculateInterest, checkPrescription } from "@/lib/legal_calculator";
import { logAuditEvent } from "@/lib/audit";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: { type?: string; [key: string]: unknown } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  switch (body.type) {
    case "deadline": {
      const marcoInicial = new Date(body.marcoInicial as string);
      const prazoDias = Number(body.prazoDias);
      const tipoContagem = (body.tipoContagem as "uteis" | "corridos") || "uteis";
      if (isNaN(marcoInicial.getTime()) || !prazoDias) {
        return NextResponse.json({ error: "marcoInicial e prazoDias obrigatórios" }, { status: 400 });
      }
      const result = calculateDeadline(marcoInicial, prazoDias, tipoContagem);
      await logAuditEvent({ action: "calc_deadline", resource: "case", metadata: { prazoDias, tipoContagem, vencimento: result.vencimento.toISOString() } });
      return NextResponse.json({ ...result, vencimento: result.vencimento.toISOString() });
    }
    case "correction": {
      const valorOriginal = Number(body.valorOriginal);
      const fatorAcumulado = Number(body.fatorAcumulado);
      const indice = (body.indice as string) || "IPCA";
      if (!valorOriginal || !fatorAcumulado) {
        return NextResponse.json({ error: "valorOriginal e fatorAcumulado obrigatórios" }, { status: 400 });
      }
      const result = calculateCorrection(valorOriginal, fatorAcumulado, indice);
      await logAuditEvent({ action: "calc_correction", resource: "case", metadata: { valorOriginal, fatorAcumulado, indice } });
      return NextResponse.json(result);
    }
    case "interest": {
      const valorPrincipal = Number(body.valorPrincipal);
      const meses = Number(body.meses);
      const taxaMensal = Number(body.taxaMensal) || 0.01;
      const base = (body.base as "cc_art_406" | "stj_482" | "clt") || "cc_art_406";
      if (!valorPrincipal || !meses) {
        return NextResponse.json({ error: "valorPrincipal e meses obrigatórios" }, { status: 400 });
      }
      const result = calculateInterest(valorPrincipal, meses, taxaMensal, base);
      await logAuditEvent({ action: "calc_interest", resource: "case", metadata: { valorPrincipal, meses, taxaMensal, base } });
      return NextResponse.json(result);
    }
    case "prescription": {
      const dataFato = new Date(body.dataFato as string);
      const dataajuizamento = new Date(body.dataajuizamento as string);
      const area = (body.area as string) || "civil";
      if (isNaN(dataFato.getTime()) || isNaN(dataajuizamento.getTime())) {
        return NextResponse.json({ error: "dataFato e dataajuizamento obrigatórios" }, { status: 400 });
      }
      const result = checkPrescription(dataFato, dataajuizamento, area);
      await logAuditEvent({ action: "calc_prescription", resource: "case", metadata: { area, prescrito: result.prescrito, diasRestantes: result.diasRestantes } });
      return NextResponse.json(result);
    }
    default:
      return NextResponse.json({ error: "type obrigatório: deadline | correction | interest | prescription" }, { status: 400 });
  }
}
