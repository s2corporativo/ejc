import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// GET /api/fontes/querido-diario — busca diários oficiais municipais
// Uso: radar de normas municipais (D+0)
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const query = url.searchParams.get("query") || "";
  const limit = url.searchParams.get("limit") || "10";
  const territoryId = url.searchParams.get("territoryId") || ""; // código IBGE do município

  try {
    const params = new URLSearchParams();
    if (query) params.append("searchstring", query);
    params.append("limit", limit);
    if (territoryId) params.append("territory_ids", territoryId);

    const apiUrl = `https://queridodiario.ok.org.br/api/gazettes?${params}`;
    const res = await fetch(apiUrl, {
      headers: { "Accept": "application/json" },
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Querido Diário retornou status ${res.status}` },
        { status: 502 }
      );
    }

    const data = await res.json();

    return NextResponse.json({
      fonte: "Querido Diário",
      query,
      totalGazettes: data.total_gazettes || 0,
      gazettes: (data.gazettes || []).map((g: {
        territory_id: string; date: string; url: string;
        newspaper_name: string; edition: string;
        excerpts: string[];
      }) => ({
        municipio: g.territory_id,
        data: g.date,
        url: g.url,
        jornal: g.newspaper_name,
        edicao: g.edition,
        trechos: (g.excerpts || []).slice(0, 3),
      })),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Erro ao acessar Querido Diário";
    return NextResponse.json({ error: msg, fonte: "Querido Diário" }, { status: 500 });
  }
}
