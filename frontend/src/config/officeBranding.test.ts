import { describe, expect, it } from "vitest";
import {
  getMailtoUrl,
  getWhatsAppUrl,
  officeBranding,
  resolveLogoPath,
  resolveOfficeName,
} from "./officeBranding";

describe("officeBranding", () => {
  it("não expõe configuração sem consumidor", () => {
    // `officeAiUrl`/`officeAiLabel` (VITE_EJC_OFFICE_AI_URL/_LABEL) eram lidos
    // do .env e nunca usados em src/. Removidos; este teste impede que voltem
    // sem uma tela que os consuma.
    expect(Object.keys(officeBranding).sort()).toEqual([
      "contactEmail",
      "dailyMessage",
      "dailyMessageSource",
      "logoPath",
      "officeName",
      "timezone",
      "whatsappNumber",
    ]);
  });

  it("normaliza nome institucional legado e preserva customização válida", () => {
    expect(resolveOfficeName("")).toBe("EJC DePaula Teixeira Adv");
    expect(resolveOfficeName("EJC — Ecossistema Jurídico Clóvis")).toBe(
      "EJC DePaula Teixeira Adv",
    );
    expect(resolveOfficeName("Minha Marca Jurídica")).toBe("Minha Marca Jurídica");
  });

  it("normaliza logos legados e preserva caminho customizado", () => {
    expect(resolveLogoPath("")).toBe("/brand/de-paula-teixeira-dt.png");
    expect(resolveLogoPath("/brand/logo-hd.png")).toBe(
      "/brand/de-paula-teixeira-dt.png",
    );
    expect(resolveLogoPath("/brand/ejc-wordmark.svg")).toBe(
      "/brand/de-paula-teixeira-dt.png",
    );
    expect(resolveLogoPath("/brand/custom-logo.svg")).toBe(
      "/brand/custom-logo.svg",
    );
  });

  it("só monta link de contato quando há dado configurado", () => {
    expect(officeBranding.whatsappNumber ? getWhatsAppUrl() : "").toBe(
      officeBranding.whatsappNumber
        ? `https://wa.me/${officeBranding.whatsappNumber}`
        : "",
    );
    expect(officeBranding.contactEmail ? getMailtoUrl() : "").toBe(
      officeBranding.contactEmail
        ? `mailto:${encodeURIComponent(officeBranding.contactEmail)}`
        : "",
    );
  });
});
