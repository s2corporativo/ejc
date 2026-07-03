import { useState } from "react";
import { PageHeader } from "../components/UI";
import { VictoryVaultPanel } from "../components/VictoryVaultPanel";
import { VeredutoIAWithVictoryVault } from "../components/VeredutoIAWithVictoryVault";
import { AssistedWritingMode } from "../components/AssistedWritingMode";

type Aba = "acervo" | "veredito" | "escrita";

const ABAS: { id: Aba; label: string }[] = [
  { id: "acervo", label: "Acervo" },
  { id: "veredito", label: "Veredito IA" },
  { id: "escrita", label: "Escrita assistida" },
];

export default function VictoryVault() {
  const [aba, setAba] = useState<Aba>("acervo");

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-primary-100 bg-white p-5 shadow-sm md:p-6">
        <PageHeader
          eyebrow="Inteligencia juridica"
          title="Victory Vault"
          subtitle="Acervo de teses vitoriosas, analise preditiva de exito e geracao de documentos por modelo."
        />
        <div className="flex gap-1 border-b border-slate-200">
          {ABAS.map((a) => (
            <button
              key={a.id}
              onClick={() => setAba(a.id)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                aba === a.id
                  ? "border-primary-600 text-primary-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {aba === "acervo" && <VictoryVaultPanel />}
      {aba === "veredito" && <VeredutoIAWithVictoryVault />}
      {aba === "escrita" && <AssistedWritingMode />}
    </div>
  );
}
