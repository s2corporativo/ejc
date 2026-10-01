import { afterEach, describe, expect, it } from "vitest";
import {
  cursorFlagAtiva,
  isActivityView,
  mapAgendaTipo,
  mapAtividadeCursor,
  situacaoColunaDe,
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
  it.each(["concluido", "concluida", "tratada", "CONCLUIDO"])(
    "%s conta como concluído",
    (s) => {
      expect(situacaoDe(s)).toBe("concluido");
    },
  );

  it("cancelado tem situação PRÓPRIA (badge neutra, não o selo verde)", () => {
    expect(situacaoDe("cancelado")).toBe("cancelado");
    expect(situacaoDe("CANCELADO")).toBe("cancelado");
  });

  it("cancelado agrupa na coluna Concluído do kanban (sem coluna própria)", () => {
    expect(situacaoColunaDe("cancelado")).toBe("concluido");
    expect(situacaoColunaDe("concluido")).toBe("concluido");
    expect(situacaoColunaDe("fazendo")).toBe("em_execucao");
    expect(situacaoColunaDe("pendente")).toBe("nao_tratado");
  });

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

describe("cursorFlagAtiva — rollback da paginação por flag (Tarefa 3)", () => {
  afterEach(() => {
    localStorage.removeItem("ejc:atividades-cursor");
  });

  it("ativa por padrão (sem flag no localStorage)", () => {
    expect(cursorFlagAtiva()).toBe(true);
  });

  it("flag '0' desliga o modo cursor (rollback para o legado)", () => {
    localStorage.setItem("ejc:atividades-cursor", "0");
    expect(cursorFlagAtiva()).toBe(false);
  });

  it("qualquer valor diferente de '0' mantém o cursor ativo", () => {
    localStorage.setItem("ejc:atividades-cursor", "1");
    expect(cursorFlagAtiva()).toBe(true);
  });
});

describe("mapAtividadeCursor — enriquecimento inline da página (Tarefa 3)", () => {
  const base = {
    id: "abc",
    tipo: "prazo",
    titulo: "Prazo X",
    descricao: null,
    date: "2026-10-05",
    status: "pendente",
    case_id: "c1",
    caso_titulo: "Caso Um",
    responsavel_id: "u1",
    prioridade: "alta",
    subtipo: null,
    dias_restantes: 4,
    urgencia: "atencao",
    confirmado: false,
    ciencia_confirmada: true,
    hora: null,
    local: null,
  };

  it("prazo recebe confirmado/ciencia_confirmada inline (botão não some)", () => {
    const item = mapAtividadeCursor(base);
    expect(item.fonte).toBe("prazo");
    expect(item.confirmado).toBe(false);
    expect(item.ciencia_confirmada).toBe(true);
    expect(item.origem).toBe("Prazos");
  });

  it("agenda recebe hora/local inline", () => {
    const item = mapAtividadeCursor({
      ...base,
      tipo: "agenda",
      subtipo: "audiencia",
      hora: "09:30",
      local: "Fórum Central",
    });
    expect(item.tipo).toBe("audiencia");
    expect(item.hora).toBe("09:30");
    expect(item.local).toBe("Fórum Central");
    expect(item.origem).toBe("Agenda");
  });

  it("campos ausentes viram undefined sem quebrar o shape", () => {
    const item = mapAtividadeCursor({ ...base, confirmado: undefined, hora: undefined });
    expect(item.confirmado).toBeUndefined();
    expect(item.dias_restantes).toBe(4);
    expect(item.caso_titulo).toBe("Caso Um");
  });

  it("suspensão e intimação mapeiam origem correta", () => {
    expect(mapAtividadeCursor({ ...base, tipo: "suspensao" }).origem).toBe(
      "Tribunais",
    );
    expect(mapAtividadeCursor({ ...base, tipo: "intimacao" }).origem).toBe(
      "DJEN",
    );
  });
});
