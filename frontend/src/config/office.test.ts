import { afterEach, describe, expect, it, vi } from "vitest";

/** Reimporta o módulo para reavaliar as constantes com o env stubado. */
async function importOffice() {
  vi.resetModules();
  return await import("./office");
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("config/office", () => {
  it("sem variáveis: WhatsApp/e-mail indefinidos (botões somem) e IA usa o padrão", async () => {
    vi.stubEnv("VITE_EJC_WHATSAPP_NUMBER", "");
    vi.stubEnv("VITE_EJC_CONTACT_EMAIL", "");
    vi.stubEnv("VITE_EJC_OFFICE_AI_URL", "");
    const office = await importOffice();
    expect(office.whatsappHref).toBeUndefined();
    expect(office.emailHref).toBeUndefined();
    expect(office.EJC_OFFICE_AI_URL).toBe("https://claude.ai");
    expect(office.EJC_TIMEZONE).toBe("America/Sao_Paulo");
  });

  it("número com máscara vira link wa.me só com dígitos", async () => {
    vi.stubEnv("VITE_EJC_WHATSAPP_NUMBER", "+55 (31) 99999-9999");
    const office = await importOffice();
    expect(office.whatsappHref).toBe("https://wa.me/5531999999999");
  });

  it("e-mail configurado gera mailto e fuso configurado é respeitado", async () => {
    vi.stubEnv("VITE_EJC_CONTACT_EMAIL", "contato@exemplo.adv.br");
    vi.stubEnv("VITE_EJC_TIMEZONE", "America/Manaus");
    const office = await importOffice();
    expect(office.emailHref).toBe("mailto:contato@exemplo.adv.br");
    expect(office.EJC_TIMEZONE).toBe("America/Manaus");
  });

  it("URL da IA configurada substitui o padrão", async () => {
    vi.stubEnv("VITE_EJC_OFFICE_AI_URL", "https://ia.interna.exemplo/");
    const office = await importOffice();
    expect(office.EJC_OFFICE_AI_URL).toBe("https://ia.interna.exemplo/");
  });
});
