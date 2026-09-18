const DEFAULT_TIMEZONE = "America/Sao_Paulo";
const DEFAULT_OFFICE_NAME = "EJC DePaula Teixeira Adv";
const LEGACY_DEFAULT_OFFICE_NAME = "EJC — Ecossistema Jurídico Clóvis";
const DEFAULT_DAILY_MESSAGE =
  "Organização, clareza e responsabilidade em cada decisão.";
const DEFAULT_DAILY_SOURCE = "Mensagem institucional";
const DEFAULT_LOGO_PATH = "/brand/de-paula-teixeira-dt.png";
const LEGACY_DEFAULT_LOGO_PATH = "/brand/logo-hd.png";
const LEGACY_WORDMARK_LOGO_PATH = "/brand/ejc-wordmark.svg";

function readPublicEnv(value: string | undefined): string {
  return value?.trim() ?? "";
}

function normalizePhone(value: string): string {
  return value.replace(/\D/g, "");
}

function resolveOfficeName(value: string): string {
  if (!value || value === LEGACY_DEFAULT_OFFICE_NAME) return DEFAULT_OFFICE_NAME;
  return value;
}

function resolveLogoPath(value: string): string {
  // Defaults legados podem permanecer em ambientes instalados. Normalizá-los
  // aqui troca a marca visual sem exigir edição manual do .env e preserva
  // qualquer caminho realmente customizado informado pelo operador.
  if (
    !value ||
    value === LEGACY_DEFAULT_LOGO_PATH ||
    value === LEGACY_WORDMARK_LOGO_PATH
  ) {
    return DEFAULT_LOGO_PATH;
  }
  return value;
}

// Contatos externos são fail-closed: ausência/configuração vazia mantém os
// controles desabilitados. O endereço/número do escritório pertence ao ambiente
// de deploy, não ao bundle versionado.
const whatsappNumber = normalizePhone(
  readPublicEnv(import.meta.env.VITE_EJC_WHATSAPP_NUMBER),
);
const contactEmail = readPublicEnv(import.meta.env.VITE_EJC_CONTACT_EMAIL);
const configuredLogoPath = readPublicEnv(import.meta.env.VITE_EJC_LOGO_PATH);

export const officeBranding = Object.freeze({
  officeName: resolveOfficeName(
    readPublicEnv(import.meta.env.VITE_EJC_OFFICE_NAME),
  ),
  // Logomarca DT (monograma dourado "De Paula Teixeira Advocacia", PNG
  // transparente) — default desde 16/08/2026 (homologação m07). O .env
  // VITE_EJC_LOGO_PATH prevalece; o caminho legado logo-hd.png também é
  // resolvido como default para instalações antigas (resolveLogoPath).
  logoPath: resolveLogoPath(configuredLogoPath),
  whatsappNumber,
  contactEmail,
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
