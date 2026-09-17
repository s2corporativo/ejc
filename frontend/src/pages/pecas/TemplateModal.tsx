// Modal "Usar modelo" (template → peça) e modal de auditoria da peça
// (auditoria §2.6 #10). Estados nas páginas; aqui só a apresentação.
import { Modal, Spinner } from "../../components/UI";
import Markdown from "../../components/Markdown";

export default function TemplateModal({
  open,
  onClose,
  templates,
  casos,
  tplSel,
  setTplSel,
  casoSel,
  setCasoSel,
  onGerar,
}: {
  open: boolean;
  onClose: () => void;
  templates: any[];
  casos: any[];
  tplSel: string;
  setTplSel: (v: string) => void;
  casoSel: string;
  setCasoSel: (v: string) => void;
  onGerar: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Usar modelo">
      <div className="space-y-3">
        <select
          className="input"
          value={tplSel}
          onChange={(e) => setTplSel(e.target.value)}
        >
          <option value="">Escolha o modelo…</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.titulo}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={casoSel}
          onChange={(e) => setCasoSel(e.target.value)}
        >
          <option value="">Vincular ao caso…</option>
          {casos.map((c) => (
            <option key={c.id} value={c.id}>
              {c.numero_interno} — {c.titulo}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-500">
          O modelo preenche a estrutura com os dados do caso e cria uma nova
          peça em elaboração.
        </p>
        <button className="btn-primary w-full justify-center" onClick={onGerar}>
          Criar a partir do modelo
        </button>
      </div>
    </Modal>
  );
}

export function AuditoriaModal({
  open,
  titulo,
  carregando,
  texto,
  onClose,
}: {
  open: boolean;
  titulo: string;
  carregando: boolean;
  texto: string | null;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title={titulo} wide>
      {carregando ? (
        <Spinner />
      ) : (
        <Markdown
          source={texto}
          className="max-h-[60vh] overflow-auto text-sm"
        />
      )}
    </Modal>
  );
}
