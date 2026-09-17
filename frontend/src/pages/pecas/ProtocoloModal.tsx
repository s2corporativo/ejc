// Modal "Registrar protocolo" (auditoria §2.6 #10). Estado do protocolo na página.
import { Stamp } from "lucide-react";
import { Modal } from "../../components/UI";
import { dataLocalISO } from "../../lib/protocoloPeca";
import type { LegalDoc } from "../../types";

export type ProtocoloForm = {
  doc: LegalDoc;
  numero: string;
  tribunal: string;
  data: string;
};

export default function ProtocoloModal({
  protocolo,
  protocolando,
  onChange,
  onFechar,
  onConfirmar,
}: {
  protocolo: ProtocoloForm | null;
  protocolando: boolean;
  onChange: (p: ProtocoloForm) => void;
  onFechar: () => void;
  onConfirmar: () => void;
}) {
  return (
    <Modal open={!!protocolo} onClose={onFechar} title="Registrar protocolo">
      <p className="mb-3 text-sm text-slate-600">
        Registre o comprovante do peticionamento para concluir o fluxo da peça.
      </p>
      <div className="space-y-3">
        <div>
          <label className="label">Número do protocolo *</label>
          <input
            className="input"
            value={protocolo?.numero || ""}
            onChange={(e) =>
              protocolo && onChange({ ...protocolo, numero: e.target.value })
            }
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Tribunal/sistema</label>
            <input
              className="input"
              placeholder="Ex.: TJMG — PJe"
              value={protocolo?.tribunal || ""}
              onChange={(e) =>
                protocolo &&
                onChange({ ...protocolo, tribunal: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Data do protocolo</label>
            <input
              type="date"
              className="input"
              max={dataLocalISO()}
              value={protocolo?.data || ""}
              onChange={(e) =>
                protocolo && onChange({ ...protocolo, data: e.target.value })
              }
            />
          </div>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onFechar}>
          Cancelar
        </button>
        <button
          className="btn-primary"
          disabled={protocolando || !protocolo?.numero.trim()}
          onClick={onConfirmar}
        >
          <Stamp size={15} />
          {protocolando ? "Registrando..." : "Registrar e concluir"}
        </button>
      </div>
    </Modal>
  );
}
