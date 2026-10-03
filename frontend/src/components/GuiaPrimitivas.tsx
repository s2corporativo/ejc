import { useEffect, useState, type ReactNode } from "react";
import { BookOpen, type LucideIcon } from "lucide-react";

type SecProps = {
  title: string;
  icon: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
  open?: boolean;
};

export function GuiaSec({
  title,
  icon,
  badge,
  children,
  open = false,
  empresarial = false,
}: SecProps & { empresarial?: boolean }) {
  const [isOpen, setIsOpen] = useState(open);
  return (
    <div className="border border-bronze-pale rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={
          empresarial
            ? "w-full flex items-center justify-between gap-2 p-4 bg-white hover:bg-slate-50 text-left"
            : "w-full flex items-center justify-between p-4 bg-white hover:bg-slate-50 text-left"
        }
      >
        <span
          className={
            empresarial
              ? "flex flex-wrap items-center gap-2 font-semibold text-slate-800"
              : "flex items-center gap-2 font-semibold text-slate-800"
          }
        >
          {icon}
          {title}
          {badge}
        </span>
        <span className="text-slate-400">{isOpen ? "▲" : "▼"}</span>
      </button>
      {isOpen && (
        <div className="p-4 border-t border-slate-100 bg-slate-50 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

export function GuiaSecEmpresarial(props: SecProps) {
  return <GuiaSec {...props} empresarial />;
}

export function GuiaSecCompacta({
  icon: Icon,
  titulo,
  children,
  aberto = false,
}: {
  icon: LucideIcon;
  titulo: string;
  children: ReactNode;
  aberto?: boolean;
}) {
  return (
    <details
      open={aberto}
      className="group border border-bronze-pale rounded-lg overflow-hidden"
    >
      <summary className="flex items-center gap-2 px-4 py-2.5 cursor-pointer bg-bronze-50/40 hover:bg-bronze-50 text-sm font-medium text-navy-900 select-none">
        <Icon size={15} className="text-bronze" /> {titulo}
        <span className="ml-auto text-slate-400 group-open:rotate-180 transition-transform">
          ▾
        </span>
      </summary>
      <div className="px-4 py-3 text-xs text-slate-700 space-y-2 leading-relaxed">
        {children}
      </div>
    </details>
  );
}

function GuiaTabela({
  headers,
  rows,
  compacta = false,
}: {
  headers: string[];
  rows: string[][];
  compacta?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className={
          compacta ? "w-full text-[11px]" : "w-full text-sm border-collapse"
        }
      >
        <thead>
          <tr
            className={compacta ? "text-left text-ink-light" : "bg-slate-200"}
          >
            {headers.map((h, i) => (
              <th
                key={compacta ? h : i}
                className={
                  compacta
                    ? "py-1 pr-3 font-semibold"
                    : "border border-bronze-pale px-3 py-2 text-left font-semibold"
                }
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={
                compacta
                  ? "border-t border-bronze-50"
                  : i % 2 === 0
                    ? "bg-white"
                    : "bg-slate-50"
              }
            >
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={
                    compacta
                      ? "py-1 pr-3 align-top"
                      : "border border-bronze-pale px-3 py-2"
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GuiaTab(props: { headers: string[]; rows: string[][] }) {
  return <GuiaTabela {...props} />;
}

export function GuiaTabCompacta({
  head,
  rows,
}: {
  head: string[];
  rows: string[][];
}) {
  return <GuiaTabela headers={head} rows={rows} compacta />;
}

export function GuiaFlow({ children }: { children: string }) {
  return (
    <pre className="text-[10px] bg-slate-50 border border-slate-100 rounded p-3 overflow-x-auto leading-relaxed whitespace-pre-wrap text-slate-700">
      {children}
    </pre>
  );
}

export function GuiaShell({
  title,
  titleClassName,
  className = "space-y-3 p-4",
  compacta = false,
  children,
}: {
  title: ReactNode;
  titleClassName?: string;
  className?: string;
  compacta?: boolean;
  children: ReactNode;
}) {
  const heading = (
    <h2
      className={
        compacta ? "font-serif font-semibold text-navy text-sm" : titleClassName
      }
    >
      {title}
    </h2>
  );
  return (
    <div className={className}>
      {compacta ? (
        <div className="flex items-center gap-2 mb-1">
          <BookOpen size={16} className="text-bronze" />
          {heading}
        </div>
      ) : (
        heading
      )}
      {children}
    </div>
  );
}

// Os guias de seções controladas persistem arrays após cada mudança de estado.
export function useGuiaChecks(key: string) {
  const [checks, setChecks] = useState<boolean[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) || "[]");
    } catch {
      return [];
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(checks));
  }, [checks, key]);
  const toggle = (i: number) =>
    setChecks((prev) => {
      const n = [...prev];
      n[i] = !n[i];
      return n;
    });
  return { checks, toggle };
}

// Os guias de <details> carregam um mapa no mount e gravam somente no toggle.
export function useGuiaMarcados(key: string) {
  const [marcados, setMarcados] = useState<Record<number, boolean>>({});
  useEffect(() => {
    try {
      setMarcados(JSON.parse(localStorage.getItem(key) || "{}"));
    } catch {}
  }, [key]);
  const toggle = (i: number) => {
    const novo = { ...marcados, [i]: !marcados[i] };
    setMarcados(novo);
    localStorage.setItem(key, JSON.stringify(novo));
  };
  return { marcados, toggle };
}
