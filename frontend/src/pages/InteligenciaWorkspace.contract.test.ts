import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const workspace = readFileSync(
  resolve(ROOT, "src/pages/InteligenciaWorkspace.tsx"),
  "utf8",
);
const registry = readFileSync(
  resolve(ROOT, "src/config/moduleRegistry.tsx"),
  "utf8",
);
const toolsPage = readFileSync(
  resolve(ROOT, "src/pages/FerramentasIA.tsx"),
  "utf8",
);
const aiService = readFileSync(
  resolve(ROOT, "src/services/ai.ts"),
  "utf8",
);
const legalResearchPage = readFileSync(
  resolve(ROOT, "src/pages/PesquisaJuridica.tsx"),
  "utf8",
);
const legalResearchService = readFileSync(
  resolve(ROOT, "src/services/legalResearch.ts"),
  "utf8",
);
const knowledgeGovernance = readFileSync(
  resolve(ROOT, "src/components/KnowledgeGovernancePanel.tsx"),
  "utf8",
);
const governance = readFileSync(
  resolve(ROOT, "src/pages/GovernancaIA.tsx"),
  "utf8",
);
const jurimetry = readFileSync(
  resolve(ROOT, "src/pages/Jurimetria.tsx"),
  "utf8",
);
const fees = readFileSync(
  resolve(ROOT, "src/components/EstimadorHonorarios.tsx"),
  "utf8",
);

describe("Inteligência Jurídica — contrato canônico da auditoria 2026-09-18", () => {
  it("liga Pesquisa e validação de fontes à base governada real", () => {
    expect(workspace).toContain(
      'const PesquisaJuridica = lazy(() => import("./PesquisaJuridica"))',
    );
    expect(workspace).toContain('sub === "pesquisa"');
    expect(workspace).toContain("<PesquisaJuridica />");
    expect(workspace).not.toContain("<ConteudoJuridico />");
  });

  it("oferece validação determinística de citações na pesquisa jurídica", () => {
    expect(legalResearchService).toContain('"/ai/citacoes/verificar"');
    expect(legalResearchService).toContain("consultar_datajud: consultarDatajud");
    expect(legalResearchPage).toContain("Validação determinística anti-alucinação");
    expect(legalResearchPage).toContain("confira");
    expect(legalResearchPage).toContain("fonte oficial");
  });

  it("preserva Jurimetria operacional para a equipe jurídica e segmenta blocos estratégicos", () => {
    const bloco = workspace.slice(
      workspace.indexOf('k: "jurimetria"'),
      workspace.indexOf('k: "conhecimento"'),
    );
    expect(bloco).toContain("roles: EQUIPE_JURIDICA_UI");
    expect(jurimetry).toContain("podeVerEstrategico");
    expect(jurimetry).toContain('api.get("/jurimetria/overview")');
    expect(jurimetry).toContain('api.get("/jurimetria/por-area")');
    expect(jurimetry).toContain('api.get("/jurimetria/por-tribunal")');
    expect(jurimetry).toContain('api.get("/jurimetria/por-tese")');
    expect(jurimetry).toContain("podeVerEstrategico && (");
  });

  it("expõe Saúde e Governança dentro de Estado da IA", () => {
    expect(workspace).toMatch(
      /k:\s*"saude"[\s\S]*?label:\s*"Saúde"[\s\S]*?label:\s*"Governança"/,
    );
    expect(workspace).toContain("<DashboardIA />");
    expect(workspace).toContain("<GovernancaIA />");
  });

  it("mantém o registry com nome único e todos os prefixes realmente consumidos", () => {
    const bloco = registry.slice(
      registry.indexOf('key: "inteligencia"'),
      registry.indexOf('key: "banco-teses"'),
    );
    expect(bloco).toContain('label: "Inteligência Jurídica"');
    for (const prefix of [
      "/api/ia",
      "/api/ai",
      "/api/ai/skills",
      "/api/jurimetria",
      "/api/rag",
      "/api/conhecimento",
      "/api/honorarios-oab",
      "/api/ia-saude",
      "/api/ia-governanca",
    ]) {
      expect(bloco).toContain(`"${prefix}"`);
    }
  });

  it("pagina a curadoria em vez de limitar o corpus aos 100 mais recentes", () => {
    expect(knowledgeGovernance).toContain("docsPage");
    expect(knowledgeGovernance).toContain("docsTotalPages");
    expect(knowledgeGovernance).toContain("page_size: 50");
    expect(knowledgeGovernance).not.toContain("page_size: 100");
  });

  it("não anuncia Curadoria RAG como aba normal da Governança da IA", () => {
    const tabs = governance.slice(
      governance.indexOf("const tabs = ["),
      governance.indexOf("] as const;", governance.indexOf("const tabs = [")),
    );
    expect(tabs).not.toContain("Curadoria da base de conhecimento");
    expect(governance).toContain('tab === "curadoria"');
  });

  it("consome o grupo funcional vindo do backend sem heurística local", () => {
    expect(aiService).toContain("functional_group:");
    expect(toolsPage).toContain("skill.functional_group");
    expect(toolsPage).not.toContain("_GRUPO_KEYWORDS");
    expect(toolsPage).not.toContain("classificarGrupo");
  });

  it("usa o normalizador canônico de erros no estimador de honorários", () => {
    expect(fees).toContain('mensagemErroHttp(e, "Falha ao estimar.")');
    expect(fees).not.toContain("e.response?.data?.detail");
  });
});
