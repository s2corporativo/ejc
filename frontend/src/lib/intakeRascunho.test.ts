import { describe, it, expect, beforeEach } from "vitest";
import {
  RASCUNHO_KEY,
  snapshotForm,
  salvarRascunho,
  carregarRascunho,
  atualizarRascunho,
  limparRascunho,
} from "./intakeRascunho";

describe("intakeRascunho", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe("snapshotForm", () => {
    it("remove chaves auxiliares '_' (File/extração) e valores nulos", () => {
      const file = new File(["x"], "peticao.pdf", { type: "application/pdf" });
      const snap = snapshotForm({
        titulo: "Ação de cobrança",
        area: "civil",
        valor_causa: "",
        numero_processo: undefined,
        _arquivo_original: file,
        _extracao: { partes: { autor: "Fulano" } },
        _cliente_candidato: { nome: "Fulano" },
      });
      expect(snap).toEqual({
        titulo: "Ação de cobrança",
        area: "civil",
        valor_causa: "",
      });
      expect(snap._arquivo_original).toBeUndefined();
      expect(snap._extracao).toBeUndefined();
    });

    it("não estoura com form vazio ou sem chaves", () => {
      expect(snapshotForm({})).toEqual({});
    });
  });

  describe("salvar / recuperar", () => {
    it("faz roundtrip preservando campos e carimba salvoEm", () => {
      const antes = Date.now();
      salvarRascunho({
        form: { titulo: "Ação X", area: "civil" },
        extracao: { partes: { autor: "Fulano" } },
        arquivoNome: "peticao.pdf",
        arquivoTipo: "peticao",
        tituloDoc: "Ação X",
        clientId: null,
        caseId: null,
        uploadFeito: false,
      });
      const lido = carregarRascunho();
      expect(lido).not.toBeNull();
      expect(lido!.form).toEqual({ titulo: "Ação X", area: "civil" });
      expect(lido!.extracao).toEqual({ partes: { autor: "Fulano" } });
      expect(lido!.arquivoNome).toBe("peticao.pdf");
      expect(lido!.caseId).toBeNull();
      expect(lido!.uploadFeito).toBe(false);
      expect(typeof lido!.salvoEm).toBe("number");
      expect(lido!.salvoEm).toBeGreaterThanOrEqual(antes);
    });

    it("grava sob a chave documentada", () => {
      salvarRascunho({ form: { titulo: "Y" } });
      expect(localStorage.getItem(RASCUNHO_KEY)).toContain('"titulo":"Y"');
    });

    it("retorna null quando não há rascunho", () => {
      expect(carregarRascunho()).toBeNull();
    });

    it("retorna null para conteúdo malformado", () => {
      localStorage.setItem(RASCUNHO_KEY, "{isto não é json");
      expect(carregarRascunho()).toBeNull();
      localStorage.setItem(RASCUNHO_KEY, JSON.stringify({ semForm: true }));
      expect(carregarRascunho()).toBeNull();
    });
  });

  describe("atualizarRascunho (avanço passo a passo)", () => {
    it("mescla caseId sem perder o restante (falha pós-criação → não recria)", () => {
      salvarRascunho({
        form: { titulo: "Ação X" },
        extracao: { partes: { autor: "Fulano" } },
        caseId: null,
        uploadFeito: false,
      });
      const depois = atualizarRascunho({ caseId: "caso-123" });
      expect(depois).not.toBeNull();
      expect(depois!.caseId).toBe("caso-123");
      // preserva os demais campos do rascunho original
      expect(depois!.form).toEqual({ titulo: "Ação X" });
      expect(depois!.extracao).toEqual({ partes: { autor: "Fulano" } });
      // persistido de fato
      expect(carregarRascunho()!.caseId).toBe("caso-123");
    });

    it("marca uploadFeito para que o retry pule o anexo já concluído", () => {
      salvarRascunho({ form: { titulo: "Z" }, caseId: "c1", uploadFeito: false });
      atualizarRascunho({ uploadFeito: true });
      expect(carregarRascunho()!.uploadFeito).toBe(true);
    });

    it("não cria rascunho do nada quando não existe base", () => {
      expect(atualizarRascunho({ caseId: "c9" })).toBeNull();
      expect(carregarRascunho()).toBeNull();
    });
  });

  describe("limparRascunho (sucesso total)", () => {
    it("remove o rascunho persistido", () => {
      salvarRascunho({ form: { titulo: "A" }, caseId: "c1" });
      expect(carregarRascunho()).not.toBeNull();
      limparRascunho();
      expect(carregarRascunho()).toBeNull();
      expect(localStorage.getItem(RASCUNHO_KEY)).toBeNull();
    });
  });
});
