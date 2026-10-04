// ingestor-fontes.ts — Ingestor de fontes oficiais brasileiras
// Tenta URLs atualizadas das fontes que falharam no probe e alimenta LegalSource.

import { db } from "@/lib/db";
import { createHash } from "crypto";

// URLs atualizadas (após pesquisa manual)
const FONTES_ATUALIZADAS = [
  // BCB — Ranking de Reclamações (URL nova)
  { name: "BCB Ranking Reclamações", url: "https://olinda.bcb.gov.br/olinda/servico/IRECL/versao/v1/odata/RegistroDeReclamacoes?$top=5&$format=json", tipo: "dados_externos", diploma: "BCB", numero: "ranking_reclamacoes" },
  // Câmara dos Deputados v2 (com timeout maior)
  { name: "Câmara Proposições", url: "https://dadosabertos.camara.leg.br/api/v2/proposicoes?itens=5&ordem=ASC&ordenarPor=id", tipo: "dados_externos", diploma: "Câmara", numero: "proposicoes" },
  // Senado (novo endpoint modernizado)
  { name: "Senado Matérias", url: "https://legis.senado.leg.br/dadosabertos/materia/lista/v3/2026?itens=5", tipo: "dados_externos", diploma: "Senado", numero: "materias_2026" },
  // Planalto — tentar HTTPS
  { name: "Planalto CPC", url: "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm", tipo: "legislacao", diploma: "CPC", numero: "Lei 13.105/2015" },
  // STJ Dados Abertos (tentar URL correta)
  { name: "STJ Dados Abertos", url: "https://ww2.stj.jus.br/repositorio/", tipo: "dados_externos", diploma: "STJ", numero: "dados_abertos" },
];

async function probe(url: string, timeoutMs = 15000): Promise<{ ok: boolean; status: number; error?: string; contentType?: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { "Accept": "application/json,text/html,*/*" },
      redirect: "follow" as RequestRedirect,
    });
    clearTimeout(timeout);
    return { ok: res.ok, status: res.status, contentType: res.headers.get("content-type") || "" };
  } catch (e) {
    clearTimeout(timeout);
    return { ok: false, status: 0, error: e instanceof Error ? e.message.slice(0, 80) : "erro" };
  }
}

async function main() {
  console.log("🔍 PROBE COM URLS ATUALIZADAS\n");
  let ok = 0, fail = 0;
  const results: { name: string; url: string; ok: boolean; status: number; error?: string }[] = [];

  for (const f of FONTES_ATUALIZADAS) {
    process.stdout.write(`  ${f.name}... `);
    const result = await probe(f.url);
    results.push({ name: f.name, url: f.url, ...result });
    if (result.ok) {
      ok++;
      console.log(`✅ ${result.status} ${result.contentType?.slice(0, 40) || ""}`);
    } else {
      fail++;
      console.log(`❌ ${result.status || "ERR"} ${result.error || ""}`);
    }
  }

  console.log(`\n=== PROBE RESULT ===`);
  console.log(`✅ ${ok} acessíveis, ❌ ${fail} inacessíveis\n`);

  // Tenta criar LegalSource para as fontes de legislação acessíveis
  console.log("🌱 Ingestor de Legislação (Planalto)\n");

  // Para o Planalto CPC — se acessível, cria/atualiza LegalSource
  const planalto = results.find((r) => r.name === "Planalto CPC");
  if (planalto?.ok) {
    try {
      const res = await fetch(planalto.url);
      const html = await res.text();
      // Extrai texto básico (remove tags HTML)
      const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 2000);
      const hash = createHash("sha256").update(text.slice(0, 500)).digest("hex");

      const existing = await db.legalSource.findFirst({ where: { diploma: "CPC", numero: "Lei 13.105/2015" } });
      if (!existing) {
        await db.legalSource.create({
          data: {
            tipo: "artigo_lei",
            diploma: "CPC",
            numero: "Lei 13.105/2015",
            tribunal: null,
            textoTrecho: text.slice(0, 1000),
            vigente: true,
            urlOficial: planalto.url,
            hashConteudo: hash,
            dataConsulta: new Date(),
            revisadoPor: "ingestor-automatico",
          },
        });
        console.log("  ✓ Lei 13.105/2015 (CPC) ingerida do Planalto");
      } else {
        console.log("  ⏭ CPC já existe na base");
      }
    } catch (e) {
      console.log(`  ✗ Erro ao ingerir CPC: ${e instanceof Error ? e.message : "erro"}`);
    }
  } else {
    console.log("  ⏭ Planalto inacessível — pulando ingestão");
  }

  console.log(`\n📊 Total LegalSource: ${await db.legalSource.count()}`);
  console.log("\n=== RESUMO DAS FONTES ===");
  console.log("Fontes diretamente acessíveis (probe OK):");
  results.filter((r) => r.ok).forEach((r) => console.log(`  ✅ ${r.name} — ${r.status}`));
  console.log("\nFontes ainda inacessíveis (precisam de abordagem alternativa):");
  results.filter((r) => !r.ok).forEach((r) => console.log(`  ❌ ${r.name} — ${r.error || r.status}`));
}

main().finally(() => db.$disconnect());
