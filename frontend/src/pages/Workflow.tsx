import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import { GitBranch, Trash2, Plus, Clock } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { detalheErro } from "../utils/erro";

type Etapa = {
  id?: string;
  nome: string;
  ordem: number;
  sla_dias_uteis?: number | null;
  obrigatoria: boolean;
};

type Template = {
  id: string;
  nome: string;
  descricao?: string | null;
  area_juridica?: string | null;
  is_default: boolean;
  etapas: Etapa[];
};

export default function Workflow() {
  const [tpls, setTpls] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    nome: "",
    descricao: "",
    area_juridica: "",
    is_default: false,
    etapas: "",
  });

  const load = () => {
    api
      .get("/workflow/templates")
      .then((r) => setTpls(r.data ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);

  const criar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (f.nome.trim().length < 3) return;
    setSaving(true);
    // Cada linha: "Nome da etapa" ou "Nome da etapa | 5" (SLA em dias úteis)
    const etapas = f.etapas
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length >= 2)
      .map((linha, i) => {
        const [nome, sla] = linha.split("|").map((x) => x.trim());
        return {
          nome: (nome || "").slice(0, 100),
          ordem: i + 1,
          sla_dias_uteis: sla && !isNaN(Number(sla)) ? Number(sla) : null,
          obrigatoria: true,
        };
      });
    try {
      await api.post("/workflow/templates", {
        nome: f.nome,
        descricao: f.descricao || null,
        area_juridica: f.area_juridica || null,
        is_default: f.is_default,
        etapas,
      });
      setF({
        nome: "",
        descricao: "",
        area_juridica: "",
        is_default: false,
        etapas: "",
      });
      setShow(false);
      setLoading(true);
      load();
    } catch (err: unknown) {
      toast.error(detalheErro(err, "Falha ao criar workflow"));
    } finally {
      setSaving(false);
    }
  };

  const excluir = async (id: string) => {
    if (!confirm("Arquivar este workflow?")) return;
    await api.delete(`/workflow/templates/${id}`);
    setTpls((p) => p.filter((t) => t.id !== id));
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
        eyebrow="Produção jurídica"
        title="Workflows (BPM)"
        subtitle="Fluxos de etapas processuais configuráveis por área — aplicáveis aos casos"
        actions={
          <button
            onClick={() => setShow((s) => !s)}
            className="btn-primary flex items-center gap-1"
          >
            <Plus size={15} /> Novo workflow
          </button>
        }
      />

      {show && (
        <form onSubmit={criar} className="card p-5 space-y-3 max-w-2xl">
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <label className="label">Nome *</label>
              <input
                className="input w-full"
                value={f.nome}
                onChange={(e) => setF({ ...f, nome: e.target.value })}
                placeholder="Ex.: Fluxo — Ação Trabalhista"
              />
            </div>
            <div>
              <label className="label">Área jurídica</label>
              <input
                className="input w-full"
                value={f.area_juridica}
                onChange={(e) => setF({ ...f, area_juridica: e.target.value })}
                placeholder="trabalhista, cível…"
              />
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
              Etapas (uma por linha — opcional "| dias de SLA")
            </label>
            <textarea
              rows={6}
              className="input w-full font-mono text-xs"
              value={f.etapas}
              onChange={(e) => setF({ ...f, etapas: e.target.value })}
              placeholder={
                "Petição inicial | 5\nCitação\nContestação | 15\nInstrução\nSentença"
              }
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={f.is_default}
              onChange={(e) => setF({ ...f, is_default: e.target.checked })}
            />
            Marcar como padrão para a área
          </label>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Salvando…" : "Criar workflow"}
          </button>
        </form>
      )}

      {tpls.length === 0 ? (
        <div className="card p-10 text-center text-slate-400">
          <GitBranch size={32} className="mx-auto mb-3 text-bronze-pale" />
          Nenhum workflow ainda. Crie fluxos de etapas por tipo de demanda —
          eles ficam disponíveis para aplicar em cada caso.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {tpls.map((t) => (
            <div key={t.id} className="card p-5">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-serif text-base font-semibold text-navy">
                    {t.nome}
                  </h3>
                  <div className="flex gap-1 mt-1">
                    {t.area_juridica && (
                      <span className="badge badge-neutral capitalize">
                        {t.area_juridica}
                      </span>
                    )}
                    {t.is_default && (
                      <span className="badge badge-neutral">padrão</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => excluir(t.id)}
                  className="text-slate-300 hover:text-danger-500"
                >
                  <Trash2 size={15} />
                </button>
              </div>
              {t.descricao && (
                <p className="text-sm text-slate-500 mb-2">{t.descricao}</p>
              )}
              <ol className="space-y-1.5 text-sm text-slate-600 mt-3">
                {(t.etapas || []).map((e, idx) => (
                  <li key={e.id || idx} className="flex items-center gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-600 text-[10px] font-semibold text-white">
                      {idx + 1}
                    </span>
                    <span className="flex-1">{e.nome}</span>
                    {e.sla_dias_uteis != null && (
                      <span className="flex items-center gap-1 text-xs text-slate-400">
                        <Clock size={11} /> {e.sla_dias_uteis}d
                      </span>
                    )}
                  </li>
                ))}
              </ol>
              <p className="text-xs text-slate-400 mt-3">
                {(t.etapas || []).length} etapa(s)
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
