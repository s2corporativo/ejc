"use client";

import { useEffect } from "react";
import {
  Brain,
  Wand2,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Settings as SettingsIcon,
  Users,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppStore } from "@/lib/store";
import { Generator } from "./generator";
import { Editor } from "./editor";
import { DocumentsList } from "./documents-list";
import { Dashboard } from "./dashboard";
import { Settings } from "./settings";
import { ClientsCases } from "./clients-cases";
import { Cerebro } from "./cerebro";

const TABS = [
  { id: "dashboard" as const, label: "Início", icon: LayoutDashboard, key: "1" },
  { id: "cerebro" as const, label: "Cérebro", icon: Brain, key: "b" },
  { id: "generator" as const, label: "Gerar minuta", icon: Wand2, key: "g" },
  { id: "editor" as const, label: "Editor", icon: FileText, key: "e" },
  { id: "documents" as const, label: "Minutas", icon: FolderOpen, key: "m" },
  { id: "clients" as const, label: "Clientes", icon: Users, key: "c" },
  { id: "settings" as const, label: "Config", icon: SettingsIcon, key: "," },
];

export function AppShell() {
  const { appTab, setAppTab } = useAppStore();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable ||
        target?.tagName === "SELECT"
      ) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      const tab = TABS.find((t) => t.key === key);
      if (tab) {
        e.preventDefault();
        setAppTab(tab.id);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setAppTab]);

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-secondary/20">
      <div className="sticky top-16 z-40 border-b border-border bg-background/80 glass">
        <div className="container-juridia">
          <Tabs value={appTab} onValueChange={(v) => setAppTab(v as typeof appTab)}>
            <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-0 bg-transparent p-2 scrollbar-juridia sm:w-auto">
              <div className="flex items-center gap-2 pr-3">
                <LayoutDashboard className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Escritório</span>
              </div>
              <div className="mx-1 h-6 w-px bg-border" />
              {TABS.map((t) => (
                <TabsTrigger
                  key={t.id}
                  value={t.id}
                  className={`gap-1.5 data-[state=active]:bg-primary/10 data-[state=active]:text-primary ${
                    t.id === "cerebro" ? "ring-1 ring-primary/20 data-[state=active]:ring-primary/40" : ""
                  }`}
                  title={`Atalho: ${t.key.toUpperCase()}`}
                >
                  <t.icon className="h-3.5 w-3.5" />
                  {t.label}
                  <kbd className="ml-1 hidden rounded border border-border bg-muted px-1 py-0.5 font-mono text-[9px] text-muted-foreground lg:inline-block">
                    {t.key}
                  </kbd>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      <div>
        {appTab === "dashboard" && <Dashboard />}
        {appTab === "cerebro" && <Cerebro />}
        {appTab === "generator" && <Generator />}
        {appTab === "editor" && <Editor />}
        {appTab === "documents" && <DocumentsList />}
        {appTab === "clients" && <ClientsCases />}
        {appTab === "settings" && <Settings />}
      </div>
    </div>
  );
}
