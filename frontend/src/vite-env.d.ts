/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EJC_OFFICE_NAME?: string;
  readonly VITE_EJC_LOGO_PATH?: string;
  readonly VITE_EJC_WHATSAPP_NUMBER?: string;
  readonly VITE_EJC_CONTACT_EMAIL?: string;
  readonly VITE_EJC_OFFICE_AI_URL?: string;
  readonly VITE_EJC_OFFICE_AI_LABEL?: string;
  readonly VITE_EJC_TIMEZONE?: string;
  readonly VITE_EJC_DAILY_MESSAGE?: string;
  readonly VITE_EJC_DAILY_MESSAGE_SOURCE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
