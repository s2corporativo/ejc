import { afterEach, describe, expect, it } from "vitest";
import {
  filtrarTabsW3,
  isDataRoomTabEnabled,
  setDataRoomTabEnabled,
} from "./w3Tabs";

describe("w3Tabs — flag da aba Data Room do caso (Onda 3)", () => {
  afterEach(() => {
    try {
      window.localStorage.removeItem("ejc_w3_dataroom");
    } catch {
      // jsdom sempre tem storage — guard apenas por segurança
    }
  });

  it("default ATIVO: sem override, a aba Data Room aparece", () => {
    expect(isDataRoomTabEnabled()).toBe(true);
    expect(filtrarTabsW3(["documentos", "dataroom", "pecas"])).toEqual([
      "documentos",
      "dataroom",
      "pecas",
    ]);
  });

  it("rollback por perfil: localStorage.ejc_w3_dataroom=false esconde a aba sem deploy", () => {
    setDataRoomTabEnabled(false);
    expect(isDataRoomTabEnabled()).toBe(false);
    expect(filtrarTabsW3(["documentos", "dataroom", "pecas"])).toEqual([
      "documentos",
      "pecas",
    ]);
  });

  it("override ON reativa a aba", () => {
    setDataRoomTabEnabled(false);
    setDataRoomTabEnabled(true);
    expect(isDataRoomTabEnabled()).toBe(true);
    expect(filtrarTabsW3(["dataroom"])).toEqual(["dataroom"]);
  });

  it("abas sem flag passam sempre (seletor é aditivo e neutro)", () => {
    expect(filtrarTabsW3([])).toEqual([]);
    expect(filtrarTabsW3(["resumo", "prazos", "financeiro"])).toEqual([
      "resumo",
      "prazos",
      "financeiro",
    ]);
  });
});
