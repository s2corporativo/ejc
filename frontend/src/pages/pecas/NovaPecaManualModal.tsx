// Modal "Nova peça manual" (auditoria §2.6 #10). Estado do form na página.
import { Modal } from "../../components/UI";
import { TIPOS_MANUAIS } from "./pecasCatalogo";

export default function NovaPecaManualModal({
  open,
  onClose,
  form,
  setForm,
  salvando,
  onSalvar,
}: {
  open: boolean;
  onClose: () => void;
  form: any;
  setForm: (f: any) => void;
  salvando: boolean;
  onSalvar: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Nova peça manual" wide>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo || ""}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Tipo</label>
            <select
              className="input"
              value={form.tipo_peca}
              onChange={(e) => setForm({ ...form, tipo_peca: e.target.value })}
            >
              {TIPOS_MANUAIS.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {tipo.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Conteúdo * (markdown)</label>
          <textarea
            className="input min-h-[260px] font-mono text-xs"
            value={form.conteudo || ""}
            onChange={(e) => setForm({ ...form, conteudo: e.target.value })}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={form.ai_generated}
            onChange={(e) =>
              setForm({ ...form, ai_generated: e.target.checked })
            }
          />
          Conteúdo recebeu assistência de IA
        </label>
        <div className="flex justify-end">
          <button
            className="btn-primary"
            disabled={salvando}
            onClick={onSalvar}
          >
            {salvando ? "Salvando..." : "Salvar peça"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
