import { useMemo, useState } from "react";
import { ScanLine, ShieldCheck, X } from "lucide-react";
import { useLocation } from "react-router-dom";
import EntradaUniversalDocumentos, { EntradaUniversalResultado } from "./EntradaUniversalDocumentos";
import { useAuth } from "../stores/auth";

const ROLES_JURIDICOS = new Set([
  "superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario",
]);

const MODALIDADES = [
  { value: "", label: "Classificação geral automática" },
  { value: "multa_transito", label: "Multa de trânsito" },
  { value: "multa_ambiental", label: "Multa ambiental" },
  { value: "multa_administrativa", label: "Multa ou processo administrativo" },
  { value: "revisao_contratual", label: "Revisão contratual" },
  { value: "revisao_bancaria", label: "Revisão bancária" },
];

function casoDaRota(pathname: string): string | undefined {
  const match = pathname.match(/^\/casos\/([^/?#]+)/);
  if (!match || match[1] === "novo") return undefined;
  return decodeURIComponent(match[1]);
}

/**
 * Atalho transversal, sem item adicional na barra lateral. Fica disponível no
 * Dashboard, Documentos, Peças, Raio-X e demais módulos jurídicos. Dentro de um
 * caso, os originais já são persistidos diretamente no respectivo GED.
 */
export default function EntradaUniversalGlobal() {
  const location = useLocation();
  const user = useAuth((state) => state.user);
  const caseId = useMemo(() => casoDaRota(location.pathname), [location.pathname]);
  const [open, setOpen] = useState(false);
  const [modalidade, setModalidade] = useState("");
  const [ultimoLote, setUltimoLote] = useState<EntradaUniversalResultado | null>(null);

  if (!user?.role || !ROLES_JURIDICOS.has(user.role)) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-4 z-30 flex h-12 items-center gap-2 rounded-2xl bg-slate-950 px-3 text-sm font-semibold text-white shadow-xl shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-slate-800 md:right-5 md:px-4"
        aria-label="Abrir Entrada Universal de Documentos"
        title="Importar PDF, Word, fotos, planilhas ou ZIP"
      >
        <ScanLine className="h-5 w-5" />
        <span className="hidden xl:inline">Importar documentos</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-slate-950/55 p-3 pt-16 backdrop-blur-sm md:p-6 md:pt-20">
          <div className="w-full max-w-6xl rounded-[2rem] border border-white/20 bg-canvas shadow-2xl">
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-4 dark:border-white/10 md:px-5">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary-700">
                  <ShieldCheck className="h-4 w-4" /> Infraestrutura transversal do EJC
                </div>
                <h2 className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">Entrada Universal de Documentos</h2>
                <p className="mt-1 text-xs text-slate-500">
                  {caseId
                    ? "Você está dentro de um caso. Todos os originais deste lote serão vinculados diretamente a ele."
                    : "Importação avulsa auditável. Para iniciar um caso com preenchimento automático, use Novo caso por documento."}
                </p>
              </div>
              <button type="button" className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" onClick={() => setOpen(false)} aria-label="Fechar">
                <X className="h-5 w-5" />
              </button>
            </header>

            <div className="p-4 md:p-5">
              <div className="mb-4 max-w-xl">
                <label className="label">Finalidade do pacote</label>
                <select className="input w-full" value={modalidade} onChange={(event) => { setModalidade(event.target.value); setUltimoLote(null); }}>
                  {MODALIDADES.map((item) => <option key={item.value || "geral"} value={item.value}>{item.label}</option>)}
                </select>
                <p className="mt-1 text-[11px] text-slate-500">A finalidade especializada ativa checklist e prontidão próprios. A opção geral apenas classifica e organiza.</p>
              </div>

              <EntradaUniversalDocumentos
                key={`${location.pathname}:${modalidade}`}
                modalidade={modalidade || undefined}
                caseId={caseId}
                onProcessado={setUltimoLote}
                titulo={caseId ? "Adicionar pacote documental ao caso" : "Importar pacote documental"}
                descricao="A função é a mesma em todos os módulos: preservar o original, gerar hash, ler página por página, classificar, comparar, apontar pendências e preparar o pacote jurídico."
              />

              {ultimoLote && (
                <div className="mt-4 rounded-xl border border-primary-200 bg-primary-50 p-3 text-xs text-primary-900">
                  Lote <b>{ultimoLote.batch_id}</b> concluído. {caseId ? "Os documentos já pertencem ao caso atual." : "O lote permanece auditável no GED e pode ser vinculado posteriormente a um caso pelo fluxo jurídico."}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
