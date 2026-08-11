import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { Link } from "react-router";

export default function DptPortalGuard() {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-950 text-amber-300">
          <LockKeyhole className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-slate-950 dark:text-white">
            Compartilhamento com cliente
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            O DPT não publica rascunhos diretamente. Para compartilhar, o
            conteúdo aprovado deve virar documento canônico e seguir o Data
            Room/Portal já existente.
          </p>
          <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 text-xs leading-5 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
            <ShieldCheck className="mr-1 inline h-3.5 w-3.5" />O Data Room
            adiciona arquivos inicialmente como não publicados; publicação
            externa exige ato explícito e respeita a classificação do documento.
          </div>
          <Link
            to="/data-room"
            className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300"
          >
            Abrir Data Room canônico <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </div>
    </section>
  );
}
