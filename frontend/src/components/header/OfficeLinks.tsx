import { Bot, Mail, MessageCircle, type LucideIcon } from "lucide-react";
import { OFFICE_LINKS } from "../../config/office";

type OfficeLink = {
  key: string;
  label: string;
  wideLabel?: string;
  title: string;
  missingTitle: string;
  href: string;
  icon: LucideIcon;
};

const links: readonly OfficeLink[] = [
  {
    key: "whatsapp",
    label: "WhatsApp",
    title: "Abrir WhatsApp do escritório",
    missingTitle: "WhatsApp do escritório ainda não configurado",
    href: OFFICE_LINKS.whatsapp,
    icon: MessageCircle,
  },
  {
    key: "email",
    label: "E-mail",
    title: "Enviar e-mail ao escritório",
    missingTitle: "E-mail do escritório ainda não configurado",
    href: OFFICE_LINKS.email,
    icon: Mail,
  },
  {
    key: "office-ai",
    label: "IA",
    wideLabel: "IA do Escritório",
    title: "Abrir IA do Escritório",
    missingTitle: "IA do Escritório ainda não configurada",
    href: OFFICE_LINKS.officeAi,
    icon: Bot,
  },
];

export default function OfficeLinks() {
  return (
    <div className="ejc-office-links" aria-label="Atalhos institucionais">
      {links.map(
        ({ key, label, wideLabel, title, missingTitle, href, icon: Icon }) => {
          const content = (
            <>
              <Icon className="h-4 w-4" aria-hidden="true" />
              <span className="hidden 2xl:inline">{wideLabel || label}</span>
              <span className="hidden lg:inline 2xl:hidden">{label}</span>
            </>
          );

          if (!href) {
            return (
              <span
                key={key}
                title={missingTitle}
                aria-label={missingTitle}
                aria-disabled="true"
                className="ejc-office-link is-disabled"
              >
                {content}
              </span>
            );
          }

          const external = !href.startsWith("mailto:");
          return (
            <a
              key={key}
              href={href}
              title={title}
              aria-label={title}
              target={external ? "_blank" : undefined}
              rel={external ? "noopener noreferrer" : undefined}
              className="ejc-office-link"
            >
              {content}
            </a>
          );
        },
      )}
    </div>
  );
}
