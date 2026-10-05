import { NextRequest, NextResponse } from "next/server";
import { logAuditEvent } from "@/lib/audit";
import { parseJsonBody } from "@/lib/api-helpers";

export const dynamic = "force-dynamic";

const DATAJUD_API_BASE = "https://api-publica.datajud.cnj.jus.br";
const DATAJAD_TOKEN = "c7o6ektnW6n4p3uI0r07bC8Y4h3t2m3";

interface DatajudResultado {
  cnj: string;
  tribunal: string | null;
  encontrado: boolean;
  dados?: Record<string, unknown>;
}

// GET /api/datajud?cnj=xxx — consulta pública por número CNJ
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const cnj = url.searchParams.get("cnj");
  if (!cnj) return NextResponse.json({ error: "cnj obrigatório" }, { status: 400 });

  // Formata CNJ: remove não-dígitos
  const cnjLimpo = cnj.replace(/\D/g, "");
  if (cnjLimpo.length < 20) {
    return NextResponse.json({ error: "CNJ deve ter 20 dígitos" }, { status: 400 });
  }

  // Identifica tribunal (segmento = posição 14-15)
  const segmento = cnjLimpo.slice(13, 15);
  const tribunalMap: Record<string, string> = {
    "8": "TJ", // estadual
    "4": "TRF", // federal
    "5": "TRT", // trabalhista
    "6": "TRE", // eleitoral
    "2": "TJM", // militar
  };
  const tribunalTipo = tribunalMap[segmento[0]] || "TJ";
  // Para TJ/TRF: usar tribunal específico (estado/region) — sem detalhamento aqui, usa endpoint genérico
  const endpoint = tribunalTipo === "TJ"
    ? "api-publica-datajud-tj"
    : tribunalTipo === "TRT"
      ? "api-publica-datajud-trt"
      : "api-publica-datajud";

  const result: DatajudResultado = {
    cnj,
    tribunal: tribunalTipo,
    encontrado: false,
  };

  try {
    const resp = await fetch(`${DATAJUD_API_BASE}/${endpoint}/api/public/processos/numero/${cnjLimpo}`, {
      method: "GET",
      headers: {
        "X-Request-DataJud": DATAJAD_TOKEN,
        "Accept": "application/json",
      },
      signal: AbortSignal.timeout(15000),
    });
    if (resp.ok) {
      const json = (await resp.json()) as Record<string, unknown>;
      result.encontrado = true;
      result.dados = json;
    } else if (resp.status === 404) {
      result.encontrado = false;
    } else {
      return NextResponse.json({ error: `DataJud retornou ${resp.status}`, cnj }, { status: 502 });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: `Falha ao consultar DataJud: ${msg}`, cnj }, { status: 502 });
  }

  await logAuditEvent({
    action: "datajud_query",
    resource: "process",
    metadata: { cnj, tribunal: tribunalTipo, encontrado: result.encontrado },
  });

  return NextResponse.json(result);
}

// POST /api/datajud — busca geral em lote (json query) ou por CNJ
export async function POST(req: NextRequest) {
  const parsed = await parseJsonBody<{ cnj?: string; query?: Record<string, unknown> }>(req);
  if (!parsed.ok) return NextResponse.json({ error: parsed.error }, { status: 400 });

  const { cnj, query } = parsed.body;
  if (!cnj && !query) {
    return NextResponse.json({ error: "Informe cnj ou query" }, { status: 400 });
  }

  // Se passou query, usa endpoint de busca por body
  if (query) {
    const endpoint = "api-publica-datajud-tj";
    try {
      const resp = await fetch(`${DATAJUD_API_BASE}/${endpoint}/api/public/processos/pesquisa`, {
        method: "POST",
        headers: {
          "X-Request-DataJud": DATAJAD_TOKEN,
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(query),
        signal: AbortSignal.timeout(20000),
      });
      if (!resp.ok) {
        return NextResponse.json({ error: `DataJud retornou ${resp.status}` }, { status: 502 });
      }
      const json = (await resp.json()) as Record<string, unknown>;
      await logAuditEvent({
        action: "datajud_search",
        resource: "process",
        metadata: { hasQuery: true, querySize: JSON.stringify(query).length },
      });
      return NextResponse.json({ resultados: json });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return NextResponse.json({ error: `Falha ao consultar DataJud: ${msg}` }, { status: 502 });
    }
  }

  // POST com cnj: trata como busca por número
  if (cnj) {
    const cnjLimpo = cnj.replace(/\D/g, "");
    if (cnjLimpo.length < 20) return NextResponse.json({ error: "CNJ deve ter 20 dígitos" }, { status: 400 });
    const endpoint = "api-publica-datajud-tj";
    try {
      const resp = await fetch(`${DATAJUD_API_BASE}/${endpoint}/api/public/processos/numero/${cnjLimpo}`, {
        method: "GET",
        headers: {
          "X-Request-DataJud": DATAJAD_TOKEN,
          Accept: "application/json",
        },
        signal: AbortSignal.timeout(15000),
      });
      if (resp.status === 404) {
        await logAuditEvent({ action: "datajud_query", resource: "process", metadata: { cnj, encontrado: false } });
        return NextResponse.json({ cnj, encontrado: false });
      }
      if (!resp.ok) return NextResponse.json({ error: `DataJud retornou ${resp.status}` }, { status: 502 });
      const json = (await resp.json()) as Record<string, unknown>;
      await logAuditEvent({ action: "datajud_query", resource: "process", metadata: { cnj, encontrado: true } });
      return NextResponse.json({ cnj, encontrado: true, dados: json });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return NextResponse.json({ error: `Falha ao consultar DataJud: ${msg}` }, { status: 502 });
    }
  }

  return NextResponse.json({ error: "Requisição inválida" }, { status: 400 });
}
