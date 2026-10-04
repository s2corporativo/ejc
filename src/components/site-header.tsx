"use client";

import { useState } from "react";
import { Menu, Scale, X, FileText, Home } from "lucide-react";
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
  { label: "Início", tab: "dashboard" as const },
  { label: "Cérebro", tab: "cerebro" as const },
  { label: "Gerar minuta", tab: "generator" as const },
  { label: "Editor", tab: "editor" as const },
  { label: "Minutas", tab: "documents" as const },
  { label: "Clientes", tab: "clients" as const },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const { view, setView, setAppTab, user } = useAppStore();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border glass">
      <div className="container-juridia flex h-16 items-center justify-between gap-4">
        <button
          onClick={() => {
            setView("app");
            setAppTab("dashboard");
          }}
          className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
          aria-label="JuridIA — Início"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Scale className="h-5 w-5" />
          </div>
          <div className="flex flex-col leading-none">
            <span className="text-lg font-bold tracking-tight">JuridIA</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Escritório
            </span>
          </div>
        </button>

        {view === "app" && (
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <Button
                key={item.tab}
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setAppTab(item.tab)}
              >
                {item.label}
              </Button>
            ))}
          </nav>
        )}

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
            }}
            className="hidden md:flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Abrir command palette (Ctrl+K)"
            title="Abrir command palette (Ctrl+K)"
          >
            <kbd className="font-mono text-[10px]">⌘K</kbd>
            <span>Comandos</span>
          </button>
          {view === "app" ? (
            <>
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {user?.name || user?.email}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setView("landing")}
                title="Ver página institucional"
              >
                <Home className="mr-1.5 h-4 w-4" />
                Site
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
                    <SheetTitle>Escritório</SheetTitle>
                  </SheetHeader>
                  <nav className="mt-4 flex flex-col gap-1">
                    {NAV.map((item) => (
                      <button
                        key={item.tab}
                        onClick={() => {
                          setAppTab(item.tab);
                          setOpen(false);
                        }}
                        className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium hover:bg-accent"
                      >
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        {item.label}
                      </button>
                    ))}
                  </nav>
                </SheetContent>
              </Sheet>
            </>
          ) : (
            <Button size="sm" onClick={() => setView("app")}>
              Entrar no escritório
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
