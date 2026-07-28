import { describe, it, expect } from "vitest";
import {
  montarPayloadProtocolo,
  temProtocoloRegistrado,
  mensagemErroProtocolo,
  dataLocalISO,
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
  describe("dataLocalISO (max do input de data — tempestividade)", () => {
    it("usa o dia LOCAL, não o dia UTC", () => {
      // 2026-03-10 22:30 local: em fuso positivo o UTC ainda seria 03-10, mas
      // em fuso negativo o UTC já seria 03-11 — o max precisa seguir o local.
      const d = new Date(2026, 2, 10, 22, 30, 0);
      expect(dataLocalISO(d)).toBe("2026-03-10");
    });
    it("madrugada local não retrocede para o dia anterior", () => {
      const d = new Date(2026, 0, 1, 0, 15, 0);
      expect(dataLocalISO(d)).toBe("2026-01-01");
    });
    it("zera à esquerda mês e dia", () => {
      expect(dataLocalISO(new Date(2026, 8, 7, 12, 0, 0))).toBe("2026-09-07");
    });
    it('sem argumento usa o "hoje" local do usuário', () => {
      const hoje = new Date();
      expect(dataLocalISO()).toBe(dataLocalISO(hoje));
      expect(dataLocalISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });
  });
});
