import { describe, expect, it } from "vitest";
import {
  isActivityView,
  mapAgendaTipo,
  situacaoDe,
} from "./CentralAtividades";
import { isCentralTab } from "./Central";

describe("Central unificada deep links", () => {
  it.each(["atividades", "relacionamento"])("aceita a aba %s", (tab) => {
    expect(isCentralTab(tab)).toBe(true);
  });

  it("rejeita aba desconhecida ou ausente (cai em atividades)", () => {
    expect(isCentralTab("crm")).toBe(false);
    expect(isCentralTab(null)).toBe(false);
  });
});

describe("CentralAtividades deep links", () => {
  it.each(["lista", "calendario", "timeline", "kanban"])(
    "aceita a visualização %s",
    (view) => {
      expect(isActivityView(view)).toBe(true);
    },
  );

  it("rejeita visualização desconhecida ou ausente", () => {
    expect(isActivityView("agenda-antiga")).toBe(false);
    expect(isActivityView(null)).toBe(false);
  });
});

describe("situacaoDe — kanban por situação usa só estados reais do backend", () => {
  it.each(["concluido", "concluida", "tratada", "cancelado", "CONCLUIDO"])(
    "%s conta como concluído",
    (s) => {
      expect(situacaoDe(s)).toBe("concluido");
    },
  );

  it("fazendo (tarefas) é o único estado de execução", () => {
    expect(situacaoDe("fazendo")).toBe("em_execucao");
  });

  it.each(["pendente", "a_fazer", "vencido", "", null, undefined])(
    "%s cai em não tratado",
    (s) => {
      expect(situacaoDe(s as string | null | undefined)).toBe("nao_tratado");
    },
  );
});

describe("mapAgendaTipo — subtipo real do evento de agenda", () => {
  it.each(["reuniao", "audiencia", "diligencia", "compromisso"] as const)(
    "preserva o subtipo %s",
    (t) => {
      expect(mapAgendaTipo(t)).toBe(t);
    },
  );

  it("cai em compromisso para 'outro', desconhecido ou ausente", () => {
    expect(mapAgendaTipo("outro")).toBe("compromisso");
    expect(mapAgendaTipo("qualquer")).toBe("compromisso");
    expect(mapAgendaTipo(null)).toBe("compromisso");
    expect(mapAgendaTipo(undefined)).toBe("compromisso");
  });
});
