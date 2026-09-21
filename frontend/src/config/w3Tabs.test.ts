import { afterEach, describe, expect, it } from "vitest";
import {
  filtrarTabsW3,
  isDataRoomTabEnabled,
  isIntimacoesTabEnabled,
  isTarefasTabEnabled,
  setDataRoomTabEnabled,
  setIntimacoesTabEnabled,
  setTarefasTabEnabled,
} from "./w3Tabs";

describe("w3Tabs — flag da aba Data Room do caso (Onda 3)", () => {
  afterEach(() => {
    try {
      window.localStorage.removeItem("ejc_w3_dataroom");
      window.localStorage.removeItem("ejc_w4_tarefas");
      window.localStorage.removeItem("ejc_w4_intimacoes");
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

describe("w3Tabs — flags das abas Tarefas e Intimações do caso (Onda 4)", () => {
  afterEach(() => {
    try {
      window.localStorage.removeItem("ejc_w4_tarefas");
      window.localStorage.removeItem("ejc_w4_intimacoes");
    } catch {
      // jsdom sempre tem storage — guard apenas por segurança
    }
  });

  it("default ATIVO: Tarefas e Intimações aparecem no workspace do caso", () => {
    expect(isTarefasTabEnabled()).toBe(true);
    expect(isIntimacoesTabEnabled()).toBe(true);
    expect(
      filtrarTabsW3(["prazos", "audiencias", "tarefas", "intimacoes"]),
    ).toEqual(["prazos", "audiencias", "tarefas", "intimacoes"]);
  });

  it("rollback por perfil: ejc_w4_tarefas=false esconde só Tarefas", () => {
    setTarefasTabEnabled(false);
    expect(isTarefasTabEnabled()).toBe(false);
    expect(isIntimacoesTabEnabled()).toBe(true);
    expect(
      filtrarTabsW3(["prazos", "tarefas", "intimacoes", "checklists"]),
    ).toEqual(["prazos", "intimacoes", "checklists"]);
  });

  it("rollback por perfil: ejc_w4_intimacoes=false esconde só Intimações", () => {
    setIntimacoesTabEnabled(false);
    expect(isIntimacoesTabEnabled()).toBe(false);
    expect(isTarefasTabEnabled()).toBe(true);
    expect(
      filtrarTabsW3(["prazos", "tarefas", "intimacoes", "checklists"]),
    ).toEqual(["prazos", "tarefas", "checklists"]);
  });

  it("override ON reativa as abas", () => {
    setTarefasTabEnabled(false);
    setIntimacoesTabEnabled(false);
    setTarefasTabEnabled(true);
    setIntimacoesTabEnabled(true);
    expect(isTarefasTabEnabled()).toBe(true);
    expect(isIntimacoesTabEnabled()).toBe(true);
    expect(filtrarTabsW3(["tarefas", "intimacoes"])).toEqual([
      "tarefas",
      "intimacoes",
    ]);
  });

  it("as duas flags compartilham a env global VITE_EJC_W4_TABS, mas são independentes por perfil", () => {
    setTarefasTabEnabled(false);
    // env default é "on" em teste — cada aba controla apenas a própria chave
    expect(isIntimacoesTabEnabled()).toBe(true);
    expect(isTarefasTabEnabled()).toBe(false);
  });
});
