import { Mail, MessageCircle, Sparkles } from "lucide-react";
import { Tooltip } from "../UI";
import {
  EJC_OFFICE_AI_URL,
  emailHref,
  whatsappHref,
} from "../../config/office";

/**
 * Atalhos compactos de contato do cabeçalho: WhatsApp, e-mail e
 * "IA do Escritório". Destinos vêm SÓ de src/config/office.ts (variáveis
 * VITE_EJC_* — nada hardcoded aqui); WhatsApp/e-mail somem quando não
 * configurados, em vez de apontar para dado inventado.
 */
export default function AtalhosContato({ className }: { className?: string }) {
  return (
    <div className={`flex items-center gap-1.5 ${className || ""}`}>
      {whatsappHref && (
        <Tooltip label="Abrir conversa no WhatsApp">
          <a
            href={whatsappHref}
            target="_blank"
            rel="noopener noreferrer"
            className="header-contact-btn"
            aria-label="Abrir conversa no WhatsApp (nova aba)"
          >
            <MessageCircle className="h-4 w-4" aria-hidden="true" />
            <span className="hidden 2xl:inline">WhatsApp</span>
          </a>
        </Tooltip>
      )}
      {emailHref && (
        <Tooltip label="Escrever e-mail ao escritório">
          <a
            href={emailHref}
            className="header-contact-btn"
            aria-label="Escrever e-mail ao escritório"
          >
            <Mail className="h-4 w-4" aria-hidden="true" />
            <span className="hidden 2xl:inline">E-mail</span>
          </a>
        </Tooltip>
      )}
      <Tooltip label="Abrir IA do Escritório">
        <a
          href={EJC_OFFICE_AI_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="header-contact-btn"
          aria-label="Abrir IA do Escritório (nova aba)"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          <span className="hidden xl:inline">
            IA do Escritório
            <span className="ml-1 font-normal text-shell-muted">Claude</span>
          </span>
        </a>
      </Tooltip>
    </div>
  );
}
