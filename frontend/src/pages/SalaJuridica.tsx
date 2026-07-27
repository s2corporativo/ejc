import { useEffect, useRef, useState } from "react";
import { Paperclip, X } from "lucide-react";
import SalaJuridicaWorkspace from "./SalaJuridicaWorkspace";
import {
  DOCUMENT_SESSION_READY_EVENT,
  installSalaJuridicaReliabilityPatches,
} from "../lib/salaJuridicaReliability";

// Instala antes do primeiro efeito do workspace, garantindo que autosave,
// paginação e criação de sessão já usem a camada de confiabilidade.
installSalaJuridicaReliabilityPatches();

export default function SalaJuridica() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [aguardandoSessaoDocumental, setAguardandoSessaoDocumental] =
    useState(false);
  const [anexoDisponivel, setAnexoDisponivel] = useState(false);

  useEffect(() => {
    const handleDocumentSession = () => {
      setAguardandoSessaoDocumental(true);
      setAnexoDisponivel(false);
    };
    window.addEventListener(
      DOCUMENT_SESSION_READY_EVENT,
      handleDocumentSession as EventListener,
    );
    return () =>
      window.removeEventListener(
        DOCUMENT_SESSION_READY_EVENT,
        handleDocumentSession as EventListener,
      );
  }, []);

  useEffect(() => {
    if (!aguardandoSessaoDocumental) return;

    let tentativas = 0;
    const timer = window.setInterval(() => {
      tentativas += 1;
      const root = rootRef.current;
      const tituloAtivo = root?.querySelector("main h2")?.textContent ?? "";
      const fileInput = root?.querySelector<HTMLInputElement>(
        'input[type="file"][multiple]',
      );
      const sessaoPronta = tituloAtivo.startsWith("Raio-X documental");

      if (sessaoPronta && fileInput) {
        window.clearInterval(timer);
        setAguardandoSessaoDocumental(false);
        setAnexoDisponivel(true);
      } else if (tentativas >= 100) {
        window.clearInterval(timer);
        setAguardandoSessaoDocumental(false);
      }
    }, 100);

    return () => window.clearInterval(timer);
  }, [aguardandoSessaoDocumental]);

  const abrirSeletorDeArquivos = () => {
    const fileInput = rootRef.current?.querySelector<HTMLInputElement>(
      'input[type="file"][multiple]',
    );
    if (!fileInput) return;
    // O click ocorre dentro do gesto explícito do usuário, como exigem os browsers.
    fileInput.click();
    setAnexoDisponivel(false);
  };

  return (
    <div ref={rootRef} data-sala-juridica-root>
      <SalaJuridicaWorkspace />

      {anexoDisponivel && (
        <div
          className="fixed bottom-5 right-5 z-50 w-[min(92vw,360px)] rounded-2xl border border-primary-200 bg-white p-4 shadow-2xl"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-bold text-slate-950">
                Raio-X documental criado
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Selecione agora os autos, contratos ou provas que serão analisados.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"
              onClick={() => setAnexoDisponivel(false)}
              aria-label="Fechar aviso"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <button
            type="button"
            className="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-bold text-white hover:bg-primary-700"
            onClick={abrirSeletorDeArquivos}
          >
            <Paperclip className="h-4 w-4" /> Anexar documentos
          </button>
        </div>
      )}
    </div>
  );
}
