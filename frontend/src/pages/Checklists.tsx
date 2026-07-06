import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import { ListChecks, Trash2, Plus } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner } from "../components/UI";
import { asList } from "../lib/list";

export default function Checklists() {
  const [tpls, setTpls] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    nome: "",
    descricao: "",
    area_juridica: "",
    itens: "",
  });

  const load = () => {
    api
      .get("/checklists/templates")
      .then((r) =>
        setTpls(asList(r.data)),
      )
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
    const itens = f.itens
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length >= 3)
      .map((texto, i) => ({ texto, obrigatorio: true, ordem: i }));
    try {
      await api.post("/checklists/templates", {
        nome: f.nome,
        descricao: f.descricao || null,
        area_juridica: f.area_juridica || null,
        itens,
      });
      setF({ nome: "", descricao: "", area_juridica: "", itens: "" });
      setShow(false);
      setLoading(true);
      load();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Falha ao criar template");
    } finally {
      setSaving(false);
    }
  };

  const excluir = async (id: string) => {
    if (!confirm("Excluir este template de checklist?")) return;
    await api.delete(`/checklists/templates/${id}`);
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
        title="Checklists"
        subtitle="Modelos de verificação por tipo de demanda — aplicáveis aos casos"
        actions={
          <button
            onClick={() => setShow((s) => !s)}
            className="btn-primary flex items-center gap-1"
          >
            <Plus size={15} /> Novo template
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
                placeholder="Ex.: Documentos — Ação Trabalhista"
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
            <label className="label">Itens (um por linha)</label>
            <textarea
              rows={6}
              className="input w-full font-mono text-xs"
              value={f.itens}
              onChange={(e) => setF({ ...f, itens: e.target.value })}
              placeholder={
                "Procuração assinada\nContrato social\nComprovante de endereço\nDocumentos de identidade"
              }
            />
          </div>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Salvando…" : "Criar template"}
          </button>
        </form>
      )}

      {tpls.length === 0 ? (
        <div className="card p-10 text-center text-slate-400">
          <ListChecks size={32} className="mx-auto mb-3 text-bronze-pale" />
          Nenhum template ainda. Crie modelos de checklist por tipo de demanda —
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
                  {t.area_juridica && (
                    <span className="badge badge-neutral capitalize mt-1">
                      {t.area_juridica}
                    </span>
                  )}
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
              <ul className="space-y-1 text-sm text-slate-600">
                {(t.itens || []).map((i: any) => (
                  <li key={i.id} className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-bronze shrink-0" />{" "}
                    {i.texto}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-slate-400 mt-3">
                {(t.itens || []).length} item(ns)
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
