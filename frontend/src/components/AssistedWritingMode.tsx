import React, { useState, useEffect } from "react";
import Markdown from "./Markdown";
import { Copy } from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";

interface Template {
  id: string;
  nome?: string;
  descricao?: string;
  area_juridica: string;
  tipo_documento: string;
}

const AREAS = [
  "Administrativa",
  "Tributaria",
  "Trabalhista",
  "Ambiental",
  "Bancaria",
];
const CAMPOS = ["cliente_nome", "cliente_cpf", "assunto", "descricao"];

export const AssistedWritingMode: React.FC = () => {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [templateData, setTemplateData] = useState<Record<string, string>>({});
  const [generatedDocument, setGeneratedDocument] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);

  useEffect(() => {
    fetchTemplates();
  }, [selectedArea]);

  const fetchTemplates = async () => {
    try {
      const r = await api.get("/document-templates/", {
        params: { area_juridica: selectedArea || undefined },
      });
      setTemplates(asList<Template>(r.data));
    } catch (err) {
      console.error("Erro ao buscar templates:", err);
    }
  };

  const handleGenerateDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTemplate) {
      setError("Selecione um template");
      return;
    }
    setLoading(true);
    setError(null);
    setGeneratedDocument(null);
    try {
      const r = await api.post("/document-templates/generate", {
        template_id: selectedTemplate,
        data: templateData,
      });
      setGeneratedDocument(r.data.documento);
    } catch (err) {
      setError("Erro ao gerar documento. Tente novamente.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    if (generatedDocument) navigator.clipboard.writeText(generatedDocument);
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card space-y-5 p-5">
        <div>
          <span className="eyebrow">Area</span>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSelectedArea(null)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                selectedArea === null
                  ? "bg-primary-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              Todas
            </button>
            {AREAS.map((area) => (
              <button
                key={area}
                type="button"
                onClick={() => setSelectedArea(area)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  selectedArea === area
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {area}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="eyebrow">Templates disponiveis</span>
          <div className="mt-2 max-h-80 space-y-2 overflow-y-auto">
            {templates.length === 0 ? (
              <p className="py-4 text-sm text-slate-400">
                Nenhum template disponivel
              </p>
            ) : (
              templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setSelectedTemplate(t.id);
                    setTemplateData({});
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${
                    selectedTemplate === t.id
                      ? "border-primary-300 bg-primary-50"
                      : "border-transparent bg-slate-900/[0.03] hover:bg-slate-900/[0.06] dark:bg-white/[0.05] dark:hover:bg-white/[0.08]"
                  }`}
                >
                  <p className="text-sm font-medium text-slate-900">
                    {t.descricao || t.tipo_documento}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {t.tipo_documento} &middot; {t.area_juridica}
                  </p>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {selectedTemplate ? (
          <form
            onSubmit={handleGenerateDocument}
            className="card space-y-4 p-5"
          >
            <span className="eyebrow">Preencha os dados</span>
            <div className="space-y-3">
              {CAMPOS.map((field) => (
                <div key={field}>
                  <label className="label capitalize">
                    {field.replace("_", " ")}
                  </label>
                  <input
                    type="text"
                    value={templateData[field] || ""}
                    onChange={(e) =>
                      setTemplateData({
                        ...templateData,
                        [field]: e.target.value,
                      })
                    }
                    className="input"
                  />
                </div>
              ))}
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full"
            >
              {loading ? "Gerando..." : "Gerar documento"}
            </button>
          </form>
        ) : (
          <div className="card flex h-full items-center justify-center p-8 text-center text-sm text-slate-400">
            Selecione um template para preencher os dados.
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-sm text-danger-700">
            {error}
          </div>
        )}

        {generatedDocument && (
          <div className="card p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="eyebrow">Documento gerado</span>
              <button onClick={copy} className="btn-outline text-xs">
                <Copy className="h-3 w-3" /> Copiar
              </button>
            </div>
            <Markdown
              source={generatedDocument}
              className="max-h-72 overflow-y-auto rounded-lg border border-slate-100 bg-slate-50/60 p-3 text-sm text-slate-700"
            />
          </div>
        )}
      </div>
    </div>
  );
};
