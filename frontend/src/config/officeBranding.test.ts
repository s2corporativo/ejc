import { describe, expect, it } from "vitest";
import { getMailtoUrl, getWhatsAppUrl, officeBranding } from "./officeBranding";

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
