"use client";

import Link from "next/link";
import { useState } from "react";
import { Menu, Scale, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAppStore } from "@/lib/store";

const NAV = [
  { label: "Recursos", href: "#recursos" },
  { label: "Tarja-1", href: "#anonimizacao" },
  { label: "Novidades", href: "#novidades" },
  { label: "Planos", href: "#planos" },
  { label: "Na mídia", href: "#midia" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const { view, setView, setAuthOpen, user } = useAppStore();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border glass">
      <div className="container-juridia flex h-16 items-center justify-between gap-4">
        <button
          onClick={() => setView("landing")}
          className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
          aria-label="JuridIA — Início"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Scale className="h-5 w-5" />
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-lg font-bold tracking-tight">JuridIA</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Direito Brasileiro
            </span>
          </div>
        </button>

        {view === "landing" && (
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/40"
              >
                {item.label}
              </a>
            ))}
          </nav>
        )}

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={() => {
              // Trigger Cmd+K via dispatch
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
            }}
            className="hidden md:flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Abrir command palette (Ctrl+K)"
            title="Abrir command palette (Ctrl+K)"
          >
            <kbd className="font-mono text-[10px]">⌘K</kbd>
            <span>Comandos</span>
          </button>
          {view === "landing" ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="hidden sm:inline-flex"
                onClick={() => setAuthOpen(true)}
              >
                Login
              </Button>
              <Button
                size="sm"
                className="hidden sm:inline-flex"
                onClick={() => {
                  setView("app");
                }}
              >
                Acessar Plataforma
              </Button>
              <Sheet open={open} onOpenChange={setOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="md:hidden"
                    aria-label="Menu"
                  >
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" className="w-[280px]">
                  <SheetHeader>
                    <SheetTitle>JuridIA</SheetTitle>
                  </SheetHeader>
                  <nav className="mt-4 flex flex-col gap-1">
                    {NAV.map((item) => (
                      <a
                        key={item.href}
                        href={item.href}
                        onClick={() => setOpen(false)}
                        className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent"
                      >
                        {item.label}
                      </a>
                    ))}
                    <div className="my-2 h-px bg-border" />
                    <Button
                      variant="outline"
                      onClick={() => {
                        setAuthOpen(true);
                        setOpen(false);
                      }}
                    >
                      Login
                    </Button>
                    <Button
                      onClick={() => {
                        setView("app");
                        setOpen(false);
                      }}
                    >
                      Acessar Plataforma
                    </Button>
                  </nav>
                </SheetContent>
              </Sheet>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {user?.name || user?.email}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setView("landing")}
              >
                Voltar ao site
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
