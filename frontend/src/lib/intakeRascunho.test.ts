import { describe, it, expect, beforeEach } from "vitest";
import {
  RASCUNHO_KEY,
  RASCUNHO_TTL_MS,
  snapshotForm,
  salvarRascunho,
  carregarRascunho,
  atualizarRascunho,
  limparRascunho,
  pendenciaDeRascunho,
} from "./intakeRascunho";

/** Reescreve o `salvoEm` do rascunho persistido (simula passagem de tempo). */
function envelhecerRascunho(salvoEm: number) {
  const raw = JSON.parse(localStorage.getItem(RASCUNHO_KEY)!);
  raw.salvoEm = salvoEm;
  localStorage.setItem(RASCUNHO_KEY, JSON.stringify(raw));
}

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
      salvarRascunho({
        form: { titulo: "Z" },
        caseId: "c1",
        uploadFeito: false,
      });
      atualizarRascunho({ uploadFeito: true });
      expect(carregarRascunho()!.uploadFeito).toBe(true);
    });

    it("não cria rascunho do nada quando não existe base", () => {
      expect(atualizarRascunho({ caseId: "c9" })).toBeNull();
      expect(carregarRascunho()).toBeNull();
    });
  });

  describe("TTL de 48h (LGPD — dados pessoais não residem indefinidamente)", () => {
    it("rascunho dentro do TTL continua recuperável", () => {
      salvarRascunho({ form: { titulo: "X" }, caseId: "c1" });
      envelhecerRascunho(Date.now() - (RASCUNHO_TTL_MS - 60_000));
      expect(carregarRascunho()).not.toBeNull();
    });

    it("rascunho mais velho que 48h é descartado E a chave é limpa", () => {
      salvarRascunho({ form: { titulo: "X" }, caseId: "c1" });
      envelhecerRascunho(Date.now() - RASCUNHO_TTL_MS - 1);
      expect(carregarRascunho()).toBeNull();
      expect(localStorage.getItem(RASCUNHO_KEY)).toBeNull();
    });

    it("rascunho legado sem batchId carrega com batchId null (compat)", () => {
      salvarRascunho({ form: { titulo: "X" }, caseId: "c1" });
      const raw = JSON.parse(localStorage.getItem(RASCUNHO_KEY)!);
      delete raw.batchId;
      localStorage.setItem(RASCUNHO_KEY, JSON.stringify(raw));
      expect(carregarRascunho()!.batchId).toBeNull();
    });

    it("rascunho de lote (sem File) faz roundtrip com batchId", () => {
      salvarRascunho({
        form: { titulo: "Lote" },
        extracao: { batch_id: "b1" } as any,
        arquivoNome: null,
        batchId: "b1",
        caseId: "c9",
      });
      const lido = carregarRascunho()!;
      expect(lido.batchId).toBe("b1");
      expect(lido.arquivoNome).toBeNull();
      expect(lido.caseId).toBe("c9");
    });
  });

  describe("pendenciaDeRascunho (retomar × recriar)", () => {
    it("com caseId e lote: retoma o caso existente (nunca recria)", () => {
      salvarRascunho({
        form: { titulo: "Lote da Silva" },
        batchId: "b1",
        caseId: "c1",
        clientId: "cli-1",
        uploadFeito: false,
      });
      const p = pendenciaDeRascunho(carregarRascunho());
      expect(p).toEqual({
        caseId: "c1",
        caseTitulo: "Lote da Silva",
        tituloDoc: "Lote da Silva",
        tipoDoc: undefined,
        clientId: "cli-1",
        batchId: "b1",
      });
    });

    it("com caseId e arquivo único: retoma sem o File (perdido no reload)", () => {
      salvarRascunho({
        form: { titulo: "Ação X" },
        arquivoNome: "peticao.pdf",
        arquivoTipo: "peticao",
        tituloDoc: "Ação X",
        caseId: "c2",
        uploadFeito: false,
      });
      const p = pendenciaDeRascunho(carregarRascunho())!;
      expect(p.caseId).toBe("c2");
      expect(p.batchId).toBeUndefined();
      expect(p.arquivo).toBeUndefined();
      expect(p.tipoDoc).toBe("peticao");
    });

    it("sem caseId (caso ainda não criado) não vira pendência — cria normalmente", () => {
      salvarRascunho({
        form: { titulo: "Ação Y" },
        batchId: "b2",
        caseId: null,
      });
      expect(pendenciaDeRascunho(carregarRascunho())).toBeNull();
    });

    it("com uploadFeito (vínculo concluído) não vira pendência", () => {
      salvarRascunho({
        form: { titulo: "Ação Z" },
        batchId: "b3",
        caseId: "c3",
        uploadFeito: true,
      });
      expect(pendenciaDeRascunho(carregarRascunho())).toBeNull();
    });

    it("sem documento a vincular (só extração) fica com o fluxo de ?revisao=", () => {
      salvarRascunho({
        form: { titulo: "Ação W" },
        extracao: { partes: { autor: "Fulano" } },
        caseId: "c4",
        uploadFeito: false,
      });
      expect(pendenciaDeRascunho(carregarRascunho())).toBeNull();
    });

    it("tolera rascunho ausente", () => {
      expect(pendenciaDeRascunho(null)).toBeNull();
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
