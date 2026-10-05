import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { logAuditEvent } from "@/lib/audit";
import { extrairEntidades } from "@/lib/assistente";

export const dynamic = "force-dynamic";

// GET /api/caso-mapa?caseId=xxx — mapa do caso + contradições
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const caseId = url.searchParams.get("caseId");
  if (!caseId) return NextResponse.json({ error: "caseId obrigatório" }, { status: 400 });

  const c = await db.case.findUnique({
    where: { id: caseId },
    include: {
      client: true,
      documents: { orderBy: { createdAt: "asc" } },
      movimentos: { orderBy: { data: "asc" } },
      audiencias: { orderBy: { data: "asc" } },
    },
  });
  if (!c) return NextResponse.json({ error: "Caso não encontrado" }, { status: 404 });

  const deadlines = await db.caseDeadline.findMany({
    where: { caseId },
    orderBy: { vencimento: "asc" },
  });

  // Extrai entidades de cada documento para detectar contradições
  const docEntities = c.documents.map((d) => ({
    id: d.id,
    title: d.title,
    templateSlug: d.templateSlug,
    rawFacts: d.rawFacts,
    generated: d.generatedContent,
    entities: extrairEntidades(`${d.rawFacts} ${d.generatedContent}`),
  }));

  // Contradições: datas conflitantes em documentos diferentes + valores divergentes
  interface Contradicao {
    tipo: string;
    documento1: string;
    documento2: string;
    detalhe: string;
  }
  const contradicoes: Contradicao[] = [];

  // Verifica datas conflitantes (mesmo documento ou entre documentos)
  for (let i = 0; i < docEntities.length; i++) {
    for (let j = i + 1; j < docEntities.length; j++) {
      const a = docEntities[i];
      const b = docEntities[j];
      // datas: datas conflitantes que estão presentes em ambos
      const datasA = new Set(a.entities.datas);
      const datasB = new Set(b.entities.datas);
      // datas mencionadas por um e omitidas pelo outro = diferença sem contradição
      // contradição real: datas diferentes referindo-se ao mesmo evento — heurística: se há sobreposição parcial
      const onlyA = Array.from(datasA).filter((d) => !datasB.has(d));
      const onlyB = Array.from(datasB).filter((d) => !datasA.has(d));
      if (onlyA.length > 0 && onlyB.length > 0 && onlyA.length + onlyB.length > 2) {
        contradicoes.push({
          tipo: "datas_divergentes",
          documento1: a.title,
          documento2: b.title,
          detalhe: `Doc1 menciona: ${onlyA.join(", ")}; Doc2 menciona: ${onlyB.join(", ")}`,
        });
      }
      // valores divergentes (mesma referência)
      const valoresA = new Set(a.entities.valores);
      const valoresB = new Set(b.entities.valores);
      // se ambos mencionam algum valor e nenhum é compartilhado
      const shared = Array.from(valoresA).filter((v) => valoresB.has(v));
      if (valoresA.size > 0 && valoresB.size > 0 && shared.length === 0) {
        contradicoes.push({
          tipo: "valores_divergentes",
          documento1: a.title,
          documento2: b.title,
          detalhe: `Doc1 valores: ${Array.from(valoresA).join(", ")}; Doc2 valores: ${Array.from(valoresB).join(", ")}`,
        });
      }
    }
  }

  // Timeline unificada: movimentos + audiências + deadlines + datas dos documentos
  interface TimelineItem {
    data: string;
    tipo: string;
    descricao: string;
    fonte: string;
  }
  const timeline: TimelineItem[] = [];
  for (const m of c.movimentos) {
    timeline.push({
      data: m.data.toISOString(),
      tipo: m.tipo,
      descricao: m.descricao,
      fonte: "movimento",
    });
  }
  for (const a of c.audiencias) {
    timeline.push({
      data: a.data.toISOString(),
      tipo: "audiencia",
      descricao: `${a.tipo}${a.orgao ? ` (${a.orgao})` : ""}${a.local ? ` @ ${a.local}` : ""}`,
      fonte: "audiencia",
    });
  }
  for (const d of deadlines) {
    timeline.push({
      data: d.vencimento.toISOString(),
      tipo: "prazo",
      descricao: `${d.descricao} (${d.prazoDias} ${d.tipoContagem})`,
      fonte: "deadline",
    });
  }
  timeline.sort((a, b) => new Date(a.data).getTime() - new Date(b.data).getTime());

  await logAuditEvent({
    action: "caso_mapa_query",
    resource: "case",
    resourceId: c.id,
    metadata: {
      movimentos: c.movimentos.length,
      audiencias: c.audiencias.length,
      deadlines: deadlines.length,
      documentos: c.documents.length,
      contradições: contradicoes.length,
    },
  });

  return NextResponse.json({
    caso: {
      id: c.id,
      title: c.title,
      number: c.number,
      area: c.area,
      status: c.status,
      responsavel: c.responsavel,
      valor: c.valor,
    },
    cliente: c.client
      ? {
          id: c.client.id,
          name: c.client.name,
          email: c.client.email,
          document: c.client.document,
        }
      : null,
    timeline,
    documentos: c.documents.map((d) => ({
      id: d.id,
      title: d.title,
      templateSlug: d.templateSlug,
      status: d.status,
      createdAt: d.createdAt.toISOString(),
    })),
    entidades: docEntities.map((d) => ({
      id: d.id,
      title: d.title,
      cnj: d.entities.cnj,
      oabs: d.entities.oabs,
      datas: d.entities.datas,
      valores: d.entities.valores,
      tipoPeca: d.entities.tipoPeca,
      area: d.entities.area,
    })),
    contradições: contradicoes,
    resumo: {
      totalMovimentos: c.movimentos.length,
      totalAudiencias: c.audiencias.length,
      totalDeadlines: deadlines.length,
      totalDocumentos: c.documents.length,
      totalContradicoes: contradicoes.length,
    },
  });
}
