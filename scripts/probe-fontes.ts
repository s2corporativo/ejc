// probes.ts — Verifica acessibilidade de fontes oficiais brasileiras
// Roda um probe em cada API pública (sem auth) e reporta status.

const SOURCES = [
  {
    name: "IBGE - SIDRA (IPCA/INPC)",
    url: "https://apisidra.ibge.gov.br/values/t/1737/n1/all",
    module: "Cálculos (índices)",
    expected: "JSON com séries do IPCA",
  },
  {
    name: "BCB - Ranking de Reclamações",
    url: "https://olinda.bcb.gov.br/olinda/servico/IRECL/versao/v1/odata/RegistroDeReclamacoes?$top=1",
    module: "Bancário (falha sistêmica)",
    expected: "OData JSON com reclamações por banco",
  },
  {
    name: "Câmara dos Deputados v2",
    url: "https://dadosabertos.camara.leg.br/api/v2/proposicoes?itens=1",
    module: "Radar Regulatório",
    expected: "JSON com proposições legislativas",
  },
  {
    name: "Senado - Dados Abertos",
    url: "https://legis.senado.leg.br/dadosabertos/materia/lista?dataInicio=2026-01-01&dataFim=2026-01-31&itens=1",
    module: "Radar Regulatório",
    expected: "XML/JSON com matérias do Senado",
  },
  {
    name: "CNJ - TPU (Tabelas Processuais)",
    url: "https://www.cnj.jus.br/corregedoriacnj/sgt/sgt.xml",
    module: "Normalização processual",
    expected: "XML/SOAP com tabelas unificadas",
  },
  {
    name: "STJ - Dados Abertos (CKAN)",
    url: "https://stj-cloud-public.jus.br/api/3/action/package_list",
    module: "Base de conhecimento",
    expected: "JSON CKAN com lista de datasets",
  },
  {
    name: "STF - Corte Aberta",
    url: "https://resultados.tse.jus.br/resultados?eleicao=2022&cargo=1",
    module: "Constitucional (analytics)",
    expected: "JSON com dados (TSE não STF - STF pode requerer CSV download)",
    note: "STF Corte Aberta é via CSV/BigQuery, não REST direta",
  },
  {
    name: "Querido Diário (municipal)",
    url: "https://queridodiario.ok.org.br/api/gazettes?limit=1",
    module: "Radar municipal",
    expected: "JSON com diários oficiais municipais",
  },
  {
    name: "Consumidor.gov.br (estatísticas)",
    url: "https://www.consumidor.gov.br/api/estatistica/claim?size=1",
    module: "Consumidor (prova estatística)",
    expected: "JSON com reclamações por empresa/tema",
    note: "API pode requerer headers específicos",
  },
  {
    name: "Planalto - Legislação (CPC)",
    url: "http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm",
    module: "Base normativa primária",
    expected: "HTML com texto da lei",
  },
  {
    name: "ANPD - Portal LGPD",
    url: "https://www.gov.br/anpd/pt-br/documentos-e-publicacoes",
    module: "Base de conhecimento (LGPD)",
    expected: "HTML gov.br com regulamentos",
  },
  {
    name: "PGFN - Dívida Ativa",
    url: "https://www.gov.br/pgfn/pt-br/dados-abertos/dados-abertos-da-pgfn",
    module: "Due diligence",
    expected: "HTML gov.br com links para CSV bulk",
  },
  {
    name: "ANS - Dados Abertos",
    url: "https://www.gov.br/ans/pt-br/assuntos/dados-abertos",
    module: "Consumidor/saúde suplementar",
    expected: "HTML gov.br com links para FTP/CSV",
  },
];

async function probe(url: string, timeoutMs = 10000): Promise<{ status: number; ok: boolean; error?: string; contentType?: string; sample?: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { "Accept": "application/json,application/xml,text/html,*/*" },
      redirect: "follow" as RequestRedirect,
    });
    clearTimeout(timeout);
    const contentType = res.headers.get("content-type") || "";
    const text = await res.text();
    return {
      status: res.status,
      ok: res.ok,
      contentType: contentType.slice(0, 80),
      sample: text.slice(0, 150).replace(/\n/g, " "),
    };
  } catch (e) {
    clearTimeout(timeout);
    return {
      status: 0,
      ok: false,
      error: e instanceof Error ? e.message.slice(0, 100) : "Erro desconhecido",
    };
  }
}

async function main() {
  console.log("🔍 PROBE DE FONTES OFICIAIS BRASILEIRAS\n");
  let ok = 0, fail = 0;

  for (const src of SOURCES) {
    process.stdout.write(`  ${src.name}... `);
    const result = await probe(src.url);
    if (result.ok) {
      ok++;
      console.log(`✅ ${result.status} ${result.contentType || ""}`);
      console.log(`     sample: ${result.sample?.slice(0, 80) || ""}`);
    } else {
      fail++;
      console.log(`❌ ${result.status || "ERR"} ${result.error || "status não-2xx"}`);
      if (src.note) console.log(`     note: ${src.note}`);
    }
    console.log(`     módulo: ${src.module}`);
    console.log("");
  }

  console.log(`\n=== RESULTADO ===`);
  console.log(`✅ ${ok} acessíveis`);
  console.log(`❌ ${fail} inacessíveis`);
  console.log(`Total: ${SOURCES.length} fontes testadas`);
}

main();
