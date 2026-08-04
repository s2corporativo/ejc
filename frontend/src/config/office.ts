type PublicEnv = Record<string, string | undefined>;

const env =
  (import.meta as unknown as { env?: PublicEnv }).env ?? ({} as PublicEnv);

function clean(value?: string) {
  return value?.trim() || "";
}

function whatsappUrl(number: string) {
  const digits = number.replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : "";
}

export const OFFICE_CONFIG = Object.freeze({
  name: clean(env.VITE_EJC_OFFICE_NAME) || "De Paula Teixeira",
  timezone: clean(env.VITE_EJC_TIMEZONE) || "America/Sao_Paulo",
  contactEmail: clean(env.VITE_EJC_CONTACT_EMAIL),
  whatsappNumber: clean(env.VITE_EJC_WHATSAPP_NUMBER),
  officeAiUrl:
    clean(env.VITE_EJC_OFFICE_AI_URL) || "https://claude.ai/",
});

export const OFFICE_LINKS = Object.freeze({
  whatsapp: whatsappUrl(OFFICE_CONFIG.whatsappNumber),
  email: OFFICE_CONFIG.contactEmail
    ? `mailto:${OFFICE_CONFIG.contactEmail}`
    : "",
  officeAi: OFFICE_CONFIG.officeAiUrl,
});
