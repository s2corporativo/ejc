import { useState } from "react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

const AREAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "ambiental",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
];

export default function ConteudoJuridico() {
  const [area, setArea] = useState("consumidor");
  const [faq, setFaq] = useState("");
  const [glos, setGlos] = useState("");
  const [termos, setTermos] = useState("");
  const [lf, setLf] = useState(false);
  const [lg, setLg] = useState(false);

  const gerarFaq = () => {
    setLf(true);
    api
      .post("/conteudo/faq", { area, quantidade: 6 })
      .then((r) => setFaq(r.data?.conteudo || ""))
      .finally(() => setLf(false));
  };
  const gerarGlos = () => {
    setLg(true);
    const body: any = termos.trim()
      ? {
          termos: termos
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        }
      : { area };
    api
      .post("/conteudo/glossario", body)
      .then((r) => setGlos(r.data?.conteudo || ""))
      .finally(() => setLg(false));
  };

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="FAQ & Glossário"
        subtitle="Conteúdo jurídico para portal/equipe — rascunho IA, revisar antes de publicar"
      />

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="card p-4">
          <h3 className="font-semibold text-ink mb-2">FAQ por área</h3>
          <div className="flex gap-2 mb-3">
            <select
              className="input text-sm flex-1"
              value={area}
              onChange={(e) => setArea(e.target.value)}
            >
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <button
              className="btn-primary text-sm"
              onClick={gerarFaq}
              disabled={lf}
            >
              {lf ? "Gerando…" : "Gerar FAQ"}
            </button>
          </div>
          {faq && (
            <pre className="text-sm whitespace-pre-wrap text-slate-700 bg-bronze-30 p-3 rounded-lg max-h-[28rem] overflow-auto">
              {faq}
            </pre>
          )}
        </div>

        <div className="card p-4">
          <h3 className="font-semibold text-ink mb-2">Glossário</h3>
          <input
            className="input w-full text-sm mb-2"
            placeholder="Termos separados por vírgula (vazio = usar a área)"
            value={termos}
            onChange={(e) => setTermos(e.target.value)}
          />
          <button
            className="btn-primary text-sm mb-3"
            onClick={gerarGlos}
            disabled={lg}
          >
            {lg ? "Gerando…" : "Gerar glossário"}
          </button>
          {glos && (
            <pre className="text-sm whitespace-pre-wrap text-slate-700 bg-bronze-30 p-3 rounded-lg max-h-[28rem] overflow-auto">
              {glos}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
