import { useEffect, useMemo, useState } from "react";
import Markdown from "../components/Markdown";
import { Sparkles, Upload, FileText, AlertTriangle } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";

type Skill = {
  id: string;
  name: string;
  display_name: string;
  description?: string | null;
  area: string;
  oab_restricted: boolean;
};

const AREA_LABEL: Record<string, string> = {
  juridico: "Jurídico",
  financeiro: "Financeiro",
  operacional: "Operacional",
};

export default function FerramentasIA() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [sel, setSel] = useState<string>("");
  const [texto, setTexto] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [res, setRes] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/ai/skills/list")
      .then((r) => {
        const arr: Skill[] = r.data ?? [];
        setSkills(arr);
        if (arr.length) setSel(arr[0].name);
      })
      .catch(() => setErro("Falha ao carregar as ferramentas de IA."))
      .finally(() => setCarregando(false));
  }, []);

  const grupos = useMemo(() => {
    const m = new Map<string, Skill[]>();
    for (const s of skills) m.set(s.area, [...(m.get(s.area) || []), s]);
    return Array.from(m.entries());
  }, [skills]);

  const skillAtual = skills.find((s) => s.name === sel);

  const executar = async () => {
    if (!sel) return;
    if (!file && texto.trim().length < 5) {
      setErro("Informe um texto ou anexe um documento.");
      return;
    }
    setLoading(true);
    setErro(null);
    setRes(null);
    try {
      let data;
      if (file) {
        const fd = new FormData();
        fd.append("skill_name", sel);
        fd.append("file", file);
        if (texto.trim()) fd.append("instrucoes", texto.trim());
        ({ data } = await api.post("/ai/skills/execute-doc", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        }));
      } else {
        ({ data } = await api.post("/ai/skills/execute", {
          skill_name: sel,
          query: texto.trim(),
        }));
      }
      setRes(data);
    } catch (e: any) {
      setErro(e?.response?.data?.detail || "Falha ao executar a ferramenta.");
    } finally {
      setLoading(false);
    }
  };

  if (carregando)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligência"
        title="Ferramentas de IA"
        subtitle={`${skills.length} assistentes jurídicos — análise de texto ou documento (PDF/DOCX/imagem) em padrão técnico-profissional.`}
      />

      <div className="grid lg:grid-cols-[320px_1fr] gap-4">
        {/* Coluna de seleção */}
        <div className="card p-4 h-fit">
          <label className="label">Ferramenta</label>
          <select
            className="input w-full"
            value={sel}
            onChange={(e) => {
              setSel(e.target.value);
              setRes(null);
            }}
          >
            {grupos.map(([area, items]) => (
              <optgroup key={area} label={AREA_LABEL[area] || area}>
                {items.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.display_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {skillAtual && (
            <p className="mt-3 text-xs text-slate-500">
              {skillAtual.description}
              {skillAtual.oab_restricted && (
                <span className="mt-2 block text-[11px] text-bronze-700">
                  Uso restrito — equipe jurídica (OAB).
                </span>
              )}
            </p>
          )}
        </div>

        {/* Coluna de execução */}
        <div className="card p-4 space-y-3">
          <div>
            <label className="label">
              Texto / contexto {file && "(instruções adicionais — opcional)"}
            </label>
            <textarea
              rows={file ? 3 : 8}
              className="input w-full"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={
                file
                  ? "Opcional: instruções específicas para o documento anexado…"
                  : "Cole aqui o texto da peça, decisão, relato do cliente, termo jurídico…"
              }
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="btn-secondary text-sm cursor-pointer inline-flex items-center gap-1">
              <Upload size={15} />
              {file ? "Trocar documento" : "Anexar documento"}
              <input
                type="file"
                className="hidden"
                accept=".pdf,.docx,.png,.jpg,.jpeg,.tiff,.webp,.txt"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            {file && (
              <span className="text-xs text-slate-600 inline-flex items-center gap-1">
                <FileText size={13} /> {file.name}
                <button
                  className="ml-1 text-danger-500 hover:underline"
                  onClick={() => setFile(null)}
                >
                  remover
                </button>
              </span>
            )}
            <button
              className="btn-primary text-sm ml-auto inline-flex items-center gap-1"
              disabled={loading}
              onClick={executar}
            >
              <Sparkles size={15} />
              {loading ? "Processando…" : "Executar"}
            </button>
          </div>

          {erro && (
            <div className="p-2 rounded bg-danger-50 text-danger-700 text-xs">
              {erro}
            </div>
          )}

          {res && (
            <div className="mt-2 rounded-lg border border-bronze-200 bg-bronze-50/40 p-4">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase text-bronze-700 mb-2">
                <AlertTriangle size={13} />
                {res.aviso || "Conferir fatos, documentos, prazos, valores e fontes antes do uso externo."}
              </div>
              <Markdown
                source={res.conteudo}
                className="text-sm text-slate-800 leading-relaxed"
              />
              <div className="mt-3 pt-2 border-t border-bronze-200 text-[11px] text-slate-500">
                {res.skill} · {res.engine} · {res.tokens_usados} tokens
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
