const DEFAULT_TIMEZONE = "America/Sao_Paulo";
const DEFAULT_OFFICE_NAME = "EJC — Ecossistema Jurídico Clóvis";
const DEFAULT_DAILY_MESSAGE =
  "Organização, clareza e responsabilidade em cada decisão.";
const DEFAULT_DAILY_SOURCE = "Mensagem institucional";

function readPublicEnv(value: string | undefined): string {
  return value?.trim() ?? "";
}

function normalizePhone(value: string): string {
  return value.replace(/\D/g, "");
}

function normalizeHttpUrl(value: string): string {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    const isHttp = parsed.protocol === "https:" || parsed.protocol === "http:";
    const hasEmbeddedCredentials = Boolean(parsed.username || parsed.password);
    return isHttp && !hasEmbeddedCredentials ? parsed.toString() : "";
  } catch {
    return "";
  }
}

const whatsappNumber = normalizePhone(
  readPublicEnv(import.meta.env.VITE_EJC_WHATSAPP_NUMBER),
);
const contactEmail = readPublicEnv(import.meta.env.VITE_EJC_CONTACT_EMAIL);
const officeAiUrl = normalizeHttpUrl(
  readPublicEnv(import.meta.env.VITE_EJC_OFFICE_AI_URL),
);

export const officeBranding = Object.freeze({
  officeName:
    readPublicEnv(import.meta.env.VITE_EJC_OFFICE_NAME) || DEFAULT_OFFICE_NAME,
  logoPath:
    readPublicEnv(import.meta.env.VITE_EJC_LOGO_PATH) ||
    "/brand/ejc-wordmark.svg",
  whatsappNumber,
  contactEmail,
  officeAiUrl,
  officeAiLabel:
    readPublicEnv(import.meta.env.VITE_EJC_OFFICE_AI_LABEL) || "Claude",
  timezone:
    readPublicEnv(import.meta.env.VITE_EJC_TIMEZONE) || DEFAULT_TIMEZONE,
  dailyMessage:
    readPublicEnv(import.meta.env.VITE_EJC_DAILY_MESSAGE) ||
    DEFAULT_DAILY_MESSAGE,
  dailyMessageSource:
    readPublicEnv(import.meta.env.VITE_EJC_DAILY_MESSAGE_SOURCE) ||
    DEFAULT_DAILY_SOURCE,
});

export function getWhatsAppUrl(): string {
  return officeBranding.whatsappNumber
    ? `https://wa.me/${officeBranding.whatsappNumber}`
    : "";
}

export function getMailtoUrl(): string {
  return officeBranding.contactEmail
    ? `mailto:${encodeURIComponent(officeBranding.contactEmail)}`
    : "";
}
