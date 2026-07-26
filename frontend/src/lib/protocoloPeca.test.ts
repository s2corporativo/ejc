import { describe, it, expect } from "vitest";
import {
  montarPayloadProtocolo,
  temProtocoloRegistrado,
  mensagemErroProtocolo,
} from "./protocoloPeca";

describe("protocoloPeca — FLX-070", () => {
  describe("montarPayloadProtocolo", () => {
    it("número vazio ou só espaços → null (obrigatório)", () => {
      expect(
        montarPayloadProtocolo({ numero: "", tribunal: "", data: "" }),
      ).toBeNull();
      expect(
        montarPayloadProtocolo({ numero: "   ", tribunal: "TJMG", data: "" }),
      ).toBeNull();
    });

    it("só o número → payload mínimo, sem campos opcionais vazios", () => {
      expect(
        montarPayloadProtocolo({
          numero: " 2026.01.99 ",
          tribunal: "",
          data: "",
        }),
      ).toEqual({ numero_protocolo: "2026.01.99" });
    });

    it("tribunal e data preenchidos entram aparados no payload", () => {
      expect(
        montarPayloadProtocolo({
          numero: "123",
          tribunal: " TJMG — PJe ",
          data: "2026-07-20",
        }),
      ).toEqual({
        numero_protocolo: "123",
        protocolo_tribunal: "TJMG — PJe",
        protocolado_em: "2026-07-20",
      });
    });
  });

  describe("temProtocoloRegistrado (pular o modal)", () => {
    it("true quando numero_protocolo é não vazio", () => {
      expect(temProtocoloRegistrado({ numero_protocolo: "abc" })).toBe(true);
    });
    it("false para ausente, null ou vazio", () => {
      expect(temProtocoloRegistrado({})).toBe(false);
      expect(temProtocoloRegistrado({ numero_protocolo: null })).toBe(false);
      expect(temProtocoloRegistrado({ numero_protocolo: "  " })).toBe(false);
    });
  });

  describe("mensagemErroProtocolo", () => {
    it("403 → mensagem fixa de restrição a advogados", () => {
      expect(mensagemErroProtocolo(403, "qualquer detail")).toBe(
        "Apenas advogados podem registrar protocolo",
      );
    });
    it("422 com detail string → repassa o detalhe do backend", () => {
      expect(
        mensagemErroProtocolo(422, "Número de protocolo é obrigatório"),
      ).toBe("Número de protocolo é obrigatório");
    });
    it("detail objeto {mensagem} → usa a mensagem", () => {
      expect(
        mensagemErroProtocolo(422, { mensagem: "peça não aprovada" }),
      ).toBe("peça não aprovada");
    });
    it("sem detail → fallback", () => {
      expect(mensagemErroProtocolo(500, undefined)).toBe(
        "Falha ao registrar o protocolo",
      );
      expect(mensagemErroProtocolo(undefined, null, "custom")).toBe("custom");
    });
  });
});
