/**
 * Parâmetros institucionais do escritório — fonte ÚNICA para os atalhos de
 * contato e integrações do cabeçalho (WhatsApp, e-mail, IA do Escritório,
 * fuso horário). Nada de telefone/e-mail/URL hardcoded espalhado por
 * componente: quem precisar desses dados importa daqui.
 *
 * Os valores vêm de variáveis Vite públicas (prefixo VITE_ — entram no
 * bundle servido ao navegador). Por isso, AQUI SÓ ENTRA DADO PÚBLICO:
 * nunca credencial, token ou URL com segredo embutido.
 *
 * Documentação das variáveis: frontend/.env.example.
 */

function env(name: string): string | undefined {
  const value = (import.meta.env as Record<string, string | undefined>)[name];
  const trimmed = typeof value === "string" ? value.trim() : "";
  return trimmed ? trimmed : undefined;
}

/** Fuso horário usado por hora/data do cabeçalho e pelo calendário. */
export const EJC_TIMEZONE = env("VITE_EJC_TIMEZONE") || "America/Sao_Paulo";

/**
 * Telefone do WhatsApp institucional, apenas dígitos com DDI (ex.:
 * 5531999999999). Sem a variável configurada o botão NÃO aparece —
 * preferível a apontar para um número inventado.
 */
export const EJC_WHATSAPP_NUMBER = env("VITE_EJC_WHATSAPP_NUMBER")?.replace(
  /\D/g,
  "",
);

/** E-mail de contato institucional. Sem a variável, o botão não aparece. */
export const EJC_CONTACT_EMAIL = env("VITE_EJC_CONTACT_EMAIL");

/**
 * URL do ambiente de IA usado pelo escritório (botão "IA do Escritório").
 * Configurável por ambiente; o padrão abre o Claude. A URL é aberta em
 * nova aba — jamais embuta login/senha nela.
 */
export const EJC_OFFICE_AI_URL =
  env("VITE_EJC_OFFICE_AI_URL") || "https://claude.ai";

/** Link wa.me pronto, ou undefined quando o número não está configurado. */
export const whatsappHref = EJC_WHATSAPP_NUMBER
  ? `https://wa.me/${EJC_WHATSAPP_NUMBER}`
  : undefined;

/** Link mailto pronto, ou undefined quando o e-mail não está configurado. */
export const emailHref = EJC_CONTACT_EMAIL
  ? `mailto:${EJC_CONTACT_EMAIL}`
  : undefined;
