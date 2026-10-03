// Regressão do bug de logout (auditoria Onda B): o caminho REAL do botão
// "Sair" é api.logout() (SecurityMenu/TrocarSenha/Configurar2FA) — e ele
// limpava apenas o rascunho de intake, deixando sobreviver à sessão:
//  - o rascunho da Entrada Única (sessionStorage, mesma aba — PII do relato);
//  - a fila offline + rascunhos do cadastro manual (localStorage — PII).
// auth.clearSession fazia a limpeza completa, mas NENHUMA tela o chamava.
// Com o contrato único (lib/rascunho/contrato.ts + registro.ts), ambos os
// caminhos chamam limparTodosRascunhos() e este teste trava a garantia.
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { logout } from "./api";
import { RASCUNHO_ENTRADA_PREFIXO, RASCUNHO_INTAKE_KEY } from "./rascunho/contrato";
import { limparTodosRascunhos } from "./rascunho/registro";
import {
  salvarRascunho as salvarIntake,
  carregarRascunho as carregarIntake,
} from "./intakeRascunho";
import { useCadastroManualStore } from "../stores/cadastroManual";

function semearRascunhos() {
  // Intake documental (localStorage, TTL 48h).
  salvarIntake({
    form: { titulo: "Caso com PII" },
    extracao: null,
    salvoEm: undefined,
  } as never);
  // Entrada Única (sessionStorage — ponteiro + dados + órfã).
  sessionStorage.setItem(`${RASCUNHO_ENTRADA_PREFIXO}_atual`, "r1");
  sessionStorage.setItem(
    `${RASCUNHO_ENTRADA_PREFIXO}:r1`,
    JSON.stringify({ rascunhoId: "r1", dados: "relato com PII" }),
  );
  // Cadastro manual (zustand persist em localStorage + estado em memória).
  useCadastroManualStore.setState({
    rascunhoCliente: { nome: "Cliente PII" },
    fila: [
      {
        id: "i1",
        tipo: "cliente",
        payload: { nome: "Cliente PII" },
        criado_em: new Date().toISOString(),
        status: "pendente",
        usuarioId: "u1",
      },
    ],
    usuarioId: "u1",
  });
}

function rascunhosVisiveis(): boolean {
  const intake = localStorage.getItem(RASCUNHO_INTAKE_KEY) !== null;
  let entrada = false;
  for (let i = sessionStorage.length - 1; i >= 0; i--) {
    const chave = sessionStorage.key(i);
    if (chave?.startsWith(RASCUNHO_ENTRADA_PREFIXO)) entrada = true;
  }
  const manual = useCadastroManualStore.getState().fila.length > 0;
  return intake || entrada || manual;
}

describe("logout — nenhum rascunho sobrevive à sessão (LGPD)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    limparTodosRascunhos();
  });

  it("api.logout limpa intake, Entrada Única e cadastro manual", () => {
    vi.spyOn(axios, "post").mockResolvedValue({} as never);
    semearRascunhos();
    expect(rascunhosVisiveis()).toBe(true);

    logout(); // jsdom registra "Not implemented: navigation" — não lança.

    expect(rascunhosVisiveis()).toBe(false);
    expect(carregarIntake()).toBeNull();
    expect(useCadastroManualStore.getState().usuarioId).toBeNull();
  });
});
