import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import Markdown from "../components/Markdown";
import { Sparkles, Trash2, Plus, Play } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, Modal } from "../components/UI";

const CATS = [
  "peticao",
  "contrato",
  "audiencia",
  "email",
  "modelo",
  "analise",
  "resumo",
  "negociacao",
  "outros",
];

export default function Prompts() {
  const [prompts, setPrompts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    titulo: "",
    categoria: "peticao",
    conteudo: "",
    descricao: "",
  });
  const [exec, setExec] = useState<any>(null); // prompt sendo executado
  const [vars, setVars] = useState<Record<string, string>>({});
  const [out, setOut] = useState("");
  const [running, setRunning] = useState(false);

  const load = () => {
    api
      .get("/prompts-juridicos")
      .then((r) => setPrompts(r.data?.data ?? r.data ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (f.titulo.trim().length < 3 || f.conteudo.trim().length < 20) {
      toast.error("Título (3+) e conteúdo (20+) obrigatórios.");
      return;
    }
    setSaving(true);
    try {
      await api.post("/prompts-juridicos", {
        ...f,
        descricao: f.descricao || null,
      });
      setF({ titulo: "", categoria: "peticao", conteudo: "", descricao: "" });
      setShow(false);
      setLoading(true);
      load();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao criar");
    } finally {
      setSaving(false);
    }
  };

  const excluir = async (id: string) => {
    if (!confirm("Excluir este prompt?")) return;
    await api.delete(`/prompts-juridicos/${id}`);
    setPrompts((p) => p.filter((x) => x.id !== id));
  };

  const abrirExec = (p: any) => {
    setExec(p);
    setOut("");
    setVars(
      Object.fromEntries((p.variaveis || []).map((v: string) => [v, ""])),
    );
  };
  const executar = async () => {
    setRunning(true);
    setOut("");
    try {
      const { data } = await api.post(
        `/prompts-juridicos/${exec.id}/executar`,
        { variaveis: vars },
      );
      setOut(
        data.resultado ?? data.conteudo ?? data.texto ?? JSON.stringify(data),
      );
    } catch (err: any) {
      setOut("Erro: " + (err.response?.data?.detail || "falha"));
    } finally {
      setRunning(false);
    }
  };

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Inteligência"
        title="Biblioteca de Prompts"
        subtitle="Modelos de instrução reutilizáveis — com variáveis {{campo}}"
        actions={
          <button
            onClick={() => setShow((s) => !s)}
            className="btn-primary flex items-center gap-1"
          >
            <Plus size={15} /> Novo prompt
          </button>
        }
      />

      {show && (
        <form onSubmit={criar} className="card p-5 space-y-3 max-w-2xl">
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <label className="label">Título *</label>
              <input
                className="input w-full"
                value={f.titulo}
                onChange={(e) => setF({ ...f, titulo: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Categoria</label>
              <select
                className="input w-full capitalize"
                value={f.categoria}
                onChange={(e) => setF({ ...f, categoria: e.target.value })}
              >
                {CATS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Descrição</label>
            <input
              className="input w-full"
              value={f.descricao}
              onChange={(e) => setF({ ...f, descricao: e.target.value })}
            />
          </div>
          <div>
            <label className="label">
              Conteúdo * (use {"{{variavel}}"} para campos)
            </label>
            <textarea
              rows={5}
              className="input w-full"
              value={f.conteudo}
              onChange={(e) => setF({ ...f, conteudo: e.target.value })}
              placeholder="Redija uma petição de {{tipo}} para o cliente {{cliente}} sobre {{assunto}}."
            />
          </div>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Salvando…" : "Criar prompt"}
          </button>
        </form>
      )}

      {prompts.length === 0 ? (
        <div className="card p-10 text-center text-slate-400">
          <Sparkles size={32} className="mx-auto mb-3 text-bronze-pale" />
          Nenhum prompt salvo. Crie modelos de instrução reutilizáveis para
          acelerar peças, e-mails e análises.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {prompts.map((p) => (
            <div key={p.id} className="card p-5">
              <div className="flex justify-between items-start mb-1">
                <h3 className="font-serif text-base font-semibold text-navy">
                  {p.titulo}
                </h3>
                <button
                  onClick={() => excluir(p.id)}
                  className="text-slate-300 hover:text-red-500"
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <span className="badge badge-neutral capitalize">
                {p.categoria}
              </span>
              {p.descricao && (
                <p className="text-sm text-slate-500 mt-2">{p.descricao}</p>
              )}
              {p.variaveis?.length > 0 && (
                <p className="text-xs text-slate-400 mt-2">
                  Variáveis:{" "}
                  {p.variaveis.map((v: string) => `{{${v}}}`).join(", ")}
                </p>
              )}
              <button
                onClick={() => abrirExec(p)}
                className="btn-outline text-xs mt-3 flex items-center gap-1"
              >
                <Play size={12} /> Executar
              </button>
            </div>
          ))}
        </div>
      )}

      {exec && (
        <Modal
          open={!!exec}
          onClose={() => setExec(null)}
          title={`Executar — ${exec.titulo}`}
        >
          <div className="space-y-3">
            {(exec.variaveis || []).length === 0 && (
              <p className="text-sm text-slate-500">
                Este prompt não tem variáveis.
              </p>
            )}
            {(exec.variaveis || []).map((v: string) => (
              <div key={v}>
                <label className="label">{v}</label>
                <input
                  className="input w-full"
                  value={vars[v] || ""}
                  onChange={(e) => setVars({ ...vars, [v]: e.target.value })}
                />
              </div>
            ))}
            <button
              onClick={executar}
              disabled={running}
              className="btn-primary w-full"
            >
              {running ? "Processando…" : "Gerar"}
            </button>
            {out && (
              <Markdown source={out} className="text-sm text-slate-700 border-t border-bronze-pale pt-3 leading-relaxed" />
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
