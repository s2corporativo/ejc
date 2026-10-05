import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import {
  calculateDeadline,
  calculateCorrection,
  calculateInterest,
  checkPrescription,
} from "@/lib/legal_calculator";
import { parseJsonBody, MAX_PRAZO_DIAS } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

// POST /api/calculadora-juridica — tipo=prazo|correcao|juros|prescricao
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ type?: string; [k: string]: unknown }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const body = parsed.body;
  switch (body.type) {
    case "prazo": {
      const marcoInicialRaw = body.marcoInicial as string;
      const prazoDias = Number(body.prazoDias);
      const tipoContagem = (body.tipoContagem as "uteis" | "corridos") || "uteis";
      if (!marcoInicialRaw || !prazoDias) {
        return NextResponse.json({ error: "marcoInicial e prazoDias obrigatórios" }, { status: 400 });
      }
      if (prazoDias > MAX_PRAZO_DIAS) {
        return NextResponse.json({ error: `prazoDias acima do limite (${MAX_PRAZO_DIAS})` }, { status: 400 });
      }
      const marcoInicial = new Date(marcoInicialRaw);
      if (isNaN(marcoInicial.getTime())) {
        return NextResponse.json({ error: "marcoInicial inválido" }, { status: 400 });
      }
      const result = calculateDeadline(marcoInicial, prazoDias, tipoContagem);
      await logAuditEvent({
        action: "calc_juridica",
        resource: "case",
        metadata: { tipo: "prazo", prazoDias, tipoContagem, vencimento: result.vencimento.toISOString() },
      });
      return NextResponse.json({ ...result, vencimento: result.vencimento.toISOString(), marcoInicial: marcoInicial.toISOString() });
    }
    case "correcao": {
      const valorOriginal = Number(body.valorOriginal);
      const fatorAcumulado = Number(body.fatorAcumulado);
      const indice = (body.indice as string) || "IPCA";
      if (!valorOriginal || !fatorAcumulado) {
        return NextResponse.json({ error: "valorOriginal e fatorAcumulado obrigatórios" }, { status: 400 });
      }
      const result = calculateCorrection(valorOriginal, fatorAcumulado, indice);
      await logAuditEvent({
        action: "calc_juridica",
        resource: "case",
        metadata: { tipo: "correcao", valorOriginal, fatorAcumulado, indice },
      });
      return NextResponse.json(result);
    }
    case "juros": {
      const valorPrincipal = Number(body.valorPrincipal);
      const meses = Number(body.meses);
      const taxaMensal = Number(body.taxaMensal) || 0.01;
      const base = (body.base as "cc_art_406" | "stj_482" | "clt") || "cc_art_406";
      if (!valorPrincipal || !meses) {
        return NextResponse.json({ error: "valorPrincipal e meses obrigatórios" }, { status: 400 });
      }
      const result = calculateInterest(valorPrincipal, meses, taxaMensal, base);
      await logAuditEvent({
        action: "calc_juridica",
        resource: "case",
        metadata: { tipo: "juros", valorPrincipal, meses, taxaMensal, base },
      });
      return NextResponse.json(result);
    }
    case "prescricao": {
      const dataFatoRaw = body.dataFato as string;
      const dataAjuizamentoRaw = body.dataajuizamento as string;
      const area = (body.area as string) || "civil";
      if (!dataFatoRaw || !dataAjuizamentoRaw) {
        return NextResponse.json({ error: "dataFato e dataajuizamento obrigatórios" }, { status: 400 });
      }
      const dataFato = new Date(dataFatoRaw);
      const dataajuizamento = new Date(dataAjuizamentoRaw);
      if (isNaN(dataFato.getTime()) || isNaN(dataajuizamento.getTime())) {
        return NextResponse.json({ error: "datas inválidas" }, { status: 400 });
      }
      const result = checkPrescription(dataFato, dataajuizamento, area);
      await logAuditEvent({
        action: "calc_juridica",
        resource: "case",
        metadata: { tipo: "prescricao", area, prescrito: result.prescrito, diasRestantes: result.diasRestantes },
      });
      return NextResponse.json(result);
    }
    default:
      return NextResponse.json(
        { error: "type obrigatório: prazo | correcao | juros | prescricao" },
        { status: 400 },
      );
  }
}
