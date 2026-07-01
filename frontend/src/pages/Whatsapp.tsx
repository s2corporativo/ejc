import { MessageCircle } from "lucide-react";
import { PageHeader } from "../components/UI";

/**
 * Placeholder da integração WhatsApp (Evolution API).
 * A funcionalidade completa (conexão do número, QR code e caixa de mensagens)
 * está em desenvolvimento no backend. Esta tela evita que o botão de WhatsApp
 * caia na home (BUG-05).
 */
export default function Whatsapp() {
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Relacionamento"
        title="WhatsApp"
        subtitle="Atendimento e disparos via WhatsApp integrados ao CRM."
      />
      <div className="mx-auto max-w-xl rounded-xl border border-slate-200 bg-white p-10 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-green-50">
          <MessageCircle className="h-7 w-7 text-green-600" />
        </div>
        <h2 className="text-lg font-semibold text-slate-800">
          Integração WhatsApp em desenvolvimento.
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Em breve você poderá conectar o número do escritório e conversar com
          clientes diretamente por aqui. Enquanto isso, use os botões de
          WhatsApp nas fichas de clientes e leads para abrir a conversa no
          aplicativo.
        </p>
      </div>
    </div>
  );
}
