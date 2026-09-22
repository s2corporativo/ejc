import { describe, expect, it } from "vitest";
import {
  avisoOverlayCofre,
  capacidadesDoItem,
  groupIntegrationItems,
  type IntegrationItem,
} from "./IntegrationHealthPanel";

const items: IntegrationItem[] = [
  {
    key: "ai",
    label: "IA",
    group: "Inteligência",
    enabled: true,
    configured: true,
    status: "ready",
    detail: "ok",
  },
  {
    key: "email",
    label: "E-mail",
    group: "Comunicação",
    enabled: true,
    configured: false,
    status: "attention",
    detail: "incompleta",
  },
  {
    key: "push",
    label: "Push",
    group: "Comunicação",
    enabled: false,
    configured: false,
    status: "disabled",
    detail: "desabilitada",
  },
];

describe("IntegrationHealthPanel", () => {
  it("agrupa integrações sem perder a ordem", () => {
    const groups = groupIntegrationItems(items);

    expect(groups.map(([group]) => group)).toEqual([
      "Inteligência",
      "Comunicação",
    ]);
    expect(groups[1][1].map((item) => item.key)).toEqual(["email", "push"]);
  });
});

// Achado P2 (revisão de 04/09/2026): o backend passou a devolver
// `credential_overlay`, mas o painel não declarava nem renderizava o campo —
// com o overlay falho o administrador seguia vendo "Configurada" nas
// integrações afetadas, sem aviso nenhum, enquanto o processo usava o arquivo
// de ambiente (que não conhece revogação).
describe("avisoOverlayCofre", () => {
  it("não avisa quando o overlay está aplicado", () => {
    expect(
      avisoOverlayCofre({ status: "aplicado", aplicado: true, campos: 3 }),
    ).toBeNull();
  });

  it("não avisa quando o backend não envia o campo", () => {
    expect(avisoOverlayCofre(undefined)).toBeNull();
    expect(avisoOverlayCofre(null)).toBeNull();
  });

  it("avisa que o cofre não está aplicado, com o motivo e a revogação", () => {
    const aviso = avisoOverlayCofre({
      status: "falho",
      aplicado: false,
      erro_tipo: "TimeoutError",
      falhas: 3,
    });

    expect(aviso).toBeTruthy();
    expect(aviso).toContain("TimeoutError");
    expect(aviso).toContain("revogada");
    expect(aviso).toContain("3 tentativas");
  });

  it("avisa também quando o estado do overlay é ilegível", () => {
    const aviso = avisoOverlayCofre({
      status: "indisponivel",
      aplicado: false,
    });

    expect(aviso).toBeTruthy();
    expect(aviso).toContain("Cofre de Credenciais");
  });
});

describe("capacidadesDoItem", () => {
  it("lista as sete capacidades na ordem canônica, marcando as ativas", () => {
    const datajud: IntegrationItem = {
      ...items[0],
      key: "datajud",
      capacidades: {
        consultar_processo: true,
        sincronizar_movimentacoes: true,
        partes: true,
        audiencias: false,
        baixar_documentos: false,
        intimacoes: false,
        protocolar: false,
      },
    };
    const caps = capacidadesDoItem(datajud);
    expect(caps.map((c) => c.chave)).toEqual([
      "consultar_processo",
      "sincronizar_movimentacoes",
      "partes",
      "audiencias",
      "baixar_documentos",
      "intimacoes",
      "protocolar",
    ]);
    expect(caps.filter((c) => c.ativa).map((c) => c.chave)).toEqual([
      "consultar_processo",
      "sincronizar_movimentacoes",
      "partes",
    ]);
    expect(caps.find((c) => c.chave === "protocolar")?.ativa).toBe(false);
  });

  it("item sem capacidades (não é conector judicial) não gera chips", () => {
    expect(capacidadesDoItem(items[1])).toEqual([]);
  });
});
