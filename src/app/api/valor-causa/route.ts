import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";
import { calcularValorCausa, type PedidoInput, type RelacaoPedidos } from "@/lib/lexvalida_port";

export const dynamic = "force-dynamic";

// GET /api/valor-causa — lista tipos de pedido e relações disponíveis
export async function GET() {
  return NextResponse.json({
    tipos: [
      { tipo: "cobranca", rotulo: "Cobrança", base: "CPC, art. 292, I" },
      { tipo: "ato_juridico", rotulo: "Ato jurídico", base: "CPC, art. 292, II" },
      { tipo: "alimentos", rotulo: "Alimentos", base: "CPC, art. 292, III" },
      { tipo: "bem", rotulo: "Bem", base: "CPC, art. 292, IV" },
      { tipo: "indenizacao", rotulo: "Indenização", base: "CPC, art. 292, V" },
      { tipo: "prestacoes", rotulo: "Prestações", base: "CPC, art. 292, §§ 1º e 2º" },
    ],
    relacoes: [
      { relacao: "cumulados", rotulo: "Cumulados (soma)", base: "CPC, art. 292, VI" },
      { relacao: "alternativos", rotulo: "Alternativos (maior)", base: "CPC, art. 292, VII" },
      { relacao: "subsidiarios", rotulo: "Subsidiários (principal)", base: "CPC, art. 292, VIII" },
    ],
  });
}

// POST /api/valor-causa — calcula valor da causa
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{
    pedidos?: PedidoInput[];
    relacao?: RelacaoPedidos;
  }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { pedidos, relacao = "cumulados" } = parsed.body;
  if (!Array.isArray(pedidos) || pedidos.length === 0) {
    return NextResponse.json({ error: "pedidos obrigatório (lista não vazia)" }, { status: 400 });
  }

  // validação prévia de tipos
  const tiposValidos = new Set(["cobranca", "ato_juridico", "alimentos", "bem", "indenizacao", "prestacoes"]);
  for (const p of pedidos) {
    if (!p.tipo || !tiposValidos.has(p.tipo)) {
      return NextResponse.json({ error: `tipo inválido: ${p.tipo}. Válidos: ${Array.from(tiposValidos).join(", ")}` }, { status: 400 });
    }
  }
  if (!["cumulados", "alternativos", "subsidiarios"].includes(relacao)) {
    return NextResponse.json({ error: "relacao inválida: cumulados | alternativos | subsidiarios" }, { status: 400 });
  }

  let result;
  try {
    result = calcularValorCausa(pedidos, relacao);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: msg }, { status: 400 });
  }

  await logAuditEvent({
    action: "valor_causa_calc",
    resource: "case",
    metadata: {
      totalPedidos: pedidos.length,
      tipos: pedidos.map((p) => p.tipo),
      relacao,
      valorDaCausa: result.valorDaCausa,
    },
  });

  return NextResponse.json(result);
}
