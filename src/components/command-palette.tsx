"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  LayoutDashboard,
  Wand2,
  FileText,
  Search,
  Layers,
  FolderOpen,
  Sun,
  Moon,
  Home,
  Sparkles,
  Github,
  HelpCircle,
  Printer,
  Settings,
  FileSearch,
  ShieldCheck,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { useTheme } from "next-themes";
import { toast } from "@/hooks/use-toast";

interface CommandItemDef {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  shortcut?: string;
  onSelect: () => void;
  group: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const { setView, setAppTab, setAuthOpen } = useAppStore();
  const { setTheme, resolvedTheme } = useTheme();

  const go = useCallback((view: "landing" | "app", tab?: "dashboard" | "generator" | "editor" | "case-analysis" | "jurisprudence" | "batch" | "documents" | "audit" | "settings") => {
    setView(view);
    if (tab) setAppTab(tab);
    setOpen(false);
  }, [setView, setAppTab]);

  // Keyboard shortcut Cmd+K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const items: CommandItemDef[] = [
    { icon: Home, label: "Ir para o site (Landing)", group: "Navegação", onSelect: () => go("landing") },
    { icon: LayoutDashboard, label: "Dashboard", group: "Plataforma", onSelect: () => go("app", "dashboard") },
    { icon: Wand2, label: "Gerar nova minuta", shortcut: "G", group: "Plataforma", onSelect: () => go("app", "generator") },
    { icon: FileText, label: "Abrir editor", shortcut: "E", group: "Plataforma", onSelect: () => go("app", "editor") },
    { icon: Search, label: "Pesquisar jurisprudência", shortcut: "J", group: "Plataforma", onSelect: () => go("app", "jurisprudence") },
    { icon: FileSearch, label: "Resumo avançado do caso", shortcut: "C", group: "Plataforma", onSelect: () => go("app", "case-analysis") },
    { icon: ShieldCheck, label: "Auditoria & créditos", shortcut: "A", group: "Plataforma", onSelect: () => go("app", "audit") },
    { icon: Layers, label: "Geração em lote", shortcut: "B", group: "Plataforma", onSelect: () => go("app", "batch") },
    { icon: FolderOpen, label: "Minutas salvas", shortcut: "D", group: "Plataforma", onSelect: () => go("app", "documents") },
    { icon: Settings, label: "Configurações do perfil", shortcut: ",", group: "Plataforma", onSelect: () => go("app", "settings") },
    { icon: Sparkles, label: "Login / Criar conta", group: "Conta", onSelect: () => { setAuthOpen(true); setOpen(false); } },
    resolvedTheme === "dark"
      ? { icon: Sun, label: "Mudar para tema claro", group: "Aparência", onSelect: () => { setTheme("light"); setOpen(false); } }
      : { icon: Moon, label: "Mudar para tema escuro", group: "Aparência", onSelect: () => { setTheme("dark"); setOpen(false); } },
    { icon: Printer, label: "Imprimir página atual", shortcut: "⌘P", group: "Ações", onSelect: () => { window.print(); setOpen(false); } },
    { icon: HelpCircle, label: "Ver documentação", group: "Ajuda", onSelect: () => { toast({ title: "Documentação", description: "Consulte o /home/z/my-project/worklog.md" }); setOpen(false); } },
    { icon: Github, label: "Código-fonte no GitHub", group: "Ajuda", onSelect: () => { toast({ title: "Projeto demonstrativo", description: "Código disponível no ambiente de desenvolvimento." }); setOpen(false); } },
  ];

  const groups = Array.from(new Set(items.map((i) => i.group)));

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Digite um comando ou busque..." />
      <CommandList className="max-h-[400px]">
        <CommandEmpty>Nenhum resultado encontrado.</CommandEmpty>
        {groups.map((g) => (
          <div key={g}>
            <CommandGroup heading={g}>
              {items
                .filter((i) => i.group === g)
                .map((i) => (
                  <CommandItem
                    key={i.label}
                    value={i.label}
                    onSelect={i.onSelect}
                    className="gap-2"
                  >
                    <i.icon className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1">{i.label}</span>
                    {i.shortcut && (
                      <kbd className="ml-auto rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        {i.shortcut}
                      </kbd>
                    )}
                  </CommandItem>
                ))}
            </CommandGroup>
            <CommandSeparator />
          </div>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
