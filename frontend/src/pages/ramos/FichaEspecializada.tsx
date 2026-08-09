import { useState } from "react";
import { Plus } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../components/Toast";
import { Modal } from "../../components/UI";
import type { Case } from "../../types";
import type { RamoConfig } from "./ramosConfig";

function rotulo(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function FichaEspecializada({
  cfg,
  casos,
  onSaved,
}: {
  cfg: RamoConfig;
  casos: Case[];
  onSaved?: () => void;
}) {
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<Record<string, any>>({});
  const [salvando, setSalvando] = useState(false);

  if (cfg.externo) return null;

  const salvar = async () => {
    if (!form.case_id) {
      toast.error("Selecione o caso canônico ao qual a ficha será vinculada.");
      return;
    }
    const obrigatorio = cfg.campos.find(
      (campo) => campo.obrigatorio && !form[campo.nome],
    );
    if (obrigatorio) {
      toast.error(`Campo obrigatório: ${obrigatorio.label}`);
      return;
    }
    setSalvando(true);
    try {
      await api.post(cfg.endpoint, form);
      toast.success("Ficha especializada registrada e vinculada ao caso.");
      setModal(false);
      setForm({});
      onSaved?.();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === "string"
          ? detail
          : "Não foi possível registrar a ficha especializada.",
      );
    } finally {
      setSalvando(false);
    }
  };

  return (
    <>
      <section className="card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-2xl">
            <h2 className="font-serif font-semibold text-navy">
              Ficha especializada do núcleo
            </h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              Registro auxiliar opcional para dados específicos desta área. A
              ficha sempre depende de um caso já existente e não cria outro
              caso, cliente ou processo em paralelo.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary flex items-center gap-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            disabled={casos.length === 0}
            onClick={() => setModal(true)}
          >
            <Plus size={15} /> Adicionar ficha especializada
          </button>
        </div>
        {casos.length === 0 && (
          <p className="mt-2 text-xs text-warn-700">
            Abra primeiro um caso canônico desta área. A ficha especializada só
            pode ser vinculada depois.
          </p>
        )}
      </section>

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title={`Ficha especializada — ${cfg.titulo}`}
        wide
      >
        <div className="mb-4 rounded-xl border border-primary-100 bg-primary-50/60 p-3 text-xs leading-5 text-primary-800">
          Este formulário cria apenas um registro auxiliar do núcleo. O caso
          selecionado abaixo continua sendo a fonte de verdade jurídica e
          operacional no EJC.
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="label">Caso canônico vinculado *</label>
            <select
              className="input"
              value={form.case_id || ""}
              onChange={(e) => setForm({ ...form, case_id: e.target.value })}
            >
              <option value="">Selecione o caso...</option>
              {casos.map((caso) => (
                <option key={caso.id} value={caso.id}>
                  {caso.numero_interno || "Sem nº interno"} — {caso.titulo}
                </option>
              ))}
            </select>
          </div>

          {cfg.campos.map((campo) => (
            <div
              key={campo.nome}
              className={campo.col === 2 ? "sm:col-span-2" : ""}
            >
              <label className="label">
                {campo.label}
                {campo.obrigatorio && " *"}
              </label>
              {campo.tipo === "select" ? (
                <select
                  className="input"
                  value={form[campo.nome] || ""}
                  onChange={(e) =>
                    setForm({ ...form, [campo.nome]: e.target.value })
                  }
                >
                  <option value="">Selecione...</option>
                  {campo.opcoes?.map((opcao) => (
                    <option key={opcao} value={opcao}>
                      {rotulo(opcao)}
                    </option>
                  ))}
                </select>
              ) : campo.tipo === "textarea" ? (
                <textarea
                  className="input"
                  rows={3}
                  value={form[campo.nome] || ""}
                  placeholder={campo.placeholder}
                  onChange={(e) =>
                    setForm({ ...form, [campo.nome]: e.target.value })
                  }
                />
              ) : campo.tipo === "checkbox" ? (
                <label className="mt-1 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={Boolean(form[campo.nome])}
                    onChange={(e) =>
                      setForm({ ...form, [campo.nome]: e.target.checked })
                    }
                  />
                  <span className="text-slate-600">{campo.ajuda || "Sim"}</span>
                </label>
              ) : (
                <input
                  className="input"
                  type={campo.tipo}
                  step={campo.tipo === "number" ? "0.01" : undefined}
                  placeholder={campo.placeholder}
                  value={form[campo.nome] || ""}
                  onChange={(e) =>
                    setForm({ ...form, [campo.nome]: e.target.value })
                  }
                />
              )}
              {campo.ajuda && campo.tipo !== "checkbox" && (
                <p className="mt-1 text-xs text-slate-400">{campo.ajuda}</p>
              )}
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            className="btn-primary"
            disabled={salvando}
            onClick={salvar}
          >
            {salvando ? "Salvando..." : "Salvar ficha especializada"}
          </button>
        </div>
      </Modal>
    </>
  );
}
