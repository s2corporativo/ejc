import { beforeEach, describe, expect, it } from "vitest";
import {
  limparTodosRascunhos,
  registrarLimpezaRascunho,
  RASCUNHO_CADASTRO_MANUAL_KEY,
  RASCUNHO_ENTRADA_PREFIXO,
  RASCUNHO_INTAKE_KEY,
  storageLocal,
  storageSessao,
} from "./contrato";
// Importa o registro eager: garante que as limpezas dos três rascunhos
// (intake, Entrada Única via varredura de prefixo, cadastro manual) estejam
// registradas — exatamente como os caminhos de logout reais consomem.
import { limparTodosRascunhos as limparViaRegistro } from "./registro";
import {
  salvarRascunho as salvarIntake,
  carregarRascunho as carregarIntake,
} from "../intakeRascunho";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  // NÃO esvazia o registro: os auto-registros dos módulos reais rodaram uma
  // única vez na carga (efeito colateral de import) e são justamente o que
  // os testes do "registro eager" provam. Os testes de mecânica usam funções
  // próprias e não dependem do estado prévio do registro.
});

describe("contrato único de rascunho — chaves", () => {
  it("mantém as chaves históricas (migração nula de storage)", () => {
    expect(RASCUNHO_INTAKE_KEY).toBe("ejc_intake_rascunho");
    expect(RASCUNHO_ENTRADA_PREFIXO).toBe("ejc_entrada_rascunho");
    expect(RASCUNHO_CADASTRO_MANUAL_KEY).toBe("ejc_cadastro_manual");
  });
});

describe("registro de limpeza", () => {
  it("limparTodosRascunhos executa todas as limpezas registradas", () => {
    localStorage.setItem("a_rascunho_1", "x");
    sessionStorage.setItem("b_rascunho_1", "y");
    let chamadas = 0;
    registrarLimpezaRascunho(() => {
      localStorage.removeItem("a_rascunho_1");
      chamadas++;
    });
    registrarLimpezaRascunho(() => {
      sessionStorage.removeItem("b_rascunho_1");
      chamadas++;
    });
    limparTodosRascunhos();
    expect(chamadas).toBe(2);
    expect(localStorage.getItem("a_rascunho_1")).toBeNull();
    expect(sessionStorage.getItem("b_rascunho_1")).toBeNull();
  });

  it("falha de um storage não impede os demais (tolerância do logout)", () => {
    const s = storageLocal();
    expect(s).not.toBeNull();
    registrarLimpezaRascunho(() => {
      throw new Error("storage estourou");
    });
    let limpou = false;
    registrarLimpezaRascunho(() => {
      limpou = true;
    });
    expect(() => limparTodosRascunhos()).not.toThrow();
    expect(limpou).toBe(true);
  });

  it("registro duplicado é inofensivo (dedupe por identidade)", () => {
    let chamadas = 0;
    const fn = () => {
      chamadas++;
    };
    registrarLimpezaRascunho(fn);
    registrarLimpezaRascunho(fn);
    limparTodosRascunhos();
    expect(chamadas).toBe(1);
  });
});

describe("registro eager (registro.ts) — os três rascunhos reais", () => {
  it("limpa intake documental (localStorage) via contrato", () => {
    salvarIntake({
      form: { titulo: "Caso de teste" },
      extracao: null,
      salvoEm: undefined,
    } as never);
    expect(carregarIntake()).not.toBeNull();
    // O registro eager (importado acima) garantiu o auto-registro do módulo
    // de intake na carga — mesmo sem nenhuma página de casos ter montado.
    limparViaRegistro();
    expect(carregarIntake()).toBeNull();
    expect(storageLocal()!.getItem(RASCUNHO_INTAKE_KEY)).toBeNull();
  });

  it("limpa rascunho da Entrada Única (sessionStorage) incluindo órfãs", () => {
    const s = storageSessao()!;
    s.setItem(`${RASCUNHO_ENTRADA_PREFIXO}_atual`, "r1");
    s.setItem(`${RASCUNHO_ENTRADA_PREFIXO}:r1`, JSON.stringify({ rascunhoId: "r1" }));
    s.setItem(`${RASCUNHO_ENTRADA_PREFIXO}:orfã`, "resto de sessão antiga");
    limparViaRegistro();
    expect(s.getItem(`${RASCUNHO_ENTRADA_PREFIXO}_atual`)).toBeNull();
    expect(s.getItem(`${RASCUNHO_ENTRADA_PREFIXO}:r1`)).toBeNull();
    expect(s.getItem(`${RASCUNHO_ENTRADA_PREFIXO}:orfã`)).toBeNull();
  });

  it("limpa a fila do cadastro manual (localStorage) via contrato", () => {
    const s = storageLocal()!;
    s.setItem(
      RASCUNHO_CADASTRO_MANUAL_KEY,
      JSON.stringify({
        state: {
          rascunhoCliente: { nome: "Cliente PII" },
          rascunhoCaso: {},
          fila: [{ id: "i1", tipo: "cliente", payload: { nome: "Cliente PII" }, criado_em: new Date().toISOString(), status: "pendente" }],
          clientesCache: [],
          usuarioId: "u1",
        },
        version: 2,
      }),
    );
    limparViaRegistro();
    expect(s.getItem(RASCUNHO_CADASTRO_MANUAL_KEY)).toBeNull();
  });
});
