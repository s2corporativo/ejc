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
const knowledgeGovernance = readFileSync(
  resolve(ROOT, "src/components/KnowledgeGovernancePanel.tsx"),
  "utf8",
);
const governance = readFileSync(
  resolve(ROOT, "src/pages/GovernancaIA.tsx"),
  "utf8",
);
const fees = readFileSync(
  resolve(ROOT, "src/components/EstimadorHonorarios.tsx"),
  "utf8",
);

describe("Inteligência Jurídica — contrato canônico da auditoria 2026-09-18", () => {
  it("liga Pesquisa e validação de fontes à base governada real", () => {
    expect(workspace).toContain('const Conhecimento = lazy(() => import("./Conhecimento"))');
    expect(workspace).toContain('sub === "pesquisa"');
    expect(workspace).toContain("<Conhecimento />");
    expect(workspace).not.toContain("<ConteudoJuridico />");
  });

  it("restringe Jurimetria estratégica aos gestores no agregador", () => {
    expect(workspace).toMatch(
      /k:\s*"jurimetria"[\s\S]*?roles:\s*GESTORES/,
    );
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

  it("usa o normalizador canônico de erros no estimador de honorários", () => {
    expect(fees).toContain('mensagemErroHttp(e, "Falha ao estimar.")');
    expect(fees).not.toContain("e.response?.data?.detail");
  });
});
