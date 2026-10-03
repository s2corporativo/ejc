"use client";

import {
  Wand2,
  FileText,
  Search,
  Layers,
  FolderOpen,
  LayoutDashboard,
  Settings as SettingsIcon,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppStore } from "@/lib/store";
import { Generator } from "./generator";
import { Editor } from "./editor";
import { Jurisprudence } from "./jurisprudence";
import { Batch } from "./batch";
import { DocumentsList } from "./documents-list";
import { Dashboard } from "./dashboard";
import { Settings } from "./settings";

const TABS = [
  { id: "dashboard" as const, label: "Dashboard", icon: LayoutDashboard },
  { id: "generator" as const, label: "Gerar minuta", icon: Wand2 },
  { id: "editor" as const, label: "Editor", icon: FileText },
  { id: "jurisprudence" as const, label: "JurisprudênciaIA", icon: Search },
  { id: "batch" as const, label: "Geração em lote", icon: Layers },
  { id: "documents" as const, label: "Minutas salvas", icon: FolderOpen },
  { id: "settings" as const, label: "Configurações", icon: SettingsIcon },
];

export function AppShell() {
  const { appTab, setAppTab } = useAppStore();

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-secondary/20">
      <div className="sticky top-16 z-40 border-b border-border bg-background/80 glass">
        <div className="container-juridia">
          <Tabs value={appTab} onValueChange={(v) => setAppTab(v as typeof appTab)}>
            <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-0 bg-transparent p-2 scrollbar-juridia sm:w-auto">
              <div className="flex items-center gap-2 pr-3">
                <LayoutDashboard className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Plataforma</span>
              </div>
              <div className="mx-1 h-6 w-px bg-border" />
              {TABS.map((t) => (
                <TabsTrigger
                  key={t.id}
                  value={t.id}
                  className="gap-1.5 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
                >
                  <t.icon className="h-3.5 w-3.5" />
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </div>

      <div>
        {appTab === "dashboard" && <Dashboard />}
        {appTab === "generator" && <Generator />}
        {appTab === "editor" && <Editor />}
        {appTab === "jurisprudence" && <Jurisprudence />}
        {appTab === "batch" && <Batch />}
        {appTab === "documents" && <DocumentsList />}
        {appTab === "settings" && <Settings />}
      </div>
    </div>
  );
}
