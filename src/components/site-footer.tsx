"use client";

import { Scale, Github, Linkedin, Twitter } from "lucide-react";

const COLS = [
  {
    title: "Produto",
    links: ["Recursos", "Tarja-1", "Conecta", "Planos", "Novidades"],
  },
  {
    title: "Recursos",
    links: ["Templates", "Habilidades (skills)", "JurisprudênciaIA", "Geração em lote", "Editor"],
  },
  {
    title: "Empresa",
    links: ["Sobre", "Na mídia", "Conformidade", "LGPD", "CNJ 615/2025"],
  },
  {
    title: "Suporte",
    links: ["Central de ajuda", "Status", "Termos de Uso", "Política de Privacidade", "Contato"],
  },
];

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-border bg-secondary/40">
      <div className="container-juridia py-12">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-6">
          <div className="col-span-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Scale className="h-5 w-5" />
              </div>
              <span className="text-lg font-bold">JuridIA</span>
            </div>
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">
              Inteligência artificial para o Direito brasileiro. De petições a
              sentenças, a IA que mais entende — e mais produz.
            </p>
            <div className="mt-5 flex gap-2">
              <a
                href="#"
                aria-label="GitHub"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Github className="h-4 w-4" />
              </a>
              <a
                href="#"
                aria-label="LinkedIn"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Linkedin className="h-4 w-4" />
              </a>
              <a
                href="#"
                aria-label="Twitter"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Twitter className="h-4 w-4" />
              </a>
            </div>
          </div>
          {COLS.map((col) => (
            <div key={col.title}>
              <h3 className="text-sm font-semibold">{col.title}</h3>
              <ul className="mt-3 space-y-2">
                {col.links.map((l) => (
                  <li key={l}>
                    <a
                      href="#"
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {l}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row">
          <p>© {new Date().getFullYear()} JuridIA. Projeto demonstrativo inspirado em LegalTech brasileira.</p>
          <p>Conformidade LGPD · Resolução CNJ 615/2025 · AES-256</p>
        </div>
      </div>
    </footer>
  );
}
